"""Sample one Jetson power rail and integrate over the benchmark window."""
from bisect import bisect_left, bisect_right
import math
import re
import subprocess
import threading
import time

POWER = re.compile(r"\b([A-Za-z][A-Za-z0-9_]*)\s+(\d+(?:\.\d+)?)(?:mW)?/(\d+(?:\.\d+)?)(?:mW)?\b")


def parse_power(line):
    # tegrastats gives instantaneous/average mW; use instantaneous only.
    return {name: float(current) / 1000 for name, current, _ in POWER.findall(line)}


def integrate(samples, start, end):
    """Trapezoids with interpolated endpoints; never extrapolate missing data."""
    if end <= start or len(samples) < 2:
        raise ValueError("Need a positive window and at least two power samples")
    if samples[0][0] > start or samples[-1][0] < end:
        raise ValueError("Power samples do not bracket the measurement window")
    energy = 0.0
    for (t0, p0), (t1, p1) in zip(samples, samples[1:]):
        if t1 <= t0 or not all(math.isfinite(x) for x in (t0, t1, p0, p1)):
            raise ValueError("Invalid power samples")
        left, right = max(start, t0), min(end, t1)
        if right <= left:
            continue
        pl = p0 + (p1 - p0) * (left - t0) / (t1 - t0)
        pr = p0 + (p1 - p0) * (right - t0) / (t1 - t0)
        energy += (pl + pr) * 0.5 * (right - left)
    return energy


def frame_energy(samples, start, end, interval_ms):
    """Integrate a single frame against the sorted Linux monotonic power trace."""
    first = bisect_left(samples, (start, -math.inf))
    after = bisect_right(samples, (end, math.inf))
    count = after - first
    # Include just the two boundary samples needed for interpolation. Searching
    # the full trace for every image would be quadratic on the full LFW run.
    left = bisect_right(samples, (start, math.inf)) - 1
    right = bisect_left(samples, (end, -math.inf))
    energy = None
    if left < 0 or right >= len(samples):
        status = "missing boundary sample"
    elif count < 3:
        status = "fewer than three samples inside frame window"
    else:
        segment = samples[left:right + 1]
        gap = max(b[0] - a[0] for a, b in zip(segment, segment[1:]))
        if gap > 3 * interval_ms / 1000:
            status = "gap exceeds three sampling intervals"
        else:
            energy = integrate(segment, start, end)
            status = "measured"
    return {"module_extraction_j": energy, "power_samples_in_frame": count, "energy_status": status}


class Tegrastats:
    def __init__(self, executable="tegrastats", rail="VDD_IN", interval_ms=100):
        if interval_ms < 20:
            raise ValueError("Use a sampling interval of at least 20 ms")
        self.executable, self.rail, self.interval_ms = executable, rail, interval_ms
        self.samples, self.lines = [], []
        self.condition = threading.Condition()
        self.process = None

    def start(self):
        self.process = subprocess.Popen(
            [self.executable, "--interval", str(self.interval_ms)],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1,
        )
        self.thread = threading.Thread(target=self._read, daemon=True)
        self.thread.start()
        try:
            self.wait_until(time.monotonic())
        except BaseException:
            self.stop()
            raise

    def _read(self):
        for line in self.process.stdout:
            timestamp = time.monotonic()
            with self.condition:
                self.lines.append((timestamp, line.rstrip()))
                rails = parse_power(line)
                if self.rail in rails:
                    self.samples.append((timestamp, rails[self.rail]))
                self.condition.notify_all()

    def wait_until(self, timestamp):
        deadline = time.monotonic() + max(5, self.interval_ms / 1000 * 5)
        with self.condition:
            while not self.samples or self.samples[-1][0] < timestamp:
                remaining = deadline - time.monotonic()
                if remaining <= 0 or self.process.poll() is not None:
                    tail = "\n".join(line for _, line in self.lines[-3:])
                    raise RuntimeError(
                        f"No current {self.rail} samples. Check tegrastats permissions/rail name.\n{tail}"
                    )
                self.condition.wait(min(remaining, 0.2))

    def stop(self):
        if self.process is not None:
            if self.process.poll() is None:
                self.process.terminate()  # only this process, never tegrastats --stop
                try:
                    self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait()
            self.thread.join(timeout=3)
            self.process.stdout.close()

    def summary(self, start, end, count):
        samples = list(self.samples)
        if sum(start <= t <= end for t, _ in samples) < 3:
            raise RuntimeError("Too few power samples; increase seconds or iterations")
        relevant = [(a, b) for a, b in zip(samples, samples[1:])
                    if b[0] >= start and a[0] <= end]
        gap = max(b[0] - a[0] for a, b in relevant)
        if gap > max(1.0, self.interval_ms / 1000 * 5):
            raise RuntimeError("Power sampling has a large gap; measurement rejected")
        joules = integrate(samples, start, end)
        return {"rail": self.rail, "energy_j": joules,
                "mean_power_w": joules / (end - start),
                "energy_j_per_operation": joules / count,
                "samples_in_window": sum(start <= t <= end for t, _ in samples),
                "max_sample_gap_s": gap,
                "scope": "selected rail, includes idle power and measurement overhead"}
