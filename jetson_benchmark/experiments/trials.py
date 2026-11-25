"""Prepare role-specific files, run paired decision benchmarks, and report medians."""

import argparse
import asyncio
import json
import statistics
import sys
from pathlib import Path

from A.oracle import encode
from B.mpc import peer_pool, setting
from setup_slot import exclusive, prepare
from thresholds import add_profile_option, select_profile

HERE = Path(__file__).resolve().parent
MODES = ("A", "H", "T", "B", "Q", "C")


def camera_pairs(args, bank):
    if not args.images or not args.per_class or args.per_class < 1:
        raise ValueError("Camera pair files require --images and a positive --per-class")
    roots = args.images.resolve()
    counts = [0, 0]
    selected = []
    for index, row in enumerate(args.camera_pairs.read_text().splitlines(), start=1):
        label, gallery, probe, *_ = row.split()
        label = int(label)
        if label not in (0, 1) or not probe.startswith("../"):
            raise ValueError(f"Invalid pair at row {index}")
        if counts[label] == args.per_class:
            continue
        path = (roots / probe[3:]).resolve()
        path.relative_to(roots)
        selected.append((encode(bank[gallery]), path, {"label": label, "pair_row": index}))
        counts[label] += 1
        if min(counts) == args.per_class:
            return selected
    raise ValueError("Too few labeled pairs for --per-class")


def setup(args):
    from camera.input import frame_id, seal_frame, sensor_pixels

    bank = json.loads(args.bank.read_text())
    if args.camera_pairs:
        if args.reference or args.camera_image or args.warmups is not None or args.repeats is not None:
            raise ValueError("Pair mode uses the gallery and probe in each labeled row once")
        cases = camera_pairs(args, bank)
        warmups = 0
    else:
        if not args.reference:
            raise ValueError("A single-probe batch requires --reference")
        repeats = args.repeats if args.repeats is not None else 5
        warmups = args.warmups if args.warmups is not None else 1
        if repeats < 1 or warmups < 0:
            raise ValueError("Require positive repeats and nonnegative warmups")
        cases = [(encode(bank[args.reference]), args.camera_image, {})] * (repeats + warmups)
    args.out.mkdir(mode=0o700)
    drone, peer = args.out / "drone", args.out / "peer"
    drone.mkdir(mode=0o700)
    peer.mkdir(mode=0o700)
    key = args.key.read_bytes()
    profile = select_profile(args.bank, args.threshold_profile)
    trials = []
    for rep, (x, image, metadata) in enumerate(cases):
        pixels = sensor_pixels(image, args.sensor_max_side) if image else None
        source_id = frame_id(pixels, key) if pixels else None
        modes = ("A", "H", "T", "B") if pixels else MODES
        # Rotate the order so one implementation does not always run last.
        start = rep % len(modes)
        for mode in modes[start:] + modes[:start]:
            box, roles = prepare(mode, x, key, profile, camera=pixels is not None)
            trial = f"{rep:03d}-{setting(mode)}"
            folder = drone / trial
            folder.mkdir(mode=0o700)
            exclusive(folder / "ta.box", box)
            if pixels is not None:
                exclusive(folder / "frame.box", seal_frame(pixels, box[1:17], key))
            if roles:
                exclusive(folder / "party0.json", json.dumps(roles[0]).encode())
                exclusive(peer / (trial + ".json"), json.dumps(roles[1]).encode())
            trials.append(
                {
                    **({"frame_id": source_id} if pixels is not None else {}),
                    "name": trial,
                    "mode": mode,
                    "threshold_profile": profile,
                    "warmup": rep < warmups,
                    **metadata,
                }
            )
    exclusive(drone / "trials.json", json.dumps(trials).encode())
    exclusive(peer / "trials.json", json.dumps(trials).encode())
    print(f"Created {len(trials)} trials. Transfer drone/ and peer/ separately.")


def summarize(root):
    groups, expected, operations = {}, {}, {}
    for trial in json.loads((root / "trials.json").read_text()):
        path = root / trial["name"] / "summary.json"
        if not path.is_file():
            raise ValueError(f"Incomplete suite: missing {path}")
        rec = json.loads(path.read_text())
        if rec["setting"] != setting(trial["mode"]):
            raise ValueError(f"Unexpected setting in {path}")
        if rec.get("threshold_profile", "lfw") != trial.get("threshold_profile", "lfw"):
            raise ValueError(f"Unexpected threshold in {path}")
        if ("frame_id" in trial) != (rec.get("input_path") == "sealed-sensor-frame"):
            raise ValueError(f"Wrong input path in {path}")
        group = "quantized" if trial["mode"] in ("C", "Q") else "fp32"
        pair = trial["name"].split("-", 1)[0], group
        decision = (
            trial["frame_id"] if "frame_id" in trial else rec["crop_sha256"],
            rec.get("threshold_profile", "lfw"),
            rec["decision"],
        )
        if decision != expected.setdefault(pair, decision):
            raise ValueError(f"Paired input or decision disagrees in {path}")
        if not trial["warmup"]:
            groups.setdefault(rec["setting"], []).append(dict(rec, **{k: trial[k] for k in ("label", "pair_row") if k in trial}))
            profile = path.with_name("op-times.json")
            if profile.is_file():
                samples = operations.setdefault(rec["setting"], {})
                for label, elapsed_ns in json.loads(profile.read_text())["ns"].items():
                    samples.setdefault(label, []).append(elapsed_ns / 1_000_000)
    stats = {}
    for name, rows in groups.items():
        profiles = {r.get("threshold_profile", "lfw") for r in rows}
        if len(profiles) != 1:
            raise ValueError(f"Mixed thresholds for {name}")
        info = {
            "threshold_profile": profiles.pop(),
            "trials": len(rows),
            "backend": rows[0]["backend"],
            "decision_ones": sum(r["decision"] for r in rows),
        }
        if "label" in rows[0]:
            info["correct"] = sum(r["decision"] == r["label"] for r in rows)
            info["false_accepts"] = sum(r["decision"] == 1 and r["label"] == 0 for r in rows)
            info["false_rejects"] = sum(r["decision"] == 0 and r["label"] == 1 for r in rows)
        for metric in (
            "setup_seconds",
            "crop_to_decision_ms",
            "frame_to_decision_ms",
            "frame_to_embedding_ms",
            "sface_steps_ms",
            "module_frame_to_embedding_j",
            "module_sface_steps_j",
            "module_frame_to_decision_j",
            "masked_packet_to_decision_ms",
            "module_crop_to_decision_j",
            "module_setup_j",
            "scalar_decision_ms",
            "dot_sign_local_ms",
            "margin_sign_with_exchange_ms",
            "and_with_exchange_ms",
        ):
            values = [r[metric] for r in rows if r.get(metric) is not None]
            info[metric] = {
                "n": len(values),
                "median": statistics.median(values) if values else None,
                "mean": statistics.mean(values) if values else None,
            }
        if name in operations:
            info["operation_ms"] = {
                label: {
                    "n": len(values),
                    "median": statistics.median(values),
                    "mean": statistics.mean(values),
                }
                for label, values in operations[name].items()
            }
        stats[name] = info
    print(json.dumps(stats, indent=2))
    return stats


async def peer_trials(args):
    async with peer_pool(61504, "127.0.0.1", 61503) as control:
        print("Peer batch ready", flush=True)
        for trial in json.loads((args.peer_material / "trials.json").read_text()):
            if trial["mode"] == "A":
                continue
            material = args.peer_material / (trial["name"] + ".json")
            slot = json.loads(material.read_text())["slot"]
            await asyncio.wait_for(control.recv("server", slot + "/start"), 600)
            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                str(HERE / "B/mpc.py"),
                str(material),
                "--connect",
                "127.0.0.1",
                "61501",
                stdout=asyncio.subprocess.PIPE,
            )
            try:
                stdout, _ = await asyncio.wait_for(proc.communicate(), 300)
            finally:
                if proc.returncode is None:
                    proc.kill()
                    await proc.wait()
            await control.send(
                "server", stdout if proc.returncode == 0 else b"", slot + "/done"
            )
            if proc.returncode:
                raise RuntimeError(f"Peer failed in {trial['name']}")


async def run(args, control):
    args.output.mkdir(parents=True, exist_ok=False)
    manifest = (args.drone / "trials.json").read_bytes()
    exclusive(args.output / "trials.json", manifest)
    for trial in json.loads(manifest):
        name, mode = trial["name"], trial["mode"]
        folder = args.drone / name
        cmd = [
            sys.executable,
            str(HERE / ("profile_run.py" if args.profile_operations else "run.py")),
            "--box",
            str(folder / "ta.box"),
            "--output",
            str(args.output / name),
        ]
        if "frame_id" in trial:
            if args.image or args.prepared_bgr:
                raise ValueError("A camera batch takes its sealed frames from drone material")
            cmd += ["--sealed-frame", str(folder / "frame.box")]
        elif args.prepared_bgr:
            cmd += ["--prepared-bgr", str(args.prepared_bgr)]
        elif args.image:
            cmd += ["--image", str(args.image)]
        else:
            raise ValueError("A legacy crop batch requires --image or --prepared-bgr")
        if args.power:
            cmd += ["--power"]
        if args.native_key:
            cmd += ["--native-key", str(args.native_key)]
        if mode != "A":
            cmd += ["--party0", str(folder / "party0.json")]
        drone = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE
        )
        try:
            if mode != "A":
                while True:
                    line = await asyncio.wait_for(drone.stdout.readline(), 180)
                    if not line:
                        raise RuntimeError(
                            f"{name}: drone stopped before TNO was ready"
                        )
                    if line.startswith(b"Party 0 ready on TNO"):
                        break
                slot = (folder / "ta.box").read_bytes()[1:17].hex()
                await control.send("server", b"start", slot + "/start")
                peer = await asyncio.wait_for(
                    control.recv("server", slot + "/done"), 300
                )
                if not peer or json.loads(peer)["slot"] != slot:
                    raise RuntimeError(f"{name}: peer failed")
                exclusive(args.output / name / "peer-summary.json", peer)
            await asyncio.wait_for(drone.communicate(), 300)
            if drone.returncode:
                raise RuntimeError(f"{name}: drone exited {drone.returncode}")
        finally:
            if drone.returncode is None:
                drone.kill()
                await drone.wait()
        print(f"{name} complete", flush=True)
    stats = summarize(args.output)
    exclusive(args.output / "medians.json", json.dumps(stats, indent=2).encode())


async def drone_trials(args):
    async with peer_pool(61503, "127.0.0.1", 61504) as control:
        await run(args, control)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="action", required=True)
    prep = sub.add_parser("prepare")
    for opt in ("key", "bank", "out"):
        prep.add_argument("--" + opt, type=Path, required=True)
    add_profile_option(prep)
    prep.add_argument("--reference")
    prep.add_argument("--camera-pairs", type=Path, help="Dealer-side labeled pair file, gallery first")
    prep.add_argument("--images", type=Path, help="Trusted sensor image root for --camera-pairs")
    prep.add_argument("--per-class", type=int, help="Select this many genuine and impostor pairs")
    prep.add_argument("--camera-image", type=Path, help="Seal full sensor frames for A and the three B runs")
    prep.add_argument("--sensor-max-side", type=int, help="Optional long edge at the simulated camera")
    prep.add_argument("--repeats", type=int)
    prep.add_argument("--warmups", type=int)
    batch = sub.add_parser("run")
    for opt in ("drone", "output"):
        batch.add_argument("--" + opt, type=Path, required=True)
    imgs = batch.add_mutually_exclusive_group()
    imgs.add_argument("--image", type=Path)
    imgs.add_argument("--prepared-bgr", type=Path)
    batch.add_argument("--power", action="store_true")
    batch.add_argument(
        "--profile-operations",
        action="store_true",
        help="Write per-command elapsed times and counts in each trial",
    )
    batch.add_argument(
        "--native-key", type=Path, help="Explicit native workstation simulation"
    )
    peer = sub.add_parser("peer")
    peer.add_argument("--peer-material", type=Path, required=True)
    report = sub.add_parser("summary")
    report.add_argument("directory", type=Path)
    args = p.parse_args()
    if args.action == "prepare":
        setup(args)
    elif args.action == "run":
        asyncio.run(drone_trials(args))
    elif args.action == "peer":
        asyncio.run(peer_trials(args))
    else:
        summarize(args.directory)


if __name__ == "__main__":
    main()
