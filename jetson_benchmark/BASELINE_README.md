> Comparison only: this path does not meet the requirement for inference inside the TEE. Use README.md and jetson_sface.ipynb for the secure inference path.

# Jetson embedding and masking experiment

Open `masking_baseline.ipynb` to generate a 128-value SFace embedding, measure feature
extraction and masking latency, estimate energy using Jetson power telemetry, and
write the masked embedding to a normal-world JSON file. **Real OP-TEE masking is
required by default**; missing hardware/runtime/TA support fails without a fallback.
This folder is independent
of the existing two-party protocol; it does not alter its data or configuration.

## What runs where

| Mode | SFace and fixed-point encoding | Random mask and addition | Export |
| --- | --- | --- | --- |
| Explicit software baseline | Linux/Python | Linux/Python | Masked vector only |
| Default `OpteeMasker` | Linux/Python | OP-TEE trusted application | Masked vector only |
| Full protected inference | **Not implemented** | Would also be inside TEE | Masked vector only |

Neither implemented mode keeps the original image or embedding secret from the
normal-world OS. Python buffer clearing is not guaranteed secure erasure. The
TA implements the real secure-world transition for masking; it does
not run OpenCV, Python, or CUDA in the TEE. A full design needs an inference runtime
ported to the trusted world and a protected image acquisition path.

The attached paper motivated the experiment, but it is not used as configuration.
The repository has 128-dimensional embedding files but no original extraction
script or model checkpoint. This implementation uses **OpenCV Zoo SFace 2021dec**.
The paper's reference [11] names a different SFace publication; confirm the original
checkpoint before claiming reproduction or reusing verification thresholds.

## Install and open the notebook

On the Jetson, from this folder (Python 3.8+):

```bash
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -c 'import cv2; print(cv2.__version__); print(cv2.getBuildInformation())'
```

Use OpenCV >= 4.8 with `FaceRecognizerSF` and `FaceDetectorYN` for the provided
SFace/YuNet models. If suitable OpenCV is absent, for the **CPU baseline** install:

```bash
python -m pip install 'opencv-contrib-python>=4.8,<5'
```

Pip OpenCV packages should not be assumed to provide CUDA. For GPU runs use a
Jetson-compatible OpenCV build with CUDA DNN enabled. Preserve that build instead
of installing a pip wheel over it. `backend="cuda"` rejects an unavailable CUDA
target; inspect OpenCV warnings for individual layers that may fall back to CPU.

Download the models once (review their licenses in the linked OpenCV directories):

```bash
mkdir -p models images
curl -fL --retry 3 https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx -o models/face_recognition_sface_2021dec.onnx
curl -fL --retry 3 https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx -o models/face_detection_yunet_2023mar.onnx
python -m jupyterlab jetson_sface.ipynb
```

Complete the OP-TEE setup below, put a single-face image at `images/face.jpg`, then
run the notebook cells. Model
hashes are recorded with results because upstream downloads can change. Detection
must find exactly one face. Already landmark-aligned 112x112 crops can use
`aligned=True`; merely resizing a face is not alignment.

## Timing and energy

The default run warms up 10 times, then performs at least 100 iterations and runs
for at least 30 seconds. It separately times feature extraction, fixed-point
encoding and masking, plus their combined latency. Image loading, model loading,
detection/alignment, opening the TEE session and file export are outside the
measurement window. Feature extraction returns a host array before its timer
stops. Preparation time is recorded separately; it is not a repeated benchmark.

Energy covers the whole repeated loop, including Python bookkeeping and sampling
overhead. `tegrastats` supplies instantaneous power in mW; the sampler converts to
watts and uses trapezoidal integration, with interpolated window boundaries.
Joules per operation = measured window energy / completed operations. This is an
estimate for the **selected power rail**, including idle power, not isolated
process energy or an independent energy measurement of each tiny masking call.
Timestamps are host receipt times, not hardware sensor timestamps. Very short
operations require repeated runs; do not interpret a single sub-sample operation
as a direct energy measurement.

Check a few lines of `tegrastats --interval 100` on the Jetson and stop it with
Ctrl-C. Select `VDD_IN` when provided as the input rail, or the appropriate rail
for your model (older devices may expose `POM_5V_IN`). Do not sum an input rail
with component rails. If permission is denied, fix telemetry access on the device;
the notebook does not invoke sudo. A missing executable/rail, too few samples or
a long sampling gap fails the run. `power=False` explicitly runs timing only and
records energy as unavailable, never zero.

Record Jetson model, JetPack/L4T, power mode (`sudo nvpmodel -q`), clock policy,
cooling, temperature and other workloads in the notebook's `NOTES`. Device/L4T
and software versions are captured where available. Use the same settings and
image across CPU/GPU or software/TEE comparisons, and repeat whole runs to assess
variation. The timing p95 is descriptive, not a confidence interval.

Each new results directory contains:

- `summary.json`: timing summaries, energy, mode, software/device metadata.
- `timings.csv`: individual operation timings.
- `power.csv` and `tegrastats.log`: samples including measurement boundaries.
- `masked_embedding.json`: the last masked vector as decimal strings, preserving
  all 64 bits. Read with `[int(v) for v in packet["values"]]`.

Neither raw embeddings nor pads are exported. Inputs still exist in their source
files. Reusing a results path fails rather than overwriting an earlier experiment.

## Masking and relationship to Obscura

For each coordinate: `q = int(embedding * 256) mod 2**64`, then
`Delta = (q + delta) mod 2**64`. Truncation matches `common/helper.py`; the scale
and ring match the semi-honest path in `common/constants.py`. No additional L2
normalization is introduced. Each operation draws a fresh independent 64-bit pad
per coordinate using OS randomness or `TEE_GenerateRandom`.

This is a **masking benchmark**, not a complete verification session. Pads are
discarded after use. The packet cannot be substituted into the existing dealer
files: their masks, shares and multiplication material are correlated. Integrating
with the two-party protocol requires provisioning/deriving matching fresh shares
and correlated material inside the trusted boundary. Never reuse a pad across
queries. This experiment does not implement that provisioning or remote attestation.

## OP-TEE on the Jetson

NVIDIA calls its supported TrustZone environment **OP-TEE**. Open-TEE is a separate
project; the notebook does not install either or flash firmware. Setup depends on
the exact Jetson model and JetPack/L4T release. The NVIDIA r36 guide linked below
applies to Orin devices; use the matching documentation/source release for your
board. Do not assume these instructions apply to a Jetson Nano or a different BSP.

1. Record `cat /etc/nv_tegra_release` and `tr -d '\0' </proc/device-tree/model`.
   Check `ls /dev/tee*` and `pgrep -a tee-supplicant`. These are diagnostics,
   not proof of an established secure boot chain.
2. Follow the matching NVIDIA OP-TEE guide to obtain/build the trusted OS, client
   development headers/library and the **matching TA development kit**. Run its
   hello-world sample (and `xtest` when provided) before using this TA. Missing
   firmware support cannot be fixed with a Python package.
3. Build the TA using that kit/toolchain, and build the normal-world bridge. Example
   paths below are placeholders for your build outputs. Run the host build on the
   Jetson, or explicitly supply its target compiler if cross-compiling:

```bash
make -C optee/ta TA_DEV_KIT_DIR=/absolute/path/to/export-ta_arm64 CROSS_COMPILE=/absolute/path/to/aarch64-toolchain-prefix-
make -C optee/host OPTEE_CLIENT_EXPORT=/absolute/path/to/optee-client-export
```

4. Install `optee/ta/4e2da771-9b3f-47c0-a986-2d8f1b547431.ta` into the TA search
   directory configured for your BSP's `tee-supplicant` (commonly `/lib/optee_armtz`).
   Use the signing configuration required by that BSP. Make `libteec.so` available
   to the loader and give the notebook account the required TEE device access.
5. Leave the notebook's `MASK_BACKEND` set to `"optee"`. It opens one session outside
   the timed loop. Each masking time includes Python/ctypes conversion, the
   `TEEC_InvokeCommand` round trip, TA random generation/addition and output copy.
   Failure is reported; there is no silent software fallback.

The TA accepts 128 fixed-point uint64 values and returns only the masked values.
It copies the input into secure memory and wipes its temporary pad/output buffers.
Its public-login session is appropriate for this experiment; authentication,
provisioning and secure deployment policy remain application-specific. The TA and
bridge must be compiled and validated on your BSP; local tests do not establish
hardware security or actual Jetson performance.

## CLI and local verification

```bash
# SFace inference on Jetson CPU, real OP-TEE masking and power sampling:
python benchmark.py --image images/face.jpg --output results/cpu-01

# Mask an existing repository embedding; explicitly NOT an inference benchmark:
python benchmark.py --embeddings ../data/embeddings_droneface_raw_sface11.txt --mask-backend software --no-power --seconds 0 --iterations 20 --output results/replay-01

# Explicit bridge path, with inference still in normal-world OpenCV:
python benchmark.py --image images/face.jpg --optee-library optee/host/libobscura_tee.so --output results/tee-01

python -m unittest discover -s tests -v
```

## Sources

- [NVIDIA OP-TEE architecture, setup and examples](https://docs.nvidia.com/jetson/archives/r36.3/DeveloperGuide/SD/Security/OpTee.html)
- [NVIDIA tegrastats power units and options](https://docs.nvidia.com/jetson/archives/r36.4.3/DeveloperGuide/AT/JetsonLinuxDevelopmentTools/TegrastatsUtility.html)
- [OpenCV Zoo SFace model and license](https://github.com/opencv/opencv_zoo/tree/main/models/face_recognition_sface)
- [OpenCV Zoo YuNet model and license](https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet)
- [OP-TEE example TA/client build layout](https://github.com/linaro-swg/optee_examples/tree/master/hello_world)
