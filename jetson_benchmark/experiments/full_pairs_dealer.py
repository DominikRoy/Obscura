"""Prepare sealed frames and independent verification slots for the full loopback study."""

import argparse
import json
import os
import sqlite3
import tempfile
from pathlib import Path

from A.oracle import ROOT, encode
from camera.input import seal_frame, sensor_pixels
from setup_slot import prepare

SPLITS = {
    "lfw1": ("veri_test1.txt", "new_emb1.txt", "lfw", 1000),
    "drone9": (
        "veri_balanced_cosine9sface.txt",
        "embeddings_droneface_raw_sface9.txt",
        "droneface",
        2728,
    ),
    "drone11": (
        "veri_balanced_cosine11sface.txt",
        "embeddings_droneface_raw_sface11.txt",
        "droneface",
        1364,
    ),
}
MODES = ("A", "H", "T", "B")
SHARD_SIZE = 25


def pair_rows(dataset):
    pair_file, _, _, expected = SPLITS[dataset]
    rows = [
        line.split()[:3]
        for line in (ROOT / "data" / pair_file).read_text().splitlines()
    ]
    if len(rows) != expected or any(
        label not in ("0", "1") or not probe.startswith("../")
        for label, _, probe in rows
    ):
        raise ValueError(f"Unexpected input in {pair_file}")
    return rows


def build_shard(
    destination, dataset, first, rows, bank, key, images, attempts, only=None
):
    # Publish a whole read-only shard by atomic rename; partial shards are never scheduled.
    fd, tmp = tempfile.mkstemp(prefix=".preparing-", dir=destination.parent)
    os.close(fd)
    try:
        db = sqlite3.connect(tmp)
        try:
            db.execute("""CREATE TABLE material(row_no INTEGER, mode TEXT, attempt INTEGER,
                label INTEGER, gallery TEXT, probe TEXT, box BLOB, frame BLOB, role0 TEXT, role1 TEXT,
                PRIMARY KEY(row_no,mode,attempt))""")
            for number, (label, gallery, probe) in enumerate(rows, first):
                if only is not None and number not in only:
                    continue
                path = (images / probe[3:]).resolve()
                path.relative_to(images)
                pixels = sensor_pixels(path, 640)
                x = encode(bank[gallery])
                for mode in MODES:
                    if only is not None and mode not in only[number]:
                        continue
                    for attempt in range(attempts):
                        box, roles = prepare(
                            mode, x, key, SPLITS[dataset][2], camera=True
                        )
                        sealed = seal_frame(pixels, box[1:17], key)
                        role0, role1 = (
                            [json.dumps(r, separators=(",", ":")) for r in roles]
                            if roles
                            else (None, None)
                        )
                        db.execute(
                            "INSERT INTO material VALUES (?,?,?,?,?,?,?,?,?,?)",
                            (
                                number,
                                mode,
                                attempt,
                                int(label),
                                gallery,
                                probe,
                                box,
                                sealed,
                                role0,
                                role1,
                            ),
                        )
            db.commit()
        finally:
            db.close()
        os.replace(tmp, destination)
    finally:
        Path(tmp).unlink(missing_ok=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--key", required=True, type=Path)
    p.add_argument("--images", type=Path, default=ROOT / "ppface")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--attempts", type=int, default=2)
    p.add_argument("--generation", type=int, default=0)
    p.add_argument(
        "--missing",
        type=Path,
        help="CSV from the collector containing split,pair_row,mode",
    )
    args = p.parse_args()
    if (
        args.attempts < 1
        or args.generation < 0
        or bool(args.generation) != bool(args.missing)
    ):
        p.error(
            "Use a positive attempt count. Additional generations require --missing."
        )
    missing = {}
    if args.missing:
        import csv

        with args.missing.open() as f:
            for r in csv.DictReader(f):
                missing.setdefault(r["split"], {}).setdefault(
                    int(r["pair_row"]), set()
                ).add(r["mode"])
    key = args.key.read_bytes()
    args.out.mkdir(parents=True, exist_ok=True, mode=0o700)
    for dataset, (_, bank_file, _, _) in SPLITS.items():
        rows = pair_rows(dataset)
        bank = json.loads((ROOT / "data" / bank_file).read_text())
        for offset in range(0, len(rows), SHARD_SIZE):
            shard = args.out / f"{dataset}-{offset + 1:04}-g{args.generation:03}.sqlite"
            targets = missing.get(dataset, {}) if args.missing else None
            if shard.exists() or (
                targets is not None
                and not any(
                    n in targets for n in range(offset + 1, offset + SHARD_SIZE + 1)
                )
            ):
                continue
            build_shard(
                shard,
                dataset,
                offset + 1,
                rows[offset : offset + SHARD_SIZE],
                bank,
                key,
                args.images.resolve(),
                args.attempts,
                targets,
            )
            print(shard.name, flush=True)


if __name__ == "__main__":
    main()
