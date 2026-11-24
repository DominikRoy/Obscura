"""Two non-colluding semi-honest parties. Dealer material is single use."""

import argparse
import asyncio
import contextlib
import hmac
import json
import os
import secrets
import struct
import time
from pathlib import Path

R = 1 << 64
W = 1 << 128
if __package__:
    from .comparison import evaluate, keys
else:
    from comparison import evaluate, keys
DEN, NUM = 100000000, 11368578
B_MODES = {"mpc": "B", "linux": "H", "tee": "T"}


def setting(mode):
    return {"A": "A", "B": "B-mpc", "H": "B-linux", "T": "B-tee", "C": "C", "Q": "Q"}[
        mode
    ]


def inner(a, b):
    return sum(x * y for x, y in zip(a, b))


def split(v, modulus):
    first = secrets.randbelow(modulus)
    return first, (v - first) % modulus


def distribute(x, slot, mode):
    dx = [secrets.randbits(64) for _ in x]
    dy = [secrets.randbits(64) for _ in x]
    key = secrets.token_bytes(32)
    roles = [
        {
            "role": i,
            "slot": slot.hex(),
            "mode": mode,
            "key": key.hex(),
            "X": [(v + m) % R for v, m in zip(x, dx)],
            "lift": [],
            "products": [],
        }
        for i in range(2)
    ]
    for name, values in [
        ("dx", dx),
        ("dy", dy),
        ("quad", [inner(dx, dy), inner(dx, dx), inner(dy, dy)]),
    ]:
        for role, share in zip(roles, zip(*(split(v, R) for v in values))):
            role[name] = share
    plain = struct.pack("<128Q", *dy) + key
    if mode == "H":
        return roles, plain
    if mode == "T":
        # Fresh material exclusively for the peer and TA. OTP the three scalar
        # shares and authenticate them against this invocation's masked packet.
        pad, auth = secrets.token_bytes(24), secrets.token_bytes(32)
        roles[1]["ta_pad"], roles[1]["ta_auth"] = pad.hex(), auth.hex()
        return roles, plain + pad + auth
    # The fresh value r masks an arithmetic share for conversion to R128.
    # FSS distributes [z < r], the carry needed to undo a 64-bit wrap.
    for index in range(3):
        r = secrets.randbits(64)
        carry = keys(r, 64, 128)
        low = keys(r % (1 << 63), 63, 1) if index == 0 else (None, None)
        top = split(r >> 63, 2)
        for i, (part, wide) in enumerate(zip(split(r, R), split(r, W))):
            roles[i]["lift"].append(
                {
                    "mask": part,
                    "wide": wide,
                    "carry": carry[i],
                    "low": low[i],
                    "top": top[i],
                }
            )
    r = secrets.randbits(128)
    low = keys(r % (1 << 127), 127, 1)
    for i, (part, top) in enumerate(zip(split(r, W), split(r >> 127, 2))):
        roles[i]["sign"] = {"mask": part, "top": top, "low": low[i]}
    a, b = secrets.randbits(1), secrets.randbits(1)
    for i, and_parts in enumerate(zip(split(a, 2), split(b, 2), split(a & b, 2))):
        roles[i]["and"] = and_parts
    for _ in range(2):
        a, b = secrets.randbits(128), secrets.randbits(128)
        for role, triple in zip(roles, zip(split(a, W), split(b, W), split(a * b, W))):
            role["products"].append(triple)
    return roles, plain


@contextlib.asynccontextmanager
async def peer_pool(local_port, peer_host, peer_port):
    from tno.mpc.communication import Pool

    pool = Pool(max_retries=2)
    try:
        pool.add_http_server(addr="127.0.0.1", port=local_port)
        pool.add_http_client("server", addr=peer_host, port=peer_port)
        await pool.http_server.server_task
        yield pool
    finally:
        await pool.shutdown()


class Exchange:
    def __init__(self, pool, config):
        self.pool = pool
        self.config = config
        self.seq = 0
        self.sent_bytes = 0
        self.received_bytes = 0
        self.before_send = pool.pool_handlers["server"].total_bytes_sent
        self.before_recv = pool.http_server.total_bytes_recv

    def tno_counts(self):
        return {
            "tno_bytes_sent": self.pool.pool_handlers["server"].total_bytes_sent
            - self.before_send,
            "tno_bytes_received": self.pool.http_server.total_bytes_recv
            - self.before_recv,
        }

    def mac(self, role, message):
        header = bytes.fromhex(self.config["slot"]) + struct.pack(">BI", role, self.seq)
        return (
            hmac.digest(bytes.fromhex(self.config["key"]), header + message, "sha256")
            .hex()
            .encode()
        )

    async def __call__(self, values):
        role = self.config["role"]
        body = json.dumps(values, separators=(",", ":")).encode()
        line = self.mac(role, body) + b" " + body + b"\n"
        msg_id = f"{self.config['slot']}/round/{self.seq}"
        await asyncio.wait_for(self.pool.send("server", line, msg_id), 120)
        raw = await asyncio.wait_for(self.pool.recv("server", msg_id), 120)
        if not isinstance(raw, bytes) or len(raw) > 16384 or not raw.endswith(b"\n"):
            raise ValueError("Invalid peer message")
        self.sent_bytes += len(line)
        self.received_bytes += len(raw)
        check, other = raw[:-1].split(b" ", 1)
        if not hmac.compare_digest(check, self.mac(1 - role, other)):
            raise ValueError("Peer slot, sequence or authentication mismatch")
        self.seq += 1
        result = json.loads(other)
        if len(result) != len(values) or any(type(v) is not int for v in result):
            raise ValueError("Invalid peer payload")
        return result


async def scalar_decision(config, packet, shares, exchange, ta_check, timings):
    role, trusted = config["role"], config["mode"] == "T"
    # Only party 1 sends usable shares towards the drone. Party 0 sends zeros.
    length = 56 if trusted else 24
    outbound = bytes(length)
    if role == 1:
        outbound = struct.pack("<3Q", *shares)
        if trusted:
            pad = bytes.fromhex(config["ta_pad"])
            sealed = bytes(a ^ b for a, b in zip(outbound, pad))
            mac = hmac.digest(
                bytes.fromhex(config["ta_auth"]),
                packet[:16] + packet[-32:] + sealed,
                "sha256",
            )
            outbound = sealed + mac
    (remote,) = await exchange([int.from_bytes(outbound, "little")])
    bit = 0
    if role == 0:
        payload = remote.to_bytes(length, "little")
        started = time.monotonic()
        if trusted:
            bit = ta_check(struct.pack("<3Q", *shares) + payload)
        else:
            dot, xx, yy = [
                (a + b) % R for a, b in zip(shares, struct.unpack("<3Q", payload))
            ]
            if dot >= R // 2:
                dot -= R
            bound = 128 * 32767**2
            if abs(dot) > bound or max(xx, yy) > bound:
                raise ValueError("Scalar outside the enrolled coordinate bound")
            bit = int(dot >= 0 and DEN * dot * dot >= NUM * xx * yy)
        timings["scalar_decision_ms"] = (time.monotonic() - started) * 1000
    (other,) = await exchange([bit])
    return other if role else bit


async def verify(config, packet, exchange, ta_check=None, timings=None):
    if timings is None:
        timings = {}
    role = config["role"]
    if (
        len(packet) != 1072
        or packet[:16].hex() != config["slot"]
        or not hmac.compare_digest(
            packet[-32:],
            hmac.digest(bytes.fromhex(config["key"]), packet[:-32], "sha256"),
        )
    ):
        raise ValueError("Invalid TA packet or wrong preprocessing slot")
    Y = struct.unpack_from("<128Q", packet, 16)
    X, dx, dy = config["X"], config["dx"], config["dy"]
    dot, xx, yy = config["quad"]
    # From X=x+dx and Y=y+dy. Public terms enter party zero's share once.
    shares = [
        ((1 - role) * inner(X, Y) - inner(X, dy) - inner(Y, dx) + dot) % R,
        ((1 - role) * inner(X, X) - 2 * inner(X, dx) + xx) % R,
        ((1 - role) * inner(Y, Y) - 2 * inner(Y, dy) + yy) % R,
    ]
    if config["mode"] in ("H", "T"):
        return await scalar_decision(
            config, packet, shares, exchange, ta_check, timings
        )
    lifts = config["lift"]
    masked = [(v + k["mask"]) % R for v, k in zip(shares, lifts)]
    opened = [(a + b) % R for a, b in zip(masked, await exchange(masked))]
    acc = []
    for z, k in zip(opened, lifts):
        carry = evaluate(role, z, 64, 128, k["carry"])
        acc.append(((1 - role) * z - k["wide"] + R * carry) % W)

    def nonnegative(z, k, bits):
        high = bits - 1
        borrow = evaluate(role, z % (1 << high), high, 1, k["low"])
        return k["top"] ^ borrow ^ ((1 ^ (z >> high)) if role == 0 else 0)

    started = time.monotonic()
    dot_ok = nonnegative(opened[0], lifts[0], 64)
    timings["dot_sign_local_ms"] = (time.monotonic() - started) * 1000
    products = []
    for (x, y), (a, b, c) in zip(
        [(acc[0], acc[0]), (acc[1], acc[2])], config["products"]
    ):
        d, e = (x - a) % W, (y - b) % W
        f, g = await exchange([d, e])
        d, e = (d + f) % W, (e + g) % W
        products.append((c + d * b + e * a + (1 - role) * d * e) % W)
    diff = (DEN * products[0] - NUM * products[1]) % W
    k = config["sign"]
    started = time.monotonic()
    share = (diff + k["mask"]) % W
    z = (share + (await exchange([share]))[0]) % W
    margin_ok = nonnegative(z, k, 128)
    timings["margin_sign_with_exchange_ms"] = (time.monotonic() - started) * 1000
    started = time.monotonic()
    a, b, c = config["and"]
    e, f = dot_ok ^ a, margin_ok ^ b
    u, v = await exchange([e, f])
    e, f = e ^ u, f ^ v
    bit = c ^ (e & b) ^ (f & a) ^ ((e & f) if role == 0 else 0)
    timings["and_with_exchange_ms"] = (time.monotonic() - started) * 1000
    return bit ^ (await exchange([bit]))[0]


def consume(path, cfg):
    slot = bytes.fromhex(cfg["slot"])
    if len(slot) != 16 or cfg["role"] not in (0, 1):
        raise ValueError("Invalid preprocessing slot")
    used = path.parent / (slot.hex() + f".party{cfg['role']}.spent")
    fd = os.open(used, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(fd)
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


async def main():
    p = argparse.ArgumentParser(
        description="Run party 1 after the drone announces its port"
    )
    p.add_argument("material", type=Path)
    p.add_argument("--connect", nargs=2, required=True, metavar=("HOST", "PORT"))
    p.add_argument("--port", type=int, default=61502, help="Local TNO listener")
    args = p.parse_args()
    cfg = json.loads(args.material.read_text())
    if cfg["role"] != 1:
        p.error("Expected party 1 material")
    async with peer_pool(args.port, args.connect[0], int(args.connect[1])) as pool:
        consume(args.material, cfg)
        slot = cfg["slot"]
        exchange = Exchange(pool, cfg)
        await asyncio.wait_for(pool.send("server", b"ready", slot + "/ready"), 120)
        # Exclude the outgoing greeting even if the first peer packet is already queued.
        exchange.before_send = pool.pool_handlers["server"].total_bytes_sent
        packet = await asyncio.wait_for(pool.recv("server", slot + "/packet"), 180)
        start = time.monotonic()
        bit = await verify(cfg, packet, exchange)
        if await exchange([bit]) != [bit]:
            raise ValueError("Peer decision mismatch")
        counts = exchange.tno_counts()
        print(
            json.dumps(
                {
                    "slot": slot,
                    "transport": "tno.mpc.communication",
                    "decision": bit,
                    "rounds": exchange.seq,
                    "packet_to_decision_ms": (time.monotonic() - start) * 1000,
                    "application_bytes_sent": exchange.sent_bytes,
                    "application_bytes_received": len(packet) + exchange.received_bytes,
                    **counts,
                }
            )
        )


if __name__ == "__main__":
    asyncio.run(main())
