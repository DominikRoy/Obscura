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

HERE = Path(__file__).resolve().parent
MODES = ("A", "H", "T", "B", "Q", "C")


def setup(args):
    if args.repeats < 1 or args.warmups < 0:
        raise ValueError("Require positive repeats and nonnegative warmups")
    args.out.mkdir(mode=0o700)
    drone, peer = args.out / "drone", args.out / "peer"
    drone.mkdir(mode=0o700)
    peer.mkdir(mode=0o700)
    x = encode(json.loads(args.bank.read_text())[args.reference])
    key = args.key.read_bytes()
    trials = []
    for rep in range(args.repeats + args.warmups):
        # Rotate the order so one implementation does not always run last.
        start = rep % len(MODES)
        for mode in MODES[start:] + MODES[:start]:
            box, roles = prepare(mode, x, key)
            trial = f"{rep:03d}-{setting(mode)}"
            folder = drone / trial
            folder.mkdir(mode=0o700)
            exclusive(folder / "ta.box", box)
            if roles:
                exclusive(folder / "party0.json", json.dumps(roles[0]).encode())
                exclusive(peer / (trial + ".json"), json.dumps(roles[1]).encode())
            trials.append({"name": trial, "mode": mode, "warmup": rep < args.warmups})
    exclusive(drone / "trials.json", json.dumps(trials).encode())
    exclusive(peer / "trials.json", json.dumps(trials).encode())
    print(f"Created {len(trials)} trials. Transfer drone/ and peer/ separately.")


def summarize(root):
    groups, expected = {}, {}
    for trial in json.loads((root / "trials.json").read_text()):
        path = root / trial["name"] / "summary.json"
        if not path.is_file():
            raise ValueError(f"Incomplete suite: missing {path}")
        rec = json.loads(path.read_text())
        if rec["setting"] != setting(trial["mode"]):
            raise ValueError(f"Unexpected setting in {path}")
        group = "quantized" if trial["mode"] in ("C", "Q") else "fp32"
        pair = trial["name"].split("-", 1)[0], group
        decision = rec["crop_sha256"], rec["decision"]
        if decision != expected.setdefault(pair, decision):
            raise ValueError(f"Paired input or decision disagrees in {path}")
        if not trial["warmup"]:
            groups.setdefault(rec["setting"], []).append(rec)
    stats = {}
    for name, rows in groups.items():
        info = {
            "trials": len(rows),
            "backend": rows[0]["backend"],
            "decision_ones": sum(r["decision"] for r in rows),
        }
        for metric in (
            "setup_seconds",
            "crop_to_decision_ms",
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
            str(HERE / "run.py"),
            "--box",
            str(folder / "ta.box"),
            "--output",
            str(args.output / name),
        ]
        cmd += (
            ["--prepared-bgr", str(args.prepared_bgr)]
            if args.prepared_bgr
            else ["--image", str(args.image)]
        )
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
    prep.add_argument("--reference", required=True)
    prep.add_argument("--repeats", type=int, default=5)
    prep.add_argument("--warmups", type=int, default=1)
    batch = sub.add_parser("run")
    for opt in ("drone", "output"):
        batch.add_argument("--" + opt, type=Path, required=True)
    imgs = batch.add_mutually_exclusive_group(required=True)
    imgs.add_argument("--image", type=Path)
    imgs.add_argument("--prepared-bgr", type=Path)
    batch.add_argument("--power", action="store_true")
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
