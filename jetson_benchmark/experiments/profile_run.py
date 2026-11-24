"""Time host-visible operations in one experiment child process, in nanoseconds."""

import argparse
import asyncio
import json
import time
from pathlib import Path
from unittest.mock import patch

import run as bench

LABELS = {
    bench.BEGIN: "input",
    bench.STEP: "weight_and_kernel",
    bench.BLIND: "gpu_blind",
    bench.ACCEPT: "gpu_verify_unblind",
    bench.CONTROL: "quantized_cpu_control",
    bench.FINISH: "finish",
    bench.DECIDE: "tee_scalar_check",
}


def main():
    parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    parser.add_argument("--output", type=Path, required=True)
    args, _ = parser.parse_known_args()
    totals, counts = {}, {}
    call, cuda = bench.Session.call, bench.cuda_worker
    begin = None

    def record(label, start, end):
        totals[label] = totals.get(label, 0) + end - start
        counts[label] = counts.get(label, 0) + 1

    def timed_call(session, cmd, *args, **kwargs):
        nonlocal begin
        start = time.perf_counter_ns()
        if cmd == bench.BEGIN:
            begin = start
        result = call(session, cmd, *args, **kwargs)
        end = time.perf_counter_ns()
        if cmd in LABELS:
            record(LABELS[cmd], start, end)
        if cmd == bench.FINISH:
            record("begin_through_embedding", begin, start)
        return result

    def timed_cuda():
        worker = cuda()

        def timed(weights, blinded):
            start = time.perf_counter_ns()
            result = worker(weights, blinded)
            record("cuda_worker", start, time.perf_counter_ns())
            return result

        return timed

    with (
        patch.object(bench.Session, "call", timed_call),
        patch.object(bench, "cuda_worker", timed_cuda),
    ):
        asyncio.run(bench.main())
    (args.output / "op-times.json").write_text(
        json.dumps({"ns": totals, "calls": counts}, indent=2)
    )


if __name__ == "__main__":
    main()
