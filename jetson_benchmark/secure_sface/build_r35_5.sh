#!/usr/bin/env bash
# Build user-space artifacts only; never flashes firmware or installs to /lib.
set -euo pipefail
if [[ $# -lt 2 || $# -gt 3 ]]; then
    echo "Usage: $0 /path/to/extracted/optee /path/to/aarch64-buildroot-linux-gnu- [build-directory]" >&2
    exit 2
fi
sf_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
sf_sources="$(cd -- "$1" && pwd)"
sf_cross="$2"
sf_build="${3:-$sf_root/build-r35.5}"
sf_python="${PYTHON3:-python3}"
mkdir -p -- "$sf_build"
sf_build="$(cd -- "$sf_build" && pwd)"
[[ -f "$sf_sources/optee_os/core/arch/arm/plat-tegra/conf.mk" ]]
[[ -f "$sf_sources/optee_client/public/tee_client_api.h" ]]
[[ -f "$sf_root/generated/model.h" ]]
"${sf_cross}gcc" --version
"$sf_python" -c 'import elftools, cryptography, Crypto'

make -C "$sf_sources/optee_os" ta_dev_kit PLATFORM=tegra PLATFORM_FLAVOR=t234 \
    CROSS_COMPILE64="$sf_cross" PYTHON3="$sf_python" CFG_TA_FLOAT_SUPPORT=y \
    O="$sf_build/ta-kit" -j"${JOBS:-4}"
make -C "$sf_sources/optee_client" build-libteec CROSS_COMPILE="$sf_cross" \
    O="$sf_build/client" -j"${JOBS:-4}"
mkdir -p "$sf_build/client-export/include" "$sf_build/client-export/lib"
cp -a "$sf_sources/optee_client/public/." "$sf_build/client-export/include/"
cp -a "$sf_build/client/libteec/"libteec.so* "$sf_build/client-export/lib/"
make -C "$sf_root/ta" TA_DEV_KIT_DIR="$sf_build/ta-kit/export-ta_arm64" \
    CROSS_COMPILE="$sf_cross" PYTHON3="$sf_python"
make -C "$sf_root/host" CC="${sf_cross}gcc" OPTEE_CLIENT_EXPORT="$sf_build/client-export"
echo "Built TA and host/libsecure_sface.so. No target installation was performed."
