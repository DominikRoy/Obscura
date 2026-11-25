"""Score public pairs with the native camera/SFace kernels and existing enrollment."""

import argparse
import ctypes as ct
import json
import struct
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
    def __init__(self):
        self.lib = ct.CDLL(str(HERE / "build/native.so"))
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
        self.model = ct.CDLL(str(HERE / "build/test_oracle.so"))
        self.model.test_extract.argtypes = [ct.c_void_p] * 3
        self.blob = (HERE.parent / "secure_sface/generated/weights.bin").read_bytes()

    def extract(self, path):
        pixels = sensor_pixels(path, 640)
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
            raise ValueError(f"Camera front end failed on {path}")
        vector = (ct.c_float * 128)()
        if self.model.test_extract(crop, self.blob, vector):
            raise ValueError(f"SFace failed on {path}")
        return encode(vector), info[0], info[1]


def evaluate(images, workers):
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
        print(group, groups[group], flush=True)
    return groups


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--images", type=Path, default=ROOT / "ppface")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = evaluate(args.images, args.workers)
    with args.output.open("x") as output:
        json.dump(result, output, indent=2)
        output.write("\n")
