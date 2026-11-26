"""Time original Obscura arithmetic with two TNO processes on one board."""

import argparse
import asyncio
import contextlib
import fcntl
import hmac
import json
import multiprocessing as mp
from pathlib import Path
import sqlite3
import struct
import sys
import time

from material import ROOT, NAMES, SPLITS, VEC, expand, batches

sys.path.insert(0, str(ROOT / "obscura-protocol"))
from obscura import Server
from common.helper import plain_convert_raw
from B.mpc import peer_pool
from run import PROVISION, DECIDE, Session
from ina_meter import InputRail
from power import frame_energy
from thresholds import NUMERATORS, DEN

MASK_STORED, MASK_BENCH = 24, 25
GROUP_SETUP, GROUP_NEXT = 26, 27
PORT = 61753


def server(role, seed, masked_x, corr=None):
    s = Server(role)
    s.vec_s = VEC.unpack(masked_x)
    s.circuit = expand(seed)
    if role == 1:
        for i, k in enumerate(NAMES[2:]):
            s.circuit[k] = VEC.unpack_from(corr, i * VEC.size)
    return s


def verify_masked_probe(packet, slot, mac_key, profile):
    """WD verifies the TA tag before using the public masked coordinates."""
    aad = packet[:1040] + (b"D" if profile == "droneface" else b"")
    if (
        len(packet) != 1072
        or packet[:16] != slot
        or not hmac.compare_digest(hmac.digest(mac_key, aad, "sha256"), packet[1040:])
    ):
        raise ValueError("Invalid masked packet")
    return VEC.unpack_from(packet, 16)


def seal_reply(shares, slot, packet_tag, auth):
    """Protect the WD's two output shares on their way to DECIDE."""
    ct = bytes(a ^ b for a, b in zip(struct.pack("<2Q", *shares), auth[32:48]))
    return ct + hmac.digest(auth[56:], slot + packet_tag + ct, "sha256")


def peer_process(pipe):
    async def serve():
        async with peer_pool(PORT + 1, "127.0.0.1", PORT) as pool:
            pipe.send(True)
            while True:
                msg = pipe.recv()
                if msg is None:
                    break
                mode, profile, materials = msg
                prepared = [
                    (slot, server(1, seed, mx, corr), auth)
                    for slot, seed, mx, corr, auth in materials
                ]
                pipe.send(True)
                timings = []
                for slot, s, auth in prepared:
                    ident = slot.hex()
                    packet = await asyncio.wait_for(
                        pool.recv("server", ident + "/Y"), 30
                    )
                    start = time.perf_counter_ns()
                    if mode == "L":
                        masked = packet
                    else:
                        masked = verify_masked_probe(packet, slot, auth[:32], profile)
                    before = time.perf_counter_ns()
                    shares = s.getFirstRoundMessage(masked)
                    after = time.perf_counter_ns()
                    if mode == "R":
                        reply = seal_reply(shares, slot, packet[1040:], auth)
                    else:
                        reply = shares
                    done = time.perf_counter_ns()
                    await pool.send("server", reply, ident + "/shares")
                    timings.append((after - before, done - start))
                pipe.send(timings)

    try:
        asyncio.run(serve())
    finally:
        pipe.close()


def ready(pipe):
    if not pipe.poll(30):
        raise TimeoutError("Wireless-device control timeout")
    return pipe.recv()


def rail_record(meter, start, end):
    samples = meter.trace(start, end)
    energy = frame_energy([(t, v * i / 1e6) for t, v, i, d in samples], start, end, 100)
    return dict(
        **energy,
        elapsed_s=end - start,
        samples=[[t - start, v, i, d] for t, v, i, d in samples],
    )


async def one(pool, mode, profile, record, session):
    number, label, expected, ident, s, raw, mask, probe = record
    if session:
        session.call(GROUP_NEXT)
    start = time.perf_counter_ns()
    q = plain_convert_raw(raw)
    scaled = time.perf_counter_ns()
    if mode == "L":
        masked = packet = s.maskProbe(q, mask)
    else:
        packet = session.call(MASK_STORED, struct.pack("<128q", *q), 1072)
        masked = VEC.unpack_from(packet, 16)
    masked_at = time.perf_counter_ns()
    local = s.getFirstRoundMessage(masked)
    shared = time.perf_counter_ns()
    await pool.send("server", packet, ident + "/Y")
    reply = await asyncio.wait_for(pool.recv("server", ident + "/shares"), 30)
    arrived = time.perf_counter_ns()
    if mode == "R":
        bit = session.call(DECIDE, struct.pack("<2Q", *local) + reply, 1)[0]
    else:
        bit = int(s.reconstructDecision(local, reply, q, NUMERATORS[profile] / DEN))
    end = time.perf_counter_ns()
    if bit != expected:
        raise ValueError(f"Decision differs from oracle: {number}/{mode}")
    return dict(
        number=number,
        mode=mode,
        label=label,
        decision=bit,
        slot=ident,
        probe=probe,
        scale_ns=scaled - start,
        mask_ns=masked_at - scaled,
        drone_shares_ns=shared - masked_at,
        roundtrip_ns=arrived - shared,
        reconstruct_decide_ns=end - arrived,
        online_ns=end - start,
    )


async def collect(args):
    ctx = mp.get_context("spawn")
    pipe, other = ctx.Pipe()
    proc = ctx.Process(target=peer_process, args=(other,), daemon=True)
    proc.start()
    other.close()
    try:
        if ready(pipe) is not True:
            raise RuntimeError("Peer is unavailable")
        if args.native_key:
            with contextlib.closing(Session(True)) as session:
                session.call(PROVISION, args.native_key.read_bytes())
        with contextlib.ExitStack() as stack:
            db = stack.enter_context(
                contextlib.closing(
                    sqlite3.connect(
                        args.material.resolve().as_uri() + "?mode=ro&immutable=1",
                        uri=True,
                    )
                )
            )
            log = stack.enter_context(
                contextlib.closing(sqlite3.connect(args.out / "groups.sqlite"))
            )
            log.execute(
                "CREATE TABLE IF NOT EXISTS results(split,first,mode,setup_ms,rows,energy, PRIMARY KEY(split,first,mode))"
            )
            meter = None if args.native_key else stack.enter_context(InputRail())
            async with peer_pool(PORT, "127.0.0.1", PORT + 1) as pool:
                for split, (_, bankfile, profile, total) in SPLITS.items():
                    bank = json.loads((ROOT / "data" / bankfile).read_text())
                    count = db.execute(
                        "select count(*) from material where split=? and mode='L'",
                        (split,),
                    ).fetchone()[0]
                    if count != (args.limit or total):
                        raise ValueError("Unexpected material population")
                    for idx, group in enumerate(batches(count)):
                        first = group.start
                        pivot = idx % len(args.modes)
                        for mode in args.modes[pivot:] + args.modes[:pivot]:
                            key = (split, first, mode)
                            if log.execute(
                                "select 1 from results where split=? and first=? and mode=?",
                                key,
                            ).fetchone():
                                continue
                            (box,) = db.execute(
                                "select box from batches where split=? and first=? and mode=?",
                                key,
                            ).fetchone()
                            prep, peer = [], []
                            for (
                                n,
                                label,
                                expected,
                                y,
                                slot,
                                mx,
                                s0,
                                s1,
                                corr,
                                mask,
                                auth,
                            ) in db.execute(
                                """select number,label,expected,y,slot,masked_x,seed0,seed1,corr,drone_input,peer_auth
                                   from material where split=? and mode=? and number between ? and ? order by number""",
                                (split, mode, first, group.stop - 1),
                            ):
                                prep.append(
                                    (
                                        n,
                                        label,
                                        expected,
                                        slot.hex(),
                                        server(0, s0, mx),
                                        bank[y],
                                        VEC.unpack(mask) if mode == "L" else None,
                                        y,
                                    )
                                )
                                peer.append((slot, s1, mx, corr, auth))
                            if len(prep) != len(group):
                                raise ValueError("Incomplete dealer batch")
                            pipe.send((mode, profile, peer))
                            if ready(pipe) is not True:
                                raise RuntimeError("Peer setup failed")
                            with contextlib.ExitStack() as batch:
                                setup = time.monotonic()
                                session = None
                                if mode != "L":
                                    session = batch.enter_context(
                                        contextlib.closing(
                                            Session(bool(args.native_key))
                                        )
                                    )
                                    session.call(GROUP_SETUP, box)
                                start = time.monotonic()
                                rows = [
                                    await one(pool, mode, profile, r, session)
                                    for r in prep
                                ]
                                end = time.monotonic()
                                timings = ready(pipe)
                                if len(timings) != len(rows):
                                    raise RuntimeError("Incomplete peer timings")
                                for r, (shares, peer_time) in zip(rows, timings):
                                    r.update(
                                        peer_shares_ns=shares, peer_compute_ns=peer_time
                                    )
                                energy = (
                                    rail_record(meter, start, end) if meter else None
                                )
                                with log:
                                    log.execute(
                                        "insert into results values(?,?,?,?,?,?)",
                                        (
                                            *key,
                                            (start - setup) * 1000,
                                            json.dumps(rows),
                                            json.dumps(energy),
                                        ),
                                    )
                            print(
                                split,
                                group.stop - 1,
                                mode,
                                len(rows),
                                "complete",
                                flush=True,
                            )
    finally:
        with contextlib.suppress(BrokenPipeError, EOFError):
            pipe.send(None)
        pipe.close()
        proc.join(3)
        if proc.is_alive():
            proc.terminate()
            proc.join()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("material", type=Path)
    p.add_argument("out", type=Path)
    p.add_argument("--limit", type=int)
    p.add_argument("--modes", choices=["LPR", "L", "PR"], default="LPR")
    p.add_argument(
        "--native-key", type=Path, help="Explicit test shim; disables rail sampling"
    )
    args = p.parse_args()
    args.out.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (args.out / "active.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        asyncio.run(collect(args))
