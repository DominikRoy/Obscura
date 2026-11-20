"""Read-only checks to run ON the target Jetson; does not configure or flash it."""
import ctypes.util
import glob
import json
import os
from pathlib import Path
import shutil
import subprocess


def read(path):
    try:
        return Path(path).read_text().strip("\0\n")
    except OSError:
        return None


def run(args):
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=5)
        return {"returncode": result.returncode, "output": result.stdout.strip()}
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"error": str(error)}


if __name__ == "__main__":
    print(json.dumps({
        "model": read("/proc/device-tree/model"),
        "l4t": read("/etc/nv_tegra_release"),
        "tee_devices": [{"path": p, "readable": os.access(p, os.R_OK), "writable": os.access(p, os.W_OK)}
                        for p in sorted(glob.glob("/dev/tee*"))],
        "tee_supplicant": run(["pgrep", "-a", "-x", "tee-supplicant"]),
        "libteec": ctypes.util.find_library("teec"),
        "tegrastats": shutil.which("tegrastats"),
        "secure_sface_ta_in_common_location": Path("/lib/optee_armtz/91e80c62-c52a-4b3c-93b5-7f874cdc25a4.ta").exists(),
        "note": "Device nodes and daemon presence do not prove secure boot policy or available secure heap. A real TA session is still required."
    }, indent=2))
