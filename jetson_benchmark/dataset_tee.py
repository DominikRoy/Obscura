"""Dataset SFace extraction inside the existing OP-TEE TA; no raw-feature export.

Only detection/alignment/resize run in Linux. The unchanged TA infers, encodes,
and masks. Its independent pads are discarded: outputs are timing artifacts,
NOT inputs compatible with the current Obscura dealer.
"""
import argparse
from collections import Counter
import csv
from dataclasses import dataclass
import hashlib
from importlib import metadata
import json
from pathlib import Path
import platform
import re
import time

import numpy as np

from power import Tegrastats, frame_energy
from secure_sface.client import ROOT, SecureSFace, validate_crop

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}
DRONE_NAME = re.compile(
    r"^(?P<subject>[a-k]{1,3})_[a-z]+_(?P<height>[0-5]|na)_"
    r"(?P<pose>ef|porf|porl|porr)_(?P<distance>\d{2,3}|na)\.jpe?g$", re.I
)


@dataclass(frozen=True)
class FaceImage:
    key: str
    path: Path
    subject: str
    role: str


def default_ppface():
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "ppface"
        if (candidate / "DnHFaces").is_dir() or (candidate / "lfw").is_dir():
            return candidate
    return Path(__file__).resolve().parents[1] / "ppface"


def select_pair_images(images, pairs):
    """Resolve the legacy four-column verification list against enumerated images."""
    pairs = Path(pairs)
    wanted = set()
    pair_count = 0
    with pairs.open(encoding="utf-8") as source:
        for line_no, line in enumerate(source, 1):
            if not line.strip():
                continue
            fields = line.split()
            if len(fields) != 4 or fields[0] not in {"0", "1"}:
                raise ValueError(f"{pairs}:{line_no}: expected label image1 image2 distance")
            wanted.update(fields[1:3])
            pair_count += 1
    if not wanted:
        raise ValueError(f"No verification pairs in {pairs}")
    missing = wanted.difference(item.key for item in images)
    if missing:
        example = min(missing)
        raise ValueError(f"{pairs}: {len(missing)} image keys outside this selection "
                         f"(for example {example}). Check dataset, gallery and easy-probe filter.")

    # Each logged DroneFace gallery key stands for a mean over the subject's
    # portraits. Include the source photos, keeping one masked result per image.
    gallery_subjects = {item.subject for item in images
                        if item.role == "portrait" and item.key in wanted}
    selected = [item for item in images if item.key in wanted or
                (item.role == "portrait" and item.subject in gallery_subjects)]
    return selected, {"file": pairs.name, "pair_count": pair_count, "unique_keys": len(wanted),
                      "additional_gallery_images": len(selected) - len(wanted)}


def collect_images(ppface, dataset, gallery="trio_cam", easy_probes=False, pairs=None, probes_only=False):
    """Stable ordering and the legacy notebook's ../lfw or ../DnHFaces keys."""
    ppface = Path(ppface).resolve()
    images = []
    ignored = []
    if probes_only and dataset != "droneface":
        raise ValueError("--probes-only selects DroneFace camera frames")
    if dataset == "lfw":
        root = ppface / "lfw"
        if not root.is_dir():
            raise FileNotFoundError(root)
        for subject in sorted(root.iterdir()):
            if subject.is_dir():
                for path in sorted(subject.iterdir()):
                    if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES:
                        images.append(FaceImage("../" + path.relative_to(ppface).as_posix(),
                                                path, subject.name, "image"))
    elif dataset == "droneface":
        if gallery not in ("trio_cam", "trio_gp"):
            raise ValueError("gallery must be trio_cam or trio_gp")
        root = ppface / "DnHFaces/open_data_set"
        folders = [("photos_all_faces", "probe")]
        if not probes_only or pairs is not None:
            folders.insert(0, (gallery, "portrait"))
        for folder, role in folders:
            directory = root / folder
            if not directory.is_dir():
                raise FileNotFoundError(directory)
            for path in sorted(directory.rglob("*")):
                if not path.is_file() or path.suffix.lower() not in IMAGE_SUFFIXES:
                    continue
                match = DRONE_NAME.fullmatch(path.name)
                if not match or (role == "portrait") != match["pose"].lower().startswith("por"):
                    ignored.append(path.relative_to(ppface).as_posix())
                    continue
                if role == "probe" and easy_probes:
                    if match["height"] not in ("3", "4") or match["distance"].lower() == "na" or int(match["distance"]) > 30:
                        continue
                images.append(FaceImage("../" + path.relative_to(ppface).as_posix(),
                                        path, match["subject"].lower(), role))
    else:
        raise ValueError("dataset must be lfw or droneface")
    if not images:
        raise ValueError("No matching images found")
    pair_info = None
    if pairs is not None:
        images, pair_info = select_pair_images(images, pairs)
    if probes_only:
        images = [item for item in images if item.role == "probe"]
        if not images:
            raise ValueError("No DroneFace probe frames in this selection")
    return images, {"dataset": dataset, "images": len(images),
                    "probes_only": probes_only,
                    "pairs": pair_info,
                    "subjects": len({item.subject for item in images}),
                    "roles": dict(Counter(item.role for item in images)),
                    "gallery": gallery if dataset == "droneface" else None,
                    "easy_probes": easy_probes if dataset == "droneface" else False,
                    "ignored_image_names": ignored}


def prepare_face(path):
    """Reproduce the SFace input preparation from DeepFace 0.0.93, without inference.

The old notebook selected represent(...)[0]; use the same first-face policy.
No represent(), recognition model, native feature(), or inference fallback here.
"""
    from deepface.modules import detection, preprocessing

    faces = detection.extract_faces(img_path=str(path), detector_backend="opencv",
                                    enforce_detection=False, align=True,
                                    grayscale=False, expand_percentage=0,
                                    color_face="rgb", normalize_face=True,
                                    anti_spoofing=False)
    if not faces:
        raise ValueError("Face preparation returned no result: " + str(path))
    face = faces[0]
    batch = preprocessing.resize_image(img=face["face"][:, :, ::-1], target_size=(112, 112))
    batch = preprocessing.normalize_input(img=batch, normalization="base")
    # This is the conversion at SFaceClient.forward's input to OpenCV feature().
    # In this program the resulting pixels go to OP-TEE instead.
    crop = validate_crop((batch[0] * 255).astype(np.uint8))
    return crop, {"face_count": len(faces), "selected_face_index": 0,
                  "face_confidence": float(face["confidence"])}


def preprocessing_info():
    try:
        version = metadata.version("deepface")
    except metadata.PackageNotFoundError as error:
        raise RuntimeError("DeepFace is needed ONLY for Linux face preparation; see DATASET_WORKFLOW.md") from error
    if version != "0.0.93":
        raise RuntimeError("This preparation path is pinned to deepface==0.0.93; use the dedicated environment in DATASET_WORKFLOW.md")
    import cv2
    from deepface.modules import detection, preprocessing

    versions = {}
    for package in ("deepface", "tensorflow", "tensorflow-cpu", "keras", "numpy", "Pillow"):
        try:
            versions[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            pass
    sources = {module.__name__: hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()
               for module in (detection, preprocessing)}
    cascade_names = ("haarcascade_frontalface_default.xml", "haarcascade_eye.xml")
    cascades = {}
    for name in cascade_names:
        path = Path(cv2.data.haarcascades) / name
        if path.exists():
            cascades[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return {"versions": versions, "opencv": cv2.__version__, "python": platform.python_version(),
            "source_sha256": sources, "opencv_cascade_sha256": cascades,
            "detector_backend": "opencv", "align": True, "normalization": "base",
            "enforce_detection": False, "multiple_faces": "first returned face, as in original notebook",
            "location": "Linux; input images are not protected by the TEE"}


def write_json(path, value):
    temporary = Path(str(path) + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")
    temporary.replace(path)


def masked_values(values):
    if len(values) != 128 or any(not isinstance(v, int) or isinstance(v, bool) or not 0 <= v < 2**64 for v in values):
        raise ValueError("TA must return exactly 128 uint64 coordinates")
    return [str(v) for v in values]


def describe(values):
    if len(values) == 0:
        return {"mean": None, "median": None, "p95": None}
    return {"mean": float(np.mean(values)), "median": float(np.median(values)),
            "p95": float(np.percentile(values, 95))}


def write_frame_report(output, rows, monitor, start, workspace):
    """Join frame windows to the completed power trace, outside the timed loop."""
    energies = []
    fields = ("frame", "key", "extraction_start_s", "extraction_end_s", "extraction_ms",
              "ta_inference_ms", "ta_weights_ms", "prepare_ms", "pipeline_ms",
              "module_extraction_j", "power_samples_in_frame", "energy_status",
              "secure_workspace_bytes", "secure_persistent_bytes_written")
    temporary = output / "frames.csv.tmp"
    with temporary.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for index, row in enumerate(rows, 1):
            energy = {"module_extraction_j": None, "power_samples_in_frame": 0, "energy_status": "disabled"}
            if monitor is not None:
                energy = frame_energy(monitor.samples, start + row["extraction_start_s"],
                                      start + row["extraction_end_s"], monitor.interval_ms)
                if energy["module_extraction_j"] is not None:
                    energies.append(energy["module_extraction_j"])
            writer.writerow(dict(row, frame=index, secure_workspace_bytes=workspace,
                                 secure_persistent_bytes_written=0, **energy))
    temporary.replace(output / "frames.csv")
    return {"rail": monitor.rail if monitor else None,
            "sampling_interval_ms": monitor.interval_ms if monitor else None,
            "frames": len(rows), "frames_with_energy": len(energies),
            "frames_without_energy": len(rows) - len(energies),
            "module_extraction_j": describe(energies),
            "scope": "Module input energy from SF_BEGIN through the last SF_STEP. Includes secure "
                     "input preparation, weight copies and verification, inference, Linux overhead "
                     "and idle power. SF_FINISH (encoding and masking) follows the window.",
            "secure_memory": {"workspace_bytes": workspace, "raw_embedding_bytes": 128 * 4,
                              "configured_heap_bytes": 8 * 1024**2, "configured_stack_bytes": 16 * 1024,
                              "secure_persistent_bytes_written_per_frame": 0,
                              "basis": "Fixed allocations of this TA build (two activation buffers and "
                                       "one weight buffer), reused for each frame. Total peak RAM is uninstrumented. "
                                       "The TA uses volatile memory for the embedding."}}


def run_dataset(ppface, dataset, output, *, gallery="trio_cam", easy_probes=False, pairs=None,
                limit=None, offset=0, warmup=2, power=True, interval_ms=100,
                profile_extraction=False, probes_only=False,
                generated=ROOT / "generated", library=ROOT / "host/libsecure_sface.so"):
    if offset < 0 or warmup < 0 or (limit is not None and limit < 1):
        raise ValueError("offset/warmup must be nonnegative and limit must be positive")
    images, inventory = collect_images(ppface, dataset, gallery, easy_probes, pairs, probes_only)
    selected = images[offset:] if limit is None else images[offset:offset + limit]
    if not selected:
        raise ValueError("Selected image range is empty")
    prep_info = preprocessing_info()  # dependency checks/imports before opening a run
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    manifest = {"status": "running", "dataset": dataset, "inventory": inventory,
                "selected_images": len(selected), "offset": offset, "limit": limit,
                "warmup": warmup, "preparation": prep_info, "inference_inside_tee": True,
                "input_mode": "Sequential file replay; Linux prepares and supplies one face crop at a time",
                "profile_extraction": profile_extraction,
                "encoding_inside_tee": True, "masking_inside_tee": True,
                "secure_camera_path": False, "obscura_dealer_compatible": False,
                "export": "masked uint64 decimal strings only; no raw embeddings or pads",
                "mask_policy": "existing TA: fresh independent pad per invocation, then discarded",
                "images": [{"key": i.key, "subject": i.subject, "role": i.role} for i in selected]}
    write_json(output / "manifest.json", manifest)
    monitor = Tegrastats(interval_ms=interval_ms) if power else None
    rows = []
    start = None
    try:
        with SecureSFace(generated=generated, library=library) as session:
            manifest["secure_model"] = session.metadata
            # Warm the real TA using the first prepared image; results are discarded.
            if warmup:
                initial_crop, _ = prepare_face(selected[0].path)
                for _ in range(warmup):
                    session.run(initial_crop)
            if monitor:
                monitor.start()
            start = time.monotonic()
            batch_power_error = None
            try:
                with (output / "records.jsonl").open("x") as records:
                    for index, item in enumerate(selected):
                        before_prepare = time.monotonic()
                        source_hash = hashlib.sha256(item.path.read_bytes()).hexdigest()
                        crop, face_info = prepare_face(item.path)
                        before_tee = time.monotonic()
                        if profile_extraction:
                            values, metrics, window = session.run_profiled(crop)
                        else:
                            values, metrics = session.run(crop)
                        after_tee = time.monotonic()
                        row = {"key": item.key, "source_sha256": source_hash,
                               "prepared_bgr_sha256": hashlib.sha256(crop.tobytes()).hexdigest(),
                               "subject": item.subject, "role": item.role, **face_info,
                               "prepare_ms": (before_tee - before_prepare) * 1000,
                               "pipeline_ms": (after_tee - before_tee) * 1000,
                               "sample_ms": (after_tee - before_prepare) * 1000,
                               **{"ta_" + k: int(v) for k, v in metrics.items()},
                               "masked_values": masked_values(values)}
                        if profile_extraction:
                            begin, ready = window
                            if not before_tee <= begin < ready <= after_tee:
                                raise RuntimeError("Extraction timestamps fall outside the Linux call window")
                            row.update(extraction_start_s=begin - start, extraction_end_s=ready - start,
                                       extraction_ms=(ready - begin) * 1000)
                        records.write(json.dumps(row, allow_nan=False) + "\n")
                        records.flush()
                        rows.append(row)
                        if (index + 1) % 25 == 0 or index + 1 == len(selected):
                            print(f"{dataset}: {index + 1}/{len(selected)} images completed", flush=True)
                end = time.monotonic()
                if monitor:
                    try:
                        monitor.wait_until(end)
                    except RuntimeError as error:
                        if not profile_extraction:
                            raise
                        batch_power_error = str(error)
            finally:
                if monitor:
                    monitor.stop()
        # Preserve completed masked records even if telemetry validation fails below.
        packet = {"format": "obscura-dataset-masked-benchmark-v1", "dataset": dataset,
                  "dimension": 128, "ring_bits": 64, "scale": 256,
                  "obscura_dealer_compatible": False,
                  "model_sha256": manifest["secure_model"]["model_sha256"],
                  "embeddings": {r["key"]: r["masked_values"] for r in rows}}
        write_json(output / f"masked_embeddings_{dataset}.txt", packet)
        energy = None
        if monitor and batch_power_error is None:
            try:
                energy = monitor.summary(start, end, len(rows))
            except (RuntimeError, ValueError) as error:
                if not profile_extraction:
                    raise
                batch_power_error = str(error)
        timing_keys = [key for key in rows[0] if key.endswith("_ms")]
        summary = {"status": "complete", "dataset": dataset, "images": len(rows),
                   "wall_seconds": end - start, "power": energy,
                   "batch_power_error": batch_power_error,
                   "power_scope": "module rail during image hash/preparation, TEE calls, record writes and progress; excludes imports, session open, warmup and final exports",
                   "timing_scope": "pipeline_ms: host elapsed TEE call incl. weights/hash/transitions; ta_inference_ms: secure neural kernels only, coarse milliseconds",
                   "timings_ms": {key: describe([r[key] for r in rows]) for key in timing_keys},
                   "multiple_face_images": sum(r["face_count"] > 1 for r in rows),
                   "zero_confidence_images": sum(r["face_confidence"] == 0 for r in rows),
                   "obscura_dealer_compatible": False}
        if profile_extraction:
            summary["frame_extraction"] = write_frame_report(
                output, rows, monitor, start, manifest["secure_model"]["secure_working_bytes"])
        write_json(output / "summary.json", summary)
        manifest["status"] = "complete"
        write_json(output / "manifest.json", manifest)
        return summary
    except BaseException as error:
        manifest.update(status="failed", completed_images=len(rows), error=str(error))
        write_json(output / "manifest.json", manifest)
        raise
    finally:
        if monitor and start is not None:
            # Keep evidence even if a sampling-gap check rejects the energy estimate.
            with (output / "power.csv").open("w") as stream:
                stream.write("seconds_from_window_start,watts\n")
                for stamp, watts in monitor.samples:
                    stream.write(f"{stamp - start:.9f},{watts}\n")
            (output / "tegrastats.log").write_text("\n".join(line for _, line in monitor.lines) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ppface", type=Path, default=default_ppface())
    parser.add_argument("--dataset", choices=("lfw", "droneface"), required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--gallery", choices=("trio_cam", "trio_gp"), default="trio_cam")
    parser.add_argument("--easy-probes", action="store_true")
    parser.add_argument("--probes-only", action="store_true", help="Replay only DroneFace probe images")
    parser.add_argument("--profile-extraction", action="store_true",
                        help="Measure each frame up to the completed embedding and write frames.csv")
    parser.add_argument("--pairs", type=Path, help="Extract images used by this Obscura verification list "
                        "(including companion gallery portraits for DroneFace). Default: entire dataset.")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--warmup", type=int, default=2)
    parser.add_argument("--no-power", action="store_true")
    parser.add_argument("--interval-ms", type=int, default=100)
    parser.add_argument("--list-only", action="store_true")
    args = vars(parser.parse_args())
    if args.pop("list_only"):
        _, inventory = collect_images(args["ppface"], args["dataset"], args["gallery"], args["easy_probes"],
                                      args["pairs"], args["probes_only"])
        print(json.dumps(inventory, indent=2))
        return
    if args["output"] is None:
        parser.error("--output is required unless --list-only is used")
    args["power"] = not args.pop("no_power")
    print(json.dumps(run_dataset(**args), indent=2))


if __name__ == "__main__":
    main()
