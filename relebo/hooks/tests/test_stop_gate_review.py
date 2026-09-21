"""The reviewed diff joins the judge's files after the turn's own, inside the same budget."""

import stop_gate


def _review(n_files: int, size: int) -> dict:
    paths = [f"/repo/lib/f{i}.dart" for i in range(n_files)]
    return {"paths": paths, "diffs": {p: "+" + "x" * (size - 1) for p in paths}}


def test_review_files_are_appended_with_the_review_source():
    files, omitted = [{"path": "/repo/own.dart", "source": "edit", "diff": "+a", "head": ""}], []
    stop_gate._append_review_files(files, omitted, _review(2, 10))
    assert [f["source"] for f in files] == ["edit", "review", "review"]
    assert omitted == []


def test_review_files_respect_the_file_and_char_budgets():
    files, omitted = [], []
    stop_gate._append_review_files(files, omitted, _review(stop_gate._MAX_FILES + 3, 10))
    assert len(files) == stop_gate._MAX_FILES
    assert len(omitted) == 3
    files, omitted = [], []
    per_file = stop_gate._MAX_FILE_CHARS
    fits = stop_gate._MAX_TOTAL_FILE_CHARS // per_file
    stop_gate._append_review_files(files, omitted, _review(fits + 2, per_file))
    assert len(files) == fits and len(omitted) == 2
