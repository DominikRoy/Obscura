"""Reproduce a standalone TA extraction without an earlier measurement database."""

import argparse
import contextlib
import hashlib
import json
from pathlib import Path
import sys
import time

E = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(E))
from camera.input import seal_frame, sensor_pixels
from run import BENCH, Model, Session, SETUP, camera_clock, camera_heap, private_window
from ina_meter import InputRail
from setup_slot import prepare
from camera_accuracy import Reference
from power import frame_energy


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    dealer = sub.add_parser("seal")
    dealer.add_argument("key", type=Path)
    dealer.add_argument("image", type=Path)
    dealer.add_argument("destination", type=Path)
    board = sub.add_parser("run")
    board.add_argument("image", type=Path)
    board.add_argument("destination", type=Path)
    board.add_argument("output", type=Path)
    args = parser.parse_args()
    pixels = sensor_pixels(args.image, 640)
    checksum = hashlib.sha256(pixels).hexdigest()
    path = args.destination
    if args.command == "seal":
        key = args.key.read_bytes()
        box, _ = prepare("A", [0] * 128, key, camera=True)
        path.mkdir(mode=0o700)
        (path / "ta.box").write_bytes(box)
        (path / "camera.box").write_bytes(seal_frame(pixels, box[1:17], key))
        (path / "pixels.sha256").write_text(checksum)
        return
    if checksum != (path / "pixels.sha256").read_text():
        raise ValueError("Linux pixels differ from the dealer frame")
    model = Model(BENCH / "secure_sface/generated")
    reference = Reference(E / "build/plain_sface.so")
    sealed = (path / "camera.box").read_bytes()
    with InputRail() as meter:
        start = time.monotonic()
        vec, _, _ = reference.extract_pixels(pixels)
        end = time.monotonic()
        windows = [("linux", start, end)]
        with contextlib.closing(Session(False)) as session:
            session.call(SETUP, (path / "ta.box").read_bytes())
            bounds, _, _ = camera_clock(session)
            marks = {}
            start = time.monotonic()
            model.extract(session, "A", sealed, None, camera=True, clock=marks)
            timing, private, status = private_window(
                session, bounds, start, marks["embedding_ready"]
            )
            if private is None:
                raise ValueError(status)
            live, peak = camera_heap(session)
            windows.append(("tee", *private))
        result = dict(
            pixels_sha256=checksum,
            coordinates=len(vec),
            ta_timing=timing,
            ta_heap_at_pixels_bytes=live,
            ta_peak_heap_bytes=peak,
        )
        for mode, start, end in windows:
            samples = meter.trace(start, end)
            energy = frame_energy(
                [(t, v * i / 1e6) for t, v, i, _ in samples], start, end, 100
            )
            if energy["energy_status"] != "measured":
                raise ValueError(energy["energy_status"])
            result[mode] = dict(
                ms=(end - start) * 1000,
                energy=energy,
                samples=[[t - start, v, i, d] for t, v, i, d in samples],
            )
    with args.output.open("x") as f:
        json.dump(result, f, indent=2)


if __name__ == "__main__":
    main()
