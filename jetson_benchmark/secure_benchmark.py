"""Benchmark real secure-world SFace inference plus encoding and masking."""
import argparse
import csv
import json
import time
from pathlib import Path

import numpy as np

from benchmark import device_info
from power import Tegrastats
from secure_sface.client import ROOT, SecureSFace


def run_secure_benchmark(image, *, output, generated=ROOT / "generated",
                         library=ROOT / "host/libsecure_sface.so", iterations=10,
                         seconds=30.0, warmup=2, power=True, rail="VDD_IN",
                         tegrastats="tegrastats", interval_ms=100, notes=""):
    if iterations < 1 or warmup < 0 or not np.isfinite(seconds) or seconds < 0:
        raise ValueError("iterations >= 1, warmup >= 0 and finite seconds >= 0 required")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    monitor = Tegrastats(tegrastats, rail, interval_ms) if power else None
    rows = []
    with SecureSFace(image, generated=generated, library=library) as session:
        for _ in range(warmup):
            session.run()
        try:
            if monitor:
                monitor.start()
            start = time.perf_counter()
            while len(rows) < iterations or time.perf_counter() - start < seconds:
                before = time.perf_counter()
                masked, metrics = session.run()
                row = {"pipeline_ms": (time.perf_counter() - before) * 1000,
                       **{"ta_" + k: v for k, v in metrics.items()}}
                rows.append(row)
            end = time.perf_counter()
            if monitor:
                monitor.wait_until(end)
        finally:
            if monitor:
                monitor.stop()
        metadata = session.metadata
    energy = monitor.summary(start, end, len(rows)) if monitor else None
    timings = {}
    for key in rows[0]:
        values = np.asarray([row[key] for row in rows])
        timings[key] = {"mean": float(values.mean()), "median": float(np.median(values)),
                        "p95": float(np.percentile(values, 95)), "min": float(values.min())}
    summary = {"mode": "secure_sface_inference_and_masking", "inference_inside_tee": True,
               "encoding_inside_tee": True, "masking_inside_tee": True,
               "secure_camera_path": False, "iterations": len(rows), "warmup": warmup,
               "wall_seconds": end - start, "timings_ms": timings, "power": energy,
               "energy_status": "measured" if power else "disabled; no energy result",
               "device": device_info(), "source": metadata, "notes": notes,
               "measurement_scope": "Repeated secure SFace + encoding + masking, including streamed weights, hashing, transitions and clearing; excludes file loading, alignment and session open",
               "ta_timing_note": "TEE_GetSystemTime millisecond counters; sums of short intervals are coarse. Zero does not mean zero cost. pipeline_ms uses host monotonic high-resolution clock."}
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    with (output / "timings.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    packet = {"format": "obscura-masked-v1", "dimension": 128, "ring_bits": 64, "scale": 256,
              "mask_backend": "optee_secure_sface", "model_sha256": metadata["model_sha256"],
              "values": [str(v) for v in masked]}
    (output / "masked_embedding.json").write_text(json.dumps(packet, indent=2) + "\n")
    if monitor:
        with (output / "power.csv").open("w", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(["seconds_from_window_start", "watts"])
            writer.writerows((t - start, watts) for t, watts in monitor.samples)
        (output / "tegrastats.log").write_text("\n".join(f"{t - start:.9f} {line}" for t, line in monitor.lines) + "\n")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True, type=Path, help="Already aligned 112x112 face crop")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--generated", type=Path, default=ROOT / "generated")
    parser.add_argument("--library", type=Path, default=ROOT / "host/libsecure_sface.so")
    parser.add_argument("--iterations", type=int, default=10)
    parser.add_argument("--seconds", type=float, default=30)
    parser.add_argument("--warmup", type=int, default=2)
    parser.add_argument("--rail", default="VDD_IN")
    parser.add_argument("--tegrastats", default="tegrastats")
    parser.add_argument("--interval-ms", type=int, default=100)
    parser.add_argument("--no-power", action="store_true")
    parser.add_argument("--notes", default="")
    args = vars(parser.parse_args())
    args["power"] = not args.pop("no_power")
    print(json.dumps(run_secure_benchmark(**args), indent=2))
