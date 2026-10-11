#!/usr/bin/env python3
"""Published headline claims must agree with the committed evidence records
(issue #245). Stdlib only, PDK-free, fail-closed. Run by
scripts/run-pdk-free-tests.sh (step `claim-drift`).

Checks, over the DOCS below (README.md, spec/evidence-ledger.md,
spec/consumers.md):

1. CITATION  every `sim/<bench>/records/<id>.md` path cited in a doc must be
   a tracked file (plain existence when the tree is not a git checkout) and
   have its `.json` twin.
2. STALE     if a cited record has a NEWER record of the same bench and the
   same DUT binding (dut_id + netlist sha256), the citation must sit under a
   historical marker (historical / earlier / superseded / prior / previous /
   history / obsolete within 250 chars before to 120 after the path in the
   doc), or the check names the newer record. Newer records for a different
   DUT (extracted layout, an experiment netlist) are not successors.
3. NUMERIC   every entry of spec/claim-registry.json ties one literal string
   in a named doc to a value in a record's committed JSON twin. The value,
   rendered with the entry's decimals, must appear inside the literal.

HOW TO ADD A REGISTRY ROW (spec/claim-registry.json, key "claims"; the check
only detects disagreement, it never edits a number):
    {"id": "unique-name",
     "doc": "README.md",                      # one of DOCS
     "literal": "128.8 µV rms worst case",    # exact text, must occur once+
     "record": "sim/<bench>/records/<id>.json",
     "pointer": "/summary/vn_in_uv/max",      # JSON pointer into the twin
     "decimals": 1,                           # rendered with f"{v:.{d}f}"
     "scale": 1,                              # optional, value*scale
     "corner": "ff_125c_3.63v",               # optional: the corner that
     "corner_pointer": "/summary/vn_in_uv/at_max"}  # must be in the literal
Pointer syntax: "/"-separated keys; a segment `corner_id=X` selects the list
element whose corner_id is X; a segment `*` ranges over all keys of a dict and
needs "agg": "min" or "max" (the extreme is the value, its key the corner, so
"corner_pointer" is not needed).

Known, already-reported drift is waived in the registry key "known_drift"
({"doc","cited","newer":[ids],"issue":"#N"}). A waiver that no longer matches
anything fails the check, so waivers cannot rot silently.
"""
import json
import math
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ("README.md", "spec/evidence-ledger.md", "spec/consumers.md")
REGISTRY = "spec/claim-registry.json"
CITE = re.compile(r"sim/(comparator-[a-z0-9-]+)/records/([0-9][0-9A-Za-z_.-]*?)\.md")
MARKER = re.compile(r"historical|earlier|superseded|prior|previous|history|"
                    r"obsolete", re.I)
BEFORE, AFTER = 250, 120


def tracked(root):
    """Set of git-tracked paths, or None when root is not a git checkout."""
    if not (Path(root) / ".git").exists():
        return None
    r = subprocess.run(["git", "-C", str(root), "ls-files"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return None
    return set(r.stdout.splitlines())


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def dut_key(twin):
    d = twin.get("dut") or twin.get("context") or {}
    return (d.get("dut_id"), d.get("dut_netlist_sha256"))


def citations(root, docs=DOCS):
    """[(doc, bench, record_id, text, start)] for each cited record path."""
    out, errs = [], []
    for doc in docs:
        f = Path(root) / doc
        if not f.is_file():
            errs.append(f"CLAIM-DRIFT: {doc} not found")
            continue
        text = f.read_text(encoding="utf-8")
        for m in CITE.finditer(text):
            out.append((doc, m.group(1), m.group(2), text, m.start()))
    return out, errs


def check_citations(root, cites, trk):
    errs = []
    for doc, bench, rid, _t, _s in sorted({(c[0], c[1], c[2], "", 0) for c in cites}):
        rel = f"sim/{bench}/records/{rid}"
        for ext in (".md", ".json"):
            ok = (Path(root) / (rel + ext)).is_file()
            if ok and trk is not None and (rel + ext) not in trk:
                ok = False
            if not ok:
                errs.append(f"CLAIM-DRIFT: {doc} cites {rel}.md but "
                            f"{rel + ext} is missing or untracked")
    return errs


def check_stale(root, cites, waivers):
    errs, used = [], set()
    seen = set()
    for doc, bench, rid, text, start in cites:
        if (doc, bench, rid) in seen:
            continue
        rdir = Path(root) / "sim" / bench / "records"
        cj = rdir / (rid + ".json")
        if not cj.is_file():
            continue  # reported by the citation check
        seen.add((doc, bench, rid))
        key = dut_key(load_json(cj))
        newer = []
        for p in sorted(rdir.glob("*.json")):
            if p.stem > rid and dut_key(load_json(p)) == key:
                newer.append(p.stem)
        if not newer:
            continue
        # every occurrence of this citation must be labelled historical
        occ = [c for c in cites if c[:3] == (doc, bench, rid)]
        if all(MARKER.search(t[max(0, s - BEFORE):s + AFTER]) for *_x, t, s in occ):
            continue
        w = next((w for w in waivers if w["doc"] == doc and w["cited"] == rid
                  and set(newer) <= set(w["newer"])), None)
        if w:
            used.add(id(w))
            continue
        errs.append(f"CLAIM-DRIFT: {doc} cites sim/{bench}/records/{rid}.md "
                    f"without a historical marker, but newer same-DUT "
                    f"record(s) exist: {', '.join(newer)}")
    return errs, used


def walk(node, segs, agg):
    """Resolve segs in node. Returns (value, key_or_None)."""
    if not segs:
        return node, None
    seg, rest = segs[0], segs[1:]
    if seg == "*":
        if not isinstance(node, dict) or agg not in ("min", "max"):
            raise KeyError("'*' needs a dict and agg min|max")
        vals = {}
        for k, sub in node.items():
            try:
                vals[k] = walk(sub, rest, agg)[0]
            except KeyError:
                pass
        if not vals:
            raise KeyError("'*' matched nothing")
        k = (min if agg == "min" else max)(vals, key=vals.get)
        return vals[k], k
    if "=" in seg:
        k, v = seg.split("=", 1)
        if not isinstance(node, list):
            raise KeyError(f"{seg}: not a list")
        hits = [e for e in node if isinstance(e, dict) and str(e.get(k)) == v]
        if len(hits) != 1:
            raise KeyError(f"{seg}: {len(hits)} matches")
        return walk(hits[0], rest, agg)
    if not isinstance(node, dict) or seg not in node:
        raise KeyError(f"no key {seg!r}")
    return walk(node[seg], rest, agg)


def resolve(twin, pointer, agg=None):
    if not isinstance(pointer, str) or not pointer.startswith("/"):
        raise KeyError(f"bad pointer {pointer!r}")
    return walk(twin, pointer[1:].split("/"), agg)


def has_token(literal, shown):
    """True if `shown` occurs in `literal` as a complete numeric token: not
    glued to more digits, a decimal part, an exponent, or a leading minus
    (a minus right after a digit is a range dash, not a sign)."""
    for m in re.finditer(re.escape(shown), literal):
        a, b = m.start(), m.end()
        before, after = literal[:a], literal[b:]
        if re.search(r"\d$|\d\.$|\.$|\d\.?[eE][+-]?$", before):
            continue
        if re.match(r"\d|\.\d|\.?[eE][+-]?\d", after):
            continue
        if not shown.startswith("-") and re.search(r"(?<!\d)[-\u2212]$", before):
            continue
        return True
    return False


FIELDS = {"id", "doc", "literal", "record", "pointer", "decimals", "scale",
          "agg", "corner", "corner_pointer"}


def check_claims(root, claims):
    errs, ids = [], set()
    docs = {}
    for c in claims:
        cid = c.get("id", "?") if isinstance(c, dict) else "?"
        tag = f"CLAIM-DRIFT: claim {cid}:"
        if not isinstance(c, dict) or set(c) - FIELDS or not {
                "id", "doc", "literal", "record", "pointer", "decimals"} <= set(c):
            errs.append(f"{tag} malformed registry entry")
            continue
        if cid in ids:
            errs.append(f"{tag} duplicate id")
        ids.add(cid)
        if c["doc"] not in DOCS:
            errs.append(f"{tag} doc {c['doc']} is not one of {DOCS}")
            continue
        if c["doc"] not in docs:
            f = Path(root) / c["doc"]
            docs[c["doc"]] = f.read_text(encoding="utf-8") if f.is_file() else None
        text = docs[c["doc"]]
        if text is None:
            errs.append(f"{tag} {c['doc']} not found")
            continue
        if c["literal"] not in text:
            errs.append(f"{tag} literal {c['literal']!r} not found in {c['doc']}")
            continue
        rec = Path(root) / c["record"]
        if not rec.is_file():
            errs.append(f"{tag} record twin {c['record']} not found")
            continue
        try:
            twin = load_json(rec)
            val, key = resolve(twin, c["pointer"], c.get("agg"))
            dec, scale = c["decimals"], float(c.get("scale", 1))
            if (not isinstance(dec, int) or isinstance(dec, bool) or dec < 0
                    or not math.isfinite(scale)):
                raise ValueError(f"invalid decimals {c['decimals']!r} "
                                 f"or scale {c.get('scale')!r}")
            val = float(val) * scale
            if not math.isfinite(val):
                raise ValueError(f"non-finite resolved value {val}")
            corner = c.get("corner")
            if corner is not None:
                if "corner_pointer" in c:
                    key = resolve(twin, c["corner_pointer"])[0]
                if key != corner:
                    errs.append(f"{tag} record puts the value at corner "
                                f"{key!r}, registry says {corner!r}")
                if corner not in c["literal"]:
                    errs.append(f"{tag} corner {corner} not in the literal")
        except (KeyError, TypeError, ValueError) as e:
            errs.append(f"{tag} cannot resolve {c['pointer']} in "
                        f"{c['record']}: {e}")
            continue
        shown = f"{val:.{dec}f}"
        if not has_token(c["literal"], shown):
            errs.append(f"{tag} {c['doc']} says {c['literal']!r} but "
                        f"{c['record']}{c['pointer']} = {shown}")
    return errs


def run(root=ROOT):
    root = Path(root)
    reg_path = root / REGISTRY
    if not reg_path.is_file():
        return [f"CLAIM-DRIFT: {REGISTRY} not found"]
    try:
        reg = load_json(reg_path)
        claims, waivers = reg["claims"], reg.get("known_drift", [])
        for w in waivers:
            if not (isinstance(w.get("issue"), str)
                    and re.fullmatch(r"#\d+", w["issue"])
                    and {"doc", "cited", "newer"} <= set(w)):
                return [f"CLAIM-DRIFT: malformed known_drift waiver {w!r} "
                        f"(needs doc, cited, newer, issue '#N')"]
    except (ValueError, KeyError, TypeError, AttributeError) as e:
        return [f"CLAIM-DRIFT: {REGISTRY} unreadable: {e}"]
    cites, errs = citations(root)
    if errs:
        return errs
    errs = check_citations(root, cites, tracked(root))
    if not errs:
        e2, used = check_stale(root, cites, waivers)
        errs += e2
        errs += [f"CLAIM-DRIFT: unused known_drift waiver {w['issue']} "
                 f"({w['doc']}, {w['cited']}); remove it" for w in waivers
                 if id(w) not in used]
    errs += check_claims(root, claims)
    return errs


def main(root=ROOT):
    errs = run(root)
    for e in errs:
        print(e)
    if not errs:
        print("claim drift: ok")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
