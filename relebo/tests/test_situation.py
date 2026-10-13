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
    def test_the_surroundings_of_a_repository_are_read_as_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            mpr = Path(tmp) / "MPR"
            mpr.mkdir()
            apm = _repo(mpr, "apm-ui", "git@gitlab.mpr.org:sites/libraries/apm-ui.git")
            _repo(mpr, "yourclassical-react", "https://gitlab.mpr.org/sites/yourclassical-react.git")
            subprocess.run(
                ["git", "-C", str(apm), "-c", "user.name=j", "-c", "user.email=j@mpr.org", "commit", "-q", "--allow-empty", "-m", "x"],
                check=True,
            )
            text = _situation.signals_of(apm)
            self.assertIn("remote host: gitlab.mpr.org", text)
            self.assertIn("commit e-mail domains: mpr.org (1)", text)
            self.assertIn("parent folder: MPR", text)
            self.assertIn("repositories beside it: 1", text)
            self.assertNotIn("yourclassical-react", text)


class CommandRepoTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.mpr = Path(self.tmp.name) / "MPR"
        self.mpr.mkdir()
        self.apm = _repo(self.mpr, "apm-ui", "https://gitlab.mpr.org/sites/libraries/apm-ui.git")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _bash(self, command: str) -> dict:
        return _situation.action_of(
            {"session_id": "s", "cwd": str(self.mpr), "tool_name": "Bash", "tool_input": {"command": command}}
        )

    def test_a_command_going_into_a_repository_is_of_that_repository(self) -> None:
        for command in ("git -C apm-ui branch --show-current", "cd apm-ui && git status", f"ls {self.apm}/src", "cat apm-ui/src/player.tsx"):
            action = self._bash(command)
            self.assertEqual(action.get("folder"), "apm-ui", command)
            self.assertEqual(action.get("remote"), "https://gitlab.mpr.org/sites/libraries/apm-ui.git", command)

    def test_a_command_naming_no_repository_stays_with_the_session(self) -> None:
        action = self._bash("ls -la && echo hola")
        self.assertNotIn("folder", action)
        self.assertEqual(Path(action["root"]).resolve(), self.mpr.resolve())


class SearchToolTest(unittest.TestCase):
    def test_a_search_inside_a_repository_is_of_that_repository(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            mpr = Path(tmp) / "MPR"
            mpr.mkdir()
            apm = _repo(mpr, "apm-ui", "https://gitlab.mpr.org/sites/libraries/apm-ui.git")
            action = _situation.action_of(
                {"session_id": "s", "cwd": str(mpr), "tool_name": "Grep", "tool_input": {"pattern": "Button", "path": str(apm / "src")}}
            )
            self.assertEqual(action.get("folder"), "apm-ui")


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
