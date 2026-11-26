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
    if record is None:
        return None
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


def paper_tables(sface, summaries, pairs, topology):
    """Render pooled protocol medians from the audited per-pair rows."""
    if sface["coordinates"] != 128 or sface["ta_peak_heap_bytes"] <= 0:
        raise ValueError("Expected 128 SFace coordinates and measured TA heap")
    lines = [
        "## Full-frame SFace extraction",
        "",
        "| Environment | Window | Time (ms) | Module energy (J) | Peak TA heap (bytes) |",
        "| --- | --- | ---: | ---: | ---: |",
    ]
    for mode, title in (("linux", "Linux CPU"), ("tee", "OP-TEE")):
        observation = sface[mode]
        points = [(t, v * a / 1e6) for t, v, a, _ in observation["samples"]]
        end = observation["ms"] / 1000
        windows = []
        if "stages" in observation:
            prep, net = (observation["stages"][k] for k in ("prepare", "sface"))
            boundary = prep["ms"] / 1000
            if not 0 < boundary < end or not math.isclose(
                prep["ms"] + net["ms"], observation["ms"]
            ):
                raise ValueError("Invalid extraction stage boundaries")
            windows.extend(
                [
                    ("Face preparation", 0, boundary, prep),
                    ("SFace forward", boundary, end, net),
                ]
            )
        windows.append(("Pixels to raw embedding", 0, end, observation))
        for name, a, b, r in windows:
            measured = frame_energy(points, a, b, 100)
            j = measured["module_extraction_j"]
            original = r["energy"]
            if (
                measured["energy_status"] != original["energy_status"]
                or measured["power_samples_in_frame"]
                != original["power_samples_in_frame"]
                or (j is None) != (original["module_extraction_j"] is None)
                or (
                    j is not None
                    and not math.isclose(
                        j, original["module_extraction_j"], rel_tol=1e-7
                    )
                )
            ):
                raise ValueError(f"Inconsistent SFace rail trace for {title}/{name}")
            energy = f"{j:.3f}" if j is not None else measured["energy_status"]
            heap = (
                str(sface["ta_peak_heap_bytes"])
                if mode == "tee" and r is observation
                else "—"
            )
            lines.append(f"| {title} | {name} | {r['ms']:.2f} | {energy} | {heap} |")
    lines += [
        "",
        "One matched image. The TA preparation window ends when the camera command returns to Linux. It includes tensor initialization and command cleanup. The Linux preparation window ends after cropping. Older observations record only the total.",
        "",
        "## Stored-embedding verification",
        "",
        topology,
        "",
        "| Setting | Pairs | Scale | Mask | Drone shares | WD shares | WD round trip | Reconstruct + decide | Total online | mJ per covered pair | Energy coverage |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for mode, title in (
        ("L", "Original Obscura"),
        ("P", "TEE masking"),
        ("R", "TEE masking and reconstruction"),
    ):
        rows = [r for r in pairs if r["mode"] == mode]
        groups = [r for r in summaries if r["setting"] == mode]
        covered = sum(r["pairs_with_batch_energy"] for r in groups)
        joules = sum(
            r["amortized_module_j"] * r["pairs_with_batch_energy"]
            for r in groups
            if r["pairs_with_batch_energy"]
        )
        keys = (
            "scale_ns",
            "mask_ns",
            "drone_shares_ns",
            "peer_shares_ns",
            "roundtrip_ns",
            "reconstruct_decide_ns",
            "online_ns",
        )
        times = " | ".join(f"{st.median(r[k] for r in rows) / 1e6:.3f}" for k in keys)
        energy = f"{joules * 1000 / covered:.2f}" if covered else "unavailable"
        lines.append(
            f"| {title} | {len(rows)} | {times} | {energy} | {covered}/{len(rows)} |"
        )
    lines += [
        "",
        "Stage times are per-pair medians in milliseconds. The WD share time is part of the round trip. Energy is gross VDD_IN input to the metered board, amortized over valid online batches after provisioning.",
        "",
    ]
    return "\n".join(lines)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("db", type=Path)
    p.add_argument("csv", type=Path)
    p.add_argument("--partial", action="store_true")
    p.add_argument(
        "--per-pair", type=Path, help="Export audited individual timings to CSV"
    )
    p.add_argument(
        "--tables",
        type=Path,
        nargs=2,
        metavar=("SFACE_JSON", "OUTPUT_MD"),
        help="Generate the SFace and protocol tables from a complete hardware run",
    )
    args = p.parse_args()
    if args.tables and args.partial:
        p.error("--tables requires a complete hardware run")
    summaries, seen = [], set()
    per_pair = []
    with sqlite3.connect(args.db.resolve().as_uri() + "?mode=ro", uri=True) as db:
        topology = "One-board TNO loopback. Both roles share the metered Jetson."
        if db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='run_info'"
        ).fetchone():
            _, backend, *transport = json.loads(
                db.execute("SELECT settings FROM run_info WHERE id=1").fetchone()[0]
            )
            if args.tables and backend != "hardware":
                p.error("Hardware paper tables require a TA and a drone rail trace")
            topology = "Separate drone and WD processes using the two-board driver. VDD_IN covers the drone only. The round trip includes the configured transport and remote WD processing."
            if transport:
                topology += " Transport: direct TNO HTTP on the LAN."
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
                        if args.per_pair or args.tables:
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
    if args.tables:
        source, output = args.tables
        output.write_text(
            paper_tables(json.loads(source.read_text()), summaries, per_pair, topology)
        )
    if args.per_pair and per_pair:
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
