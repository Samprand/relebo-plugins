"""The pending write runs the mechanical guards before it lands: what the Stop gate used
to correct after the fact now asks the human first."""

import pre_tool

ANCHORS = {"imports", "utils-structure", "one-principal-definition-per", "naming-conventions"}


def test_write_with_relative_import_and_util_function_is_caught_before_landing():
    content = "import '../shared/foo.dart';\n\nString formatDate(DateTime d) => d.toString();\n"
    tool_input = {"file_path": "/repo/lib/shared/utils/date/formatter.dart", "content": content}
    anchors = {f["anchor"] for f in pre_tool._edit_findings("Write", tool_input, ANCHORS)}
    assert anchors == {"imports", "utils-structure"}


def test_write_of_two_classes_into_a_types_file_is_caught():
    tool_input = {
        "file_path": "/repo/lib/shared/types/embedded_form.dart",
        "content": "class EmbeddedFormRef {}\n\nclass EmbeddedFormContext {}\n",
    }
    findings = pre_tool._edit_findings("Write", tool_input, ANCHORS)
    assert [f["anchor"] for f in findings] == ["one-principal-definition-per"]


def test_edit_fragment_does_not_run_the_whole_file_guard():
    """An Edit is a fragment: it cannot say how many definitions the file ends up with."""
    tool_input = {
        "file_path": "/repo/lib/shared/types/embedded_form.dart",
        "new_string": "class A {}\nclass B {}\n",
    }
    assert pre_tool._edit_findings("Edit", tool_input, ANCHORS) == []


def test_clean_write_passes():
    tool_input = {
        "file_path": "/repo/lib/shared/utils/date/formatter.dart",
        "content": "import 'package:app/shared/foo.dart';\n\nclass DateFormatterUtil {}\n",
    }
    assert pre_tool._edit_findings("Write", tool_input, ANCHORS) == []


def test_findings_outside_the_pinned_anchors_are_dropped():
    tool_input = {"file_path": "/repo/lib/x.dart", "content": "import '../y.dart';\n"}
    assert pre_tool._edit_findings("Write", tool_input, set()) == []
