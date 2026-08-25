#!/usr/bin/env python3
"""Install css-blocklist-merge and print the Steam launch option to paste.

    python3 install.py              # install
    python3 install.py --uninstall  # remove it again

Works on Linux, macOS and Windows. Standard library only, no root needed.
"""

from __future__ import annotations

import argparse
import os
import shutil
import stat
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import css_blocklist_merge as tool  # noqa: E402 - needs HERE on sys.path first

SCRIPT_SOURCE = HERE / "css_blocklist_merge.py"
SOURCES_SOURCE = HERE / "sources.txt"
COMMAND = "css-blocklist-merge"

WINDOWS_SHIM = """\
@echo off
rem Launch shim so Steam can call the merger as a plain executable.
python "%~dp0css_blocklist_merge.py" %*
"""


def install_dir() -> Path:
    """Where the command belongs on this platform."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA")
        root = Path(base) if base else Path.home() / "AppData" / "Local"
        return root / "Programs" / COMMAND
    # XDG_BIN_HOME is not in the base directory spec, but it is widely honoured
    # and costs nothing to respect.
    base = os.environ.get("XDG_BIN_HOME")
    return Path(base) if base else Path.home() / ".local" / "bin"


def installed_paths() -> tuple[Path, Path]:
    """(the thing Steam invokes, the script itself)."""
    target = install_dir()
    if sys.platform == "win32":
        return target / f"{COMMAND}.cmd", target / "css_blocklist_merge.py"
    return target / COMMAND, target / COMMAND


def quote(path: Path) -> str:
    text = str(path)
    return f'"{text}"' if " " in text else text


def install() -> int:
    launcher, script = installed_paths()
    script.parent.mkdir(parents=True, exist_ok=True)

    shutil.copyfile(SCRIPT_SOURCE, script)
    if sys.platform == "win32":
        launcher.write_text(WINDOWS_SHIM, encoding="utf-8")
    else:
        script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    print(f"installed  {launcher}")

    config = tool.config_dir() / "sources.txt"
    if config.exists():
        print(f"kept       {config} (already present, not overwritten)")
    else:
        config.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SOURCES_SOURCE, config)
        print(f"seeded     {config}")

    blacklist = tool.find_blacklist()
    if blacklist is None:
        print(
            "\nCould not find Counter-Strike: Source. It still works — the merger looks\n"
            "again every launch — but if CS:S lives somewhere unusual, set CSS_BLACKLIST\n"
            "to the full path of cstrike/cfg/server_blacklist.txt."
        )
    else:
        print(f"found CS:S {blacklist}")

    print("\nSet this as the game's Steam launch option")
    print("(Steam → right-click Counter-Strike: Source → Properties → Launch Options):\n")
    print(f"    {quote(launcher)} %command%\n")

    if sys.platform != "win32" and str(launcher.parent) not in os.environ.get("PATH", "").split(
        os.pathsep
    ):
        print(
            f"Note: {launcher.parent} is not on your PATH. Steam does not care — the\n"
            "launch option above is an absolute path — but you will need the full path\n"
            "to run the command by hand.\n"
        )
    return 0


def uninstall(purge: bool) -> int:
    launcher, script = installed_paths()
    for path in {launcher, script}:
        if path.exists():
            path.unlink()
            print(f"removed    {path}")
        else:
            print(f"not found  {path}")
    if sys.platform == "win32" and script.parent.is_dir() and not any(script.parent.iterdir()):
        script.parent.rmdir()

    config = tool.config_dir() / "sources.txt"
    if purge and config.exists():
        config.unlink()
        print(f"removed    {config}")
    elif config.exists():
        print(f"kept       {config} (use --purge to remove)")

    print("\nRemember to clear the game's Steam launch option.")
    print("Your merged server_blacklist.txt is left alone; CS:S keeps using it.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--uninstall", action="store_true", help="remove the installed command")
    parser.add_argument("--purge", action="store_true", help="with --uninstall, delete sources.txt too")
    args = parser.parse_args()
    return uninstall(args.purge) if args.uninstall else install()


if __name__ == "__main__":
    sys.exit(main())
