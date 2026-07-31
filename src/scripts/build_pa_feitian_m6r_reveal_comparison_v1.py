#!/usr/bin/env python3
import argparse
import base64
import hashlib
import json
import re
from pathlib import Path


def sha(path): return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--decoded-reveal", type=Path, required=True)
    ap.add_argument("--sealed-reveal", type=Path, required=True)
    ap.add_argument("--blind-pack", type=Path, required=True)
    ap.add_argument("--blind-annotations", type=Path, required=True)
    ap.add_argument("--contract", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    a=ap.parse_args()
    reveal=json.loads(a.decoded_reveal.read_text()); sealed=json.loads(a.sealed_reveal.read_text())
    pack=json.loads(a.blind_pack.read_text()); ann=json.loads(a.blind_annotations.read_text()); c=json.loads(a.contract.read_text())
    if sha(a.blind_annotations) != c["blind_annotations_sha256"] or sha(a.blind_pack) != c["blind_pack_sha256"]: raise ValueError("frozen blind hash drift")
    if sha(a.sealed_reveal) != c["sealed_reveal_artifact_sha256"] or sealed.get("payload_sha256") != c["sealed_reveal_payload_sha256"]: raise ValueError("sealed hash drift")
    raw_payload = base64.b64decode(sealed["payload_base64"])
    if "sha256:" + hashlib.sha256(raw_payload).hexdigest() != sealed["payload_sha256"]: raise ValueError("sealed payload bytes hash drift")
    if json.loads(raw_payload) != reveal: raise ValueError("decoded reveal does not match sealed payload")
    if len(ann.get("annotations", [])) != 72 or len(pack.get("episodes", [])) != 72 or len(reveal.get("episodes", [])) != 72: raise ValueError("episode count drift")
    if [x["episode_id"] for x in ann["annotations"]] != [x["episode_id"] for x in pack["episodes"]] or [x["episode_id"] for x in pack["episodes"]] != [x["episode_id"] for x in reveal["episodes"]]: raise ValueError("episode ID order drift")
    closes={e["episode_id"]:e["bars"][-1]["close_index"] for e in pack["episodes"]}
    rows=[]
    for index in range(72):
        item, ep = ann["annotations"][index], reveal["episodes"][index]
        text=item["annotation"]; anchor=closes[ep["episode_id"]]; future=ep["future_bars"]
        context=re.search(r"Context: ([^.]+)",text).group(1)
        turns=int(re.search(r"contains (\d+) visible local turns",text).group(1))
        rang=re.search(r"Range behavior: ([^.]+)",text).group(1)
        shape=re.search(r"Decision-bar shape: ([^.]+)",text).group(1)
        by={x["bar_offset"]:x for x in future}
        horizons={str(h):{"close_change_pct":round((by[h]["close_index"]/anchor-1)*100,6),"future_high_change_pct":round(max(x["high_index"] for x in future if x["bar_offset"]<=h)/anchor*100-100,6),"future_low_change_pct":round(min(x["low_index"] for x in future if x["bar_offset"]<=h)/anchor*100-100,6)} for h in c["fixed_horizons"]}
        rows.append({"episode_id":ep["episode_id"],"context":context,"local_turn_count":turns,"range_behavior":rang,"bar_0_shape":shape,"sampling_role":ep["provenance"]["sampling_role"],"instrument_family":ep["provenance"]["instrument_family"],"frozen_era":ep["provenance"]["anchor_stratum"],"horizons":horizons})
    out={"schema_version":"pa_feitian_m6r_reveal_comparison_v1","contract_schema_version":c["schema_version"],"blind_annotations_sha256":c["blind_annotations_sha256"],"blind_pack_sha256":c["blind_pack_sha256"],"sealed_reveal_artifact_sha256":c["sealed_reveal_artifact_sha256"],"sealed_reveal_payload_sha256":c["sealed_reveal_payload_sha256"],"episode_count":len(rows),"verdict":"no_candidate","candidate_count":0,"horizons":c["fixed_horizons"],"rows":rows}
    out["aggregates"]={"sampling_role":{},"instrument_family":{},"frozen_era":{},"descriptor_distribution":{}}
    for row in rows:
        for key in ("sampling_role","instrument_family","frozen_era"):
            out["aggregates"][key][row[key]]=out["aggregates"][key].get(row[key],0)+1
        for key in ("context","range_behavior","bar_0_shape"):
            out["aggregates"]["descriptor_distribution"][key]=out["aggregates"]["descriptor_distribution"].get(key,{})
            out["aggregates"]["descriptor_distribution"][key][row[key]]=out["aggregates"]["descriptor_distribution"][key].get(row[key],0)+1
    out["aggregates"]["role_descriptor_response"] = {}
    for row in rows:
        for descriptor in ("context", "range_behavior", "bar_0_shape"):
            category = row[descriptor]
            bucket = out["aggregates"]["role_descriptor_response"].setdefault(descriptor, {}).setdefault(category, {}).setdefault(row["sampling_role"], {"n": 0, "families": {}, "eras": {}, "horizons": {}})
            bucket["n"] += 1
            bucket["families"][row["instrument_family"]] = bucket["families"].get(row["instrument_family"], 0) + 1
            bucket["eras"][row["frozen_era"]] = bucket["eras"].get(row["frozen_era"], 0) + 1
            for h, metrics in row["horizons"].items():
                q = bucket["horizons"].setdefault(h, {m: [] for m in ("close_change_pct", "future_high_change_pct", "future_low_change_pct")})
                for m, value in metrics.items(): q[m].append(value)
    for groups in out["aggregates"]["role_descriptor_response"].values():
        for roles in groups.values():
            for bucket in roles.values():
                for h, metrics in bucket["horizons"].items():
                    for m, values in metrics.items():
                        values.sort()
                        middle = len(values) // 2
                        median = (values[middle] + values[middle - 1]) / 2 if values and len(values) % 2 == 0 else (values[middle] if values else None)
                        bucket["horizons"][h][m] = {"positive": sum(v > 0 for v in values), "negative": sum(v < 0 for v in values), "zero": sum(v == 0 for v in values), "median": median, "min": min(values) if values else None, "max": max(values) if values else None}
    audit = []
    categories = [("context", row["context"]) for row in rows] + [("range_behavior", row["range_behavior"]) for row in rows] + [("bar_0_shape", row["bar_0_shape"]) for row in rows] + [("local_turn_count", row["local_turn_count"]) for row in rows]
    for descriptor, value in sorted(set(categories), key=lambda x: (x[0], str(x[1]))):
        group = [row for row in rows if row[descriptor] == value]
        families = sorted({row["instrument_family"] for row in group})
        eras = sorted({row["frozen_era"] for row in group})
        horizon_values = [row["horizons"]["20"]["close_change_pct"] for row in group]
        audit.append({"descriptor": descriptor, "value": value, "n": len(group), "instrument_families": families, "frozen_eras": eras, "structural_floor_pass": len(group) >= c["candidate_floor"]["minimum_episodes"] and len(families) >= c["candidate_floor"]["minimum_instrument_families"] and len(eras) >= c["candidate_floor"]["minimum_frozen_eras"], "horizon_20_min_id": min(group, key=lambda row: row["horizons"]["20"]["close_change_pct"])["episode_id"], "horizon_20_max_id": max(group, key=lambda row: row["horizons"]["20"]["close_change_pct"])["episode_id"], "horizon_20_min": min(horizon_values), "horizon_20_max": max(horizon_values)})
    passing = [item for item in audit if item["structural_floor_pass"]]
    mixed_sign = [item for item in passing if item["horizon_20_min"] < 0 < item["horizon_20_max"]]
    out["candidate_floor_audit"] = {"category_count": len(audit), "structural_floor_pass_count": len(passing), "mixed_sign_horizon_20_count": len(mixed_sign), "minimum_episodes": c["candidate_floor"]["minimum_episodes"], "minimum_instrument_families": c["candidate_floor"]["minimum_instrument_families"], "minimum_frozen_eras": c["candidate_floor"]["minimum_frozen_eras"], "categories": audit, "selected_candidates": [], "verdict": "no_candidate"}
    a.output.write_text(json.dumps(out,indent=2)+"\n")
if __name__=="__main__": main()
