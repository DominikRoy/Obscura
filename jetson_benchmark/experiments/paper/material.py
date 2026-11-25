"""Fresh offline material for the two coordinatewise products used by Obscura."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import struct
import sys

E = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(E))
from A.oracle import ROOT, decision, encode
from full_pairs_dealer import SPLITS, pair_rows
from setup_slot import MODEL_DIGEST
from thresholds import NUMERATORS
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

WORD = (1 << 64) - 1
VEC = struct.Struct("<128Q")
NAMES = ("in_s", "in_v", "s_v", "s_s")


def expand(seed):
    # Independent role seeds compress uniformly pseudorandom additive shares.
    values = struct.unpack(
        "<512Q", hashlib.shake_256(b"obscura-paper-v1/" + seed).digest(4096)
    )
    return {name: values[i * 128 : (i + 1) * 128] for i, name in enumerate(NAMES)}


def add(a, b):
    return [(x + y) & WORD for x, y in zip(a, b)]


def batches(count):
    groups = max(1, count // 128)
    for i in range(groups):
        yield range(1 + i * count // groups, 1 + (i + 1) * count // groups)


def make_row(x, mode):
    slot, seed0, seed1 = os.urandom(16), os.urandom(32), os.urandom(32)
    a, b = expand(seed0), expand(seed1)
    dx, dy = [add(a[k], b[k]) for k in NAMES[:2]]
    # Replacement shares for the peer make the sums exactly dx*dy and dx*dx.
    corr = b"".join(
        VEC.pack(*[(i * j - k) & WORD for i, j, k in zip(dx, other, a[name])])
        for name, other in (("s_v", dy), ("s_s", dx))
    )
    masked_x = VEC.pack(*add(x, dx))
    mac, pad, peer_key = os.urandom(32), os.urandom(24), os.urandom(32)
    mask = VEC.pack(*dy)
    auth = b"" if mode == "L" else (mac if mode == "P" else mac + pad + peer_key)
    role0_input = mask if mode == "L" else b""
    private = b"" if mode == "L" else slot + mask + auth
    return (slot, masked_x, seed0, seed1, corr, role0_input, auth), private


def seal_group(key, mode, profile, records):
    code = {"P": "J", "R": "K"}[mode]
    header = (code if profile == "lfw" else code.lower()).encode() + os.urandom(16)
    nonce = os.urandom(12)
    domain = f"obscura-v1/SFace128/trunc256/tau2={NUMERATORS[profile]:08d}e-8/".encode()
    return (
        header
        + nonce
        + AESGCM(key).encrypt(nonce, b"".join(records), domain + MODEL_DIGEST + header)
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("key", type=Path)
    p.add_argument("db", type=Path)
    p.add_argument("--limit-per-split", type=int)
    args = p.parse_args()
    key = args.key.read_bytes()
    if len(key) != 32:
        raise ValueError("Expected 32 byte dealer key")
    fd = os.open(args.db, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
    with sqlite3.connect(args.db) as db:
        db.execute("""CREATE TABLE material(split,number,mode,label,expected,y,slot BLOB UNIQUE,
                   masked_x,seed0,seed1,corr,drone_input,peer_auth,PRIMARY KEY(split,number,mode))""")
        db.execute(
            "CREATE TABLE batches(split,first,mode,box,PRIMARY KEY(split,first,mode))"
        )
        for split, (_, bankfile, profile, _) in SPLITS.items():
            bank = json.loads((ROOT / "data" / bankfile).read_text())
            rows = pair_rows(split)[: args.limit_per_split]
            for group in batches(len(rows)):
                for mode in "LPR":
                    records = []
                    for number in group:
                        label, enrolled, probe = rows[number - 1]
                        # Pair manifests specify the enrolled gallery first and live probe second.
                        x, y = encode(bank[enrolled]), encode(bank[probe])
                        shares, private = make_row(x, mode)
                        records.append(private)
                        db.execute(
                            "INSERT INTO material VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            (
                                split,
                                number,
                                mode,
                                int(label),
                                decision(x, y, profile),
                                probe,
                                *shares,
                            ),
                        )
                    box = (
                        b"" if mode == "L" else seal_group(key, mode, profile, records)
                    )
                    db.execute(
                        "INSERT INTO batches VALUES(?,?,?,?)",
                        (split, group.start, mode, box),
                    )
            print(split, len(rows), flush=True)


if __name__ == "__main__":
    main()
