"""The reviewed diff as the hooks consume it, on the real prompt and real diff excerpts of
the PR whose review missed its comments (mpr-news-mobile #200, 2026-09-10)."""

import _review

REVIEW_PROMPT = (
    "revisa este pr feat: GA4 form_submit for embedded in-article forms (MSA-349) by "
    "emanuelsamprand · Pull Request #200 · Samprand/mpr-news-mobile"
)
DIFF = """diff --git a/lib/shared/config/constants/analytics_events.dart b/lib/shared/config/constants/analytics_events.dart
index 8702ddd7..0e6b15df 100644
--- a/lib/shared/config/constants/analytics_events.dart
+++ b/lib/shared/config/constants/analytics_events.dart
@@ -19,4 +19,5 @@ class AnalyticsEvents {
   static const String signUp = 'sign_up';
   static const String search = 'search';
   static const String searchResultClick = 'search_result_click';
+  static const String formSubmit = 'form_submit';
 }
diff --git a/lib/shared/utils/analytics/embedded_form.dart b/lib/shared/utils/analytics/embedded_form.dart
new file mode 100644
index 00000000..bf5340b0
--- /dev/null
+++ b/lib/shared/utils/analytics/embedded_form.dart
@@ -0,0 +1,130 @@
+import 'package:mpr/shared/config/constants/analytics_values.dart';
+
+/// A form embedded in article body copy, identified from the CMS HTML.
+class EmbeddedFormRef {
+  final String formType;
+}
"""


def test_target_reads_a_pr_a_branch_or_the_checkout_but_only_behind_a_review_verb():
    assert _review.target(REVIEW_PROMPT) == {"kind": "pr", "ref": "200"}
    assert _review.target("revisa la rama feat/form-submit") == {
        "kind": "branch",
        "ref": "feat/form-submit",
    }
    assert _review.target("review branch release-2.1 please") == {
        "kind": "branch",
        "ref": "release-2.1",
    }
    assert _review.target("revisa esto") == {"kind": "current"}
    assert _review.target("implementa el PR #200 del ticket") is None
    assert _review.target("arregla el login") is None


def test_split_collects_added_lines_keeps_each_diff_block_and_flags_new_files():
    files = _review.split(DIFF)
    assert set(files) == {
        "lib/shared/config/constants/analytics_events.dart",
        "lib/shared/utils/analytics/embedded_form.dart",
    }
    modified = files["lib/shared/config/constants/analytics_events.dart"]
    assert modified["added"] == "  static const String formSubmit = 'form_submit';"
    assert modified["new"] is False
    assert modified["diff"].startswith(
        "diff --git a/lib/shared/config/constants/analytics_events.dart"
    )
    assert "@@ -19,4 +19,5 @@" in modified["diff"]
    created = files["lib/shared/utils/analytics/embedded_form.dart"]
    assert created["new"] is True
    assert "class EmbeddedFormRef {" in created["added"]
    assert "+++" not in created["added"] and "@@" not in created["added"]


def test_guard_findings_run_on_the_reviewed_additions_and_stay_within_the_anchors():
    review = {
        "paths": ["/repo/lib/shared/utils/x.dart", "/repo/lib/shared/types/y.dart"],
        "added": {"/repo/lib/shared/utils/x.dart": "import '../a.dart';\nvoid helper() {}\n"},
        "new_texts": {"/repo/lib/shared/types/y.dart": "class A {}\nclass B {}\n"},
    }
    anchors = {f["anchor"] for f in _review.guard_findings(review, {"imports", "utils-structure"})}
    assert anchors == {"imports", "utils-structure"}
    everything = {f["anchor"] for f in _review.guard_findings(review, set(_guards_anchors()))}
    assert everything == {"imports", "utils-structure", "one-principal-definition-per"}


def _guards_anchors():
    import _guards

    return {_guards.ANCHOR_IMPORTS, _guards.ANCHOR_UTILS, _guards.ANCHOR_ONE_PRINCIPAL}


def test_delta_is_none_when_the_prompt_is_not_a_review():
    assert _review.delta("/tmp", "arregla el login") is None
