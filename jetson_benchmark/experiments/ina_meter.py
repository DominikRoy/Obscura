"""Timestamp Jetson INA3221 voltage and current at sysfs acquisition."""

import bisect
from collections import deque
from pathlib import Path
import threading
import time


class InputRail:
    interval_ms = 100

    def __init__(self, root=Path("/sys/class/hwmon")):
        found = []
        for device in root.glob("hwmon*"):
            if (device / "name").read_text().strip() != "ina3221":
                continue
            for label in sorted(device.glob("in*_label")):
                try:
                    if label.read_text().strip() == "VDD_IN":
                        found.append((device, label.name[2:-6]))
                except PermissionError:
                    continue
        if len(found) != 1:
            raise ValueError("Expected one readable INA3221 VDD_IN label")
        device, channel = found[0]
        self.voltage = device / f"in{channel}_input"
        self.current = device / f"curr{channel}_input"
        self.samples = deque(maxlen=600)
        self.condition = threading.Condition()
        self.shutdown = threading.Event()
        self.error = None

    def __enter__(self):
        self.worker = threading.Thread(target=self._sample, daemon=True)
        self.worker.start()
        self.wait_until(time.monotonic())
        return self

    def __exit__(self, *_):
        self.shutdown.set()
        self.worker.join(2)

    def _sample(self):
        try:
            with self.voltage.open() as v, self.current.open() as c:
                deadline = time.monotonic()
                while not self.shutdown.is_set():
                    begin = time.monotonic()
                    v.seek(0)
                    mv = int(v.readline())
                    c.seek(0)
                    ma = int(c.readline())
                    end = time.monotonic()
                    if mv <= 0 or ma <= 0:
                        raise ValueError(f"Invalid input rail reading {mv} mV, {ma} mA")
                    if end - begin <= 0.020:
                        with self.condition:
                            self.samples.append(
                                ((begin + end) / 2, mv, ma, end - begin)
                            )
                            self.condition.notify_all()
                    deadline += self.interval_ms / 1000
                    if deadline <= end:
                        deadline = end + self.interval_ms / 1000
                    self.shutdown.wait(deadline - end)
        except Exception as exc:
            with self.condition:
                self.error = exc
                self.condition.notify_all()

    def wait_until(self, target):
        with self.condition:
            ok = self.condition.wait_for(
                lambda: self.error or (self.samples and self.samples[-1][0] >= target),
                timeout=5,
            )
            if self.error:
                raise RuntimeError("VDD_IN acquisition failed") from self.error
            if not ok:
                raise TimeoutError("VDD_IN sampling timed out")

    def trace(self, start, end):
        self.wait_until(end)
        with self.condition:
            records = list(self.samples)
        times = [s[0] for s in records]
        left = max(0, bisect.bisect_right(times, start) - 1)
        right = bisect.bisect_left(times, end) + 1
        return records[left:right]
