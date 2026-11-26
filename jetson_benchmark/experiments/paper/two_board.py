"""Run the paper's drone and wireless-device roles on separate machines."""

import argparse
import asyncio
import contextlib
import fcntl
import json
import os
from pathlib import Path
import sqlite3
import time

from compare import (
    GROUP_SETUP,
    PORT,
    PROVISION,
    InputRail,
    Session,
    one,
    peer_group,
    peer_pool,
    rail_record,
    server,
)
from material import ROOT, SPLITS, VEC, batches


def read_only(path):
    return sqlite3.connect(path.resolve().as_uri() + "?mode=ro&immutable=1", uri=True)


def split_material(source, dest):
    """Project into new files. Each SQLite file contains only its role's columns."""
    dest.mkdir(mode=0o700)
    campaign = os.urandom(16).hex()
    for role, extra in (
        ("drone", "label,expected,y,seed0,drone_input"),
        ("wd", "seed1,corr,peer_auth"),
    ):
        with contextlib.closing(read_only(source)) as db:
            # Keep the combined source read-only. The attached destination is writable.
            target = (dest / (role + ".sqlite")).resolve()
            fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(fd)
            db.execute("ATTACH DATABASE ? AS delivery", (target.as_uri() + "?mode=rw",))
            with db:
                db.execute(
                    "CREATE TABLE delivery.material AS SELECT split,number,mode,slot,masked_x,"
                    + extra
                    + " FROM main.material"
                )
                db.execute(
                    "CREATE UNIQUE INDEX delivery.row_key ON material(split,mode,number)"
                )
                db.execute("CREATE TABLE delivery.info(role,campaign)")
                db.execute("INSERT INTO delivery.info VALUES(?,?)", (role, campaign))
                if role == "drone":
                    db.execute(
                        "CREATE TABLE delivery.batches AS SELECT * FROM main.batches"
                    )
                    db.execute(
                        "CREATE UNIQUE INDEX delivery.batch_key ON batches(split,mode,first)"
                    )
    print(
        "Transfer drone.sqlite to the drone and wd.sqlite to the WD. Keep the combined source on the dealer."
    )


def identity(db, role):
    rows = db.execute("SELECT role,campaign FROM info").fetchall()
    if len(rows) != 1 or rows[0][0] != role:
        raise ValueError("Incorrect role delivery")
    return rows[0][1]


async def receive(pool, message):
    return await asyncio.wait_for(pool.recv("server", message), 180)


async def wireless(args):
    with contextlib.ExitStack() as stack:
        db = stack.enter_context(contextlib.closing(read_only(args.material)))
        campaign = identity(db, "wd")
        args.state.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        used = stack.enter_context(contextlib.closing(sqlite3.connect(args.state)))
        used.execute("CREATE TABLE IF NOT EXISTS spent(slot BLOB PRIMARY KEY)")
        async with peer_pool(PORT + 1, "127.0.0.1", PORT) as pool:
            print("WD ready on loopback port", PORT + 1, flush=True)
            seq = 0
            while True:
                # At startup allow time to log into the drone and start the runner.
                tag = f"paper/control/{seq}"
                hello = (
                    await pool.recv("server", tag)
                    if seq == 0
                    else await receive(pool, tag)
                )
                if hello[0] != campaign:
                    await pool.send(
                        "server", "dealer deliveries differ", tag + "/ready"
                    )
                    raise ValueError("Dealer deliveries differ")
                if hello[1] == "done":
                    await pool.send("server", "done", tag + "/ready")
                    return
                _, split, mode, first, last = hello
                try:
                    if (
                        split not in SPLITS
                        or mode not in ("L", "P", "R")
                        or not 1 <= last - first + 1 <= 256
                    ):
                        raise ValueError("Invalid group")
                    rows = db.execute(
                        """SELECT slot,seed1,masked_x,corr,peer_auth FROM material
                                     WHERE split=? AND mode=? AND number BETWEEN ? AND ? ORDER BY number""",
                        (split, mode, first, last),
                    ).fetchall()
                    if len(rows) != last - first + 1:
                        raise ValueError("Incomplete WD group")
                    prepared = [
                        (slot, server(1, seed, mx, corr), auth)
                        for slot, seed, mx, corr, auth in rows
                    ]
                    # Commit all reservations before a single share is released.
                    with used:
                        used.executemany(
                            "INSERT INTO spent VALUES(?)", [(r[0],) for r in rows]
                        )
                except (ValueError, sqlite3.Error):
                    await pool.send(
                        "server",
                        "WD group unavailable or already consumed",
                        tag + "/ready",
                    )
                    raise
                await pool.send("server", "ready", tag + "/ready")
                times = await peer_group(pool, mode, SPLITS[split][2], prepared)
                await pool.send("server", times, tag + "/times")
                seq += 1


async def drone(args):
    args.output.mkdir(mode=0o700, parents=True, exist_ok=True)
    with contextlib.ExitStack() as stack:
        lock = stack.enter_context((args.output / "two-board.lock").open("a"))
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        db = stack.enter_context(contextlib.closing(read_only(args.material)))
        campaign = identity(db, "drone")
        log = stack.enter_context(
            contextlib.closing(sqlite3.connect(args.output / "lan-groups.sqlite"))
        )
        counts = {
            s: db.execute(
                "SELECT count(*) FROM material WHERE split=? AND mode='L'", (s,)
            ).fetchone()[0]
            for s in SPLITS
        }
        run_info = json.dumps(
            [counts, "native" if args.native_key else "hardware"], sort_keys=True
        )
        with log:
            log.execute(
                "CREATE TABLE IF NOT EXISTS run_info(id INTEGER PRIMARY KEY,settings TEXT)"
            )
            log.execute("INSERT OR IGNORE INTO run_info VALUES(1,?)", (run_info,))
            if (
                log.execute("SELECT settings FROM run_info WHERE id=1").fetchone()[0]
                != run_info
            ):
                raise ValueError("Population or backend differs from existing output")
            log.execute("""CREATE TABLE IF NOT EXISTS results(split,first,mode,setup_ms,rows,energy,
                         PRIMARY KEY(split,first,mode))""")
        if args.native_key:
            with contextlib.closing(Session(True)) as session:
                session.call(PROVISION, args.native_key.read_bytes())
        meter = None if args.native_key else stack.enter_context(InputRail())
        seq = 0
        async with peer_pool(PORT, "127.0.0.1", PORT + 1) as pool:
            for split, (_, bank_file, profile, total) in SPLITS.items():
                if not 0 < counts[split] <= total:
                    raise ValueError("Unexpected split size")
                bank = json.loads((ROOT / "data" / bank_file).read_text())
                for idx, group in enumerate(batches(counts[split])):
                    first, last = group.start, group.stop - 1
                    pivot = idx % 3
                    for mode in "LPR"[pivot:] + "LPR"[:pivot]:
                        key = (split, first, mode)
                        if log.execute(
                            "SELECT 1 FROM results WHERE split=? AND first=? AND mode=?",
                            key,
                        ).fetchone():
                            continue
                        prep = []
                        for (
                            n,
                            label,
                            expected,
                            probe,
                            slot,
                            mx,
                            seed,
                            mask,
                        ) in db.execute(
                            """SELECT number,label,expected,y,slot,masked_x,seed0,drone_input FROM material
                               WHERE split=? AND mode=? AND number BETWEEN ? AND ? ORDER BY number""",
                            (split, mode, first, last),
                        ):
                            prep.append(
                                (
                                    n,
                                    label,
                                    expected,
                                    slot.hex(),
                                    server(0, seed, mx),
                                    bank[probe],
                                    VEC.unpack(mask) if mode == "L" else None,
                                    probe,
                                )
                            )
                        if len(prep) != len(group):
                            raise ValueError("Incomplete drone group")
                        with contextlib.ExitStack() as batch:
                            (box,) = db.execute(
                                "SELECT box FROM batches WHERE split=? AND first=? AND mode=?",
                                key,
                            ).fetchone()
                            before = time.monotonic()
                            session = None
                            if mode != "L":
                                session = batch.enter_context(
                                    contextlib.closing(Session(bool(args.native_key)))
                                )
                                session.call(GROUP_SETUP, box)
                            setup_ms = (time.monotonic() - before) * 1000
                            tag = f"paper/control/{seq}"
                            await pool.send(
                                "server", [campaign, split, mode, first, last], tag
                            )
                            status = await receive(pool, tag + "/ready")
                            if status != "ready":
                                raise RuntimeError(status)
                            start = time.monotonic()
                            rows = [
                                await one(pool, mode, profile, r, session) for r in prep
                            ]
                            end = time.monotonic()
                            timings = await receive(pool, tag + "/times")
                            if len(timings) != len(rows):
                                raise ValueError("Missing WD timings")
                            for row, (shares, peer_time) in zip(rows, timings):
                                row.update(
                                    peer_shares_ns=shares, peer_compute_ns=peer_time
                                )
                            energy = rail_record(meter, start, end) if meter else None
                            with log:
                                log.execute(
                                    "INSERT INTO results VALUES(?,?,?,?,?,?)",
                                    (
                                        *key,
                                        setup_ms,
                                        json.dumps(rows),
                                        json.dumps(energy),
                                    ),
                                )
                            print(split, last, mode, "complete", flush=True)
                            seq += 1
            tag = f"paper/control/{seq}"
            await pool.send("server", [campaign, "done"], tag)
            if await receive(pool, tag + "/ready") != "done":
                raise ValueError("WD shutdown not confirmed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    split = sub.add_parser("split")
    split.add_argument("source", type=Path)
    split.add_argument("destination", type=Path)
    wd = sub.add_parser("wd")
    wd.add_argument("material", type=Path)
    wd.add_argument(
        "--state",
        type=Path,
        default=Path.home() / ".local/state/obscura-paper-wd/spent.sqlite",
    )
    board = sub.add_parser("drone")
    board.add_argument("material", type=Path)
    board.add_argument("output", type=Path)
    board.add_argument(
        "--native-key",
        type=Path,
        help="Test shim only; disables hardware energy collection",
    )
    args = parser.parse_args()
    os.umask(0o077)
    if args.action == "split":
        split_material(args.source, args.destination)
    elif args.action == "wd":
        asyncio.run(wireless(args))
    else:
        asyncio.run(drone(args))


if __name__ == "__main__":
    main()
