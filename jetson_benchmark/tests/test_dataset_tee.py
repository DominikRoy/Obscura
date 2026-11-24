import ctypes
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import dataset_tee as workflow
from secure_sface.client import SecureSFace, validate_crop


class TestOnlySession:
    """Only tests substitute the TA; the executable workflow has no such option."""
    metadata = {"model_sha256": "test-only"}
    calls = []
    closed = False

    def __init__(self, **kwargs):
        type(self).calls = []
        type(self).closed = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        type(self).closed = True

    def run(self, crop):
        self.calls.append(int(crop[0, 0, 0]))
        return [2**64 - 1] * 128, dict(preprocess_ms=0, weights_ms=1, inference_ms=2,
                                     encode_ms=0, mask_ms=0)


def prepared(path):
    return np.full((112, 112, 3), int(path.read_text()), np.uint8), {
        "face_count": 1, "selected_face_index": 0, "face_confidence": 0.9}


class DatasetTests(unittest.TestCase):
    def fixture(self, root, name, content="7"):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return path

    def test_collection_roles_case_filters_and_stable_legacy_keys(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for relative in ["trio_cam/a_cam_0_porF_00.JPG", "photos_all_faces/a_gp_4_ef_28.jpg",
                             "photos_all_faces/a_gp_1_ef_40.jpg", "photos_all_faces/unknown.jpg"]:
                self.fixture(root, "DnHFaces/open_data_set/" + relative)
            full, info = workflow.collect_images(root, "droneface")
            easy, _ = workflow.collect_images(root, "droneface", easy_probes=True)
            self.assertEqual(info["roles"], {"portrait": 1, "probe": 2})
            self.assertEqual(len(info["ignored_image_names"]), 1)
            self.assertEqual(len(easy), 2)
            self.assertTrue(full[0].key.startswith("../DnHFaces/"))
            self.fixture(root, "lfw/B/b.jpg")
            self.fixture(root, "lfw/A/a.JPG")
            self.fixture(root, "lfw/A/.DS_Store")
            images, _ = workflow.collect_images(root, "lfw")
            self.assertEqual([i.key for i in images], ["../lfw/A/a.JPG", "../lfw/B/b.jpg"])

    def test_loop_exports_only_masked_coordinates_and_timings(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.fixture(root, "lfw/A/1.jpg", "7")
            self.fixture(root, "lfw/A/2.jpg", "9")
            output = root / "results"
            with patch.object(workflow, "preprocessing_info", return_value={"test": True}), \
                 patch.object(workflow, "prepare_face", side_effect=prepared), \
                 patch.object(workflow, "SecureSFace", TestOnlySession):
                summary = workflow.run_dataset(root, "lfw", output, warmup=1, power=False)
            self.assertEqual(TestOnlySession.calls, [7, 7, 9])
            self.assertTrue(TestOnlySession.closed)
            self.assertEqual(summary["images"], 2)
            self.assertIsNone(summary["power"])
            packet = json.loads((output / "masked_embeddings_lfw.txt").read_text())
            self.assertFalse(packet["obscura_dealer_compatible"])
            self.assertEqual(packet["embeddings"]["../lfw/A/1.jpg"], [str(2**64 - 1)] * 128)
            records = [json.loads(line) for line in (output / "records.jsonl").read_text().splitlines()]
            self.assertEqual(records[0]["ta_inference_ms"], 2)
            for row in records:
                self.assertNotIn("embedding", row)
                self.assertNotIn("pad", row)
            self.assertEqual(json.loads((output / "manifest.json").read_text())["status"], "complete")

    def test_no_fallback_if_tee_unavailable(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.fixture(root, "lfw/A/1.jpg")
            output = root / "results"
            with patch.object(workflow, "preprocessing_info", return_value={}), \
                 patch.object(workflow, "SecureSFace", side_effect=RuntimeError("TEE unavailable")), \
                 patch.object(workflow, "prepare_face") as prepare:
                with self.assertRaisesRegex(RuntimeError, "TEE unavailable"):
                    workflow.run_dataset(root, "lfw", output, power=False)
                prepare.assert_not_called()
            self.assertFalse((output / "masked_embeddings_lfw.txt").exists())
            self.assertEqual(json.loads((output / "manifest.json").read_text())["status"], "failed")

    def test_failed_image_preserves_partial_records_without_complete_output(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.fixture(root, "lfw/A/1.jpg", "7")
            self.fixture(root, "lfw/A/2.jpg", "invalid image")
            output = root / "results"
            with patch.object(workflow, "preprocessing_info", return_value={}), \
                 patch.object(workflow, "prepare_face", side_effect=prepared), \
                 patch.object(workflow, "SecureSFace", TestOnlySession):
                with self.assertRaises(ValueError):
                    workflow.run_dataset(root, "lfw", output, warmup=0, power=False)
            self.assertTrue(TestOnlySession.closed)
            self.assertEqual(len((output / "records.jsonl").read_text().splitlines()), 1)
            self.assertFalse((output / "summary.json").exists())
            self.assertEqual(json.loads((output / "manifest.json").read_text())["completed_images"], 1)

    def test_preparation_uses_first_face_and_bgr_without_recognition(self):
        rgb = np.zeros((112, 112, 3), dtype=np.float64)
        rgb[:, :, 0] = 1
        detection = types.SimpleNamespace(extract_faces=lambda **kwargs: [
            {"face": rgb, "confidence": 0.7}, {"face": rgb * 0, "confidence": 0.8}])
        preprocessing = types.SimpleNamespace(resize_image=lambda img, target_size: img[None],
                                              normalize_input=lambda img, normalization: img)
        modules = types.ModuleType("deepface.modules")
        modules.detection, modules.preprocessing = detection, preprocessing
        with patch.dict(sys.modules, {"deepface": types.ModuleType("deepface"), "deepface.modules": modules}):
            crop, info = workflow.prepare_face("unused.jpg")
        self.assertEqual(list(crop[0, 0]), [0, 0, 255])
        self.assertEqual(info["face_count"], 2)

    def test_client_sends_new_crop_and_rejects_wrong_types(self):
        class Bridge:
            seen = None
            def secure_sface_run(self, handle, pointer, count, weights, weight_size, output, metrics):
                self.seen = ctypes.string_at(pointer, count)
                return 0
        session = SecureSFace.__new__(SecureSFace)
        session.handle = ctypes.c_void_p(1)
        session.crop = np.zeros((112, 112, 3), np.uint8)
        session.weights = np.zeros(1, np.uint8)
        session.lib = Bridge()
        crop = np.full((112, 112, 3), 13, np.uint8)[:, ::-1]
        session.run(crop)
        self.assertEqual(session.lib.seen, crop.tobytes())
        with self.assertRaises(ValueError):
            session.run(crop.astype(np.float32))
        with self.assertRaises(ValueError):
            validate_crop(np.zeros((224, 224, 3), np.uint8))

    def test_export_rejects_raw_float_vectors(self):
        with self.assertRaises(ValueError):
            workflow.masked_values([0.2] * 128)
        with self.assertRaises(ValueError):
            workflow.masked_values([-1] * 128)

    def test_notebook_parses_and_calls_only_secure_dataset_path(self):
        notebook = json.loads((ROOT / "dataset_embeddings_tee.ipynb").read_text())
        sources = []
        for cell in notebook["cells"]:
            if cell["cell_type"] == "code":
                source = "".join(cell["source"])
                compile(source, "dataset-notebook-cell", "exec")
                sources.append(source)
        self.assertIn("run_dataset(", "\n".join(sources))
        self.assertNotIn("DeepFace.represent", "\n".join(sources))


if __name__ == "__main__":
    unittest.main()
