"""Compile TA logic against a TEST-ONLY host API substitute; never builds a .ta."""
import argparse
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def verify(generated):
    with tempfile.TemporaryDirectory() as folder:
        executable = Path(folder) / "ta-protocol-test"
        subprocess.run(["cc", "-O2", "-std=c11", "-ffp-contract=off", "-Wall", "-Wextra", "-Werror",
                        "-fsanitize=undefined", "-fno-sanitize-recover=all",
                        "-I" + str(ROOT / "tests/stubs"), "-I" + str(ROOT), "-I" + str(generated),
                        str(ROOT / "runtime.c"), str(ROOT / "ta/secure_ta.c"),
                        str(ROOT / "tests/ta_protocol_test.c"), "-lcrypto", "-o", str(executable)], check=True)
        subprocess.run([str(executable), str(generated / "weights.bin")], check=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generated", type=Path, default=ROOT / "generated")
    verify(parser.parse_args().generated.resolve())
