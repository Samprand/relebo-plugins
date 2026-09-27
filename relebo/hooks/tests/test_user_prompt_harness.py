"""A user turn the harness injected — a task notice, a shell command's output — is nobody's
statement: the prompt hook lets it pass without recall and without recording it."""

import user_prompt


def test_harness_messages_are_not_prompts():
    assert user_prompt._is_harness_message("<task-notification>\n<task-id>x</task-id>")
    assert user_prompt._is_harness_message("  <bash-stdout>out</bash-stdout>")
    assert user_prompt._is_harness_message("<system-reminder>\nnote")
    assert not user_prompt._is_harness_message("por qué falla el deploy")
    assert not user_prompt._is_harness_message('<pasted_content id="x">text</pasted_content>')
