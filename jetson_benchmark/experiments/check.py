"""Run public native regression checks, including two separate MPC processes."""

import argparse
import asyncio
import ctypes as ct
import hashlib
import json
import os
import socket
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

from A.oracle import ROOT, decision, encode
from B.mpc import distribute, verify
from run import BENCH, DECIDE, HERE, PROVISION, SETUP, Model, Session, cpu_worker
from setup_slot import prepare

BANK = ROOT / "data/embeddings_droneface_raw_sface9.txt"
KEY = "../DnHFaces/open_data_set/trio_cam/k_cam_0_porF_00.jpg"
PROBE = "DnHFaces/open_data_set/photos_all_faces/k_gp_3_ef_27.jpg"


def command(*argv):
    return [sys.executable, *map(str, argv)]


def reference_probe(model, pixels):
    # Independent public-fixture harness calls the pre-existing FP32 primitives.
    native = ct.CDLL(str(HERE / "build/test_oracle.so"))
    native.test_extract.argtypes = [ct.c_void_p, ct.c_void_p, ct.c_void_p]
    native.test_extract.restype = ct.c_int
    y = (ct.c_float * 128)()
    if native.test_extract(pixels, b"".join(model.blocks), y):
        raise RuntimeError("Oracle failed")
    return encode(y)


def checked_pair(roles, packet, ta_check=None):
    async def compare():
        queues = [asyncio.Queue(), asyncio.Queue()]

        async def party(i):
            async def exchange(message):
                await queues[1 - i].put(message)
                return await queues[i].get()

            return await verify(
                roles[i], packet, exchange, ta_check if i == 0 else None
            )

        a, b = await asyncio.gather(party(0), party(1))
        assert a == b
        return a

    return asyncio.run(compare())


def circuit_cases():
    import hmac
    from secrets import token_bytes

    cases = [
        ([0] * 128, [0] * 128),
        ([1] * 128, [-1] * 128),
        ([32767] * 128, [32767] * 128),
        ([-32767] * 128, [32767] * 128),
        ([1] + [0] * 127, [0, 1] + [0] * 126),
    ]
    for x, y in cases:
        slot = token_bytes(16)
        parties, plain = distribute(x, slot, "B")
        dy = struct.unpack("<128Q", plain[:1024])
        public = slot + struct.pack(
            "<128Q", *[(a + b) % (1 << 64) for a, b in zip(y, dy)]
        )
        packet = public + hmac.digest(plain[1024:], public, "sha256")
        assert checked_pair(parties, packet) == decision(x, y)


def run_case(tmp, mode, key_file, bgr, x, profile="lfw"):
    from secrets import token_bytes

    key = key_file.read_bytes()
    box, roles = prepare(mode, x, key, profile)
    folder = tmp / (mode + token_bytes(3).hex())
    folder.mkdir()
    (folder / "box").write_bytes(box)
    cmd = command(
        HERE / "run.py",
        "--native-key",
        key_file,
        "--box",
        folder / "box",
        "--prepared-bgr",
        bgr,
        "--output",
        folder / "result",
    )
    if roles:
        for i, role in enumerate(roles):
            (folder / f"party{i}.json").write_text(json.dumps(role))
        with socket.socket() as probe, socket.socket() as other:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
            other.bind(("127.0.0.1", 0))
            peer_port = other.getsockname()[1]
        cmd += [
            "--port",
            str(port),
            "--peer-port",
            str(peer_port),
            "--party0",
            str(folder / "party0.json"),
        ]
        with subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True) as drone:
            try:
                if "ready" not in drone.stdout.readline():
                    raise RuntimeError("No party 0 listener")
                peer = subprocess.run(
                    command(
                        HERE / "B/mpc.py",
                        folder / "party1.json",
                        "--port",
                        peer_port,
                        "--connect",
                        "127.0.0.1",
                        port,
                    ),
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=45,
                )
                drone.communicate(timeout=45)
                if drone.returncode:
                    raise RuntimeError("Drone failed")
            finally:
                if drone.poll() is None:
                    drone.kill()
        peer_report = json.loads(peer.stdout)
        peer_bit = peer_report["decision"]
    else:
        subprocess.run(cmd, check=True, capture_output=True, timeout=45)
    answer = json.loads((folder / "result/summary.json").read_text())["decision"]
    if not roles:
        return answer, None
    drone_report = json.loads((folder / "result/summary.json").read_text())
    assert drone_report["tno_bytes_sent"] == peer_report["tno_bytes_received"] > 0
    assert drone_report["tno_bytes_received"] == peer_report["tno_bytes_sent"] > 0
    assert (
        drone_report["application_bytes_sent"]
        == peer_report["application_bytes_received"]
        > 1072
    )
    assert (
        drone_report["application_bytes_received"]
        == peer_report["application_bytes_sent"]
        > 0
    )
    assert (
        peer_report["threshold_profile"] == drone_report["threshold_profile"] == profile
    )
    assert peer_bit == answer
    # Only the dealer test harness can combine both shares. Never export y.
    packet = (folder / "result/masked_packet.bin").read_bytes()
    if profile == "droneface":
        wrong_profile = dict(roles[1], threshold_profile="lfw")
        try:
            asyncio.run(verify(wrong_profile, packet, None))
        except ValueError as exc:
            assert "Invalid TA packet" in str(exc)
        else:
            raise AssertionError("Accepted a packet under the wrong dataset threshold")
    z = struct.unpack_from("<128Q", packet, 16)
    y = [(v - a - b) % (1 << 64) for v, a, b in zip(z, roles[0]["dy"], roles[1]["dy"])]
    return answer, [v - (1 << 64) if v >> 63 else v for v in y]


def decision_variants(model, pixels, x, key, *, tamper=False):
    # The test keeps slot material in a single process. The hardware runners
    # deliver party 1's pad and key only to the peer and the trusted TA.
    expected = decision(x, reference_probe(model, pixels))
    for mode in ("H", "T"):
        box, roles = prepare(mode, x, key)
        assert "ta_auth" not in roles[0] and "ta_pad" not in roles[0]
        ta = Session(True)
        try:
            ta.call(SETUP, box)
            packet = model.extract(ta, mode, pixels, None)

            def check(body, session=ta):
                if tamper:
                    bad = bytearray(body)
                    bad[-1] ^= 1
                    body = bytes(bad)
                return session.call(DECIDE, body, 1)[0]

            if tamper and mode == "T":
                try:
                    checked_pair(roles, packet, check)
                except RuntimeError as exc:
                    assert "0xffff000f" in str(exc)
                else:
                    raise AssertionError("Accepted a modified peer share tag")
            else:
                assert checked_pair(roles, packet, check) == expected
            if mode == "T":
                try:
                    ta.call(DECIDE, bytes(80), 1)
                except RuntimeError as exc:
                    assert "0xffff0007" in str(exc)
                else:
                    raise AssertionError("Reused a finished scalar decision")
        finally:
            ta.close()


def rejected_gpu(model, pixels, x, key):
    box, _ = prepare("C", x, key)
    s = Session(True)
    try:
        s.call(PROVISION, key)
        s.call(SETUP, box)
        model.setup(s, "C")

        def corrupt(w, b):
            result = bytearray(cpu_worker(w, b))
            result[0] ^= 1
            return bytes(result)

        try:
            model.extract(s, "C", pixels, corrupt)
        except RuntimeError as e:
            if "command 18 failed: 0xffff000f" not in str(e):
                raise
        else:
            raise AssertionError("Accepted invalid GPU result")
    finally:
        s.close()
    s = Session(True)
    try:
        try:
            s.call(SETUP, box)
        except RuntimeError:
            pass
        else:
            raise AssertionError("Accepted a consumed slot")
    finally:
        s.close()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--ppface", type=Path, default=ROOT / "ppface")
    args = p.parse_args()
    circuit_cases()
    bank = json.loads(BANK.read_text())
    x = encode(bank[KEY])
    with Image.open(args.ppface / PROBE) as im:
        if im.size != (112, 112):
            raise ValueError("Expected original 112x112 public crop")
        pixels = np.asarray(im.convert("RGB"))[:, :, ::-1].tobytes()
    model = Model(BENCH / "secure_sface/generated")
    y = reference_probe(model, pixels)
    with tempfile.TemporaryDirectory() as work:
        tmp = Path(work)
        key = tmp / "key"
        key.write_bytes(os.urandom(32))
        bgr = tmp / "frame"
        bgr.write_bytes(pixels)
        a, _ = run_case(tmp, "A", key, bgr, x)
        b, yb = run_case(tmp, "B", key, bgr, x)
        q, yq = run_case(tmp, "Q", key, bgr, x)
        c, yc = run_case(tmp, "C", key, bgr, x)
        other = encode(bank[KEY.replace("/k_cam", "/c_cam")])
        negative, _ = run_case(tmp, "A", key, bgr, other)
        assert a == b == decision(x, y) and yb == y
        assert c == q == decision(x, yq) and yc == yq
        assert negative == decision(other, y)
        # Pick a public gallery vector whose decision changes for both extractors.
        between = next(
            ref
            for ref in map(encode, bank.values())
            if all(
                decision(ref, probe, "lfw") == 0
                and decision(ref, probe, "droneface") == 1
                for probe in (y, yq)
            )
        )
        for profile, expected in (("lfw", 0), ("droneface", 1)):
            for mode in "AHTBQC":
                answer, _ = run_case(tmp, mode, key, bgr, between, profile)
                assert answer == expected, (profile, mode)
        rejected_gpu(model, pixels, x, key.read_bytes())
        decision_variants(model, pixels, x, key.read_bytes())
        decision_variants(model, pixels, other, key.read_bytes())
        decision_variants(model, pixels, x, key.read_bytes(), tamper=True)
        print(
            json.dumps(
                {
                    "backend": "native; C uses untrusted CPU worker for testing",
                    "probe": PROBE,
                    "crop_sha256": hashlib.sha256(pixels).hexdigest(),
                    "A": a,
                    "B": b,
                    "C": c,
                    "Q": q,
                    "A_other_reference": negative,
                    "fp32_vs_pilot_fixed_coordinates_changed": sum(
                        i != j for i, j in zip(y, yq)
                    ),
                    "B_vs_FP32_coordinates_changed": sum(i != j for i, j in zip(y, yb)),
                    "C_vs_Q_coordinates_changed": sum(i != j for i, j in zip(yc, yq)),
                    "altered_result": "rejected",
                    "slot_replay": "rejected",
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
