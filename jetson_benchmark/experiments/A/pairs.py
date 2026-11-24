"""Prepare an enrollment manifest on the dealer, or evaluate images on the drone."""

import argparse
import contextlib
import hashlib
import json
import sys
from pathlib import Path

EXP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EXP))
from A.oracle import ROOT, encode
from run import BENCH, PROVISION, SETUP, Model, Session
from setup_slot import exclusive, prepare


def enroll(args):
    bank = json.loads(args.bank.read_text())
    counts = [0, 0]
    refs = {}
    rows = []
    args.out.mkdir(mode=0o700)
    key = args.key.read_bytes()
    for line in args.pairs.read_text().splitlines():
        label, x, y, _ = line.split()
        label = int(label)
        if label not in (0, 1):
            raise ValueError("Expected binary labels")
        if counts[label] >= args.per_class:
            continue
        if x not in refs:
            name = f"x-{len(refs):04}.box"
            box, _ = prepare("A", encode(bank[x]), key)
            exclusive(args.out / name, box)
            refs[x] = name
        if not y.startswith("../DnHFaces/open_data_set/photos_all_faces/"):
            raise ValueError("Expected DroneFace gallery first and probe second")
        rows.append({"label": label, "reference": x, "box": refs[x], "probe": y[3:]})
        counts[label] += 1
        if min(counts) == args.per_class:
            break
    if min(counts) != args.per_class:
        raise ValueError("Too few pairs for requested split")
    exclusive(args.out / "pairs.json", json.dumps(rows, indent=2).encode())


def evaluate(args):
    from dataset_tee import prepare_face

    roots = args.ppface.resolve()
    pairs = json.loads((args.enrollment / "pairs.json").read_text())
    model = Model(BENCH / "secure_sface/generated")
    output = []
    if args.native_key:
        with contextlib.closing(Session(True)) as session:
            session.call(PROVISION, args.native_key.read_bytes())
    for row in pairs:
        path = (roots / row["probe"]).resolve()
        path.relative_to(roots)
        with contextlib.closing(Session(bool(args.native_key))) as session:
            session.call(SETUP, (args.enrollment / row["box"]).read_bytes())
            crop, _ = prepare_face(path)
            bit = model.extract(session, "A", crop.tobytes(), None)[0]
        output.append(
            dict(
                **row,
                decision=bit,
                crop_sha256=hashlib.sha256(crop.tobytes()).hexdigest(),
            )
        )
    result = {
        "backend": "native validation" if args.native_key else "OP-TEE",
        "pairs": len(output),
        "correct": sum(r["label"] == r["decision"] for r in output),
        "false_accepts": sum(r["decision"] == 1 and r["label"] == 0 for r in output),
        "false_rejects": sum(r["decision"] == 0 and r["label"] == 1 for r in output),
    }
    exclusive(
        args.report, json.dumps(dict(**result, records=output), indent=2).encode()
    )
    print(json.dumps(result))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sp = p.add_subparsers(dest="action", required=True)
    a = sp.add_parser("enroll")
    a.add_argument("--key", type=Path, required=True)
    a.add_argument(
        "--bank", type=Path, default=ROOT / "data/embeddings_droneface_raw_sface9.txt"
    )
    a.add_argument(
        "--pairs", type=Path, default=ROOT / "data/veri_balanced_cosine9sface.txt"
    )
    a.add_argument("--per-class", type=int, default=15)
    a.add_argument("--out", type=Path, required=True)
    d = sp.add_parser("run")
    d.add_argument("--ppface", type=Path, default=ROOT / "ppface")
    d.add_argument("--enrollment", type=Path, required=True)
    d.add_argument("--report", type=Path, required=True)
    d.add_argument("--native-key", type=Path)
    args = p.parse_args()
    if args.action == "enroll":
        if args.per_class < 1:
            p.error("Choose a positive pair count")
        enroll(args)
    else:
        evaluate(args)


if __name__ == "__main__":
    main()
