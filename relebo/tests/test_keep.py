"""The keep command: the agent's call on a label, as the plugin sends it to the engine."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))

import keep  # noqa: E402


class KeepParsesTheCall(unittest.TestCase):
    def test_a_fact_with_its_label_and_text(self) -> None:
        body = keep.parse(["--session", "s1", "--label", "R1", "--text", "el deploy es desde main"])
        assert body["origin_id"] == "s1" and body["label"] == "R1"
        assert body["text"] == "el deploy es desde main" and body["places"] == []

    def test_a_place_with_its_chain_and_the_persons_yes(self) -> None:
        body = keep.parse(
            [
                "--session", "s1", "--label", "R2", "--confirmed",
                "--place", "mpr", "--what", "Minnesota Public Radio",
                "--place", "mpr news mobile", "--what", "la app", "--repo", "Samprand/mpr-news-mobile",
                "--chain", "mpr > mpr news mobile",
            ]
        )
        assert body["confirmed"] is True
        assert body["places"] == [
            {"name": "mpr", "description": "Minnesota Public Radio"},
            {"name": "mpr news mobile", "description": "la app", "repo": "Samprand/mpr-news-mobile"},
        ]
        assert body["chain"] == ["mpr", "mpr news mobile"]

    def test_work_drop_and_said(self) -> None:
        body = keep.parse(["--session", "s1", "--label", "R1", "--work", "--drop", "--said", "de Samprand"])
        assert body["kind"] == "work" and body["drop"] is True and body["said"] == "de Samprand"

    def test_without_a_session_or_without_label_and_text_nothing_is_sent(self) -> None:
        assert keep.parse(["--label", "R1", "--text", "x"]) is None
        assert keep.parse(["--session", "s1"]) is None
        assert keep.parse(["--session", "s1", "--text", "my own words"]) is not None
        assert keep.parse(["--session", "s1", "--bogus"]) is None


if __name__ == "__main__":
    unittest.main()
