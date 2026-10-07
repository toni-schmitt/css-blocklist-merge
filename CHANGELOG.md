# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] - 2026-10-07

### Added

- Plain IP lists as sources: one IPv4 address per line, as published for
  firewalls, each merged as an every-port (`ip:0`) entry. Addresses ending in
  `.0` are skipped, since the game would read them as a whole /24
- Exomatic/steamserverspamfilter (~1.8k IPs, ~1.5k not in the other lists) as
  a fourth default source

## [1.0.0] - 2026-08-25

### Added

- Merger that folds any number of community blocklists into the game's
  `cstrike/cfg/server_blacklist.txt`, deduplicating by server address
- Steam launch-option wrapper: merges, then hands off to the real game command,
  which is the only moment CS:S will not overwrite the file from memory
- Lenient KeyValues parser accepting the malformed entries found in published
  lists — odd indentation, and blocks missing their `"server"` key
- Entries already on disk are preserved, so servers blocked in-game survive
- Atomic writes via a temporary file beside the target, with the previous
  blocklist kept as `server_blacklist.txt.bak`
- Server names sanitized on output, so a hostile name cannot inject entries
- Steam installation discovery on Linux (including Flatpak and Snap), macOS and
  Windows, following `libraryfolders.vdf` to games on other drives and reading
  the real install directory from `appmanifest_240.acf`
- `sources.txt` in the per-platform config directory as the extension point,
  with GitHub blob URLs rewritten to raw URLs automatically
- `install.py` with per-platform install locations, a Windows `.cmd` shim,
  `--uninstall` and `--purge`
- `--dry-run`, `--output`, `--sources`, `--timeout` and `--version`
- Test suite covering parsing, merge precedence, atomic writes, sanitization
  and library discovery, with no network access required

### Notes

- Every failure path is non-fatal: a dead source is skipped, a total failure
  leaves the existing blocklist untouched, and the game launches regardless.
- Ships with three sources: krnl86 (~7.6k entries, the only one covering the
  SGaming.RU network), Ballganda (~310) and JakeM650 (~91).
