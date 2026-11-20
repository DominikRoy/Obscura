"""Numerical test on the build host. This is NOT a TEE/performance experiment.

The temporary test harness exposes features solely to compare with ONNX Runtime.
It is never compiled into the TA, whose protocol has no raw-feature command.
"""
import argparse
import ctypes
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import onnxruntime as ort

ROOT = Path(__file__).resolve().parent
HARNESS = r'''
#include <stdlib.h>
#include <string.h>
#include "model.h"
int verify(const unsigned char *crop, const float *blob, float *features) {
    float *a = calloc(SF_BUFFER_FLOATS, sizeof(float));
    float *b = calloc(SF_BUFFER_FLOATS, sizeof(float));
    if (!a || !b) { free(a); free(b); return -1; }
    float *x = a, *y = b;
    sf_input(crop, x);
    for (size_t i = 0; i < SF_STEP_COUNT; ++i)
        if (sf_step_run(&sf_steps[i], blob + sf_steps[i].offset / 4, &x, &y)) {
            free(a); free(b); return -2;
        }
    memcpy(features, x, 128 * sizeof(float));
    sf_wipe(a, SF_BUFFER_FLOATS * sizeof(float));
    sf_wipe(b, SF_BUFFER_FLOATS * sizeof(float));
    free(a); free(b);
    return 0;
}
'''


def verify(model, generated, images=()):
    manifest = json.loads((generated / "manifest.json").read_text())
    raw = (generated / "weights.bin").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == manifest["blob_sha256"]
    for step in manifest["steps"]:
        block = raw[step["offset"]:step["offset"] + step["size"]]
        assert hashlib.sha256(block).hexdigest() == step["sha256"]
    options = ort.SessionOptions()
    options.intra_op_num_threads = 1
    options.log_severity_level = 3
    session = ort.InferenceSession(str(model), options, providers=["CPUExecutionProvider"])
    rng = np.random.default_rng(2103)
    samples = [np.zeros((112, 112, 3), dtype=np.uint8),
               np.full((112, 112, 3), 127, dtype=np.uint8),
               rng.integers(0, 256, (112, 112, 3), dtype=np.uint8),
               np.tile(np.arange(112, dtype=np.uint8)[None, :, None] * 2, (112, 1, 3))]
    if images:
        import cv2
        for path in images:
            crop = cv2.imread(str(path))
            if crop is None or crop.shape != (112, 112, 3):
                raise ValueError("Verification images must be aligned 112x112 BGR crops")
            samples.append(crop)
    with tempfile.TemporaryDirectory() as folder:
        harness = Path(folder) / "verify.c"
        harness.write_text(HARNESS)
        library = Path(folder) / "verify.so"
        subprocess.run(["cc", "-O2", "-std=c11", "-ffp-contract=off", "-Wall", "-Wextra", "-Werror",
                        "-shared", "-fPIC", "-I" + str(ROOT), "-I" + str(generated),
                        str(ROOT / "runtime.c"), str(harness), "-o", str(library)], check=True)
        native = ctypes.CDLL(str(library))
        native.verify.argtypes = [ctypes.c_void_p] * 3
        native.verify.restype = ctypes.c_int
        blob = np.frombuffer(raw, dtype="<f4").copy()
        results = []
        for index, crop in enumerate(samples):
            actual = np.zeros(128, dtype=np.float32)
            if native.verify(crop.ctypes.data, blob.ctypes.data, actual.ctypes.data):
                raise RuntimeError("Native runtime failed")
            nchw = crop[:, :, ::-1].transpose(2, 0, 1)[None].astype(np.float32)
            expected = session.run(None, {"data": nchw})[0].reshape(-1)
            np.testing.assert_allclose(actual, expected, rtol=3e-4, atol=3e-4)
            results.append({"sample": index, "max_abs_error": float(np.max(np.abs(actual - expected))),
                            "cosine": float(np.dot(actual, expected) / (np.linalg.norm(actual) * np.linalg.norm(expected))),
                            "fixed_point_coordinates_different": int(np.count_nonzero(
                                np.trunc(actual.astype(np.float64) * 256) != np.trunc(expected.astype(np.float64) * 256)))})
    report = {"scope": "native CPU numerical validation only; not OP-TEE execution",
              "onnxruntime": ort.__version__, "model_sha256": manifest["model_sha256"],
              "blob_sha256": manifest["blob_sha256"], "rtol": 3e-4, "atol": 3e-4,
              "samples": results}
    (generated / "native_validation.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model", type=Path)
    parser.add_argument("--generated", type=Path, default=ROOT / "generated")
    parser.add_argument("--images", nargs="*", type=Path, default=[])
    args = parser.parse_args()
    verify(args.model, args.generated.resolve(), args.images)
