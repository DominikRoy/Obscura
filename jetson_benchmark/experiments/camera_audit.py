"""Audit hardware camera reports and export public per-trial measurements."""

import argparse
import csv
import json
from pathlib import Path

from A.oracle import decision, encode
from camera_accuracy import ROOT, Reference

SPLITS = {
    "lfw1": ("veri_test1.txt", "new_emb1.txt"),
    "drone9": ("veri_balanced_cosine9sface.txt", "embeddings_droneface_raw_sface9.txt"),
    "drone11": (
        "veri_balanced_cosine11sface.txt",
        "embeddings_droneface_raw_sface11.txt",
    ),
}


def read(path):
    return json.loads(path.read_text())


def audit(directories, images):
    reference = Reference()
    slots = set()
    vectors = {}
    measurements = []
    for folder in directories:
        pairs = []
        if folder.name.startswith("camera-pairs-"):
            pairs_file, bank_file = SPLITS[folder.name[len("camera-pairs-") :]]
            pairs = (ROOT / "data" / pairs_file).read_text().splitlines()
            bank = read(ROOT / "data" / bank_file)
        grouped = {}
        for trial in read(folder / "trials.json"):
            run = folder / trial["name"]
            rec = read(run / "summary.json")
            op = read(run / "op-times.json")
            if (rec["backend"], rec["input_path"], rec["rail"]) != (
                "OP-TEE",
                "sealed-sensor-frame",
                "VDD_IN",
            ):
                raise ValueError(f"Unexpected execution path in {run}")
            if rec["slot"] in slots:
                raise ValueError(f"Duplicate slot in {run}")
            slots.add(rec["slot"])
            if any(
                op["calls"].get(k) != n
                for k, n in [
                    ("decrypt_detect_align_crop_input", 1),
                    ("weight_and_kernel", 172),
                    ("finish", 1),
                ]
            ):
                raise ValueError(f"Unexpected extraction command count in {run}")
            if rec["setting"] != "A":
                peer = read(run / "peer-summary.json")
                if (peer["slot"], peer["decision"]) != (rec["slot"], rec["decision"]):
                    raise ValueError(f"Peer mismatch in {run}")
            group = trial["name"].split("-", 1)[0]
            expected = (trial["frame_id"], rec["decision"])
            previous, modes = grouped.setdefault(group, (expected, set()))
            if previous != expected or rec["setting"] in modes:
                raise ValueError(f"Pairing mismatch in {run}")
            modes.add(rec["setting"])
            if pairs:
                label, gallery, probe, *_ = pairs[trial["pair_row"] - 1].split()
                if probe not in vectors:
                    vectors[probe] = reference.extract(images / probe[3:])[0]
                pred = decision(
                    encode(bank[gallery]), vectors[probe], rec["threshold_profile"]
                )
                if int(label) != trial["label"] or pred != rec["decision"]:
                    raise ValueError(
                        f"Workstation and hardware checks disagree in {run}"
                    )
            measurements.append(
                dict(
                    batch=folder.name,
                    trial=trial["name"],
                    warmup=int(trial["warmup"]),
                    setting=rec["setting"],
                    pair_row=trial.get("pair_row"),
                    label=trial.get("label"),
                    decision=rec["decision"],
                    sensor_to_tensor_ms=op["ns"]["decrypt_detect_align_crop_input"]
                    / 1e6,
                    weight_copy_hash_kernel_ms=op["ns"]["weight_and_kernel"] / 1e6,
                    frame_to_embedding_ms=op["ns"]["begin_through_embedding"] / 1e6,
                    finish_ms=op["ns"]["finish"] / 1e6,
                    post_finish_ms=rec.get("masked_packet_to_decision_ms"),
                    frame_to_decision_ms=rec["frame_to_decision_ms"],
                    module_frame_to_embedding_j=rec.get("module_frame_to_embedding_j"),
                    module_sface_steps_j=rec.get("module_sface_steps_j"),
                    module_frame_to_decision_j=rec["module_frame_to_decision_j"],
                    energy_status=rec["energy_status"],
                    samples=rec["samples"],
                    **rec["memory"],
                )
            )
        if any(
            modes != {"A", "B-linux", "B-tee", "B-mpc"} for _, modes in grouped.values()
        ):
            raise ValueError(f"Missing paired setting in {folder}")
    return measurements


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("directories", nargs="+", type=Path)
    p.add_argument("--images", type=Path, default=ROOT / "ppface")
    p.add_argument("--csv", required=True, type=Path)
    args = p.parse_args()
    rows = audit(args.directories, args.images)
    with args.csv.open("x", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Audited {len(rows)} trials including warmups")
