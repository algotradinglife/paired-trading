import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const dir = dirname(fileURLToPath(import.meta.url));
const packPath = join(dir, "blind_episode_pack_v1.json");
const templatePath = join(dir, "blind_annotation_template_v1.json");
const annotationsPath = join(dir, "blind_annotations_v1.json");
const pack = JSON.parse(readFileSync(packPath, "utf8"));
const template = JSON.parse(readFileSync(templatePath, "utf8"));
const annotations = JSON.parse(readFileSync(annotationsPath, "utf8"));
const packHash = `sha256:${createHash("sha256").update(readFileSync(packPath)).digest("hex")}`;

const expectedIds = pack.episodes.map((episode) => episode.episode_id);
const forbiddenKeys = new Set(["provenance", "calendar", "date", "contract", "future", "path", "family", "exchange", "product", "activity", "control", "role", "source", "identity", "reveal", "outcome", "return", "pnl", "ev", "win_rate", "confidence", "entry", "stop", "option"]);

const mean = (values) => values.reduce((sum, value) => sum + value, 0) / values.length;
const median = (values) => {
  const sorted = [...values].sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
};
function descriptors(episode) {
  const closes = episode.bars.map((bar) => bar.close_index);
  const highs = episode.bars.map((bar) => bar.high_index);
  const lows = episode.bars.map((bar) => bar.low_index);
  const scale = median(closes);
  const drift = closes.at(-1) - closes[0];
  const context = drift > 0.012 * scale ? "a rising close sequence across the window" :
    drift < -0.012 * scale ? "a falling close sequence across the window" :
    "a mixed close sequence with no dominant net drift";
  let turns = 0;
  for (let index = 1; index < closes.length - 1; index += 1) {
    if ((closes[index] - closes[index - 1]) * (closes[index + 1] - closes[index]) < 0) turns += 1;
  }
  const ranges = highs.map((high, index) => high - lows[index]);
  const ratio = mean(ranges.slice(-5)) / median(ranges.slice(-15, -5));
  const range = ratio > 1.25 ? "recent candle ranges expand relative to the preceding local range" :
    ratio < 0.8 ? "recent candle ranges narrow relative to the preceding local range" :
    "recent candle ranges remain comparable to the preceding local range";
  const recentHigh = Math.max(...highs.slice(-6, -1));
  const recentLow = Math.min(...lows.slice(-6, -1));
  const high0 = highs.at(-1);
  const low0 = lows.at(-1);
  const close0 = closes.at(-1);
  const shape = high0 > recentHigh ? (close0 <= recentHigh ? "bar 0 probes above the recent upper boundary but closes back within it" : "bar 0 closes above the recent upper boundary") :
    low0 < recentLow ? (close0 >= recentLow ? "bar 0 probes below the recent lower boundary but closes back within it" : "bar 0 closes below the recent lower boundary") :
    ((close0 - recentLow) / (recentHigh - recentLow || 1)) > 2 / 3 ? "bar 0 closes near the recent upper third" :
    ((close0 - recentLow) / (recentHigh - recentLow || 1)) < 1 / 3 ? "bar 0 closes near the recent lower third" :
    "bar 0 closes within the recent middle third";
  return { context, turns: `the close sequence contains ${turns} visible local turns`, range, shape };
}

function validate(candidate) {
  if (candidate.schema_version !== template.schema_version) throw new Error("annotation schema drift");
  if (Object.keys(candidate).sort().join(",") !== "annotations,blind_pack_sha256,schema_version") throw new Error("annotation top-level fields drifted");
  if (candidate.blind_pack_sha256 !== packHash) throw new Error("blind pack hash mismatch");
  if (pack.episode_count !== 72 || pack.episodes.length !== 72) throw new Error("blind pack count drift");
  if (!Array.isArray(candidate.annotations) || candidate.annotations.length !== 72) throw new Error("annotation count drift");
  const seen = new Set();
  candidate.annotations.forEach((item, index) => {
    if (Object.keys(item).sort().join(",") !== "annotation,episode_id") throw new Error("annotation fields expose extra information");
    if (item.episode_id !== expectedIds[index] || seen.has(item.episode_id)) throw new Error("episode id order/set drift");
    if (typeof item.annotation !== "string" || item.annotation.trim().length < 40) throw new Error("empty annotation");
    const lower = item.annotation.toLowerCase();
    for (const key of forbiddenKeys) if (new RegExp(`\\b${key}\\b`).test(lower)) throw new Error(`forbidden annotation token: ${key}`);
    const expected = descriptors(pack.episodes[index]);
    for (const [family, fragment] of Object.entries(expected)) if (!item.annotation.includes(fragment)) throw new Error(`${family} descriptor drift`);
    seen.add(item.episode_id);
  });
  if (seen.size !== 72) throw new Error("not every episode annotated exactly once");
  return seen.size;
}

const count = validate(annotations);
if (process.argv.includes("--negative-tests")) {
  const expectReject = (label, mutation) => {
    const candidate = structuredClone(annotations);
    mutation(candidate);
    try { validate(candidate); throw new Error(`${label} mutation was accepted`); } catch (error) {
      if (error.message === `${label} mutation was accepted`) throw error;
    }
  };
  expectReject("top-level", (value) => { value.identity = "unknown"; });
  expectReject("item-fields", (value) => { value.annotations[0].family = "unknown"; });
  expectReject("id-order", (value) => { [value.annotations[0], value.annotations[1]] = [value.annotations[1], value.annotations[0]]; });
  expectReject("provenance-text", (value) => { value.annotations[0].annotation += " provenance"; });
  expectReject("outcome-text", (value) => { value.annotations[0].annotation += " outcome"; });
  expectReject("context-semantic", (value) => { value.annotations[0].annotation = value.annotations[0].annotation.replace(/a mixed close sequence with no dominant net drift/, "a rising close sequence across the window"); });
  expectReject("turn-semantic", (value) => { value.annotations[0].annotation = value.annotations[0].annotation.replace(/contains \d+ visible local turns/, "contains 0 visible local turns"); });
  expectReject("range-semantic", (value) => { value.annotations[0].annotation = value.annotations[0].annotation.replace(descriptors(pack.episodes[0]).range, "recent candle ranges narrow relative to the preceding local range"); });
  expectReject("shape-semantic", (value) => { value.annotations[0].annotation = value.annotations[0].annotation.replace(/bar 0 closes within the recent middle third/, "bar 0 closes within the recent upper third"); });
}
console.log(JSON.stringify({ ok: true, episodes: count, blind_pack_sha256: packHash, negative_tests: process.argv.includes("--negative-tests") }));
