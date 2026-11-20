"""Notebook/CLI entry point. Inference is always in normal-world OpenCV."""
import argparse
import csv
import hashlib
import json
import platform
import time
from pathlib import Path

import numpy as np

from masking import OpteeMasker, SoftwareMasker, encode
from power import Tegrastats

DEFAULT_TEE_LIBRARY = Path(__file__).resolve().parent / "optee/host/libobscura_tee.so"

def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest() if hasattr(hashlib, "file_digest") else hashlib.sha256(stream.read()).hexdigest()


def device_info():
    info = {"platform": platform.platform(), "python": platform.python_version(),
            "numpy": np.__version__}
    for name, filename in [("jetson_model", "/proc/device-tree/model"),
                           ("l4t_release", "/etc/nv_tegra_release")]:
        path = Path(filename)
        info[name] = path.read_text().strip("\x00\n") if path.exists() else None
    return info


class SFaceSource:
    mode = "sface_inference"

    def __init__(self, image, model, detector=None, backend="cpu", aligned=False):
        import cv2
        self.cv = cv2
        if backend not in ("cpu", "cuda"):
            raise ValueError("backend must be cpu or cuda")
        if backend == "cuda":
            targets = cv2.dnn.getAvailableTargets(cv2.dnn.DNN_BACKEND_CUDA)
            if cv2.dnn.DNN_TARGET_CUDA not in targets:
                raise RuntimeError("This OpenCV build has no CUDA DNN target. Use CPU or a CUDA-enabled build.")
            backend_id, target_id = cv2.dnn.DNN_BACKEND_CUDA, cv2.dnn.DNN_TARGET_CUDA
        else:
            backend_id, target_id = cv2.dnn.DNN_BACKEND_OPENCV, cv2.dnn.DNN_TARGET_CPU
        self.recognizer = cv2.FaceRecognizerSF.create(
            str(model), "", backend_id=backend_id, target_id=target_id)
        frame = cv2.imread(str(image))
        if frame is None:
            raise ValueError("Cannot read input image")
        start = time.perf_counter()
        if aligned:
            if frame.shape[:2] != (112, 112):
                raise ValueError("Aligned input must be a landmark-aligned 112x112 face crop")
            self.crop = frame
        else:
            if detector is None:
                raise ValueError("Provide a YuNet detector, or aligned=True for an already aligned face")
            finder = cv2.FaceDetectorYN.create(
                str(detector), "", (frame.shape[1], frame.shape[0]), 0.9, 0.3, 5000,
                backend_id, target_id)
            _, faces = finder.detect(frame)
            if faces is None or len(faces) != 1:
                raise ValueError("Input must contain exactly one detected face")
            self.crop = self.recognizer.alignCrop(frame, faces[0])
        preparation_ms = (time.perf_counter() - start) * 1000
        self.metadata = {"model": "OpenCV Zoo SFace 2021dec", "model_sha256": digest(model),
                         "detector_sha256": digest(detector) if detector and not aligned else None,
                         "opencv": cv2.__version__, "backend_requested": backend,
                         "preparation_ms": preparation_ms,
                         "input": "pre-aligned crop" if aligned else "YuNet detection + alignment",
                         "normalization": "raw model feature; no added L2 normalization"}

    def embedding(self):
        # feature() returns host data, completing inference/transfers before timing stops.
        return self.recognizer.feature(self.crop).reshape(-1).copy()


class ReplaySource:
    mode = "existing_embedding_mask_only"

    def __init__(self, path, key=None):
        data = json.loads(Path(path).read_text())
        self.value = np.asarray(data[key if key is not None else next(iter(data))], dtype=np.float64)
        encode(self.value)
        self.metadata = {"dataset_sha256": digest(path),
                         "note": "Precomputed embedding; no inference measured"}

    def embedding(self):
        return self.value.copy()


def run_benchmark(source, masker=None, *, iterations=100, seconds=30.0, warmup=10,
                  power=True, rail="VDD_IN", interval_ms=100, tegrastats="tegrastats",
                  output="results/run", notes=""):
    masker = masker if masker is not None else OpteeMasker(DEFAULT_TEE_LIBRARY)
    monitor = None
    rows = []

    def operation():
        t0 = time.perf_counter()
        embedding = source.embedding()
        t1 = time.perf_counter()
        encoded = encode(embedding)
        t2 = time.perf_counter()
        masked = masker.mask(encoded)
        t3 = time.perf_counter()
        # These writes reduce lifetime of these particular buffers only. Python,
        # OpenCV, CUDA and the OS can retain other copies; this is not secure erasure.
        embedding.fill(0)
        for i in range(len(encoded)):
            encoded[i] = 0
        return masked, {"feature_or_replay_ms": (t1 - t0) * 1000,
                        "encode_ms": (t2 - t1) * 1000,
                        "mask_ms": (t3 - t2) * 1000,
                        "pipeline_ms": (t3 - t0) * 1000}

    try:
        if iterations < 1 or warmup < 0 or not np.isfinite(seconds) or seconds < 0:
            raise ValueError("iterations >= 1, warmup >= 0 and finite seconds >= 0 required")
        monitor = Tegrastats(tegrastats, rail, interval_ms) if power else None
        output = Path(output)
        output.mkdir(parents=True, exist_ok=False)
        for _ in range(warmup):
            operation()
        if monitor:
            monitor.start()
        start = time.perf_counter()
        while len(rows) < iterations or time.perf_counter() - start < seconds:
            masked, row = operation()
            rows.append(row)
        end = time.perf_counter()
        if monitor:
            monitor.wait_until(end)
    finally:
        if monitor:
            monitor.stop()
        masker.close()

    energy = monitor.summary(start, end, len(rows)) if monitor else None
    timings = {}
    for name in rows[0]:
        values = np.array([row[name] for row in rows])
        timings[name] = {"mean": float(values.mean()), "median": float(np.median(values)),
                         "p95": float(np.percentile(values, 95)), "min": float(values.min())}
    summary = {"mode": source.mode, "mask_backend": masker.name,
               "inference_inside_tee": False, "masking_inside_tee": masker.name == "optee_mask_only",
               "iterations": len(rows), "warmup": warmup, "wall_seconds": end - start,
               "timings_ms": timings, "power": energy,
               "energy_status": "measured" if power else "disabled; no energy result",
               "device": device_info(), "source": source.metadata, "notes": notes,
               "measurement_scope": "Repeated feature/replay + encoding + mask; excludes model/image loading, detection, alignment, file export and TEE session opening"}
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    with (output / "timings.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    # Decimal strings preserve uint64 precision in JSON readers using IEEE doubles.
    packet = {"format": "obscura-masked-v1", "dimension": 128, "ring_bits": 64,
              "scale": 256, "mask_backend": masker.name,
              "values": [str(x) for x in masked]}
    (output / "masked_embedding.json").write_text(json.dumps(packet, indent=2) + "\n")
    if monitor:
        with (output / "power.csv").open("w", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(["seconds_from_window_start", "watts"])
            writer.writerows((t - start, watts) for t, watts in monitor.samples)
        (output / "tegrastats.log").write_text("\n".join(
            f"{t - start:.9f} {line}" for t, line in monitor.lines) + "\n")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--image", type=Path)
    inputs.add_argument("--embeddings", type=Path, help="Replay only; no inference measured")
    parser.add_argument("--key")
    parser.add_argument("--model", type=Path, default=Path("models/face_recognition_sface_2021dec.onnx"))
    parser.add_argument("--detector", type=Path, default=Path("models/face_detection_yunet_2023mar.onnx"))
    parser.add_argument("--aligned", action="store_true")
    parser.add_argument("--backend", choices=["cpu", "cuda"], default="cpu")
    parser.add_argument("--mask-backend", choices=["optee", "software"], default="optee",
                        help="Real OP-TEE by default; software is an explicit non-TEE baseline")
    parser.add_argument("--optee-library", type=Path, default=DEFAULT_TEE_LIBRARY)
    parser.add_argument("--iterations", type=int, default=100)
    parser.add_argument("--seconds", type=float, default=30)
    parser.add_argument("--warmup", type=int, default=10)
    parser.add_argument("--no-power", action="store_true")
    parser.add_argument("--rail", default="VDD_IN")
    parser.add_argument("--interval-ms", type=int, default=100)
    parser.add_argument("--tegrastats", default="tegrastats")
    parser.add_argument("--output", type=Path, default=Path("results/run"))
    parser.add_argument("--notes", default="")
    args = parser.parse_args()
    source = (ReplaySource(args.embeddings, args.key) if args.embeddings else
              SFaceSource(args.image, args.model, args.detector, args.backend, args.aligned))
    masker = (OpteeMasker(args.optee_library.resolve()) if args.mask_backend == "optee"
              else SoftwareMasker())
    result = run_benchmark(source, masker, iterations=args.iterations, seconds=args.seconds,
                           warmup=args.warmup, power=not args.no_power, rail=args.rail,
                           interval_ms=args.interval_ms, tegrastats=args.tegrastats,
                           output=args.output, notes=args.notes)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
