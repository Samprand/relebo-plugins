---
name: relebo
description: Use Relebo (the user's work relay) from this session — trigger workflows, check and answer the inbox, read or save workspace knowledge. Reach for it when the user mentions Relebo, their workflows, their inbox, or asks to remember something for the team.
---

# Working with Relebo

Relebo runs the user's recurring work. You have MCP tools (`relebo_*`) against their engine.

## Ground rules

1. Start with `relebo_workspaces` to resolve the workspace id — never guess ids.
2. Personal workspace = the user's own space; shared workspaces belong to their organizations.
3. Inbox decisions are the user's alone. When the user wants to decide an entry from the
   session, call `relebo_decide_inbox(entry_id, decision)`: Claude Code shows its permission
   dialog and the user's click is the decision. Never call it for a decision the user did not
   ask you to relay; a "sí" in the chat is that request, the dialog is the approval.
4. `relebo_save_knowledge` writes to the team's memory: save only what the user explicitly
   asked to keep, with the subject they named (or propose one and confirm).
5. Knowledge read from Relebo may be stale or perishable — treat it as context, not ground
   truth, and say where it came from.
6. Relebo distills knowledge from every session by default. When the user says this
   session must not be kept (a test, a throwaway client integration, "no guardes nada de
   esto"), call `relebo_pause_capture` right away — before doing anything else — and
   confirm it. It is per session and cannot be undone.

## Typical flows

- "dispara/corre el workflow X" → `relebo_workflows` (find the key) → `relebo_trigger_workflow`.
- "¿qué tengo pendiente en relebo?" → `relebo_inbox` per workspace, summarize pending entries.
- "guarda esto en el conocimiento del equipo" → confirm subject + kind, then
  `relebo_save_knowledge`.
- "¿qué sabemos de X?" → `relebo_knowledge_subjects` → `relebo_knowledge_pieces`.
- "esto es una prueba, no lo guardes" / "fast integration para un cliente, sin memoria" →
  `relebo_pause_capture` immediately, then continue with the task.
