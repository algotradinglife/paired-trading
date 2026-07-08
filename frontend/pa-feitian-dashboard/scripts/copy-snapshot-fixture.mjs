import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const DEFAULT_CONTRACT_VERSION = "pa_feitian_snapshot_v1";
const SUPPORTED_CONTRACT_VERSIONS = new Set([
  "pa_feitian_snapshot_v1",
  "pa_feitian_snapshot_v0",
]);
const dashboardRoot = resolve(fileURLToPath(new URL("../", import.meta.url)));
const repoRoot = resolve(dashboardRoot, "../..");
const defaultSource = resolve(repoRoot, `src/tests/fixtures/${DEFAULT_CONTRACT_VERSION}.json`);
const defaultOut = resolve(dashboardRoot, `fixtures/${DEFAULT_CONTRACT_VERSION}.json`);

function usage() {
  return [
    "Usage: node scripts/copy-snapshot-fixture.mjs [snapshot.json] [--out path]",
    "",
    "Copies a pa_feitian_snapshot_v1 or pa_feitian_snapshot_v0 JSON artifact into the dashboard fixture path.",
    "Defaults to the shared contract fixture when no source is supplied.",
  ].join("\n");
}

function resolvePath(value) {
  return resolve(process.cwd(), value);
}

function parseArgs(argv) {
  const args = {
    source: process.env.PA_FEITIAN_SNAPSHOT_SOURCE
      ? resolvePath(process.env.PA_FEITIAN_SNAPSHOT_SOURCE)
      : defaultSource,
    out: process.env.PA_FEITIAN_SNAPSHOT_OUT
      ? resolvePath(process.env.PA_FEITIAN_SNAPSHOT_OUT)
      : defaultOut,
    quiet: false,
  };

  const positionals = [];
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "--help" || arg === "-h") {
      return { ...args, help: true };
    }
    if (arg === "--quiet") {
      args.quiet = true;
      continue;
    }
    if (arg === "--source") {
      const value = argv[index + 1];
      if (!value) {
        throw new Error("--source requires a path");
      }
      args.source = resolvePath(value);
      index += 1;
      continue;
    }
    if (arg === "--out" || arg === "--dest") {
      const value = argv[index + 1];
      if (!value) {
        throw new Error(`${arg} requires a path`);
      }
      args.out = resolvePath(value);
      index += 1;
      continue;
    }
    if (arg.startsWith("-")) {
      throw new Error(`Unknown option: ${arg}`);
    }
    positionals.push(arg);
  }

  if (positionals.length > 1) {
    throw new Error(`Expected at most one source path, received ${positionals.length}`);
  }
  if (positionals.length === 1) {
    args.source = resolvePath(positionals[0]);
  }

  return args;
}

function validateSnapshot(raw, sourcePath) {
  let snapshot;
  try {
    snapshot = JSON.parse(raw);
  } catch (error) {
    throw new Error(`Invalid JSON in ${sourcePath}: ${error.message}`);
  }

  if (!snapshot || !SUPPORTED_CONTRACT_VERSIONS.has(snapshot.schema_version)) {
    throw new Error(
      `Unsupported snapshot contract in ${sourcePath}: ${snapshot?.schema_version ?? "missing"}`,
    );
  }
  if (!Array.isArray(snapshot.signals)) {
    throw new Error(`Snapshot ${sourcePath} must contain a signals array`);
  }

  return snapshot;
}

async function writeIfChanged(outPath, content) {
  try {
    const existing = await readFile(outPath, "utf8");
    if (existing === content) {
      return false;
    }
  } catch (error) {
    if (error.code !== "ENOENT") {
      throw error;
    }
  }

  await mkdir(dirname(outPath), { recursive: true });
  await writeFile(outPath, content, "utf8");
  return true;
}

export async function copySnapshotFixture({ source = defaultSource, out = defaultOut, quiet = false } = {}) {
  const raw = await readFile(source, "utf8");
  const snapshot = validateSnapshot(raw, source);
  const content = raw;
  const changed = await writeIfChanged(out, content);

  if (!quiet) {
    const sourceLabel = relative(process.cwd(), source) || source;
    const outLabel = relative(process.cwd(), out) || out;
    const mode = snapshot.run_config?.mode || "unknown";
    const action = changed ? "copied" : "unchanged";
    console.log(`${action} ${sourceLabel} -> ${outLabel} (${snapshot.signals.length} signals, ${mode})`);
  }

  return { changed, snapshot };
}

if (process.argv[1] && fileURLToPath(import.meta.url) === resolve(process.argv[1])) {
  try {
    const args = parseArgs(process.argv.slice(2));
    if (args.help) {
      console.log(usage());
    } else {
      await copySnapshotFixture(args);
    }
  } catch (error) {
    console.error(error.message);
    console.error("");
    console.error(usage());
    process.exitCode = 1;
  }
}
