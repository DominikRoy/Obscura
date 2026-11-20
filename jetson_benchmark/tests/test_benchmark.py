import json
import struct
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from benchmark import ReplaySource, run_benchmark
from masking import DIMENSION, MODULUS, OpteeMasker, SoftwareMasker, encode
from power import Tegrastats, integrate, parse_power


class MaskingTests(unittest.TestCase):
    def test_missing_real_tee_fails_without_software_fallback(self):
        with self.assertRaisesRegex(RuntimeError, "No software fallback"):
            OpteeMasker("/nonexistent/libobscura_tee.so")

    def test_quantization_negative_truncation_and_wrap(self):
        value = [-1.25, -0.001, 0.001, 1.999] * 32
        expected = [(-320) % MODULUS, 0, 0, 511] * 32
        self.assertEqual(encode(value), expected)

    def test_mask_can_be_recovered_with_known_pad_in_test_only(self):
        q = encode([-1.25, 0.0, 1.0, -0.125] * 32)
        pads = [MODULUS - 1, 1, 2**63, 777] * 32
        with patch("masking.secrets.token_bytes", return_value=struct.pack("<128Q", *pads)):
            masked = SoftwareMasker().mask(q)
        self.assertEqual([(x - p) % MODULUS for x, p in zip(masked, pads)], q)
        self.assertTrue(all(0 <= x < MODULUS for x in masked))

    def test_fresh_masks(self):
        masker = SoftwareMasker()
        self.assertNotEqual(masker.mask([0] * DIMENSION), masker.mask([0] * DIMENSION))

    def test_invalid_input(self):
        for values in [[1] * 127, [float("nan")] * 128, [float("inf")] * 128, [1e30] * 128]:
            with self.assertRaises(ValueError):
                encode(values)


class PowerTests(unittest.TestCase):
    def test_parse_instantaneous_milliwatts_both_formats(self):
        self.assertEqual(parse_power("RAM 100/1000MB VDD_IN 5000mW/4500mW VDD_CPU_GPU_CV 2000mW/1900mW"),
                         {"VDD_IN": 5.0, "VDD_CPU_GPU_CV": 2.0})
        self.assertEqual(parse_power("POM_5V_IN 6000/5500"), {"POM_5V_IN": 6.0})

    def test_constant_power_and_boundary_interpolation(self):
        self.assertAlmostEqual(integrate([(0, 5), (1, 5), (2, 5)], 0.25, 1.75), 7.5)
        self.assertAlmostEqual(integrate([(0, 0), (2, 4)], 0.5, 1.5), 2.0)

    def test_missing_boundaries_rejected(self):
        with self.assertRaises(ValueError):
            integrate([(1, 5), (2, 5)], 0, 2)

    def test_gap_and_too_few_samples_rejected(self):
        monitor = Tegrastats()
        monitor.samples = [(0, 5), (1, 5)]
        with self.assertRaises(RuntimeError):
            monitor.summary(0.1, 0.9, 5)
        monitor.samples = [(0, 5), (0.1, 5), (2.1, 5), (2.2, 5), (2.3, 5)]
        with self.assertRaises(RuntimeError):
            monitor.summary(0, 2.3, 5)

    def test_real_subprocess_sampling_and_cleanup(self):
        with tempfile.TemporaryDirectory() as folder:
            executable = Path(folder) / "fake-tegrastats"
            executable.write_text("#!/usr/bin/env python3\nimport time\nwhile True:\n print('VDD_IN 5000mW/4000mW', flush=True)\n time.sleep(0.02)\n")
            executable.chmod(0o700)
            monitor = Tegrastats(str(executable), interval_ms=20)
            monitor.start()
            try:
                start = time.perf_counter()
                time.sleep(0.15)
                end = time.perf_counter()
                monitor.wait_until(end)
            finally:
                monitor.stop()
            summary = monitor.summary(start, end, 10)
            self.assertAlmostEqual(summary["mean_power_w"], 5)
            self.assertAlmostEqual(summary["energy_j"], 5 * (end - start))
            self.assertIsNotNone(monitor.process.poll())

    def test_missing_rail_fails_and_stops_process(self):
        with tempfile.TemporaryDirectory() as folder:
            executable = Path(folder) / "fake-tegrastats"
            executable.write_text("#!/usr/bin/env python3\nprint('VDD_OTHER 5000/4000', flush=True)\n")
            executable.chmod(0o700)
            monitor = Tegrastats(str(executable))
            with self.assertRaisesRegex(RuntimeError, "VDD_IN"):
                monitor.start()
            self.assertIsNotNone(monitor.process.poll())


class WorkflowTests(unittest.TestCase):
    def test_replay_export_contains_no_raw_features_or_pads(self):
        with tempfile.TemporaryDirectory() as folder:
            source = ReplaySource(ROOT.parent / "data/embeddings_droneface_raw_sface11.txt")
            output = Path(folder) / "run"
            result = run_benchmark(source, SoftwareMasker(), iterations=5, seconds=0, warmup=1,
                                   power=False, output=output)
            self.assertEqual(result["iterations"], 5)
            self.assertEqual(result["mode"], "existing_embedding_mask_only")
            self.assertFalse(result["inference_inside_tee"])
            self.assertIsNone(result["power"])
            packet = json.loads((output / "masked_embedding.json").read_text())
            self.assertEqual(set(packet), {"format", "dimension", "ring_bits", "scale", "mask_backend", "values"})
            self.assertEqual(len(packet["values"]), 128)
            self.assertTrue(all(isinstance(v, str) and 0 <= int(v) < MODULUS for v in packet["values"]))
            self.assertEqual(len((output / "timings.csv").read_text().splitlines()), 6)
            with self.assertRaises(FileExistsError):
                run_benchmark(source, SoftwareMasker(), iterations=1, seconds=0, power=False, output=output)

    def test_failed_operation_closes_masker(self):
        class BadSource:
            def embedding(self):
                raise ValueError("failure")
        masker = SoftwareMasker()
        with tempfile.TemporaryDirectory() as folder, patch.object(masker, "close") as close:
            with self.assertRaises(ValueError):
                run_benchmark(BadSource(), masker, output=Path(folder) / "run", power=False)
            close.assert_called_once()

    def test_notebook_replay_cells(self):
        notebook = json.loads((ROOT / "masking_baseline.ipynb").read_text())
        self.assertEqual(notebook["nbformat"], 4)
        namespace = {}
        with tempfile.TemporaryDirectory() as folder:
            for cell in notebook["cells"]:
                if cell["cell_type"] != "code":
                    continue
                code = "".join(cell["source"])
                if "OUTPUT = ROOT" in code:
                    namespace.update(MODE="replay", MASK_BACKEND="software", MEASURE_POWER=False,
                                     ITERATIONS=3, SECONDS=0, WARMUP=0)
                    code = code.replace('ROOT / "results"', repr(folder))
                    # Keep Path semantics after changing only the output destination.
                    code = code.replace("OUTPUT = " + repr(folder), "OUTPUT = Path(" + repr(folder) + ")")
                exec(compile(code, "notebook-cell", "exec"), namespace)
            self.assertEqual(namespace["summary"]["iterations"], 3)


if __name__ == "__main__":
    unittest.main()
