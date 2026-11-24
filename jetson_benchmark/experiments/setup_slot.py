"""Trusted dealer/owner process. No live probe is read during setup."""

import argparse
import json
import os
import secrets
import struct
from pathlib import Path

from A.oracle import encode
from B.mpc import B_MODES, distribute, setting


def exclusive(path, data):
    with os.fdopen(
        os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600), "wb"
    ) as f:
        f.write(data)


def prepare(mode, x, key):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    slot = secrets.token_bytes(16)
    header = mode.encode("ascii") + slot
    iv = secrets.token_bytes(12)
    roles = []
    if mode == "A":
        plain = struct.pack("<128q", *x)
    else:
        roles, plain = distribute(x, slot, mode)
    domain = b"obscura-v1/SFace128/trunc256/tau2=11368578e-8/"
    digest = bytes.fromhex(
        "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79"
    )
    return header + iv + AESGCM(key).encrypt(iv, plain, domain + digest + header), roles


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="action", required=True)
    keygen = sub.add_parser("keygen")
    keygen.add_argument("key", type=Path)
    p = sub.add_parser("prepare")
    p.add_argument("--mode", choices=list("ABCQ"), required=True)
    p.add_argument(
        "--decision",
        choices=list(B_MODES),
        help="Decision location for B (default mpc)",
    )
    p.add_argument("--key", type=Path, required=True)
    p.add_argument("--bank", type=Path, required=True)
    p.add_argument("--reference", required=True)
    p.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.action == "keygen":
        exclusive(args.key, secrets.token_bytes(32))
        return
    x = encode(json.loads(args.bank.read_text())[args.reference])
    if args.decision and args.mode != "B":
        parser.error("--decision applies only to mode B")
    mode = B_MODES[args.decision or "mpc"] if args.mode == "B" else args.mode
    box, roles = prepare(mode, x, args.key.read_bytes())
    args.out.mkdir(mode=0o700)
    exclusive(args.out / "ta.box", box)
    for i, role in enumerate(roles):
        exclusive(args.out / f"party{i}.json", json.dumps(role).encode())
    print(
        json.dumps(
            {
                "mode": args.mode,
                "setting": setting(mode),
                "slot": box[1:17].hex(),
                "reference": args.reference,
            }
        )
    )


if __name__ == "__main__":
    main()
