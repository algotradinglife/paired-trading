# PA Feitian Read-Only Dashboard

Static dashboard shell for copied `pa_feitian_snapshot_v0` artifacts.

Run from this directory:

```bash
npm run copy:snapshot
npm run copy:snapshot -- /path/to/generated-pa-feitian-snapshot.json
npm run smoke
npm run serve
```

The default copy source is `src/tests/fixtures/pa_feitian_snapshot_v0.json`.
Generated snapshots can use the same copy path before smoke testing or serving.
The dashboard fetches only the copied frontend fixture and does not read raw data
stores or strategy internals.
