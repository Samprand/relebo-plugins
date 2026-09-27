"""~/.relebo is the machine's own home: the runner, its engines and sign-ins, the supervisor's
sessions. A session reads it freely and never writes it — from a shell line in any spelling
of the home, or from an edit tool — or the worker could reshape the supervisor gating it."""

import json

import _guards
import pre_tool

HOME_WRITES = [
    "echo '{}' > ~/.relebo/engine.json",
    "cat x >> $HOME/.relebo/engine.json",
    "printf ok | tee ${HOME}/.relebo/engines/claude/state.json",
    "rm -rf ~/.relebo/engines",
    "rm ~/.relebo/machine.json",
    "mv /tmp/engine.json /Users/julian/.relebo/engine.json",
    "cp ~/.relebo/engines/claude/config/.credentials.json /tmp/creds.json",
    "sed -i '' 's/pause/credits/' /home/julian/.relebo/engine.json",
    "touch ~/.relebo/sessions/abc.json",
    "chmod 777 ~/.relebo",
    r"Set-Content $env:USERPROFILE\.relebo\engine.json '{}'",
    r"Remove-Item %USERPROFILE%\.relebo\engines -Recurse -Force",
]
HOME_READS = [
    "cat ~/.relebo/engine.json",
    "ls -la ~/.relebo",
    "tail -20 $HOME/.relebo/runner.log",
    "grep -n supervisor ~/.relebo/engine.log > /tmp/out.txt",
    "python3 -c \"import json;print(json.load(open('/Users/julian/.relebo/machine.json')))\"",
    "echo hello > ~/Relebo/notes.txt",
    "rm -rf /tmp/relebo-tests",
]


def test_every_write_into_the_home_is_the_machine_home_effect():
    for command in HOME_WRITES:
        effects = _guards.command_effects(command)
        assert [e["effect"] for e in effects] == [_guards.EFFECT_MACHINE_HOME], command


def test_reads_and_writes_elsewhere_carry_no_machine_home_effect():
    for command in HOME_READS:
        effects = _guards.command_effects(command)
        assert _guards.EFFECT_MACHINE_HOME not in [e["effect"] for e in effects], command


def _decision(capsys) -> dict:
    out = capsys.readouterr().out.strip()
    return json.loads(out)["hookSpecificOutput"] if out else {}


def test_a_shell_write_into_the_home_is_denied_before_it_runs(capsys):
    pre_tool._gate_command({"session_id": "s"}, {"command": "echo x > ~/.relebo/engine.json"})
    decision = _decision(capsys)
    assert decision["permissionDecision"] == "deny"
    assert "~/.relebo belongs to the runner and the supervisor" in decision["permissionDecisionReason"]


def test_an_edit_tool_write_into_the_home_is_denied(capsys):
    assert pre_tool._guard_machine_home_write({"file_path": "/Users/julian/.relebo/engine.json"})
    assert _decision(capsys)["permissionDecision"] == "deny"
    assert pre_tool._guard_machine_home_write({"file_path": "/Users/julian/Relebo/engine.json"}) is False
    assert pre_tool._guard_machine_home_write({"notebook_path": "/home/x/.relebo/n.ipynb"})
