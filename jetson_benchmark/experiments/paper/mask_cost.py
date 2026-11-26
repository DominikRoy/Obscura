"""Calibrate 128-coordinate ring addition on public synthetic inputs."""

import argparse
import contextlib
import json
from pathlib import Path
import struct
import time

from compare import InputRail, MASK_BENCH, Session, rail_record
from common.constants import SEMI_HONEST_MODULO
from common.helper import vec_add


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    rows = []
    with InputRail() as meter, contextlib.closing(Session(False)) as session:
        for mode in ("linux", "tee", "tee", "linux", "linux", "tee"):
            count = ta_ms = 0
            y, delta = [0] * 128, list(range(1, 129))
            start = time.monotonic()
            while time.monotonic() - start < 2:
                if mode == "tee":
                    ms, check = struct.unpack(
                        "<2Q", session.call(MASK_BENCH, out_len=16)
                    )
                    if check != 128_000_000 or not ms:
                        raise ValueError("Mask calibration failed")
                    count += 1_000_000
                    ta_ms += ms
                else:
                    for _ in range(256):
                        y = vec_add(y, delta, SEMI_HONEST_MODULO)
                    count += 256
            end = time.monotonic()
            if mode == "linux" and y[-1] != count * 128:
                raise ValueError("Linux mask calibration failed")
            energy = rail_record(meter, start, end)
            if energy["energy_status"] != "measured":
                raise ValueError(energy["energy_status"])
            rows.append(
                dict(
                    mode=mode,
                    calls=count,
                    ta_ms=ta_ms if mode == "tee" else None,
                    energy=energy,
                )
            )
    with args.output.open("x") as f:
        json.dump(rows, f, indent=2)


if __name__ == "__main__":
    main()
