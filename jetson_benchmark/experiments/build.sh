#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
dest="$PWD/build"
model="$PWD/../secure_sface"
mkdir -p "$dest"
case "${1:-}" in
  native)
    cc -O2 -ffp-contract=off -fno-strict-aliasing -DEXP_NATIVE -fPIC -shared \
      -I"$model/tests/stubs" -I"$model" -I"$model/generated" -IA -IC -Icamera \
      ta/experiment.c ta/kernels.c camera/frame.c -fno-math-errno -lcrypto -o "$dest/native.so"
    cc -O2 -ffp-contract=off -fPIC -shared -I"$model" -I"$model/generated" \
      A/test_oracle.c "$model/runtime.c" -o "$dest/test_oracle.so" ;;
  jetson)
    : "${TA_DEV_KIT_DIR:?Set TA_DEV_KIT_DIR to the R35.5 ARM64 TA dev kit}"
    : "${OPTEE_CLIENT_EXPORT:?Set OPTEE_CLIENT_EXPORT to the libteec include/lib prefix}"
    make -C ta O="$dest/ta" TA_DEV_KIT_DIR="$TA_DEV_KIT_DIR" CROSS_COMPILE="${CROSS_COMPILE:-}" PYTHON3="${PYTHON3:-python3}"
    "${CROSS_COMPILE:-}gcc" -fPIC -O2 -shared -I"$OPTEE_CLIENT_EXPORT/include" ta/bridge.c \
      -L"$OPTEE_CLIENT_EXPORT/lib" -lteec -o "$dest/bridge.so" ;;
  cuda) nvcc -O2 -arch=sm_87 -Xcompiler=-fPIC --shared C/worker.cu -o "$dest/gpu.so" ;;
  *) echo "Usage: $0 {native|jetson|cuda}" >&2; exit 2 ;;
esac
