"""After a write lands, only rules not yet in the session reach the agent."""

import post_tool

RULE_A = "## [utils-structure]\nUtils are static-method classes."
RULE_B = "## [comments]\nPre-write test."


def test_written_content_per_tool():
    assert post_tool._written("Write", {"content": "x"}) == "x"
    assert post_tool._written("Edit", {"new_string": "y"}) == "y"
    assert (
        post_tool._written("MultiEdit", {"edits": [{"new_string": "a"}, {"new_string": "b"}]})
        == "a\nb"
    )


def test_rules_already_served_this_session_are_not_repeated():
    assert post_tool._fresh([RULE_A, RULE_B], {"utils-structure"}) == [RULE_B]
    assert post_tool._fresh([RULE_A, RULE_B], set()) == [RULE_A, RULE_B]
    assert post_tool._fresh([RULE_A], {"utils-structure", "comments"}) == []
