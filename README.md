# CS:S Blocklist Merge

Merges community blocklists of fake Counter-Strike: Source servers into your `server_blacklist.txt` every time you launch the game.

The CS:S server browser has been flooded since 2023 with servers that do not exist: thousands of entries advertising full player counts, redirecting you elsewhere or simply refusing to connect. Valve has not acted, so the community maintains blocklists by hand — but they are scattered across several repositories, they overlap, and the game will not fetch any of them for you.

This merges them all into one list and keeps it current, with no step you have to remember.

<p>
  <a href="LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/License-MIT-blue.svg"></a>
  <img alt="Python 3.9+" src="https://img.shields.io/badge/Python-3.9%2B-3776ab?logo=python&logoColor=white">
  <img alt="Dependencies: none" src="https://img.shields.io/badge/dependencies-stdlib%20only-success">
  <img alt="Linux, macOS, Windows" src="https://img.shields.io/badge/platform-Linux%20%7C%20macOS%20%7C%20Windows-lightgrey">
</p>

## Why it runs at launch

CS:S loads the blocklist once at startup and **rewrites the file from memory when it exits**. Update it while the game is running and your changes are overwritten on quit; update it on a timer and you are racing the game. The only reliable moment is immediately before the game starts, which is exactly where a Steam launch-option wrapper sits.

So this is not a background service and not something you run by hand. It is a wrapper: Steam calls it, it merges, it hands off to the game. Roughly a second of extra startup time.

## Installation

```bash
git clone https://github.com/toni-schmitt/css-blocklist-merge.git
cd css-blocklist-merge
python3 install.py
```

The installer copies the command into `~/.local/bin` (`%LOCALAPPDATA%\Programs` on Windows), seeds your personal `sources.txt`, locates your CS:S installation, and prints the launch option to paste. Nothing needs root.

Then, in Steam: right-click **Counter-Strike: Source** → **Properties** → **Launch Options**, and paste what the installer printed:

```
/home/you/.local/bin/css-blocklist-merge %command%
```

`%command%` is Steam's placeholder for the real game command. Keep any launch options you already use — put them after `%command%`.

That is the whole setup. Launch the game normally from here on.

## Blocklists included

| List | Entries | Covers |
| --- | --- | --- |
| [krnl86/css-server-blacklist](https://github.com/krnl86/css-server-blacklist) | ~7,600 | The SGaming.RU network (~5,800 entries), ATMMIX.RU, ALkoGoLiki, RR18.RU; contains all of Ballganda's entries |
| [Ballganda/css-server-blacklist](https://github.com/Ballganda/css-server-blacklist) | ~310 | The original list, most actively maintained |
| [JakeM650/css-server-blacklist](https://github.com/JakeM650/css-server-blacklist) | ~91 | Independently collected, small |

Together roughly **7,700 unique servers**. Sizes are as of August 2026 and drift as the lists are maintained.

## Adding more blocklists

Add a line to your `sources.txt`:

| Platform | Location |
| --- | --- |
| Linux | `~/.config/css-blocklist-merge/sources.txt` |
| macOS | `~/Library/Application Support/css-blocklist-merge/sources.txt` |
| Windows | `%APPDATA%\css-blocklist-merge\sources.txt` |

One URL per line; `#` starts a comment. GitHub `blob` links are rewritten to raw links automatically, so you can paste the address straight out of your browser:

```
https://github.com/someone/their-blacklist/blob/main/server_blacklist.txt
```

Any file in Valve's `serverblacklist` KeyValues format works — including one you export from the game's own **Blacklisted Servers** tab and host yourself.

## How it works

1. **Reads what is already on disk**, so servers you blocked in-game are never lost.
2. **Downloads each source** and parses it leniently. Published lists are not uniformly formatted — some entries have odd indentation, some are missing their `"server"` key entirely — and the parser accepts any `{ … }` block carrying an `addr`, which is what the game itself does.
3. **Merges by address.** The first list to mention an address supplies its name and date; the rest is a plain union.
4. **Writes atomically** — to a temporary file beside the target, then renames — so the game can never read a half-written blocklist. The previous file is kept as `server_blacklist.txt.bak`.
5. **Hands off to the game** by replacing itself with the real command, so Steam keeps tracking playtime, the overlay and the process as usual.

Server names are sanitized on the way out: quotes and control characters are stripped, so a hostile server name cannot break out of its quoted string and inject entries into your blocklist.

**A failure never stops you playing.** If a source is offline, it is skipped. If every source fails, the existing blocklist is left untouched. Any unexpected error is logged and the game launches anyway.

### Finding the game

Steam installations are found from the registry on Windows, and from the usual locations on Linux (including Flatpak and Snap) and macOS. Each `libraryfolders.vdf` is then followed to games installed on other drives, and `appmanifest_240.acf` gives the real install directory. If your setup defeats all that, point at the file directly:

```bash
export CSS_BLACKLIST="/path/to/Counter-Strike Source/cstrike/cfg/server_blacklist.txt"
```

## Options

The wrapper needs no arguments beyond `%command%`, but it is a normal CLI too:

| Option | Effect |
| --- | --- |
| `--dry-run` | Report what would change, write nothing |
| `--output PATH` | Blocklist to write, instead of auto-detecting |
| `--sources PATH` | Source list to read, instead of auto-detecting |
| `--timeout SECONDS` | Per-source download timeout (default: 20) |
| `--version` | Print the version |

```bash
css-blocklist-merge --dry-run      # see what it would do
css-blocklist-merge                # merge now, launch nothing
```

Environment: `CSS_BLACKLIST` overrides the detected blocklist path, which is useful when the game lives somewhere auto-detection cannot reach.

## Limitations

- **Blocking is by IP address**, which is all Valve's blocklist format supports. Spam networks rotate addresses, so this is only ever as current as the lists it merges.
- **The lists are third-party.** You are trusting their maintainers not to block something legitimate. Everything merged is visible in the game's Blacklisted Servers tab, and `server_blacklist.txt.bak` holds the previous state.
- **CS:S rewrites the file on exit**, so a server you unblock in-game stays unblocked only until the next launch re-adds it from the lists. Remove its source, or block nothing you want to play on.
- **Only Counter-Strike: Source.** Other Source games use the same format, but the app ID and paths here are CS:S's.

## Uninstall

```bash
python3 install.py --uninstall            # keeps your sources.txt
python3 install.py --uninstall --purge    # removes it too
```

Then clear the game's Steam launch option. Your `server_blacklist.txt` is left in place — the game keeps using it.

## Tests

```bash
python3 -m unittest discover tests
```

Covers the parser's tolerance for malformed real-world lists, merge precedence, atomic writes, name sanitization, and Steam library discovery against a synthetic install tree. No network access required.

## License

MIT — see [LICENSE](LICENSE).

## AI Honesty

This project was completely generated by LLMs.

<a href="https://www.aihonestybadge.com" target="_blank" rel="noopener"><img src="https://www.aihonestybadge.com/badges/ai-generated.svg" alt="AI Generated Badge" style="max-width: 190px; height: auto;" /></a>

Written by Claude (Opus 5) in Claude Code, under human direction and review. The merge, the parser and Steam library discovery were verified against a real CS:S installation and the live blocklists; Windows and macOS support is exercised by CI on those runners, but has not been tested against an actual Steam installation on either.
