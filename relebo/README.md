# Relebo plugin for Claude Code

Trigger workflows, answer your inbox and read/save workspace knowledge from any
Claude Code session.

## Install (from Claude Code — the only supported path)

```bash
claude plugin marketplace add Samprand/relebo-plugins
claude plugin install relebo@relebo
```

Claude Code shows a config dialog on install:

- **Engine URL** — leave empty on a registered device: the machine identity in
  `~/.relebo/machine.json` already carries the engine address and never
  expires. Set it only on devices without a registered Relebo machine.
- **Session token** — only for unregistered devices (copy from the Relebo app;
  expires ~1h).
- **Gate mode** — `shadow` (default) judges every turn and audits the verdict
  but never blocks: a one-line receipt says what would have blocked. `enforce`
  blocks the turn with the findings (bounded retries, then the unresolved
  findings escalate to your Inbox). Start in shadow, switch to enforce once the
  verdicts agree with what you would have flagged.

Requirements: `uv` (the MCP server runs with it, nothing to install manually).

## Uninstall

```bash
claude plugin uninstall relebo@relebo
```

## Tools

| Tool | What it does |
|---|---|
| `relebo_workspaces` | List your workspaces |
| `relebo_workflows` | List a workspace's workflows |
| `relebo_trigger_workflow` | Run a workflow |
| `relebo_inbox` | List your inbox |
| `relebo_answer_inbox` | Approve/reject a pending entry |
| `relebo_knowledge_subjects` / `relebo_knowledge_pieces` | Read knowledge |
| `relebo_save_knowledge` | Save knowledge |

Auth order: machine identity (`~/.relebo/machine.json`, never expires) →
`RELEBO_TOKEN` (session token, ~1h). Local development without the
marketplace: `claude --plugin-dir /path/to/Relebo/plugin/claude-code/relebo`
with `RELEBO_ENGINE_URL`/`RELEBO_TOKEN` exported.
