"""Verify full-split coverage, decisions and power integrals from the saved waveforms."""

import argparse
from collections import Counter, defaultdict
import json
import math
from pathlib import Path
import sqlite3
import statistics
import zlib

import numpy as np

from full_pairs_dealer import MODES, SPLITS, pair_rows


def integrate_trace(raw, lo, hi):
    t, mv, ma, spans = np.array(raw, dtype=np.float64).T
    p = mv * ma / 1e6
    if (
        not np.isfinite([t, mv, ma, spans]).all()
        or not (np.diff(t) > 0).all()
        or not (p > 0).all()
        or not ((spans >= 0) & (spans <= 0.020)).all()
        or not t[0] <= lo < hi <= t[-1]
    ):
        raise ValueError("Invalid trace values or endpoint coverage")
    inside = t[(t >= lo) & (t <= hi)]
    left = np.searchsorted(t, lo, side="right") - 1
    right = np.searchsorted(t, hi)
    if len(inside) < 3 or max(np.diff(t[left : right + 1])) > 0.300000001:
        raise ValueError("Sparse trace")
    cuts = np.r_[lo, t[(t > lo) & (t < hi)], hi]
    return float(np.trapz(np.interp(cuts, t, p), cuts)), len(inside)


def audit(directory, require_complete):
    expected = {k: pair_rows(k) for k in SPLITS}
    seen = defaultdict(dict)
    groups = defaultdict(list)
    rejected = Counter()
    state_count = Counter()
    largest_error = 0
    db = sqlite3.connect(
        (directory / "attempts.sqlite").resolve().as_uri() + "?mode=ro", uri=True
    )
    try:
        for split, n, mode, state, encoded, trace in db.execute(
            "SELECT split,row_no,mode,state,summary,power FROM attempts"
        ):
            state_count[state] += 1
            if state == "started":
                continue
            row = json.loads(encoded)
            if state == "invalid":
                rejected[
                    (row["private_energy_status"], row["frame_energy_status"])
                ] += 1
                continue
            if (
                state != "valid"
                or mode not in MODES
                or not 1 <= n <= len(expected[split])
            ):
                raise ValueError("Unexpected row key")
            if expected[split][n - 1] != [
                str(row["label"]),
                row["gallery"],
                row["probe"],
            ]:
                raise ValueError("Pair manifest mismatch")
            if not (
                0
                < row["ta_heap_at_private_pixels_bytes"]
                <= row["ta_heap_private_window_peak_bytes"]
                <= 12 * 1024**2
            ):
                raise ValueError("Invalid TA heap")
            if (
                row["decision"] not in (0, 1)
                or row["private_energy_status"] != "measured"
                or row["frame_energy_status"] != "measured"
            ):
                raise ValueError("Unexpected result")
            key = (split, n)
            if mode in seen[key] or (
                seen[key] and next(iter(seen[key].values())) != row["decision"]
            ):
                raise ValueError("Duplicate setting or decisions disagree")
            seen[key][mode] = row["decision"]
            raw = json.loads(zlib.decompress(trace))
            lo, hi = (
                row["private_pixels_from_frame_s"],
                row["private_embedding_from_frame_s"],
            )
            if not math.isclose(
                (hi - lo) * 1000, row["private_pixels_to_embedding_ms"], abs_tol=0.001
            ):
                raise ValueError("TA timing disagrees with mapped duration")
            for a, b, field, samples in [
                (lo, hi, "module_private_pixels_to_embedding_j", "private_samples"),
                (
                    0,
                    row["frame_to_decision_ms"] / 1000,
                    "module_frame_to_decision_j",
                    "frame_samples",
                ),
            ]:
                joules, count = integrate_trace(raw, a, b)
                error = abs(joules - row[field])
                if error > 1e-6 or count != row[samples]:
                    raise ValueError(f"Integration mismatch at {split}/{n}/{mode}")
                largest_error = max(largest_error, error)
            groups[split, row["setting"]].append(row)
    finally:
        db.close()
    total = sum(len(rows) * 4 for rows in expected.values())
    missing = total - state_count["valid"]
    if require_complete and missing:
        raise ValueError(f"{missing} missing pair-setting rows")
    report = {
        "expected": total,
        "missing": missing,
        "attempt_counts": dict(state_count),
        "max_integral_disagreement_j": largest_error,
        "rejected_attempt_reasons": [
            dict(private=p, frame=f, count=c) for (p, f), c in rejected.items()
        ],
        "splits": {},
    }
    for (split, setting), rows in sorted(groups.items()):
        result = {
            "pairs": len(rows),
            "correct": sum(r["decision"] == r["label"] for r in rows),
        }
        for col in [
            "private_pixels_to_embedding_ms",
            "module_private_pixels_to_embedding_j",
            "frame_to_decision_ms",
            "module_frame_to_decision_j",
            "ta_heap_private_window_peak_bytes",
        ]:
            vals = [r[col] for r in rows]
            result[col] = {
                "mean": statistics.mean(vals),
                "median": statistics.median(vals),
                "min": min(vals),
                "max": max(vals),
            }
        report["splits"].setdefault(split, {})[setting] = result
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("directory", type=Path)
    p.add_argument("--allow-partial", action="store_true")
    p.add_argument("--report", type=Path)
    a = p.parse_args()
    report = audit(a.directory, not a.allow_partial)
    if a.report:
        a.report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "splits"}, indent=2))
