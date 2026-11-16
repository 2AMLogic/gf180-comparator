#!/usr/bin/env python3
"""Offline fixture tests for scripts/check_work_plan_provenance.py (#411).
Never touches the forge: the API fetch is injected as a fake. Carries the
contaminated `<!-- guide:plan-body -->` region of commit 2af9216c (PR #410,
which rendered asap7-stdcells' label state into this repo) as the failing
fixture -- evidence captured in
docs/forensics/2026-11-15-work-plan-provenance-incident.md. Also covers the
region self-consistency checks (issue #419): the renderer's section
suffixes and the Backlog Balance counts against the rows they summarise.

    python3 scripts/tests/test_check_work_plan_provenance.py
"""
import contextlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
import check_work_plan_provenance as CWPP  # noqa: E402

REPO_NAME = "2AMLogic/gf180-comparator"

# This repo's real titles for a few of the numbers the contaminated region
# names -- every one of which exists here, closed, under an UNRELATED title
# (the issue's "why an existence-only check cannot work" paragraph).
LOCAL_TITLES = {
    3: "Gap-to-T1 tracker: gf180-comparator artifact-presence survey",
    112: "layout/PEX/signoff re-run for the DR-0004 input-cascode netlist "
         "(follow-up to #102)",
    122: "ci: PDK-free netlist source-pin check (#120)",
    161: "Validate integrator paths, ordered ports and area against "
         "committed artifacts",
    133: "Unify the PDK-free test entrypoint so npm test matches CI (#129)",
    406: "corners.parse_corner_id is not the strict inverse its docstring "
         "claims: non-canonical temperatures parse",
}

READY_TITLE = LOCAL_TITLES[406]

CONTAMINATED = """\
<!-- guide:plan-body:start -->
## Operator Attention: Merge-Risk-Hold Pileup

Judge-approved PRs under a hold (`loom:blocked` or `loom:operator`) — only a human merge decision is missing.

- **#145**: fix: correct drifted decision-record enumeration and item-9 klt pin in attested evidence

## Very Important

`loom:very-important` (one counts per workspace); every stage takes these first.

- **#122**: Library: several signal pins have no routable access point, so OpenROAD detailed routing cannot complete (DRT-0073)

## Important

`loom:important`; taken before unlabelled work.

- **#110**: Re-take the full DRC/LVS regression record under the CI-pinned klt 0.9.0

## Ready

Human-approved issues ready for implementation (`loom:issue`).

- **#137**: a7s_common: gate_contact's v1= parameter now shadows the module-level v1() helper
- **#139**: Docs: ROADMAP.md is on main but nothing links it
- **#154**: normalize_paths CLI: the relative-prefix test is vacuous, and a trailing flag crashes instead of printing usage
- **#156**: `--verify` cannot re-check any committed record: 541 of 581 envelopes drift on nondeterministic and uncommitted derived inputs

## In Progress

Issues currently being built (`loom:building`).

- **#120**: Docs: stale decision-record enumeration in spec/stdcells.md, and the declared 0.8.0 pin in t1-item9-inventory.json
- **#122**: Library: several signal pins have no routable access point, so OpenROAD detailed routing cannot complete (DRT-0073)
- **#129**: Collapse the package.json test/check alias chain onto one gate that runs all six self-test files
- **#142**: Item 9 inventory does not content-hash klt_helper.py (nor check_lef.py / write_lef.py)
- **#144**: Four harness/evidence scripts outside item 9 are unpinned, incl. item 2's own check command

## PRs Awaiting Review

PRs waiting on Judge (`loom:review-requested`).

- **#143**: build: run all six self-tests as one package.json gate
- **#161**: fix(lef): emit a pin's own net M2 as port geometry, not obstruction

## Approved (Awaiting Merge)

PRs that passed review and are queued for Champion auto-merge (`loom:pr`).

- **#145**: fix: correct drifted decision-record enumeration and item-9 klt pin in attested evidence
- **#153**: evidence: pin six unpinned harness/design scripts into T1 item 1 and 10
- **#159**: manifests: content-hash harness helpers in T1 item 9 attestation

## Proposed

Issues carrying `loom:curated`.

- **#120**: Docs: stale decision-record enumeration in spec/stdcells.md, and the declared 0.8.0 pin in t1-item9-inventory.json *(curated)*
- **#122**: Library: several signal pins have no routable access point, so OpenROAD detailed routing cannot complete (DRT-0073) *(curated)*
- **#137**: a7s_common: gate_contact's v1= parameter now shadows the module-level v1() helper *(curated)*
- **#139**: Docs: ROADMAP.md is on main but nothing links it *(curated)*
- **#142**: Item 9 inventory does not content-hash klt_helper.py (nor check_lef.py / write_lef.py) *(curated)*
- **#144**: Four harness/evidence scripts outside item 9 are unpinned, incl. item 2's own check command *(curated)*
- **#149**: integration/run_par.sh records an early-stage OpenROAD refusal as invalid-input (exit 1), not as a recorded refusal (exit 3) *(curated)*
- **#151**: klt_helper.py is not importable: module-level sys.argv indexing blocks unit-testing its pure parts *(curated)*
- **#154**: normalize_paths CLI: the relative-prefix test is vacuous, and a trailing flag crashes instead of printing usage *(curated)*
- **#156**: `--verify` cannot re-check any committed record: 541 of 581 envelopes drift on nondeterministic and uncommitted derived inputs *(curated)*

## Proposed (Architect / Hermit)

- **#133**: Drop the vendored design-evidence-tiers.md: a second, already-stale pin to klayout-tools that the pinned wheel already ships *(hermit)*

## Epics

_None._

## Backlog Balance

| Bucket | Count |
|------|-------|
| Operator merge-risk holds | 1 |
| Very important | 1 |
| Important | 1 |
| Ready (`loom:issue`) | 4 |
| In Progress (`loom:building`) | 5 |
| PRs awaiting review | 2 |
| Approved PRs awaiting merge | 3 |
| Curated | 10 |
| Architect / Hermit proposals | 1 |
| Active epics | 0 |
<!-- guide:plan-body:end -->
"""


def make_fake_fetch(titles, missing=(), calls=None):
    def fake(repo, number, token):
        if calls is not None:
            calls.append(number)
        if number in missing:
            raise CWPP.Failure(f"{CWPP.ERR}#{number} does not exist in "
                               f"{repo} (HTTP 404)")
        if number not in titles:
            raise CWPP.Failure(f"{CWPP.ERR}#{number} does not exist in "
                               f"{repo} (HTTP 404)")
        return {"title": titles[number]}
    return fake


def no_fetch(*_a):
    raise AssertionError("forge must not be queried without a token")


def plan(*sections):
    body = "\n".join(sections)
    return (f"header\n\n{CWPP.START}\n{body}\n{CWPP.END}\n")


def section(heading, blurb, rows, suffix=""):
    body = "\n".join(f"- **#{n}**: {t}{suffix}" for n, t in rows) or "_None._"
    return f"## {heading}\n\n{blurb}\n\n{body}\n"


def table(*rows):
    """A Backlog Balance section whose counts are `rows` (label, count).
    Labels are arbitrary: the guard pairs rows to sections by position,
    never by name."""
    body = "".join(f"| {label} | {n} |\n" for label, n in rows)
    return (f"## {CWPP.BALANCE}\n\n| Bucket | Count |\n|------|-------|\n"
            f"{body}")


# One count row per non-balance section of CLEAN, in render order -- the
# count check requires it (#419), so any fixture that renders N sections
# must pair them with N table rows.
TABLE = table(("Ready (`loom:issue`)", 1), ("Curated", 1))
TABLE_READY = table(("Ready (`loom:issue`)", 1))

CLEAN = plan(
    section("Ready", "Human-approved issues ready for implementation "
            "(`loom:issue`).", [(406, READY_TITLE)]),
    section("Proposed", "Issues carrying `loom:curated`.",
            [(406, READY_TITLE)], suffix=" *(curated)*"),
    TABLE)


class Check(unittest.TestCase):
    def run_check(self, text, token="t", fetch=None):
        errs = CWPP.check(text, REPO_NAME, token,
                          fetch=fetch or make_fake_fetch(LOCAL_TITLES))
        return errs

    def test_clean_region_passes(self):
        self.assertEqual(self.run_check(CLEAN), [])

    def test_contaminated_region_fails_naming_foreign_number(self):
        calls = []
        errs = self.run_check(CONTAMINATED, fetch=make_fake_fetch(
            LOCAL_TITLES, calls=calls))
        self.assertTrue(errs)
        joined = "\n".join(errs)
        # #122 exists here, closed, under an unrelated title -- existence
        # alone would pass; the title match is what must name it.
        self.assertIn("#122", joined)
        # One combined message (#416): this branch cannot tell a
        # stale/mis-rendered pin from a foreign row, so it must name
        # both causes and both remedies, not claim "foreign".
        self.assertIn("pinned title no longer matches", joined)
        self.assertIn("Guide document-maintenance tick", joined)
        self.assertIn("2026-11-15-work-plan-provenance-incident.md", joined)
        self.assertIn(LOCAL_TITLES[122], joined)
        # #133 is the only *(hermit)* row and the only one exercising the
        # SUFFIX fallback; its forge title is unrelated here, so it must
        # fail too -- the fixture then bites on every foreign row.
        self.assertIn("#133", joined)
        self.assertTrue(calls, "the forge fake was never queried")

    def test_number_in_neither_repo_fails(self):
        fetch = make_fake_fetch({}, missing=(406,))
        errs = self.run_check(CLEAN, fetch=fetch)
        self.assertEqual(len(errs), 1)
        self.assertIn("#406 does not exist", errs[0])

    def test_pr_and_issue_share_number(self):
        # GitHub unifies PRs and issues on /issues/{n}; the title decides.
        fetch = make_fake_fetch({406: "a PR title"})
        errs = self.run_check(
            plan(section("Ready", "blurb", [(406, "a PR title")]),
                 TABLE_READY),
            fetch=fetch)
        self.assertEqual(errs, [])
        errs = self.run_check(
            plan(section("Ready", "blurb", [(406, "the issue title")]),
                 TABLE_READY),
            fetch=fetch)
        self.assertEqual(len(errs), 1)

    def test_markdown_in_title_matches_exactly(self):
        title = "`--verify` cannot re-check (a & b) **bold** [x] records"
        errs = self.run_check(
            plan(section("Ready", "blurb", [(406, title)]), TABLE_READY),
            fetch=make_fake_fetch({406: title}))
        self.assertEqual(errs, [])

    def test_renderer_suffix_falls_back_to_bare_title(self):
        errs = self.run_check(CLEAN, fetch=make_fake_fetch(
            {406: READY_TITLE}))
        self.assertEqual(errs, [])

    def test_title_that_merely_differs_fails(self):
        errs = self.run_check(
            plan(section("Ready", "blurb",
                         [(406, READY_TITLE + " (edited later)")]),
                 TABLE_READY),
            fetch=make_fake_fetch({406: READY_TITLE}))
        self.assertEqual(len(errs), 1)
        # Same input shape as the contaminated fixture's #122 row, so
        # the same combined message (#416): no discriminator exists.
        self.assertIn("pinned title no longer matches", errs[0])
        self.assertIn("Guide document-maintenance tick", errs[0])

    def test_parsed_row_whose_title_contains_hash_number_is_one_row(self):
        # A parsed row's own title may legitimately contain #M (#133's
        # title here ends in '(#129)'): the drifted-format check is
        # line-level, never 'every #N occurrence in the region'.
        errs = self.run_check(
            plan(section("Ready", "blurb", [(133, LOCAL_TITLES[133])]),
                 TABLE_READY),
            fetch=make_fake_fetch(LOCAL_TITLES))
        self.assertEqual(errs, [])

    def test_empty_sections_pass(self):
        text = plan(section("Very Important", "blurb", []),
                    table(("Very important", 0)))
        self.assertEqual(self.run_check(text), [])


class RegionSelfConsistency(unittest.TestCase):
    """The two offline checks from issue #419 -- renderer suffixes and
    Backlog Balance counts -- each verifiable with zero API calls and no
    dependence on live forge state."""

    def run_check(self, text, token="t", fetch=None):
        errs = CWPP.check(text, REPO_NAME, token,
                          fetch=fetch or make_fake_fetch(LOCAL_TITLES))
        return errs

    # --- suffix requirement -------------------------------------------

    def test_proposed_row_without_suffix_fails_naming_row(self):
        # PR #418's head 52e7376a dropped the suffix on all 7 Proposed
        # rows and the guard of the day passed everything but its $2
        # title drift -- this is the case that head should have failed.
        text = plan(
            section("Ready", "blurb", [(406, READY_TITLE)]),
            section("Proposed", "Issues carrying `loom:curated`.",
                    [(406, READY_TITLE)]),
            table(("Ready (`loom:issue`)", 1), ("Curated", 1)))
        errs = self.run_check(text)
        self.assertEqual(len(errs), 1)
        self.assertIn("without the renderer's ' *(curated)*' suffix",
                      errs[0])
        self.assertIn("- **#406**:", errs[0])

    def test_wrong_suffix_under_proposed_fails(self):
        text = plan(
            section("Ready", "blurb", [(406, READY_TITLE)]),
            section("Proposed", "Issues carrying `loom:curated`.",
                    [(406, READY_TITLE)], suffix=" *(hermit)*"),
            table(("Ready (`loom:issue`)", 1), ("Curated", 1)))
        errs = self.run_check(text)
        self.assertEqual(len(errs), 1)
        self.assertIn("' *(curated)*'", errs[0])

    def test_curated_suffix_under_architect_hermit_fails(self):
        text = plan(
            section("Proposed (Architect / Hermit)", "",
                    [(406, READY_TITLE)], suffix=" *(curated)*"),
            table(("Architect / Hermit proposals", 1)))
        errs = self.run_check(text)
        self.assertEqual(len(errs), 1)
        self.assertIn("without the renderer's ' *(architect)*' or "
                      "' *(hermit)*' suffix", errs[0])

    def test_suffix_on_non_proposed_row_fails(self):
        # match()'s fallback would happily strip this against the bare
        # forge title -- the section check is what names it.
        text = plan(
            section("Ready", "blurb", [(406, READY_TITLE)],
                    suffix=" *(curated)*"),
            table(("Ready (`loom:issue`)", 1)))
        errs = self.run_check(text)
        self.assertEqual(len(errs), 1)
        self.assertIn("carrying a section suffix", errs[0])
        self.assertIn("'Ready'", errs[0])

    def test_forge_title_genuinely_ending_in_suffix_passes_once(self):
        # The renderer appends its suffix to the forge title; a title that
        # itself ends in ' *(curated)*' renders doubled, satisfies the
        # suffix requirement, and still matches via SUFFIX's fallback --
        # reported once at most, i.e. here: not at all.
        title = READY_TITLE + " *(curated)*"
        text = plan(
            section("Proposed", "Issues carrying `loom:curated`.",
                    [(406, title)], suffix=" *(curated)*"),
            table(("Curated", 1)))
        self.assertEqual(self.run_check(text, fetch=make_fake_fetch(
            {406: title})), [])

    # --- Backlog Balance counts ---------------------------------------

    def test_deleted_row_fails_via_count(self):
        # The currently-invisible case: a row cleanly deleted from a
        # section leaves only valid rows behind and used to exit 0.
        text = plan(
            section("Ready", "blurb", [(406, READY_TITLE)]),
            section("Proposed", "Issues carrying `loom:curated`.",
                    [(406, READY_TITLE)], suffix=" *(curated)*"),
            table(("Ready (`loom:issue`)", 1), ("Curated", 3)))
        errs = self.run_check(text)
        self.assertEqual(len(errs), 1)
        self.assertIn("'Curated'", errs[0])
        self.assertIn("says 3", errs[0])
        self.assertIn("'Proposed'", errs[0])
        self.assertIn("renders 1 row(s)", errs[0])

    def test_none_section_with_zero_count_passes_and_nonzero_fails(self):
        text = plan(section("Epics", "", []), table(("Active epics", 0)))
        self.assertEqual(self.run_check(text), [])
        text = plan(section("Epics", "", []), table(("Active epics", 1)))
        errs = self.run_check(text)
        self.assertEqual(len(errs), 1)
        self.assertIn("says 1", errs[0])
        self.assertIn("renders 0 row(s)", errs[0])

    def test_table_row_added_or_removed_without_section_fails(self):
        base = (section("Ready", "blurb", [(406, READY_TITLE)]),
                section("Proposed", "Issues carrying `loom:curated`.",
                        [(406, READY_TITLE)], suffix=" *(curated)*"))
        errs = self.run_check(plan(*base, table(("Ready (`loom:issue`)", 1))))
        self.assertEqual(len(errs), 1)
        self.assertIn("1 count row(s) for 2 rendered section(s)", errs[0])
        errs = self.run_check(plan(
            section("Ready", "blurb", [(406, READY_TITLE)]),
            table(("Ready (`loom:issue`)", 1), ("Curated", 1))))
        self.assertEqual(len(errs), 1)
        self.assertIn("2 count row(s) for 1 rendered section(s)", errs[0])

    def test_bucket_labels_pair_positionally_not_by_name(self):
        # The bucket labels deliberately differ from the headings (6 of
        # the 10 differ in more than case on main), so pairing must be
        # positional: a nonsense label with the right count passes, and
        # the right label with the wrong count still fails.
        text = plan(
            section("Proposed", "Issues carrying `loom:curated`.",
                    [(406, READY_TITLE)], suffix=" *(curated)*"),
            table(("totally-unrelated-label", 1)))
        self.assertEqual(self.run_check(text), [])
        text = plan(
            section("Proposed", "Issues carrying `loom:curated`.",
                    [(406, READY_TITLE)], suffix=" *(curated)*"),
            table(("Proposed", 2)))
        errs = self.run_check(text)
        self.assertEqual(len(errs), 1)
        self.assertIn("'Proposed'", errs[0])

    def test_malformed_balance_table_row_fails(self):
        text = plan(
            section("Ready", "blurb", [(406, READY_TITLE)]),
            "## Backlog Balance\n\n| Bucket | Count |\n|------|-------|\n"
            "| Ready (`loom:issue`) |\n")
        errs = self.run_check(text)
        self.assertTrue(errs)
        joined = "\n".join(errs)
        self.assertIn("'| label | count |' shape", joined)
        self.assertIn("| Ready (`loom:issue`) |", joined)

    def test_missing_balance_section_fails(self):
        text = plan(section("Ready", "blurb", [(406, READY_TITLE)]))
        errs = self.run_check(text)
        self.assertEqual(len(errs), 1)
        self.assertIn("'Backlog Balance'", errs[0])


class FailClosed(unittest.TestCase):
    def test_no_token_fails_without_querying(self):
        errs = CWPP.check(CLEAN, REPO_NAME, "", fetch=no_fetch)
        self.assertEqual(len(errs), 1)
        self.assertIn("no forge token", errs[0])

    def test_no_token_reports_offline_failures_too(self):
        # Issue #419: the suffix/count checks run ahead of the token
        # gate, so a tokenless invocation reports them IN ADDITION to
        # the no-token failure -- never one instead of the other.
        text = plan(
            section("Proposed", "Issues carrying `loom:curated`.",
                    [(406, READY_TITLE)]),
            table(("Curated", 1)))
        errs = CWPP.check(text, REPO_NAME, "", fetch=no_fetch)
        self.assertEqual(len(errs), 2)
        self.assertIn("without the renderer's ' *(curated)*' suffix",
                      errs[0])
        self.assertIn("no forge token", errs[1])

    def test_absent_markers_fail(self):
        errs = CWPP.check("no markers at all\n", REPO_NAME, "t",
                          fetch=no_fetch)
        self.assertEqual(len(errs), 1)
        self.assertIn("no", errs[0])
        self.assertIn("region", errs[0])

    def test_malformed_markers_fail(self):
        errs = CWPP.check(f"{CWPP.START}\nunclosed\n", REPO_NAME, "t",
                          fetch=no_fetch)
        self.assertEqual(len(errs), 1)
        self.assertIn("region", errs[0])

    def test_whitespace_only_region_fails(self):
        errs = CWPP.check(f"{CWPP.START}\n   \n{CWPP.END}\n", REPO_NAME, "t",
                          fetch=no_fetch)
        self.assertEqual(len(errs), 1)
        self.assertIn("empty", errs[0])

    def test_drifted_row_format_fails_without_querying(self):
        # A non-empty region whose rows name items but do not parse as
        # strict rows (renderer format drift): the guard must fail
        # closed instead of reporting "0 row(s) checked" -- and it must
        # do so without consulting the forge. Covers every shape that
        # changes the bullet marker, the indentation or the row's
        # container, not just the ': ' separator.
        shapes = [
            "- **#999** - a totally foreign title\n- **#998** - another",
            "* **#999**: a totally foreign title",
            "  - **#999**: a totally foreign title",
            "1. **#999**: a totally foreign title",
            "| #999 | a totally foreign title |",
            "### #999 a totally foreign title",
            "Ready: #999 a totally foreign title",
        ]
        for shape in shapes:
            with self.subTest(shape=shape.splitlines()[0]):
                errs = CWPP.check(plan(shape), REPO_NAME, "t", fetch=no_fetch)
                self.assertTrue(errs)
                joined = "\n".join(errs)
                self.assertIn("format", joined)
                self.assertIn("#999", joined)


class Main(unittest.TestCase):
    def test_main_pass_fail_and_token_gate(self):
        with tempfile.TemporaryDirectory() as d:
            good = Path(d) / "good.md"
            good.write_text(CLEAN, encoding="utf-8")
            bad = Path(d) / "bad.md"
            bad.write_text(CONTAMINATED, encoding="utf-8")
            env = dict(os.environ)
            env.pop("GITHUB_TOKEN", None)
            env.pop("GH_TOKEN", None)
            env["GITHUB_TOKEN"] = "t"
            old = os.environ
            os.environ = env
            fake = make_fake_fetch(LOCAL_TITLES)
            try:
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    rc = CWPP.main(["--plan", str(good), "--repo", REPO_NAME],
                                   fetch=fake)
                self.assertEqual(rc, 0, buf.getvalue())
                self.assertIn("ok", buf.getvalue())
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    rc = CWPP.main(["--plan", str(bad), "--repo", REPO_NAME],
                                   fetch=fake)
                self.assertEqual(rc, 1)
                self.assertIn("#122", buf.getvalue())
                env.pop("GITHUB_TOKEN", None)
                env.pop("GH_TOKEN", None)
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    rc = CWPP.main(["--plan", str(good), "--repo", REPO_NAME],
                                   fetch=no_fetch)
                self.assertEqual(rc, 1)
                self.assertIn("no forge token", buf.getvalue())
            finally:
                os.environ = old


if __name__ == "__main__":
    unittest.main()
