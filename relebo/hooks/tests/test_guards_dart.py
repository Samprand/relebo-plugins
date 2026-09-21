"""The one-definition guard on Dart, on utils/, and on text the caller holds for a file
that is not on disk — the shape a reviewed PR arrives in."""

import _guards

TYPES_PATH = "/repo/lib/shared/types/embedded_form.dart"
UTILS_PATH = "/repo/lib/shared/utils/analytics/embedded_form.dart"


def test_dart_second_class_in_a_declaration_folder_is_a_finding():
    text = "class EmbeddedFormRef {}\n\nclass EmbeddedFormContext {}\n"
    findings = _guards.principal_definition_guards([TYPES_PATH], texts={TYPES_PATH: text})
    assert [f["anchor"] for f in findings] == [_guards.ANCHOR_ONE_PRINCIPAL]
    assert "EmbeddedFormContext" in findings[0]["evidence"]


def test_utils_files_are_covered_the_real_pr_shape_is_caught():
    """Three top-level classes in a utils file — the exact shape of PR #200."""
    text = "class EmbeddedFormRef {}\n\nclass EmbeddedFormContext {}\n\nclass EmbeddedFormUtil {}\n"
    findings = _guards.principal_definition_guards([UTILS_PATH], texts={UTILS_PATH: text})
    assert len(findings) == 1
    assert "3 principal definitions" in findings[0]["evidence"]


def test_private_helper_beside_the_util_is_not_a_second_principal():
    text = "class DateFormatterUtil {}\n\nclass _Cache {}\n"
    assert _guards.principal_definition_guards([UTILS_PATH], texts={UTILS_PATH: text}) == []


def test_dart_typedef_beside_its_class_is_not_a_second_definition():
    text = "typedef OnTap = void Function();\n\nclass TapTarget {}\n"
    assert _guards.principal_definition_guards([TYPES_PATH], texts={TYPES_PATH: text}) == []


def test_dart_single_class_with_modifiers_passes():
    text = "abstract final class BookingEntity {}\n"
    assert _guards.principal_definition_guards([TYPES_PATH], texts={TYPES_PATH: text}) == []


def test_texts_stand_in_for_a_file_that_is_not_on_disk():
    text = "class A {}\nclass B {}\n"
    assert _guards.principal_definition_guards([TYPES_PATH]) == []
    assert len(_guards.principal_definition_guards([TYPES_PATH], texts={TYPES_PATH: text})) == 1
