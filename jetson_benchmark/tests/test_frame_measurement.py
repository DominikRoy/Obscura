import csv
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dataset_tee import collect_images, write_frame_report
from power import frame_energy, Tegrastats


class FrameMeasurementTests(unittest.TestCase):
    def test_energy_interpolates_only_between_the_frame_markers(self):
        # Linear ramp P(t) = 2 + t with a much larger draw outside the window.
        samples = [(round(i / 10, 1), 2 + i / 10) for i in range(11)]
        samples.extend([(1.1, 90), (1.2, 90)])
        energy = frame_energy(samples, 0.25, 0.95, 100)
        self.assertEqual(energy["power_samples_in_frame"], 7)
        self.assertAlmostEqual(energy["module_extraction_j"], 0.7 * (2 + 0.6))

    def test_summary_excludes_frames_with_missing_or_sparse_power(self):
        meter = Tegrastats()
        meter.samples = [(t / 10, 5) for t in (0, 1, 2, 3, 4, 5, 6, 7, 8, 16, 17, 18)]
        windows = [(0.1, 0.5), (0.5, 0.8), (0.7, 1.7), (1.61, 1.71), (1.7, 2.0)]
        rows = [{"key": str(i), "extraction_start_s": a, "extraction_end_s": b}
                for i, (a, b) in enumerate(windows)]
        with tempfile.TemporaryDirectory() as folder:
            report = write_frame_report(Path(folder), rows, meter, 0, 6946808)
            with (Path(folder) / "frames.csv").open() as stream:
                exported = list(csv.DictReader(stream))
        self.assertEqual(report["frames_with_energy"], 2)
        self.assertAlmostEqual(report["module_extraction_j"]["mean"], 1.75)
        self.assertAlmostEqual(report["module_extraction_j"]["median"], 1.75)
        self.assertEqual([r["module_extraction_j"] for r in exported[2:]], ["", "", ""])
        self.assertEqual(len({r["energy_status"] for r in exported[2:]}), 3)
        self.assertTrue(all(r["secure_workspace_bytes"] == "6946808" for r in exported))

    def test_camera_replay_can_use_a_probe_only_dataset(self):
        with tempfile.TemporaryDirectory() as folder:
            probes = Path(folder) / "DnHFaces/open_data_set/photos_all_faces"
            probes.mkdir(parents=True)
            for name in ["b_gp_3_ef_09.jpg", "a_gp_1_ef_22.jpg"]:
                (probes / name).touch()
            frames, info = collect_images(folder, "droneface", probes_only=True)
            self.assertEqual(info["roles"], {"probe": 2})
            self.assertEqual([frame.subject for frame in frames], ["a", "b"])
