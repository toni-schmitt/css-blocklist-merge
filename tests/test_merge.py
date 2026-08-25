"""Tests for css-blocklist-merge. Run with: python3 -m unittest discover tests"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import css_blocklist_merge as tool  # noqa: E402

WELL_FORMED = """\
"serverblacklist"
{
\t"server"
\t{
\t\t"name"\t\t\t"Spam One"
\t\t"date"\t\t\t"1747308377"
\t\t"addr"\t\t\t"1.2.3.4:0"
\t}
}
"""

# Both quirks below are taken from lists published in the wild.
MALFORMED = """\
"serverblacklist"
{
    \t"server"
\t{
\t\t"name"\t\t\t"Odd Indentation"
\t\t"date"\t\t\t"1776637069"
\t\t"addr"\t\t\t"5.6.7.8:0"
\t}
\t{
\t\t"name"\t\t\t"Missing server key"
\t\t"date"\t\t\t"1776639922"
\t\t"addr"\t\t\t"9.10.11.12:0"
\t}
\t{
\t}
}
"""


class TestParse(unittest.TestCase):
    def test_well_formed(self):
        self.assertEqual(tool.parse(WELL_FORMED), [("1.2.3.4:0", "Spam One", "1747308377")])

    def test_tolerates_odd_indentation_and_missing_server_key(self):
        addrs = [entry[0] for entry in tool.parse(MALFORMED)]
        self.assertEqual(addrs, ["5.6.7.8:0", "9.10.11.12:0"])

    def test_ignores_blocks_without_an_address(self):
        self.assertEqual(tool.parse('"serverblacklist"\n{\n\t{\n\t}\n}\n'), [])

    def test_empty_input(self):
        self.assertEqual(tool.parse(""), [])

    def test_round_trip(self):
        entries = tool.parse(MALFORMED)
        self.assertEqual(tool.parse(tool.render(entries)), entries)


class TestRender(unittest.TestCase):
    def test_quotes_in_names_cannot_break_out(self):
        rendered = tool.render([("1.2.3.4:0", 'evil" "addr" "0.0.0.0:0', "0")])
        self.assertNotIn('evil"', rendered)
        self.assertEqual([e[0] for e in tool.parse(rendered)], ["1.2.3.4:0"])

    def test_control_characters_are_stripped(self):
        rendered = tool.render([("1.2.3.4:0", "bad\nname\ttab", "0")])
        self.assertEqual(tool.parse(rendered)[0][1], "badnametab")

    def test_unicode_names_survive(self):
        name = "DUST2 ✮ ПEPEДOBOЙ 🛸 SGaming.RU"
        self.assertEqual(tool.parse(tool.render([("1.2.3.4:0", name, "0")]))[0][1], name)


class TestMerge(unittest.TestCase):
    def test_first_source_wins_and_local_entries_survive(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "server_blacklist.txt"
            output.write_text(
                tool.render([("1.1.1.1:0", "Blocked in game", "1")]), encoding="utf-8"
            )
            lists = {
                "first": tool.render([("2.2.2.2:0", "From first", "2")]),
                "second": tool.render(
                    [("2.2.2.2:0", "Duplicate, ignored", "3"), ("3.3.3.3:0", "From second", "4")]
                ),
            }
            original_fetch = tool.fetch
            tool.fetch = lambda url, timeout: lists[url]
            try:
                tool.merge(output, ["first", "second"], timeout=1, dry_run=False)
            finally:
                tool.fetch = original_fetch

            merged = {addr: name for addr, name, _ in tool.parse(output.read_text(encoding="utf-8"))}
            self.assertEqual(
                merged,
                {
                    "1.1.1.1:0": "Blocked in game",
                    "2.2.2.2:0": "From first",
                    "3.3.3.3:0": "From second",
                },
            )
            self.assertTrue(output.with_name(output.name + ".bak").exists())
            self.assertFalse(output.with_name(output.name + ".tmp").exists())

    def test_total_failure_leaves_the_file_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "server_blacklist.txt"
            before = tool.render([("1.1.1.1:0", "Keep me", "1")])
            output.write_text(before, encoding="utf-8")

            def explode(url, timeout):
                raise OSError("network down")

            original_fetch = tool.fetch
            tool.fetch = explode
            try:
                tool.merge(output, ["a", "b"], timeout=1, dry_run=False)
            finally:
                tool.fetch = original_fetch
            self.assertEqual(output.read_text(encoding="utf-8"), before)

    def test_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "server_blacklist.txt"
            original_fetch = tool.fetch
            tool.fetch = lambda url, timeout: tool.render([("2.2.2.2:0", "x", "2")])
            try:
                tool.merge(output, ["one"], timeout=1, dry_run=True)
            finally:
                tool.fetch = original_fetch
            self.assertFalse(output.exists())


class TestSources(unittest.TestCase):
    def test_comments_and_blank_lines_are_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sources.txt"
            path.write_text("# a comment\n\nhttps://example.invalid/a.txt\n\n", encoding="utf-8")
            urls, origin = tool.load_sources(str(path))
            self.assertEqual(urls, ["https://example.invalid/a.txt"])
            self.assertEqual(origin, path)

    def test_shipped_sources_file_parses(self):
        shipped = Path(__file__).resolve().parent.parent / "sources.txt"
        urls, _ = tool.load_sources(str(shipped))
        self.assertTrue(urls)
        self.assertTrue(all(url.startswith("https://") for url in urls))

    def test_github_blob_urls_become_raw_urls(self):
        self.assertEqual(
            tool.to_raw("https://github.com/owner/repo/blob/main/server_blacklist.txt"),
            "https://raw.githubusercontent.com/owner/repo/main/server_blacklist.txt",
        )

    def test_other_urls_are_left_alone(self):
        for url in (
            "https://raw.githubusercontent.com/owner/repo/main/list.txt",
            "https://example.invalid/list.txt",
        ):
            self.assertEqual(tool.to_raw(url), url)


class TestGameDiscovery(unittest.TestCase):
    def _fake_steam(self, tmp: Path, *, second_library: bool) -> Path:
        root = tmp / "Steam"
        (root / "steamapps").mkdir(parents=True)
        library = tmp / "Games" if second_library else root
        (library / "steamapps").mkdir(parents=True, exist_ok=True)
        (root / "steamapps" / "libraryfolders.vdf").write_text(
            '"libraryfolders"\n{\n\t"0"\n\t{\n\t\t"path"\t\t"'
            + str(library).replace("\\", "\\\\")
            + '"\n\t}\n}\n',
            encoding="utf-8",
        )
        (library / "steamapps" / "appmanifest_240.acf").write_text(
            '"AppState"\n{\n\t"appid"\t\t"240"\n\t"installdir"\t\t"Counter-Strike Source"\n}\n',
            encoding="utf-8",
        )
        (library / "steamapps" / "common" / "Counter-Strike Source" / "cstrike" / "cfg").mkdir(
            parents=True
        )
        return root

    def _find_with_root(self, root: Path):
        original = tool.steam_roots
        tool.steam_roots = lambda: [root]
        try:
            return tool.find_blacklist()
        finally:
            tool.steam_roots = original

    def test_finds_game_in_the_primary_library(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._fake_steam(Path(tmp), second_library=False)
            found = self._find_with_root(root)
            self.assertIsNotNone(found)
            self.assertEqual(found.name, "server_blacklist.txt")
            self.assertTrue(found.parent.is_dir())

    def test_follows_libraryfolders_to_another_drive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._fake_steam(Path(tmp), second_library=True)
            found = self._find_with_root(root)
            self.assertIsNotNone(found)
            self.assertIn("Games", str(found))

    def test_returns_none_when_the_game_is_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "Steam"
            (root / "steamapps").mkdir(parents=True)
            self.assertIsNone(self._find_with_root(root))

    def test_steam_roots_are_real_directories(self):
        self.assertTrue(all(root.is_dir() for root in tool.steam_roots()))


if __name__ == "__main__":
    unittest.main()
