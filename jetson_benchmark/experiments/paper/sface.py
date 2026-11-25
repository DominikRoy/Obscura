"""One matched Linux full-frame SFace observation and its existing real TA counterpart."""

import argparse
import hashlib
import json
import sqlite3
import sys
import time
import zlib
from pathlib import Path

E = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(E))
sys.path.insert(0, str(E.parent))
from camera_accuracy import Reference
from camera.input import sensor_pixels
from ina_meter import InputRail
from power import frame_energy


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("database", type=Path)
    p.add_argument("output", type=Path)
    args = p.parse_args()
    with sqlite3.connect(args.database.resolve().as_uri() + "?mode=ro", uri=True) as db:
        slot, record, trace = db.execute(
            "select slot,summary,power from attempts where split='lfw1' and row_no=1 "
            "and mode='A' and state='valid' order by rowid limit 1"
        ).fetchone()
    prior = json.loads(record)
    image = E.parents[1] / "ppface" / prior["probe"][3:]
    pixels = sensor_pixels(image, 640)
    model = Reference(E / "build/plain_sface.so")
    with InputRail() as meter:
        start = time.monotonic()
        vector, faces, eyes = model.extract_pixels(pixels)
        end = time.monotonic()
        samples = meter.trace(start, end)
    energy = frame_energy([(t, v * i / 1e6) for t, v, i, _ in samples], start, end, 100)
    result = dict(
        probe=prior["probe"],
        pixels_sha256=hashlib.sha256(pixels).hexdigest(),
        linux=dict(
            ms=(end - start) * 1000,
            energy=energy,
            coords=len(vector),
            detector=faces,
            eyes=eyes,
            samples=[[t - start, v, i, d] for t, v, i, d in samples],
        ),
        tee=dict(slot=slot, timing=prior, samples=json.loads(zlib.decompress(trace))),
    )
    with args.output.open("x") as f:
        json.dump(result, f, indent=2)
    print(
        result["probe"],
        result["linux"]["ms"],
        energy,
        prior["private_pixels_to_embedding_ms"],
    )


if __name__ == "__main__":
    main()
