"""Run one real TEE inference on a synthetic black crop. Requires no OpenCV/NumPy."""
import ctypes
import hashlib
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main():
    library = ROOT / "host/libsecure_sface.so"
    manifest = json.loads((ROOT / "generated/manifest.json").read_text())
    raw = (ROOT / "generated/weights.bin").read_bytes()
    if hashlib.sha256(raw).hexdigest() != manifest["blob_sha256"]:
        raise RuntimeError("Weight bundle hash mismatch")
    try:
        lib = ctypes.CDLL(str(library))
    except OSError as error:
        raise RuntimeError("Run this on the AArch64 Jetson with libteec installed") from error
    lib.secure_sface_open.argtypes = [ctypes.POINTER(ctypes.c_void_p)]
    lib.secure_sface_open.restype = ctypes.c_uint32
    lib.secure_sface_close.argtypes = [ctypes.c_void_p]
    lib.secure_sface_close.restype = None
    lib.secure_sface_run.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t,
                                    ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p]
    lib.secure_sface_run.restype = ctypes.c_uint32
    handle = ctypes.c_void_p()
    result = lib.secure_sface_open(ctypes.byref(handle))
    if result:
        raise RuntimeError(f"TA open failed: 0x{result:08x}. Check /dev/tee0 access, TA installation/signing and secure RAM.")
    try:
        crop = (ctypes.c_ubyte * (112 * 112 * 3))()
        weights = (ctypes.c_ubyte * len(raw)).from_buffer_copy(raw)
        output = (ctypes.c_uint64 * 128)()
        metrics = (ctypes.c_uint64 * 5)()
        start = time.perf_counter()
        result = lib.secure_sface_run(handle, crop, len(crop), weights, len(weights), output, metrics)
        elapsed = time.perf_counter() - start
        if result:
            raise RuntimeError(f"Secure inference failed: 0x{result:08x}")
        print(json.dumps({"status": "real TA invocation succeeded", "input": "synthetic black crop, not a biometric accuracy test",
                          "masked_coordinates_returned": len(output), "wall_seconds": elapsed,
                          "ta_phase_ms": dict(zip(["preprocess", "weights", "inference", "encode", "mask"], metrics)),
                          "energy": "not measured by this probe"}, indent=2))
    finally:
        lib.secure_sface_close(handle)


if __name__ == "__main__":
    main()
