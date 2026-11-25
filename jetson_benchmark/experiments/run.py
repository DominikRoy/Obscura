"""One frame, one experiment session. Hardware is the default and never falls back."""

import argparse
import asyncio
import contextlib
import ctypes as ct
import hashlib
import json
import resource
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
BENCH = HERE.parent
sys.path.insert(0, str(BENCH))
from power import Tegrastats, frame_energy

from B.mpc import Exchange, consume, peer_pool, setting, verify
from thresholds import DEN, NUMERATORS

PROVISION, SETUP, BEGIN, STEP, FINISH, TILE, OFFLINE, BLIND, ACCEPT, CONTROL = range(
    10, 20
)
DECIDE = 20
CAMERA_BEGIN = 21
FIRST, AFTER, CHANNELS, PIXELS = 53, 56, 512, 196


class Session:
    def __init__(self, native):
        name = "native.so" if native else "bridge.so"
        self.lib = ct.CDLL(str(HERE / "build" / name))
        self.lib.exp_open.argtypes = [ct.POINTER(ct.c_void_p)]
        self.lib.exp_open.restype = ct.c_uint32
        self.lib.exp_call.argtypes = [
            ct.c_void_p,
            ct.c_uint32,
            ct.c_void_p,
            ct.c_size_t,
            ct.c_void_p,
            ct.c_size_t,
        ]
        self.lib.exp_call.restype = ct.c_uint32
        self.lib.exp_close.argtypes = [ct.c_void_p]
        self.lib.exp_close.restype = None
        self.handle = ct.c_void_p()
        rc = self.lib.exp_open(ct.byref(self.handle))
        if rc:
            raise RuntimeError(f"Experiment TA session open failed: 0x{rc:08x}")

    def close(self):
        self.lib.exp_close(self.handle)

    def call(self, cmd, payload=b"", out_len=0):
        data = ct.create_string_buffer(out_len) if out_len else None
        rc = self.lib.exp_call(self.handle, cmd, payload, len(payload), data, out_len)
        if rc:
            raise RuntimeError(f"TA command {cmd} failed: 0x{rc:08x}")
        return data.raw if data is not None else None


class Model:
    def __init__(self, root):
        manifest = json.loads((root / "manifest.json").read_text())
        blob = (root / "weights.bin").read_bytes()
        if hashlib.sha256(blob).hexdigest() != manifest["blob_sha256"]:
            raise ValueError("Weight bundle digest mismatch")
        self.blocks = [
            blob[t["offset"] : t["offset"] + t["size"]] for t in manifest["steps"]
        ]
        self.steps = manifest["steps"]
        self.qw = None

    def setup(self, session, mode):
        if mode not in ("C", "Q"):
            return
        weights = []
        for i in range(FIRST, AFTER):
            step = self.steps[i]
            if step["node"] != "conv_9_conv2d":
                raise ValueError("Unexpected model layout")
            session.call(TILE, self.blocks[i])
            w = np.frombuffer(self.blocks[i], dtype="<f4")[: step["count"] * CHANNELS]
            weights.append(w.reshape(-1, CHANNELS))
        scaled = np.vstack(weights).astype(np.float64) * 256
        self.qw = np.ascontiguousarray(
            np.copysign(np.floor(abs(scaled) + 0.5), scaled), dtype="<i2"
        )
        session.call(OFFLINE)

    def extract(self, session, mode, pixels, worker, *, camera=False):
        session.call(CAMERA_BEGIN if camera else BEGIN, pixels)
        for i, block in enumerate(self.blocks):
            if mode in ("C", "Q") and FIRST <= i < AFTER:
                if i != FIRST:
                    continue
                if mode == "Q":
                    session.call(CONTROL)
                else:
                    blinded = session.call(BLIND, out_len=CHANNELS * PIXELS * 4)
                    session.call(ACCEPT, worker(self.qw, blinded))
            else:
                session.call(STEP, block)
        return session.call(FINISH, out_len=1 if mode == "A" else 1072)


def cpu_worker(weights, blinded):
    x = np.frombuffer(blinded, "<u4").reshape(CHANNELS, PIXELS)
    z = (weights.astype(np.int64) @ x.astype(np.int64)) % 2147483647
    return z.astype("<u4").tobytes()


def cuda_worker():
    lib = ct.CDLL(str(HERE / "build/gpu.so"))
    lib.blinded_conv.argtypes = [ct.c_void_p, ct.c_void_p, ct.c_void_p]
    lib.blinded_conv.restype = ct.c_int

    def compute(weights, blinded):
        z = ct.create_string_buffer(len(blinded))
        rc = lib.blinded_conv(weights.ctypes.data, blinded, z)
        if rc:
            raise RuntimeError(f"CUDA worker failed: {rc}")
        return z.raw

    return compute


async def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--native-key",
        type=Path,
        help="Explicit native test backend with in-process provisioning",
    )
    p.add_argument(
        "--commission",
        type=Path,
        help="One-time trusted hardware key import, then exit",
    )
    p.add_argument("--box", type=Path)
    image = p.add_mutually_exclusive_group()
    image.add_argument(
        "--image", type=Path, help="Use the existing DeepFace dataset preparation"
    )
    image.add_argument(
        "--prepared-bgr", type=Path, help="Packed 112x112 BGR uint8, already prepared"
    )
    image.add_argument("--sealed-frame", type=Path, help="Full camera frame encrypted for this slot")
    p.add_argument("--generated", type=Path, default=BENCH / "secure_sface/generated")
    p.add_argument("--party0", type=Path)
    p.add_argument("--port", type=int, default=61501)
    p.add_argument(
        "--peer-port", type=int, default=61502, help="Peer TNO port on loopback"
    )
    p.add_argument("--power", action="store_true")
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    native = args.native_key is not None
    if args.commission and native:
        p.error("Hardware commissioning uses the hardware backend")
    async with contextlib.AsyncExitStack() as stack:
        session = Session(native)
        stack.callback(session.close)
        if args.commission or native:
            key = (args.commission or args.native_key).read_bytes()
            session.call(PROVISION, key)
            if args.commission:
                print("Commissioned the experiment TA")
                return
        if not args.box or not args.output or not (args.image or args.prepared_bgr or args.sealed_frame):
            p.error("Supply --box, an image input and --output")
        box = args.box.read_bytes()
        camera = bool(box[0] & 0x80)
        if camera != bool(args.sealed_frame):
            p.error("A camera slot requires its own --sealed-frame")
        wire_mode = chr(box[0] & 0x7f)
        profile = "droneface" if wire_mode.islower() else "lfw"
        mode = wire_mode.upper()
        if len(mode) != 1 or mode not in "ABHTCQ" or (mode == "A") != (args.party0 is None):
            p.error(
                "A takes an enrollment box; B, C and Q require matching --party0 material"
            )
        model = Model(args.generated)
        worker = (cpu_worker if native else cuda_worker()) if mode == "C" else None
        if args.party0:
            cfg = json.loads(args.party0.read_text())
            if (
                cfg["role"] != 0
                or cfg["slot"] != box[1:17].hex()
                or cfg["mode"] != mode
                or cfg.get("threshold_profile", "lfw") != profile
            ):
                raise ValueError("Party 0 material does not match the TA box")
        args.output.mkdir(parents=True, exist_ok=False)
        meter = None
        if args.power:
            meter = Tegrastats(interval_ms=100)
            meter.start()
            stack.callback(meter.stop)
        setup_start = time.monotonic()
        session.call(SETUP, box)
        model.setup(session, mode)
        setup_end = time.monotonic()
        if args.party0:
            consume(args.party0, cfg)
            pool = await stack.enter_async_context(
                peer_pool(args.port, "127.0.0.1", args.peer_port)
            )
            print(f"Party 0 ready on TNO loopback port {args.port}", flush=True)
            if (
                await asyncio.wait_for(pool.recv("server", cfg["slot"] + "/ready"), 180)
                != b"ready"
            ):
                raise ValueError("Unexpected peer greeting")
            exchange = Exchange(pool, cfg)
        if args.image:
            from dataset_tee import prepare_face

            crop, _ = prepare_face(args.image)
            pixels = crop.tobytes()
        elif camera:
            pixels = args.sealed_frame.read_bytes()
        else:
            pixels = args.prepared_bgr.read_bytes()
        if not camera and len(pixels) != 112 * 112 * 3:
            raise ValueError("Expected packed 112x112 BGR input")
        start = time.monotonic()
        result = model.extract(session, mode, pixels, worker, camera=camera)
        extracted = time.monotonic()
        timings = {}
        if mode == "A":
            answer = result[0]
        else:
            await asyncio.wait_for(
                pool.send("server", result, cfg["slot"] + "/packet"), 120
            )
            answer = await verify(
                cfg,
                result,
                exchange,
                lambda body: session.call(DECIDE, body, 1)[0],
                timings,
            )
            # Wait until both parties have reconstructed the same final output.
            if await exchange([answer]) != [answer]:
                raise ValueError("Peer decision mismatch")
        end = time.monotonic()
        window = "frame" if camera else "crop"
        report = {
            "input_path": "sealed-sensor-frame" if camera else "host-prepared-crop",
            "mode": "B" if mode in ("H", "T") else mode,
            "setting": setting(mode),
            "threshold_profile": profile,
            "tau_squared": NUMERATORS[profile] / DEN,
            **timings,
            "masked_packet_to_decision_ms": (end - extracted) * 1000
            if args.party0
            else None,
            "transport": "tno.mpc.communication" if args.party0 else None,
            **(exchange.tno_counts() if args.party0 else {}),
            "backend": "native validation" if native else "OP-TEE",
            "gpu_worker": ("CPU test oracle" if native else "CUDA")
            if mode == "C"
            else None,
            "slot": box[1:17].hex(),
            "decision": answer,
            "setup_seconds": setup_end - setup_start,
            ("ciphertext_sha256" if camera else "crop_sha256"): hashlib.sha256(pixels).hexdigest(),
            f"{window}_to_ta_result_ms": (extracted - start) * 1000,
            f"{window}_to_decision_ms": (end - start) * 1000,
            "mpc_rounds": exchange.seq if args.party0 else 0,
            "application_bytes_sent": len(result) + exchange.sent_bytes
            if args.party0
            else 0,
            "application_bytes_received": exchange.received_bytes if args.party0 else 0,
        }
        if camera:
            # frame.box contains 45 bytes of envelope and 4 bytes of dimensions.
            report["memory"] = {
                "inference_workspace_bytes": 6946808,
                "detector_workspace_bytes": 73728,
                "temporary_frame_buffers_bytes": 2 * len(pixels) - 45,
                "configured_ta_heap_bytes": 12 * 1024 * 1024,
                "configured_ta_stack_bytes": 32 * 1024,
                "linux_runner_peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                "persistent_slot_markers_created": int(mode != "A"),
                "persistent_embedding_bytes_written": 0,
            }
        if meter:
            meter.wait_until(end)
            setup_energy = frame_energy(meter.samples, setup_start, setup_end, 100)
            stats = frame_energy(meter.samples, start, end, 100)
            report.update(
                rail=meter.rail,
                **{f"setup_start_from_{window}_s": setup_start - start,
                   f"setup_end_from_{window}_s": setup_end - start},
                module_setup_j=setup_energy["module_extraction_j"],
                setup_energy_status=setup_energy["energy_status"],
                **{f"module_{window}_to_decision_j": stats["module_extraction_j"]},
                energy_status=stats["energy_status"],
                samples=stats["power_samples_in_frame"],
            )
            with (args.output / "power.csv").open("x") as f:
                f.write(f"seconds_from_{window},watts\n")
                for t, w in list(meter.samples):
                    f.write(f"{t - start:.9f},{w}\n")
        if mode != "A":
            (args.output / "masked_packet.bin").write_bytes(result)
        (args.output / "summary.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
