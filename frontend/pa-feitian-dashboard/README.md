# PA Feitian Read-Only Dashboard

Static dashboard shell for copied `pa_feitian_snapshot_v1` artifacts, optional
manifest-referenced `pa_feitian_decision_intent_v1` sidecars, and legacy
`pa_feitian_snapshot_v0` rendering fallback.

Run from this directory:

```bash
npm run copy:snapshot
npm run copy:snapshot -- /path/to/generated-pa-feitian-snapshot.json
npm run smoke
npm run serve
```

Rebuild the full M4 review fixture set from the repo root:

```bash
python src/scripts/build_pa_feitian_review_artifacts.py
```

The default copy source is `src/tests/fixtures/pa_feitian_snapshot_v1.json`.
Generated v1 snapshots can use the same copy path before smoke testing or
serving. Legacy v0 snapshots are still accepted and render the legacy
`decision_trace` string instead of structured trace nodes.
When the run manifest includes `decision_intent_artifact`, the dashboard fetches
that sidecar artifact and joins `intents[]` to snapshot signals by `signal_id` for
reviewer readiness fields.
The dashboard fetches only the copied frontend fixture and does not read raw data
stores or strategy internals.
