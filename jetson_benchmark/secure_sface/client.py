"""Normal-world client: input pixels and public weights in; masked vector out."""
import ctypes
import hashlib
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent


class Metrics(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint64) for name in
                ("preprocess_ms", "weights_ms", "inference_ms", "encode_ms", "mask_ms")]


class SecureSFace:
    def __init__(self, image, *, generated=ROOT / "generated", library=ROOT / "host/libsecure_sface.so"):
        import cv2
        self.crop = cv2.imread(str(image))
        if self.crop is None or self.crop.shape != (112, 112, 3):
            raise ValueError("Provide an already landmark-aligned 112x112 face image")
        self.crop = np.ascontiguousarray(self.crop, dtype=np.uint8)
        generated = Path(generated)
        manifest = json.loads((generated / "manifest.json").read_text())
        raw = (generated / "weights.bin").read_bytes()
        if len(raw) != manifest["blob_bytes"] or hashlib.sha256(raw).hexdigest() != manifest["blob_sha256"]:
            raise ValueError("Weight bundle does not match manifest; regenerate the model bundle")
        self.weights = np.frombuffer(raw, dtype=np.uint8)
        try:
            self.lib = ctypes.CDLL(str(Path(library).resolve()))
        except OSError as error:
            raise RuntimeError("Cannot load the secure SFace bridge. Build/deploy secure_sface for R35.5.0. No baseline fallback.") from error
        self.lib.secure_sface_open.argtypes = [ctypes.POINTER(ctypes.c_void_p)]
        self.lib.secure_sface_open.restype = ctypes.c_uint32
        self.lib.secure_sface_close.argtypes = [ctypes.c_void_p]
        self.lib.secure_sface_close.restype = None
        self.lib.secure_sface_model_sha256.argtypes = []
        self.lib.secure_sface_model_sha256.restype = ctypes.c_char_p
        self.lib.secure_sface_run.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t,
                                            ctypes.c_void_p, ctypes.c_size_t,
                                            ctypes.POINTER(ctypes.c_uint64), ctypes.POINTER(Metrics)]
        self.lib.secure_sface_run.restype = ctypes.c_uint32
        if self.lib.secure_sface_model_sha256().decode("ascii") != manifest["model_sha256"]:
            raise ValueError("Bridge and model manifest disagree")
        self.handle = ctypes.c_void_p()
        result = self.lib.secure_sface_open(ctypes.byref(self.handle))
        if result:
            raise RuntimeError(f"Secure SFace TA open failed: 0x{result:08x}. Check deployment, TA heap and secure DRAM. No fallback.")
        self.metadata = {"model_sha256": manifest["model_sha256"], "blob_sha256": manifest["blob_sha256"],
                         "secure_working_bytes": manifest["secure_working_bytes"],
                         "weight_blocks_per_inference": len(manifest["steps"]),
                         "backend": "OP-TEE portable FP32 CPU", "opencv_image_loader": cv2.__version__,
                         "input": "aligned 112x112 BGR pixels; RGB/NCHW conversion inside TA"}

    def run(self):
        if not self.handle:
            raise RuntimeError("Secure SFace session is closed")
        output = (ctypes.c_uint64 * 128)()
        metrics = Metrics()
        result = self.lib.secure_sface_run(self.handle, self.crop.ctypes.data, self.crop.nbytes,
                                         self.weights.ctypes.data, self.weights.nbytes, output, ctypes.byref(metrics))
        if result:
            raise RuntimeError(f"Secure SFace inference failed: 0x{result:08x}; no embedding exported")
        return list(output), {name: int(getattr(metrics, name)) for name, _ in Metrics._fields_}

    def close(self):
        if self.handle:
            self.lib.secure_sface_close(self.handle)
            self.handle = ctypes.c_void_p()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
