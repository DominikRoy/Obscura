"""Resumable single-Jetson, two-process protocol measurements on labeled pairs."""

import argparse
import asyncio
import contextlib
import csv
import fcntl
import json
import multiprocessing
import os
from pathlib import Path
import sqlite3
import time
import traceback
import zlib

from B.mpc import Exchange, consume, peer_pool, setting, verify
from full_pairs_dealer import MODES, SHARD_SIZE, SPLITS, pair_rows
from ina_meter import InputRail
from run import (
    BENCH,
    DECIDE,
    SETUP,
    Model,
    Session,
    camera_clock,
    camera_heap,
    private_window,
)
from power import frame_energy


def readonly(path):
    return sqlite3.connect(path.resolve().as_uri() + "?mode=ro&immutable=1", uri=True)


def peer_worker(pipe):
    async def serve():
        async with peer_pool(61602, "127.0.0.1", 61601) as pool:
            pipe.send("ready")
            while True:
                msg = pipe.recv()
                if msg is None:
                    break
                shard, number, mode, attempt, used = msg
                with contextlib.closing(readonly(shard)) as db:
                    cfg = json.loads(
                        db.execute(
                            "SELECT role1 FROM material WHERE row_no=? AND mode=? AND attempt=?",
                            (number, mode, attempt),
                        ).fetchone()[0]
                    )
                consume(used, cfg)
                exchange = Exchange(pool, cfg)
                slot = cfg["slot"]
                await pool.send("server", b"ready", slot + "/ready")
                packet = await asyncio.wait_for(
                    pool.recv("server", slot + "/packet"), 90
                )
                bit = await verify(cfg, packet, exchange)
                if await exchange([bit]) != [bit]:
                    raise ValueError("Peer decision mismatch")
                pipe.send((slot, bit))

    try:
        asyncio.run(serve())
    except (EOFError, BrokenPipeError):
        pass
    except Exception:
        pipe.send(("error", traceback.format_exc()))
        raise
    finally:
        pipe.close()


def peer_reply(pipe, timeout=60):
    if not pipe.poll(timeout):
        raise TimeoutError("Peer control reply timed out")
    reply = pipe.recv()
    if isinstance(reply, tuple) and reply[0] == "error":
        raise ValueError(reply[1])
    return reply


async def measure(model, meter, pool, pipe, request, record):
    label, gallery, probe, box, sealed, cfg = record
    shard, number, mode, attempt, used = request
    with contextlib.closing(Session(False)) as session:
        session.call(SETUP, box)
        if mode != "A":
            cfg = json.loads(cfg)
            if (
                cfg["slot"] != box[1:17].hex()
                or cfg["role"] != 0
                or cfg["mode"] != mode
            ):
                raise ValueError("Dealer material mismatch")
            consume(used, cfg)
            pipe.send(request)
            slot = cfg["slot"]
            if (
                await asyncio.wait_for(pool.recv("server", slot + "/ready"), 90)
                != b"ready"
            ):
                raise ValueError("Missing peer greeting")
            exchange = Exchange(pool, cfg)
        bounds = camera_clock(session)[0]
        marks = {}
        start = time.monotonic()
        result = model.extract(session, mode, sealed, None, camera=True, clock=marks)
        if mode == "A":
            bit = result[0]
        else:
            await pool.send("server", result, slot + "/packet")
            bit = await verify(
                cfg, result, exchange, lambda data: session.call(DECIDE, data, 1)[0]
            )
            if await exchange([bit]) != [bit]:
                raise ValueError("Drone decision mismatch")
        end = time.monotonic()
        if mode != "A" and await asyncio.get_running_loop().run_in_executor(
            None, peer_reply, pipe
        ) != (slot, bit):
            raise ValueError("Wrong peer result")
        timing, private, alignment = private_window(
            session, bounds, start, marks["embedding_ready"]
        )
        live, peak = camera_heap(session)
    trace = meter.trace(start, end)
    watts = [(t, mv * ma / 1e6) for t, mv, ma, _ in trace]
    full = frame_energy(watts, start, end, meter.interval_ms)
    extraction = (
        frame_energy(watts, *private, meter.interval_ms)
        if private
        else {
            "module_extraction_j": None,
            "energy_status": alignment,
            "power_samples_in_frame": 0,
        }
    )
    result = dict(
        label=label,
        gallery=gallery,
        probe=probe,
        setting=setting(mode),
        decision=bit,
        private_pixels_to_embedding_ms=timing["private_pixels_to_embedding_ms"],
        module_private_pixels_to_embedding_j=extraction["module_extraction_j"],
        private_energy_status=extraction["energy_status"],
        private_samples=extraction["power_samples_in_frame"],
        frame_to_decision_ms=(end - start) * 1000,
        module_frame_to_decision_j=full["module_extraction_j"],
        frame_energy_status=full["energy_status"],
        frame_samples=full["power_samples_in_frame"],
        ta_heap_at_private_pixels_bytes=live,
        ta_heap_private_window_peak_bytes=peak,
        private_pixels_from_frame_s=timing.get("private_pixels_from_frame_s"),
        private_embedding_from_frame_s=timing.get("private_embedding_from_frame_s"),
        clock_error_bound_ms=timing.get("private_window_clock_error_bound_ms"),
    )
    raw = [[t - start, mv, ma, read_s] for t, mv, ma, read_s in trace]
    valid = extraction["energy_status"] == full["energy_status"] == "measured"
    return result, raw, valid


def open_results(root):
    db = sqlite3.connect(root / "attempts.sqlite", timeout=30)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("""CREATE TABLE IF NOT EXISTS attempts(split TEXT, row_no INTEGER, mode TEXT, slot TEXT PRIMARY KEY,
               state TEXT, summary TEXT, power BLOB)""")
    db.execute(
        "CREATE INDEX IF NOT EXISTS by_pair ON attempts(split,row_no,mode,state)"
    )
    db.execute("""CREATE UNIQUE INDEX IF NOT EXISTS one_valid
                  ON attempts(split,row_no,mode) WHERE state='valid'""")
    return db


async def collect(args):
    model = Model(BENCH / "secure_sface/generated")
    ctx = multiprocessing.get_context("spawn")
    pipe, child = ctx.Pipe()
    proc = ctx.Process(target=peer_worker, args=(child,), daemon=True)
    proc.start()
    child.close()
    try:
        if peer_reply(pipe) != "ready":
            raise ValueError("Peer startup failed")
        with contextlib.closing(open_results(args.out)) as log, InputRail() as meter:
            async with peer_pool(61601, "127.0.0.1", 61602) as pool:
                for dataset in SPLITS:
                    rows = pair_rows(dataset)
                    for offset in range(0, len(rows), SHARD_SIZE):
                        stem = f"{dataset}-{offset + 1:04}"
                        shards = sorted(args.material.glob(stem + "-g*.sqlite"))
                        if not shards:
                            raise FileNotFoundError(f"Missing dealer shard {stem}")
                        used = args.out / "spent" / stem / "role"
                        used.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
                        with contextlib.ExitStack() as stack:
                            material = [
                                (
                                    s,
                                    stack.enter_context(
                                        contextlib.closing(readonly(s))
                                    ),
                                )
                                for s in shards
                            ]
                            for number in range(
                                offset + 1, min(offset + SHARD_SIZE, len(rows)) + 1
                            ):
                                rotate = (number - 1) % len(MODES)
                                for mode in MODES[rotate:] + MODES[:rotate]:
                                    if log.execute(
                                        "SELECT 1 FROM attempts WHERE split=? AND row_no=? AND mode=? AND state='valid'",
                                        (dataset, number, mode),
                                    ).fetchone():
                                        continue
                                    done = False
                                    for shard, db in material:
                                        cur = db.execute(
                                            """SELECT attempt,label,gallery,probe,box,frame,role0 FROM material
                                                            WHERE row_no=? AND mode=? ORDER BY attempt""",
                                            (number, mode),
                                        )
                                        for attempt, *record in cur:
                                            if [str(record[0]), *record[1:3]] != rows[
                                                number - 1
                                            ]:
                                                raise ValueError(
                                                    "Pair differs from the repository split"
                                                )
                                            slot = record[3][1:17].hex()
                                            with log:
                                                claimed = log.execute(
                                                    "INSERT OR IGNORE INTO attempts VALUES(?,?,?,?,'started',NULL,NULL)",
                                                    (dataset, number, mode, slot),
                                                ).rowcount
                                            if not claimed:
                                                continue
                                            result, raw, done = await measure(
                                                model,
                                                meter,
                                                pool,
                                                pipe,
                                                (shard, number, mode, attempt, used),
                                                record,
                                            )
                                            with log:
                                                log.execute(
                                                    "UPDATE attempts SET state=?,summary=?,power=? WHERE slot=?",
                                                    (
                                                        "valid" if done else "invalid",
                                                        json.dumps(result),
                                                        zlib.compress(
                                                            json.dumps(raw).encode()
                                                        ),
                                                        slot,
                                                    ),
                                                )
                                            if done:
                                                break
                                        if done:
                                            break
                        n = log.execute(
                            "SELECT count(*) FROM attempts WHERE state='valid'"
                        ).fetchone()[0]
                        print(
                            f"{stem} processed; {n} valid pair-setting rows", flush=True
                        )
    finally:
        with contextlib.suppress(BrokenPipeError, EOFError):
            pipe.send(None)
        pipe.close()
        proc.join(5)
        if proc.is_alive():
            proc.terminate()
            proc.join()


def export(args):
    seen = {}
    columns = None
    csv_path = args.out / "per_pair.csv.tmp"
    with contextlib.closing(open_results(args.out)) as db, csv_path.open("w", newline="") as f:
        for split, n, mode, summary in db.execute(
            "SELECT split,row_no,mode,summary FROM attempts WHERE state='valid' ORDER BY split,row_no,mode"
        ):
            data = json.loads(summary)
            if (
                data["module_private_pixels_to_embedding_j"] is None
                or data["module_frame_to_decision_j"] is None
                or not data["ta_heap_private_window_peak_bytes"]
            ):
                raise ValueError("Incomplete measurement")
            group = seen.setdefault((split, n), {})
            if group and next(iter(group.values())) != data["decision"]:
                raise ValueError(f"Decisions disagree for {split}/{n}")
            group[mode] = data["decision"]
            row = dict(split=split, pair_row=n, mode=mode, **data)
            if columns is None:
                columns = csv.DictWriter(f, fieldnames=list(row))
                columns.writeheader()
            columns.writerow(row)
    os.replace(args.out / "per_pair.csv.tmp", args.out / "per_pair.csv")
    missing = 0
    with (args.out / "missing.csv.tmp").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["split", "pair_row", "mode"])
        for dataset in SPLITS:
            for n in range(1, len(pair_rows(dataset)) + 1):
                for mode in MODES:
                    if mode not in seen.get((dataset, n), {}):
                        w.writerow([dataset, n, mode])
                        missing += 1
    os.replace(args.out / "missing.csv.tmp", args.out / "missing.csv")
    print(f"{sum(map(len, seen.values()))} valid; {missing} missing", flush=True)
    return missing


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=["run", "export"])
    p.add_argument("--material", type=Path)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    os.umask(0o077)
    a.out.mkdir(parents=True, exist_ok=True)
    if a.action == "run":
        if not a.material:
            p.error("--material is required")
        with (a.out / "run.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            asyncio.run(collect(a))
            missing = export(a)
    else:
        missing = export(a)
    raise SystemExit(2 if missing else 0)
