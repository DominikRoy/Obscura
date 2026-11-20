import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from secure_benchmark import run_secure_benchmark


class FakeSession:
    """Test-only client substitute; this is never part of experiment selection."""
    metadata = {"model_sha256": "test fixture"}

    def __init__(self, *args, **kwargs):
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.closed = True

    def run(self):
        return [2**64 - 1] * 128, {"inference_ms": 2, "mask_ms": 0}


class SecureWorkflowTests(unittest.TestCase):
    def test_no_normal_world_fallback_on_missing_tee(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "run"
            with patch("secure_benchmark.SecureSFace", side_effect=RuntimeError("TEE unavailable")):
                with self.assertRaisesRegex(RuntimeError, "TEE unavailable"):
                    run_secure_benchmark("unused.png", output=output, power=False)
            self.assertFalse((output / "summary.json").exists())
            self.assertFalse((output / "masked_embedding.json").exists())

    def test_report_and_uint64_export_with_explicit_test_client(self):
        with tempfile.TemporaryDirectory() as folder, patch("secure_benchmark.SecureSFace", FakeSession):
            output = Path(folder) / "run"
            summary = run_secure_benchmark("unused.png", output=output, power=False, seconds=0, iterations=2, warmup=0)
            self.assertEqual(summary["iterations"], 2)
            self.assertIsNone(summary["power"])
            self.assertEqual(summary["timings_ms"]["ta_mask_ms"]["mean"], 0)
            packet = json.loads((output / "masked_embedding.json").read_text())
            self.assertEqual(packet["values"], [str(2**64 - 1)] * 128)

    def test_secure_notebook_has_no_baseline_selection(self):
        notebook = json.loads((ROOT / "jetson_sface.ipynb").read_text())
        sources = []
        for cell in notebook["cells"]:
            if cell["cell_type"] == "code":
                source = "".join(cell["source"])
                compile(source, "secure-notebook-cell", "exec")
                sources.append(source)
        combined = "\n".join(sources)
        self.assertIn("run_secure_benchmark(", combined)
        self.assertNotIn("SoftwareMasker", combined)
        self.assertNotIn("SFaceSource", combined)


if __name__ == "__main__":
    unittest.main()
