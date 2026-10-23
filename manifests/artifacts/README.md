# `manifests/artifacts/` — stored-evidence manifests

One file per stored run: `<bench>-<run-id>.manifest.json`, written by
`sim/run_store_evidence.py` (issue #331). Each entry
names one object in the fleet artifact store by its sha256, with `size`,
`kind` (`evidence`), `producer` (`tool`, `version`, `loom.repo`, `commit`),
`uri`, and `name`, the path the bytes would have had under `sim/`. The
format is klayout-tools' `docs/cli/artifact.md`.

Evidence bytes are private; these manifests are public (operator decision
1.1, 2026-10-22). The run's Markdown summary is committed under `sim/<bench>/`.

Manifests are append-only evidence: never edit or delete one. CI runs
`python3 scripts/check_artifact_manifests.py check --tree <sha>`, which checks
the schema and that no stored object's bytes are also committed. To check the
bytes, run `python3 scripts/check_artifact_manifests.py verify <manifest>` or
`klt artifact verify <manifest>` with `KLT_ARTIFACT_BROKER` set. See
`sim/README.md`, "Stored evidence".
