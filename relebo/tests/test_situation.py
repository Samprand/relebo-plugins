"""From a folder that holds several repositories, each file touched is of its own: the
action carries that repository's root, folder and remote, and the path inside it. A file of
the folder itself is of the folder, with no remote."""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOKS = Path(__file__).resolve().parents[1] / "hooks"
sys.path.insert(0, str(HOOKS))

import _situation  # noqa: E402


def _repo(parent: Path, name: str, remote: str) -> Path:
    folder = parent / name
    folder.mkdir()
    subprocess.run(["git", "init", "-q", str(folder)], check=True)
    subprocess.run(["git", "-C", str(folder), "remote", "add", "origin", remote], check=True)
    (folder / "src").mkdir()
    (folder / "src" / "player.tsx").write_text("export const x = 1\n")
    return folder


class ActionOfTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.mpr = Path(self.tmp.name) / "MPR"
        self.mpr.mkdir()
        (self.mpr / "notes.md").write_text("WEB-851\n")
        self.react = _repo(self.mpr, "yourclassical-react", "https://gitlab.mpr.org/sites/yourclassical-react.git")
        self.apm = _repo(self.mpr, "apm-ui", "https://gitlab.mpr.org/sites/libraries/apm-ui.git")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _action(self, file_path: Path, tool: str = "Edit") -> dict:
        return _situation.action_of(
            {
                "session_id": "s",
                "cwd": str(self.mpr),
                "tool_name": tool,
                "tool_input": {"file_path": str(file_path), "new_string": "y"},
            }
        )

    def test_a_file_of_a_repository_is_of_that_repository(self) -> None:
        action = self._action(self.react / "src" / "player.tsx")
        self.assertEqual(Path(action["root"]).resolve(), self.react.resolve())
        self.assertEqual(action["path"], "src/player.tsx")
        self.assertEqual(action["folder"], "yourclassical-react")
        self.assertEqual(action["remote"], "https://gitlab.mpr.org/sites/yourclassical-react.git")
        self.assertEqual(action["written"], ["y"])
        other = self._action(self.apm / "src" / "player.tsx", tool="Read")
        self.assertEqual(other["folder"], "apm-ui")
        self.assertEqual(other["remote"], "https://gitlab.mpr.org/sites/libraries/apm-ui.git")
        self.assertNotIn("written", other)

    def test_a_file_of_the_folder_itself_is_of_the_folder_with_no_remote(self) -> None:
        action = self._action(self.mpr / "notes.md")
        self.assertEqual(Path(action["root"]).resolve(), self.mpr.resolve())
        self.assertEqual(action["path"], "notes.md")
        self.assertEqual(action["folder"], "MPR")
        self.assertEqual(action["remote"], "")
        self.assertFalse(_situation.in_project(str(self.mpr)))

    def test_a_file_outside_everything_has_no_path_and_no_marks(self) -> None:
        action = self._action(Path(self.tmp.name) / "elsewhere.txt")
        self.assertIsNone(action["path"])
        self.assertNotIn("folder", action)

    def test_a_command_longer_than_the_engine_takes_goes_as_its_head_and_its_tail(self) -> None:
        """2026-10-16: a 20 KB script fed to a shell was refused by the engine (422, too long)
        and the person was asked to confirm it with no rule behind it."""
        self.assertEqual(_situation.trimmed("echo hi"), "echo hi")
        long = "python3 - <<'EOF'\n" + "x = 1\n" * 12000 + "EOF\nrm -rf build"
        action = _situation.action_of(
            {"session_id": "s", "cwd": str(self.mpr), "tool_name": "Bash", "tool_input": {"command": long}}
        )
        cut = action["command"]
        self.assertLessEqual(len(cut), _situation.MAX_COMMAND_CHARS)
        self.assertTrue(cut.startswith("python3 - <<'EOF'") and cut.endswith("EOF\nrm -rf build"))
        self.assertIn("[…]", cut)

    def test_a_shell_command_is_of_the_session_folder(self) -> None:
        action = _situation.action_of(
            {"session_id": "s", "cwd": str(self.react), "tool_name": "Bash", "tool_input": {"command": "ls"}}
        )
        self.assertEqual(action["command"], "ls")
        self.assertEqual(Path(action["root"]).resolve(), self.react.resolve())


if __name__ == "__main__":
    unittest.main()


class AboutOfTest(unittest.TestCase):
    def test_the_readme_the_manifests_and_the_folders_are_read_as_one_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text("# yourclassical-react\n\nThe web front-end of YourClassical, a brand of MPR.\n")
            (root / "package.json").write_text('{"name": "yourclassical-react", "version": "1.0.0"}')
            (root / "src").mkdir()
            (root / "node_modules").mkdir()
            (root / ".git").mkdir()
            text = _situation.about_of(root)
            self.assertIn("## README.md", text)
            self.assertIn("a brand of MPR", text)
            self.assertIn("## package.json", text)
            self.assertIn("## top-level folders\nnode_modules, src", text)
            self.assertNotIn(".git", text)

    def test_a_place_with_nothing_that_says_what_it_is_gives_an_empty_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "notes.txt").write_text("x")
            self.assertEqual(_situation.about_of(Path(tmp)), "")


class SignalsOfTest(unittest.TestCase):
    def test_the_surroundings_of_a_repository_are_read_as_public_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            mpr = Path(tmp) / "MPR"
            mpr.mkdir()
            apm = _repo(mpr, "apm-ui", "git@gitlab.mpr.org:sites/libraries/apm-ui.git")
            _repo(mpr, "yourclassical-react", "https://gitlab.mpr.org/sites/yourclassical-react.git")
            (apm / "LICENSE").write_text("MIT License\n\nCopyright (c) 2024 Minnesota Public Radio\n")
            (apm / "package.json").write_text('{"name": "@apmg-internal/ui", "homepage": "https://www.mpr.org", "keywords": ["react", "ui"]}')
            subprocess.run(["git", "-C", str(apm), "-c", "user.name=j", "-c", "user.email=j@mpr.org", "commit", "-q", "--allow-empty", "-m", "x"], check=True)
            subprocess.run(["git", "-C", str(apm), "branch", "feature/jr/web-851-app-router"], check=True)
            subprocess.run(["git", "-C", str(apm), "branch", "WEB-900-cards"], check=True)
            text = _situation.signals_of(apm)
            self.assertIn("remote host: gitlab.mpr.org", text)
            self.assertIn("remote owner and groups: sites/libraries", text)
            self.assertIn("LICENSE copyright: Minnesota Public Radio", text)
            self.assertIn("package.json name: @apmg-internal/ui", text)
            self.assertIn("package.json homepage: https://www.mpr.org", text)
            self.assertIn("ticket prefixes in branch names: WEB", text)
            self.assertIn("parent folder: MPR", text)
            self.assertIn("repositories beside it: 1", text)
            # what never leaves: e-mail domains, sibling names, internal instruction files
            self.assertNotIn("mpr.org (", text)
            self.assertNotIn("yourclassical-react", text)
            (apm / "CLAUDE.md").write_text("internal: never ship on fridays\n")
            self.assertNotIn("never ship", _situation.about_of(apm))


class ScrubTest(unittest.TestCase):
    def test_lines_that_look_like_secrets_never_leave(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text("# tools\n\nInternal scripts.\n\nAPI_KEY=sk-live-abc123\ntoken: xyz\nRun with make.\n")
            text = _situation.about_of(root)
            self.assertIn("Internal scripts", text)
            self.assertIn("Run with make", text)
            self.assertNotIn("sk-live", text)
            self.assertNotIn("xyz", text)


class ReadOnlyCommands(unittest.TestCase):
    """When the engine does not answer, a command that only looks goes through. What sits
    inside quotes is a word to look for, not a pipe, a program or a file to read."""

    def test_a_chain_of_reads_with_a_bar_inside_quotes_only_looks(self) -> None:
        command = (
            'cd /tmp/x && sed -n 28,37p a.py; grep -n "def waiting_about" -A6 b.py; '
            'grep -n -e "asked_ids\\|put_ids" c.py | head -3; '
            'git log --all -i --grep="gate\\|judge" --format="%h %s"'
        )
        self.assertTrue(_situation.read_only(command))

    def test_a_word_to_look_for_is_not_a_secret_read(self) -> None:
        self.assertTrue(_situation.read_only('grep -rn "def token" src | head'))
        self.assertTrue(_situation.read_only("grep -rn password_hash src/models"))

    def test_a_file_of_secrets_is_never_read_unjudged(self) -> None:
        for command in (
            "cat token.json",
            "cat ~/.relebo/token.json",
            "cat .env",
            'grep secret ".env"',
            "echo $API_KEY",
            "ls ~/.ssh/id_rsa",
        ):
            self.assertFalse(_situation.read_only(command), command)

    def test_a_writer_or_a_redirection_outside_quotes_is_not_a_read(self) -> None:
        self.assertFalse(_situation.read_only("sed -i 's/a/b/' x.py"))
        self.assertFalse(_situation.read_only("cat a.txt > b.txt"))
        self.assertFalse(_situation.read_only("ls | xargs rm"))
        self.assertFalse(_situation.read_only("grep -rl x src | tee found"))
        self.assertFalse(_situation.read_only("git push origin main"))

    def test_an_arrow_inside_quotes_is_a_word(self) -> None:
        self.assertTrue(_situation.read_only('grep -n "=>" src/a.ts; grep -c ">" README.md'))

    def test_a_word_too_long_for_a_path_breaks_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as parent:
            command = "git commit -q -F - <<'EOF'\n" + ("fix(engine): " + "word " * 400) + "\nEOF"
            self.assertIsNone(_situation.repo_in_command(parent, command))
