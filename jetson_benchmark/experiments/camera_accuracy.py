"""Score public pairs with the native camera/SFace kernels and existing enrollment."""

import argparse
import ctypes as ct
import json
import struct
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import cv2
import numpy as np

from A.oracle import decision, encode
from camera.input import sensor_pixels

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


class Reference:
    def __init__(self, library=None):
        self.lib = ct.CDLL(str(library or HERE / "build/native.so"))
        self.lib.frame_detector_bytes.restype = ct.c_size_t
        self.lib.frame_crop.argtypes = [
            ct.c_void_p,
            ct.c_int,
            ct.c_int,
            ct.c_void_p,
            ct.c_void_p,
            ct.c_size_t,
            ct.c_void_p,
            ct.c_void_p,
            ct.c_void_p,
        ]
        self.model = ct.CDLL(str(library or HERE / "build/test_oracle.so"))
        self.model.test_extract.argtypes = [ct.c_void_p] * 3
        self.blob = (HERE.parent / "secure_sface/generated/weights.bin").read_bytes()

    def extract(self, path):
        pixels = sensor_pixels(path, 640)
        try:
            vector, detected, eyes = self.extract_pixels(pixels)
        except ValueError as exc:
            raise ValueError(f"{exc} on {path}") from exc
        return encode(vector), detected, eyes

    def extract_pixels(self, pixels, *, clock=None):
        w, h = struct.unpack_from("<HH", pixels)
        buffers = [np.empty(802816, np.uint32) for _ in range(2)]
        workspace = ct.create_string_buffer(self.lib.frame_detector_bytes())
        crop = ct.create_string_buffer(112 * 112 * 3)
        info = (ct.c_int * 6)()
        if self.lib.frame_crop(
            pixels[4:],
            w,
            h,
            buffers[0].ctypes.data,
            buffers[1].ctypes.data,
            buffers[0].size,
            workspace,
            crop,
            info,
        ):
            raise ValueError("Camera front end failed")
        if clock is not None:
            clock["crop_ready"] = time.monotonic()
        vector = (ct.c_float * 128)()
        if self.model.test_extract(crop, self.blob, vector):
            raise ValueError("SFace failed")
        return vector, info[0], info[1]


def evaluate(images, workers, notebook_samples=0):
    cv2.setNumThreads(1)
    reference = Reference()
    groups = {}
    data = ROOT / "data"
    cache = {}
    for group, pairs, embeddings, profile in [
        ("lfw1", "veri_test1.txt", "new_emb1.txt", "lfw"),
        (
            "drone9",
            "veri_balanced_cosine9sface.txt",
            "embeddings_droneface_raw_sface9.txt",
            "droneface",
        ),
        (
            "drone11",
            "veri_balanced_cosine11sface.txt",
            "embeddings_droneface_raw_sface11.txt",
            "droneface",
        ),
    ]:
        rows = [line.split()[:3] for line in (data / pairs).read_text().splitlines()]
        if group == "lfw1":
            rows = rows[:1000]
        bank = json.loads((data / embeddings).read_text())
        probes = {p for _, _, p in rows}
        keys = sorted(probes - cache.keys())
        with ThreadPoolExecutor(workers) as pool:
            cache.update(
                zip(keys, pool.map(reference.extract, (images / k[3:] for k in keys)))
            )
        current, stored = Counter(), Counter()
        changed = 0
        for label, gallery, probe in rows:
            x = encode(bank[gallery])
            answer = decision(x, cache[probe][0], profile)
            baseline = decision(x, encode(bank[probe]), profile)
            changed += answer != baseline
            current[int(label), answer] += 1
            stored[int(label), baseline] += 1

        def metrics(counts):
            return dict(
                tn=counts[0, 0],
                fp=counts[0, 1],
                fn=counts[1, 0],
                tp=counts[1, 1],
                accuracy=(counts[0, 0] + counts[1, 1]) / len(rows),
            )

        groups[group] = dict(
            pairs=len(rows),
            unique_probes=len(probes),
            full_frame_fallback=sum(cache[k][1] == 0 for k in probes),
            two_eyes=sum(cache[k][2] >= 2 for k in probes),
            stored=metrics(stored),
            camera=metrics(current),
            decisions_changed=changed,
        )
        if notebook_samples:
            # Explicit workstation reference only; no raw vector is written to disk.
            from deepface import DeepFace

            ordered = sorted(probes)
            sample = np.linspace(
                0, len(ordered) - 1, min(notebook_samples, len(ordered)), dtype=int
            )
            cosines, changed_coords = [], []
            for idx in sample:
                key = ordered[idx]
                legacy = DeepFace.represent(
                    img_path=str(images / key[3:]),
                    model_name="SFace",
                    enforce_detection=False,
                )[0]["embedding"]
                q = np.asarray(encode(legacy), dtype=np.float64)
                y = np.asarray(cache[key][0], dtype=np.float64)
                cosines.append(float(q @ y / (np.linalg.norm(q) * np.linalg.norm(y))))
                changed_coords.append(int(np.count_nonzero(q != y)))
            groups[group]["notebook_comparison"] = dict(
                probes=len(sample),
                exact_quantized_matches=changed_coords.count(0),
                median_different_coordinates=float(np.median(changed_coords)),
                median_quantized_cosine=float(np.median(cosines)),
                minimum_quantized_cosine=min(cosines),
            )
        print(group, groups[group], flush=True)
    return groups


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--images", type=Path, default=ROOT / "ppface")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--notebook-samples",
        type=int,
        default=0,
        help="Also run DeepFace.represent on evenly spaced probes per split",
    )
    args = parser.parse_args()
    result = evaluate(args.images, args.workers, args.notebook_samples)
    with args.output.open("x") as output:
        json.dump(result, output, indent=2)
        output.write("\n")
