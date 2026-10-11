#!/usr/bin/env python3
"""PDK-free regressions for the item-8 evidence-chain validation (#275).

Each case copies the report, source manifest and registered records into a
temporary tree, mutates the copy and calls the validator / CLI. Committed
evidence is never touched.

    python3 signoff/tests/test_item8_evidence_chain.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


M8 = _load("m8_under_test", "signoff/make_item8_envelope.py")
M5 = _load("m5_under_test", "signoff/make_item5_envelope.py")
REPORT = "measurements/characterization-report.md"
SOURCES = "measurements/characterization-report.sources.json"
ENVELOPE = "measurements/characterization-report.item8.json"


def _sha(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        man = json.loads((REPO_ROOT / SOURCES).read_text())
        rels = [REPORT, SOURCES, ENVELOPE, "signoff/make_item8_envelope.py", "sim/harness/corners.py",
                "scripts/check_claim_drift.py", "spec/claim-registry.json"]
        rels += [e["path"] for e in man["records"]]
        for rel in rels:
            (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(REPO_ROOT / rel, self.root / rel)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def manifest(self) -> dict:
        return json.loads((self.root / SOURCES).read_text())

    def write_manifest(self, man: dict) -> None:
        (self.root / SOURCES).write_text(json.dumps(man, indent=2, ensure_ascii=False) + "\n")

    def problems(self) -> list[str]:
        try:
            M8.validate_chain(self.root)
        except M8.EvidenceChainError as e:
            return e.problems
        return []

    def cli(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(self.root / "signoff/make_item8_envelope.py"), *args],
                              capture_output=True, text=True, cwd=self.root)

    def assertRejected(self, needle: str) -> None:
        probs = self.problems()
        self.assertTrue(any(needle in p for p in probs), probs)


class CurrentNarrative(Base):
    def test_current_report_is_valid_and_discloses_misses(self) -> None:
        self.assertEqual(self.problems(), [])
        env = M8.build_envelope(self.root)
        self.assertEqual(env["status"], "pass")
        self.assertIn("UNSCORED", env["summary"])
        # disclosed misses travel with the pass (no all-targets-met requirement)
        self.assertIn("kickback schematic both-node target 1/45, stretch 0/45", env["summary"])
        self.assertIn("extracted target 38/45", env["summary"])

    def test_committed_envelope_matches(self) -> None:
        self.assertEqual(M8.validate_chain(REPO_ROOT)[0]["schema_version"], 1)
        self.assertEqual(self.cli("--check").returncode, 0)

    def test_scored_bounds_match_item5_rows(self) -> None:
        rows = {r[2]: (r[4], r[5]) for r in M5.ROWS}  # bench -> (target, stretch)
        want = {"offset": "comparator-offset-tran", "noise": "comparator-preamp-noise",
                "decision_schematic": "comparator-regeneration", "kickback_schematic_both": "comparator-kickback"}
        for key, bench in want.items():
            tmax, smax = M8.SCORED[key][2:]
            self.assertEqual((tmax, smax), rows[bench], key)


class ReportRejected(Base):
    def test_empty_report_rejected_before_writing(self) -> None:
        (self.root / REPORT).write_text("No characterization evidence.\n")
        before = (self.root / ENVELOPE).read_text()
        self.assertRejected("is absent from the report")
        self.assertEqual(self.cli().returncode, 1)
        self.assertIn("evidence-chain", self.cli().stderr)
        self.assertEqual((self.root / ENVELOPE).read_text(), before)  # nothing written

    def test_blank_report_rejected(self) -> None:
        (self.root / REPORT).write_text("")
        self.assertRejected("report is empty")

    def test_missing_required_section_rejected(self) -> None:
        rep = self.root / REPORT
        rep.write_text(rep.read_text().replace("### Input-referred noise", "### Renamed"))
        self.assertRejected("'noise'")
        self.assertEqual(self.cli("--check").returncode, 1)

    def test_section_not_citing_required_record_rejected(self) -> None:
        rep = self.root / REPORT
        rid = "20261002-211343-6346fad"
        text = rep.read_text()
        head = "### Kickback — decision-edge disturbance into the input"
        pre, post = text.split(head)
        body, sep, rest = post.partition("\n## Known gaps")
        rep.write_text(pre + head + body.replace(rid, "REDACTED") + sep + rest)
        self.assertRejected(f"does not cite required record {rid}")

    def test_average_power_must_stay_explicitly_unscored(self) -> None:
        rep = self.root / REPORT
        text = rep.read_text()
        head = "## Scored summary"
        pre, post = text.split(head)
        body, sep, rest = post.partition("\n## Experiment narratives")
        rep.write_text(pre + head + body.replace("UNSCORED", "scored") + sep + rest)
        self.assertRejected("lacks required text 'UNSCORED'")


class RecordsRejected(Base):
    def refresh_report_hash(self) -> None:
        """Model a refresh of the report hash + envelope: still must not pass."""
        env = self.root / ENVELOPE
        data = json.loads(env.read_text())
        data["provenance"]["input"]["content_hash"] = _sha(self.root / REPORT)
        env.write_text(json.dumps(data, indent=2) + "\n")

    def test_missing_record_rejected_after_report_hash_refresh(self) -> None:
        man = self.manifest()
        (self.root / man["records"][4]["path"]).unlink()
        self.refresh_report_hash()
        self.assertRejected("is missing")
        self.assertEqual(self.cli().returncode, 1)

    def test_changed_record_rejected_after_report_hash_refresh(self) -> None:
        path = self.root / self.manifest()["records"][3]["path"]
        path.write_text(path.read_text() + "\n")
        (self.root / REPORT).write_text((self.root / REPORT).read_text() + "\n")
        self.refresh_report_hash()
        self.assertRejected("sha256 differs from the manifest pin")

    def test_wrongly_scoped_record_rejected_even_if_repinned(self) -> None:
        man = self.manifest()
        ent = man["records"][5]  # extracted decision-time record
        self.assertEqual(ent["dut_provenance"], "extracted")
        path = self.root / ent["path"]
        rec = json.loads(path.read_text())
        rec["context"]["dut_provenance"] = "schematic"
        path.write_text(json.dumps(rec))
        ent["sha256"] = _sha(path)  # attacker re-pins the manifest
        self.write_manifest(man)
        self.assertRejected("scope dut_provenance is 'schematic', expected 'extracted'")

    def test_truncated_points_rejected_even_if_repinned(self) -> None:
        man = self.manifest()
        ent = man["records"][3]
        path = self.root / ent["path"]
        rec = json.loads(path.read_text())
        rec["points"] = rec["points"][:10]
        path.write_text(json.dumps(rec))
        ent["sha256"] = _sha(path)
        self.write_manifest(man)
        self.assertRejected("scope points is 10, expected 45")

    def test_record_registered_but_unrequired_rejected(self) -> None:
        man = self.manifest()
        man["sections"][1]["cites"] = [c for c in man["sections"][1]["cites"] if c != man["records"][0]["id"]]
        self.write_manifest(man)
        self.assertRejected("required by no section")


class CoverageRejected(Base):
    """#289: distinct expected PVT corners, not just a point count."""

    def repin(self, rid_or_key: str, mutate) -> None:
        man = self.manifest()
        ent = next(e for e in man["records"] if rid_or_key in (e["id"], e.get("summary_key")))
        path = self.root / ent["path"]
        rec = json.loads(path.read_text())
        mutate(rec)
        path.write_text(json.dumps(rec))
        ent["sha256"] = _sha(path)
        self.write_manifest(man)

    def test_current_records_cover_declared_grids(self) -> None:
        self.assertEqual(self.problems(), [])
        reduced = next(e for e in self.manifest()["records"] if e["points"] == 9)
        self.assertEqual(len(reduced["expected_grid"]["corner_ids"]), 9)
        self.assertTrue(set(reduced["expected_grid"]["corner_ids"]) <= set(M8.authoritative_grid()))
        self.assertEqual(len(M8.authoritative_grid()), 45)

    def test_45_repeats_of_one_noise_point_rejected(self) -> None:
        def m(rec):
            rec["points"] = [json.loads(json.dumps(rec["points"][0])) for _ in range(45)]
        self.repin("noise", m)
        self.assertRejected("duplicate corner tt_-40c_2.97v (45x)")
        self.assertRejected("missing expected corner")
        self.assertEqual(self.cli().returncode, 1)

    def test_missing_corner_replaced_by_duplicate_rejected(self) -> None:
        def m(rec):
            rec["points"][5] = json.loads(json.dumps(rec["points"][0]))
        self.repin("noise", m)
        self.assertRejected("duplicate corner tt_-40c_2.97v (2x)")

    def test_missing_corner_replaced_by_unexpected_rejected(self) -> None:
        def m(rec):
            pt = rec["points"][5]
            pt.update(corner="tt", temp_c=85.0, vdd=3.3, corner_id="tt_85c_3.30v")
        self.repin("noise", m)
        self.assertRejected("unexpected corner tt_85c_3.30v")
        self.assertRejected("missing expected corner")

    def test_derived_key_substitution_rejected(self) -> None:
        def m(rec):
            d = rec["derived"]
            d["tt_85c_3.30v"] = d.pop("ff_-40c_2.97v")
        self.repin("offset", m)
        self.assertRejected("unexpected corner tt_85c_3.30v")
        self.assertRejected("missing expected corner ff_-40c_2.97v")

    def test_reduced_record_not_widened_and_checked(self) -> None:
        def m(rec):
            d = rec["derived"]
            d["tt_27c_2.97v"] = d.pop("tt_27c_3.30v")
        self.repin("20261010-013540611508-4a4df37", m)
        self.assertRejected("unexpected corner tt_27c_2.97v")

    def test_malformed_identity_rejected(self) -> None:
        def m(rec):
            rec["points"][3]["corner_id"] = "garbage"
        self.repin("noise", m)
        self.assertRejected("malformed identity 'garbage'")
        self.assertEqual(self.cli().returncode, 1)

    def test_malformed_derived_key_rejected(self) -> None:
        def m(rec):
            rec["derived"]["tt_27c_3.3v"] = rec["derived"].pop("tt_27c_3.30v")
        self.repin("offset", m)
        self.assertRejected("malformed identity 'tt_27c_3.3v'")

    def test_identity_field_disagreement_rejected(self) -> None:
        def m(rec):
            rec["points"][3]["vdd"] = 3.3 if rec["points"][3]["vdd"] != 3.3 else 2.97
        self.repin("noise", m)
        self.assertRejected("disagrees with explicit fields")

    def test_expected_grid_must_be_authoritative(self) -> None:
        man = self.manifest()
        ent = next(e for e in man["records"] if e.get("summary_key") == "noise")
        ent["expected_grid"]["temps_c"] = [-40, 27, 85]  # right size, wrong grid
        self.write_manifest(man)
        self.assertRejected("do not equal the authoritative full grid")

    def test_expected_grid_size_must_match_points_and_exist(self) -> None:
        man = self.manifest()
        reduced = next(e for e in man["records"] if e["points"] == 9)
        reduced["expected_grid"]["corner_ids"].append("fs_27c_3.30v")
        self.write_manifest(man)
        self.assertRejected("expected_grid has 10 points, manifest points is 9")
        man = self.manifest()
        reduced = next(e for e in man["records"] if e["points"] == 9)
        reduced["expected_grid"]["corner_ids"][0] = "zz_27c_3.30v"
        self.write_manifest(man)
        self.assertRejected("not in the authoritative grid")
        man = self.manifest()
        del man["records"][0]["expected_grid"]
        self.write_manifest(man)
        self.assertRejected("declares no expected_grid")


class StaleSummary(Base):
    def test_stale_summary_detected_when_source_results_change(self) -> None:
        man = self.manifest()
        ent = next(e for e in man["records"] if e.get("summary_key") == "noise")
        path = self.root / ent["path"]
        rec = json.loads(path.read_text())
        for pt in rec["points"][:3]:
            pt["measurements"]["vn_in_uv"] = 700.0  # now misses the 600 uV stretch
        path.write_text(json.dumps(rec))
        ent["sha256"] = _sha(path)
        self.write_manifest(man)
        self.assertEqual(self.problems(), [])  # a coherent change validates...
        proc = self.cli("--check")  # ...but the committed envelope is now stale
        self.assertEqual(proc.returncode, 1)
        self.assertIn("committed envelope is not what", proc.stderr)
        self.assertIn("noise target 45/45, stretch 42/45", M8.build_envelope(self.root)["summary"])

    def test_hand_edited_summary_detected(self) -> None:
        env = self.root / ENVELOPE
        data = json.loads(env.read_text())
        data["summary"] = data["summary"].replace("target 1/45", "target 45/45", 1)
        env.write_text(json.dumps(data, indent=2) + "\n")
        self.assertEqual(self.cli("--check").returncode, 1)


class NarrativeClaims(Base):
    """#293: registered report numbers must agree with the pinned records."""

    def mutate(self, old: str, new: str) -> None:
        rep = self.root / REPORT
        text = rep.read_text()
        self.assertIn(old, text)
        rep.write_text(text.replace(old, new))
        # refresh the narrative hash in the envelope: must still be refused
        env = self.root / ENVELOPE
        data = json.loads(env.read_text())
        data["provenance"]["input"]["content_hash"] = _sha(rep)
        env.write_text(json.dumps(data, indent=2) + "\n")

    def test_current_claims_validate_with_scopes(self) -> None:
        self.assertEqual(self.problems(), [])
        claims = [c for c in json.loads((self.root / "spec/claim-registry.json").read_text())["claims"]
                  if c["doc"] == REPORT]
        scopes = {c["scope"] for c in claims}
        self.assertEqual(scopes, {"scored", "diagnostic", "historical"})
        self.assertFalse([c for c in claims if "power" in c["id"] or "µW" in c["literal"]])  # power UNSCORED

    def assertNamed(self, claim_id: str) -> None:
        self.assertRejected(f"claim {claim_id}:")
        proc = self.cli()
        self.assertEqual(proc.returncode, 1)
        self.assertIn(f"claim {claim_id}:", proc.stderr)
        self.assertIn("nothing written", proc.stderr)

    def test_range_endpoint_mutation_rejected(self) -> None:
        self.mutate("2.994–3.795 mV 3σ, binding", "2.994–3.895 mV 3σ, binding")
        before = (self.root / ENVELOPE).read_text()
        self.assertNamed("char-offset-scored-row-max")
        self.assertEqual((self.root / ENVELOPE).read_text(), before)

    def test_nominal_mutation_rejected(self) -> None:
        self.mutate("| 91.25 µV rms |", "| 81.25 µV rms |")
        self.assertNamed("char-noise-nominal")

    def test_binding_corner_mutation_rejected(self) -> None:
        self.mutate("| **`ff_125c_3.63v`**", "| **`ss_125c_3.63v`**")
        self.assertNamed("char-offset-scored-table-max")

    def test_scored_count_mutation_rejected(self) -> None:
        self.mutate("misses stretch 16/45", "misses stretch 15/45")
        self.assertNamed("char-dec-sch-count-stretch-miss")

    def test_historical_and_diagnostic_claims_are_checked_too(self) -> None:
        self.mutate("3σ ≈ 3.15 mV (`tt_27c_3.30v`, 9-point record)", "3σ ≈ 3.25 mV (`tt_27c_3.30v`, 9-point record)")
        self.assertNamed("char-offset-hist-9pt-nominal")

    def test_changed_record_changes_count_claim(self) -> None:
        """A coherently re-pinned record that flips a count leaves the prose wrong."""
        man = self.manifest()
        ent = next(e for e in man["records"] if e.get("summary_key") == "decision_schematic")
        path = self.root / ent["path"]
        rec = json.loads(path.read_text())
        rec["points"][0]["measurements"]["td_od50_ns"] = 1.9
        path.write_text(json.dumps(rec))
        ent["sha256"] = _sha(path)
        self.write_manifest(man)
        self.assertRejected("claim char-dec-sch-count-target:")

    def test_scored_record_without_scored_claim_rejected(self) -> None:
        reg = self.root / "spec/claim-registry.json"
        data = json.loads(reg.read_text())
        data["claims"] = [c for c in data["claims"]
                          if not (c["doc"] == REPORT and c["id"].startswith("char-noise"))]
        reg.write_text(json.dumps(data))
        self.assertRejected("no scored claim registered against summary record 20260910-125200-4805118")

    def test_claim_against_unmanifested_record_rejected(self) -> None:
        reg = self.root / "spec/claim-registry.json"
        data = json.loads(reg.read_text())
        next(c for c in data["claims"] if c["id"] == "char-noise-nominal")["record"] = "sim/other/records/x.json"
        reg.write_text(json.dumps(data))
        self.assertRejected("claim char-noise-nominal: record sim/other/records/x.json is not in the source manifest")

    def test_missing_registry_rejected(self) -> None:
        (self.root / "spec/claim-registry.json").unlink()
        self.assertRejected("narrative claim registry")

    def test_disclosed_misses_still_pass(self) -> None:
        # the committed report already discloses target/stretch misses and passes
        self.assertEqual(M8.build_envelope(self.root)["status"], "pass")
        self.assertIn("misses stretch 16/45", (self.root / REPORT).read_text())


if __name__ == "__main__":
    unittest.main(verbosity=2)
