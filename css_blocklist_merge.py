#!/usr/bin/env python3
"""Merge Counter-Strike: Source server blocklists, then launch the game.

Designed to be used as a Steam launch-option wrapper:

    css-blocklist-merge %command%

It refreshes cstrike/cfg/server_blacklist.txt and then hands off to the real
game command, so the merged list is on disk before CS:S reads it. CS:S rewrites
that file from memory when it exits, which is why the merge has to happen at
launch rather than at some arbitrary time.

Standard library only, no dependencies.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

__version__ = "1.0.0"

APP_ID = "240"
APP_NAME = "css-blocklist-merge"
RELATIVE_BLACKLIST = Path("cstrike") / "cfg" / "server_blacklist.txt"

#: Used when no sources.txt is found. Keep the file-based list as the primary
#: extension point; this only exists so a bare copy of the script still works.
DEFAULT_SOURCES = (
    "https://github.com/Ballganda/css-server-blacklist/blob/main/server_blacklist.txt",
    "https://github.com/JakeM650/css-server-blacklist/blob/main/server_blacklist.txt",
    "https://github.com/krnl86/css-server-blacklist/blob/main/server_blacklist.txt",
)

#: One "server" entry is a { ... } block holding name/date/addr keys.
BLOCK_RE = re.compile(r"\{([^{}]*)\}", re.S)
KEY_RE = re.compile(r'"(\w+)"\s+"([^"]*)"')
#: "path" entries inside steamapps/libraryfolders.vdf.
VDF_PATH_RE = re.compile(r'"path"\s+"([^"]+)"')
INSTALLDIR_RE = re.compile(r'"installdir"\s+"([^"]+)"')


def log(message: str) -> None:
    print(f"[{APP_NAME}] {message}", file=sys.stderr, flush=True)


# --------------------------------------------------------------------------
# Locating the game
# --------------------------------------------------------------------------


def steam_roots() -> list[Path]:
    """Candidate Steam installation roots for the current OS, best guess first."""
    home = Path.home()
    roots: list[Path] = []

    if sys.platform == "win32":
        try:  # the registry knows for certain; everything else is a guess
            import winreg

            for hkey, key in (
                (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam"),
            ):
                try:
                    with winreg.OpenKey(hkey, key) as handle:
                        value, _ = winreg.QueryValueEx(
                            handle, "SteamPath" if hkey == winreg.HKEY_CURRENT_USER else "InstallPath"
                        )
                        roots.append(Path(value))
                except OSError:
                    continue
        except ImportError:
            pass
        roots += [
            Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Steam",
            Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Steam",
        ]
    elif sys.platform == "darwin":
        roots.append(home / "Library" / "Application Support" / "Steam")
    else:  # Linux and the BSDs
        roots += [
            home / ".local" / "share" / "Steam",
            home / ".steam" / "steam",
            home / ".steam" / "root",
            # Flatpak and Snap keep their own private Steam home.
            home / ".var" / "app" / "com.valvesoftware.Steam" / ".local" / "share" / "Steam",
            home / "snap" / "steam" / "common" / ".local" / "share" / "Steam",
        ]

    seen: set[Path] = set()
    unique: list[Path] = []
    for root in roots:
        try:
            resolved = root.expanduser().resolve()
        except OSError:
            continue
        if resolved not in seen and resolved.is_dir():
            seen.add(resolved)
            unique.append(resolved)
    return unique


def steam_libraries(root: Path) -> list[Path]:
    """Every steamapps directory reachable from a Steam root.

    Games are routinely installed on a second drive, so the root's own
    steamapps is only the first candidate; libraryfolders.vdf lists the rest.
    """
    libraries = [root / "steamapps"]
    for name in ("libraryfolders.vdf", "config/libraryfolders.vdf"):
        manifest = root / "steamapps" / name if name.endswith(".vdf") else root / name
        try:
            text = manifest.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        libraries += [Path(p) / "steamapps" for p in VDF_PATH_RE.findall(text)]

    seen: set[Path] = set()
    unique: list[Path] = []
    for library in libraries:
        if library not in seen and library.is_dir():
            seen.add(library)
            unique.append(library)
    return unique


def find_blacklist() -> Path | None:
    """Locate cstrike/cfg/server_blacklist.txt for the installed copy of CS:S."""
    for root in steam_roots():
        for library in steam_libraries(root):
            install_dirs = []

            manifest = library / f"appmanifest_{APP_ID}.acf"
            try:
                match = INSTALLDIR_RE.search(manifest.read_text(encoding="utf-8", errors="replace"))
                if match:
                    install_dirs.append(match.group(1))
            except OSError:
                pass
            # Fall back to the stock directory name if the manifest is missing
            # (manually copied installs, or a library Steam has forgotten).
            install_dirs.append("Counter-Strike Source")

            for install_dir in install_dirs:
                candidate = library / "common" / install_dir / RELATIVE_BLACKLIST
                if candidate.parent.is_dir():
                    return candidate
    return None


def resolve_output(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).expanduser()
    from_env = os.environ.get("CSS_BLACKLIST")
    if from_env:
        return Path(from_env).expanduser()
    found = find_blacklist()
    if found is None:
        sys.exit(
            "could not find Counter-Strike: Source.\n"
            "Pass the blocklist path explicitly with --output, or set CSS_BLACKLIST."
        )
    return found


# --------------------------------------------------------------------------
# Sources
# --------------------------------------------------------------------------


def config_dir() -> Path:
    """Per-user config directory, following each platform's convention."""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA")
        return Path(base) / APP_NAME if base else Path.home() / "AppData" / "Roaming" / APP_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    base = os.environ.get("XDG_CONFIG_HOME")
    return Path(base) / APP_NAME if base else Path.home() / ".config" / APP_NAME


def sources_candidates() -> list[Path]:
    return [config_dir() / "sources.txt", Path(__file__).resolve().parent / "sources.txt"]


def load_sources(explicit: str | None) -> tuple[list[str], Path | None]:
    """Read the source list. Returns (urls, file it came from or None)."""
    paths = [Path(explicit).expanduser()] if explicit else sources_candidates()
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        urls = [
            line.strip()
            for line in text.splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        if urls:
            return urls, path
    if explicit:
        sys.exit(f"no usable sources in {explicit}")
    return list(DEFAULT_SOURCES), None


def to_raw(url: str) -> str:
    """Rewrite a GitHub blob URL to its raw equivalent, so pasted links work."""
    return re.sub(
        r"^https://github\.com/([^/]+/[^/]+)/blob/",
        r"https://raw.githubusercontent.com/\1/",
        url,
    )


def fetch(url: str, timeout: float) -> str:
    request = urllib.request.Request(
        to_raw(url), headers={"User-Agent": f"{APP_NAME}/{__version__}"}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", "replace")


# --------------------------------------------------------------------------
# Blocklist format (Valve KeyValues)
# --------------------------------------------------------------------------


def parse(text: str) -> list[tuple[str, str, str]]:
    """Extract (addr, name, date) from every block that carries an address.

    Deliberately lenient: several published lists contain entries missing their
    "server" key or with inconsistent indentation, and the game accepts them.
    """
    entries = []
    for block in BLOCK_RE.findall(text):
        keys = dict(KEY_RE.findall(block))
        addr = keys.get("addr")
        if addr:
            entries.append((addr, keys.get("name", ""), keys.get("date", "0")))
    return entries


def sanitize(value: str) -> str:
    """Keep a hostile server name from breaking out of its quoted VDF string."""
    return "".join(c for c in value if c >= " " and c != "\x7f").replace('"', "'")


def render(entries: list[tuple[str, str, str]]) -> str:
    lines = ['"serverblacklist"', "{"]
    for addr, name, date in entries:
        lines += [
            '\t"server"',
            "\t{",
            f'\t\t"name"\t\t\t"{sanitize(name)}"',
            f'\t\t"date"\t\t\t"{sanitize(date)}"',
            f'\t\t"addr"\t\t\t"{sanitize(addr)}"',
            "\t}",
        ]
    lines += ["}", ""]
    return "\n".join(lines)


def merge(output: Path, sources: list[str], timeout: float, dry_run: bool) -> None:
    merged: dict[str, tuple[str, str, str]] = {}
    failures = 0

    # Keep what is already on disk, so servers blocked in-game are not lost.
    if output.exists():
        for entry in parse(output.read_text(encoding="utf-8", errors="replace")):
            merged.setdefault(entry[0], entry)
        log(f"{len(merged)} entries already in {output.name}")

    for url in sources:
        try:
            entries = parse(fetch(url, timeout))
        except Exception as exc:  # noqa: BLE001 - any failure here is non-fatal
            log(f"FAILED {url}: {exc}")
            failures += 1
            continue
        before = len(merged)
        for entry in entries:
            merged.setdefault(entry[0], entry)
        log(f"{len(entries)} entries ({len(merged) - before} new) from {url}")

    if failures == len(sources):
        log("every source failed; leaving the blocklist untouched")
        return
    if not merged:
        log("nothing parsed; leaving the blocklist untouched")
        return

    if dry_run:
        log(f"dry run: would write {len(merged)} servers to {output}")
        return

    if output.exists():
        output.with_name(output.name + ".bak").write_bytes(output.read_bytes())

    # Write beside the target so the replace stays on one filesystem, and the
    # game can never observe a half-written blocklist.
    tmp = output.with_name(output.name + ".tmp")
    tmp.write_text(render(sorted(merged.values())), encoding="utf-8")
    tmp.replace(output)
    log(f"wrote {len(merged)} blocked servers to {output}")


# --------------------------------------------------------------------------


def launch(command: list[str]) -> int:
    """Hand off to the real game command."""
    if sys.platform == "win32":
        # No exec() worth the name on Windows: stay alive as the parent so
        # Steam keeps tracking the session.
        return subprocess.run(command).returncode
    os.execvp(command[0], command)  # replaces this process; never returns


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog=APP_NAME,
        description="Merge CS:S server blocklists, then launch the game.",
        epilog="Set it as a Steam launch option: css-blocklist-merge %command%",
    )
    parser.add_argument("--output", metavar="PATH", help="blocklist to write (default: auto-detect)")
    parser.add_argument("--sources", metavar="PATH", help="source list (default: auto-detect)")
    parser.add_argument("--timeout", type=float, default=20.0, help="seconds per source (default: 20)")
    parser.add_argument("--dry-run", action="store_true", help="report, but do not write")
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    parser.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        help="the game command to run afterwards, normally %%command%% from Steam",
    )
    args = parser.parse_args(argv)

    try:
        sources, from_file = load_sources(args.sources)
        log(f"{len(sources)} sources from {from_file}" if from_file else f"{len(sources)} built-in sources")
        merge(resolve_output(args.output), sources, args.timeout, args.dry_run)
    except SystemExit:
        if not args.command:
            raise  # nothing to launch, so the error is the whole result
        log("could not update the blocklist, launching anyway")
    except Exception as exc:  # noqa: BLE001 - a bad blocklist must never block play
        log(f"merge failed, launching anyway: {exc}")

    if args.command:
        return launch(args.command)
    return 0


if __name__ == "__main__":
    sys.exit(main())
