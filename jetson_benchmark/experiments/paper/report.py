"""Independently check split coverage, decisions, timer sums and recorded rail energy."""

import argparse
import csv
import json
import math
import sqlite3
from pathlib import Path
import statistics as st
import sys

from material import ROOT, E, SPLITS, batches, pair_rows

sys.path.insert(0, str(E.parent))
from A.oracle import decision, encode
from power import frame_energy

STAGES = (
    "scale_ns",
    "mask_ns",
    "drone_shares_ns",
    "roundtrip_ns",
    "reconstruct_decide_ns",
)


def check_energy(record):
    points = [(s, v * a / 1e6) for s, v, a, _ in record["samples"]]
    checked = frame_energy(points, 0, record["elapsed_s"], 100)
    j = checked["module_extraction_j"]
    if (
        checked["energy_status"] != record["energy_status"]
        or checked["power_samples_in_frame"] != record["power_samples_in_frame"]
        or (j is None) != (record["module_extraction_j"] is None)
        or (
            j is not None
            and not math.isclose(j, record["module_extraction_j"], rel_tol=1e-7)
        )
    ):
        raise ValueError("Power trace disagrees with reported integral")
    return j


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("db", type=Path)
    p.add_argument("csv", type=Path)
    p.add_argument("--partial", action="store_true")
    p.add_argument(
        "--per-pair", type=Path, help="Export audited individual timings to CSV"
    )
    args = p.parse_args()
    summaries, seen = [], set()
    per_pair = []
    with sqlite3.connect(args.db.resolve().as_uri() + "?mode=ro", uri=True) as db:
        for split, (_, bankfile, profile, target) in SPLITS.items():
            pairs = pair_rows(split)
            bank = json.loads((ROOT / "data" / bankfile).read_text())
            for mode in "LPR":
                by_id, measured, joules, setup = {}, 0, 0.0, []
                valid_groups = invalid_groups = 0
                for first, ms, data, power in db.execute(
                    "select first,setup_ms,rows,energy from results where split=? and mode=? order by first",
                    (split, mode),
                ):
                    rows = json.loads(data)
                    group = next(g for g in batches(target) if g.start == first)
                    if [r["number"] for r in rows] != list(group):
                        raise ValueError("Wrong group membership")
                    for r in rows:
                        index = r["number"]
                        label, ref, probe = pairs[index - 1]
                        if (
                            r["mode"] != mode
                            or r["probe"] != probe
                            or int(label) != r["label"]
                            or index in by_id
                            or r["slot"] in seen
                            or r["decision"]
                            != decision(encode(bank[ref]), encode(bank[probe]), profile)
                        ):
                            raise ValueError(f"Bad outcome at {split}/{mode}/{index}")
                        seen.add(r["slot"])
                        if sum(r[k] for k in STAGES) != r["online_ns"] or any(
                            r[k] <= 0 for k in STAGES
                        ):
                            raise ValueError("Timer partition failed")
                        by_id[index] = r
                        if args.per_pair:
                            per_pair.append(dict(split=split, reference=ref, **r))
                    setup.append(ms)
                    energy = check_energy(json.loads(power))
                    if energy is None:
                        invalid_groups += 1
                    else:
                        valid_groups += 1
                        joules += energy
                        measured += len(rows)
                if not args.partial and set(by_id) != set(range(1, target + 1)):
                    raise ValueError(
                        f"Incomplete {split}/{mode} ({len(by_id)}/{target})"
                    )
                if not by_id:
                    continue
                rec = dict(
                    split=split,
                    setting=mode,
                    pairs=len(by_id),
                    correct=sum(r["decision"] == r["label"] for r in by_id.values()),
                    pairs_with_batch_energy=measured,
                    valid_energy_groups=valid_groups,
                    invalid_energy_groups=invalid_groups,
                    amortized_module_j=joules / measured if measured else None,
                    median_session_group_setup_ms=st.median(setup),
                )
                for k in (*STAGES, "peer_shares_ns", "online_ns"):
                    v = [r[k] / 1e6 for r in by_id.values()]
                    rec[k[:-3] + "_median_ms"] = st.median(v)
                    rec[k[:-3] + "_mean_ms"] = st.mean(v)
                summaries.append(rec)
    if summaries:
        with args.csv.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(summaries[0]))
            w.writeheader()
            w.writerows(summaries)
    if per_pair:
        with args.per_pair.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(per_pair[0]))
            writer.writeheader()
            writer.writerows(per_pair)
    print(
        sum(s["pairs"] for s in summaries),
        "distinct verified rows;",
        sum(s["pairs_with_batch_energy"] for s in summaries),
        "with batch energy",
    )


if __name__ == "__main__":
    main()
