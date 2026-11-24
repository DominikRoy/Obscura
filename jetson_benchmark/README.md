# SFace inference and masking inside OP-TEE

Target: **NVIDIA Orin Nano Developer Kit, Jetson Linux R35.5.0**, the BSP associated with JetPack 5.1.3. The requested path is `jetson_sface.ipynb` → `secure_benchmark.py` → `secure_sface/host` → `secure_sface/ta`.

Start the simulated camera experiment with [frame_extraction_tee.ipynb](frame_extraction_tee.ipynb).
It follows one recorded frame into OP-TEE, then reports time and module energy for
30 individual frames and the fixed secure workspace. The [installation and
measurement guide](DATASET_WORKFLOW.md#one-camera-frame-at-a-time) explains the readings.

For loops over the supplied **LFW and DroneFace datasets**, use
[`dataset_embeddings_tee.ipynb`](dataset_embeddings_tee.ipynb). Its instructions,
analysis of `ppface/pyscripts/Untitled.ipynb`, and the proposed (not yet applied)
Obscura dealer/masking integration are in
[`DATASET_WORKFLOW.md`](DATASET_WORKFLOW.md). It performs SFace inference in the
existing TA for each image and exports masked benchmark records, never raw
features. Face preparation still runs in Linux. These independent-mask records
cannot yet replace Obscura's raw input files or correlated dealer material.

The trusted application executes the complete pinned SFace neural network on the secure CPU, encodes its 128 features and adds a fresh random mask. It returns only the masked vector and timing counters. There is no normal-world inference fallback. The notebook and power sampler stay in Linux.

**Status:** the R35.5.0 build passed the hardware probe on the user's Orin Nano. A synthetic 112×112 crop returned 128 masked coordinates in 1.102 seconds. That probe did not sample power. The dataset notebook adds Linux face preparation and per-image calls to the same TA. Real-image timing and energy measurements for those loops are pending.

## Ready-built package for your board

`dist/jetson_sface_r35.5.0.tar.gz` includes the notebook, generated weights/manifest, AArch64 bridge and signed TA. Copy it to the Jetson and extract it into a new working directory. This package skips the export/build steps below. It uses the development TA signing key from NVIDIA's source bundle; a device configured for another signing key needs a corresponding rebuild/signature.

Your diagnostics confirm `/dev/tee0`, `/dev/teepriv0`, a running `tee-supplicant` and installed `libteec`. The client device is root-only. From the extracted `jetson_benchmark` directory, install the TA and grant a dedicated group access to the client device:

```bash
sudo install -m 0644 secure_sface/ta/91e80c62-c52a-4b3c-93b5-7f874cdc25a4.ta /lib/optee_armtz/
sudo groupadd -f --system obscura-tee
sudo usermod -aG obscura-tee client
sudo chgrp obscura-tee /dev/tee0
sudo chmod 0660 /dev/tee0
```

To preserve the device permission across reboot:

```bash
echo 'SUBSYSTEM=="tee", KERNEL=="tee0", GROUP="obscura-tee", MODE="0660"' | sudo tee /etc/udev/rules.d/99-obscura-tee.rules
sudo udevadm control --reload-rules
```

Log out and back in so the `client` account receives its new group membership. Then run the dependency-free smoke check as `client`:

```bash
python3 secure_sface/probe.py
```

It invokes the actual TA on a synthetic black crop and prints only success, timing and output dimension. It does not measure energy or biometric accuracy. On success, continue with **Step 4** below to run the notebook on your face crop. If `/lib/optee_armtz` is not your supplicant's configured TA directory, use its actual directory. `/dev/teepriv0` remains restricted to the supplicant. No firmware replacement is needed merely to try loading this TA into the running OP-TEE installation.

## Boundary and inputs

```text
Linux/Jupyter                            OP-TEE trusted application
aligned 112x112 BGR crop ----------------> copy input to secure memory
                                          RGB/NCHW conversion
public model weight blocks -------------> copy + SHA-256 verification
                                          SFace FP32 CPU inference
                                          int(feature * 256) modulo 2^64
                                          fresh random pad + modular addition
masked uint64 vector + timing <---------- return only masked features and timing
```

All intermediate activations and the unmasked embedding stay in secure memory. The app has no raw-feature command. The original image is supplied from Linux; camera capture and landmark alignment are **not** protected here. Use an already landmark-aligned 112x112 face crop; resizing a face is not alignment. This measures SFace feature extraction, not a camera/detection pipeline.

This CPU implementation does not use CUDA/TensorRT or normal-world OpenCV inference. The model's 38.7 MB of public weights are streamed in blocks of at most 512 KiB. The TA copies each block into secure memory, checks its SHA-256 against a digest compiled into the TA, and computes using that same copy. A modified block aborts the run and clears state. Model topology and operation order are compiled in.

The two activation buffers plus weight workspace need **6,946,808 bytes**. The TA requests an **8 MiB heap** plus a 16 KiB stack. OP-TEE itself and other TAs need additional secure RAM. Normal-world free RAM does not establish available secure RAM. Increasing `TA_DATA_SIZE` alone does not enlarge the bootloader's secure carveout.

## 1. Check the existing Jetson setup

On the **Jetson**, from this folder:

```bash
python3 check_jetson.py
```

This reads the board/release, `/dev/tee*`, permissions, `tee-supplicant`, `libteec` and the telemetry executable. It makes no system changes. Keep the output if setup fails. Nodes and a running daemon are preliminary checks; opening and invoking this TA is the functional test.

Use NVIDIA's [R35.5.0 OP-TEE guide](https://docs.nvidia.com/jetson/archives/r35.5.0/DeveloperGuide/SD/Security/OpTee.html) and [R35.5.0 downloads](https://developer.nvidia.com/embedded/jetson-linux-r3550). Do not mix an R36/JetPack 6 development kit with this installation. Required components are the matching TA development kit (`export-ta_arm64`), client headers/library (`tee_client_api.h`, `libteec.so`) and AArch64 toolchain. The TA runtime needs floating-point support (`CFG_TA_FLOAT_SUPPORT=y`).

No firmware flashing, fuse programming, daemon replacement or privileged install is performed by the Python scripts. Test the matching hello-world/`xtest` setup before diagnosing the model application. A working experimental TA does not establish production secure-boot policy, remote attestation or physical/side-channel resistance; these depend on the deployment configuration.

## 2. Export the pinned model on a build workstation

Use a separate environment on the build workstation (Python 3.10+ recommended). These export/verification packages are not needed inside the TA or on the Jetson:

```bash
python3 -m venv .port-venv
source .port-venv/bin/activate
python -m pip install numpy onnx onnxruntime
mkdir -p models
curl -fL --retry 3 https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx -o models/face_recognition_sface_2021dec.onnx
python secure_sface/export_model.py models/face_recognition_sface_2021dec.onnx
python secure_sface/verify_native.py models/face_recognition_sface_2021dec.onnx
```

The exporter accepts only SHA-256 `0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79` and rejects other models. It writes `secure_sface/generated/model.h`, `weights.bin` and `manifest.json`. Build the bridge and TA against the **same** generated header. Retain generated files when copying the folder to the Jetson; they are Git-ignored. Model weights retain their [upstream license](https://github.com/opencv/opencv_zoo/tree/main/models/face_recognition_sface).

The original repository has 128-dimensional features but no extraction checkpoint. The supplied paper's SFace citation names a different publication from this OpenCV model. This ports **OpenCV SFace 2021dec**; it does not establish reproduction of the paper's checkpoint or recognition accuracy. Another checkpoint requires a separately validated export/runtime; arbitrary graphs are intentionally rejected.

`verify_native.py` compares a temporary host library with ONNX Runtime on synthetic inputs. For additional verification, use `--images path/to/aligned_face.png ...` (requires OpenCV on the workstation). This numerical test exposes features outside the TEE for comparison and is not the experiment. Floating-point rounding may change a coordinate near a fixed-point boundary.

To exercise parameter validation, altered-weight rejection, call ordering and the inference-to-mask path with a host API substitute (requires a C compiler and OpenSSL development headers):

```bash
python secure_sface/verify_ta_protocol.py
```

The substitute's deterministic randomness is **only** in `secure_sface/tests`. Real TA builds use `TEE_GenerateRandom` and never include those test stubs.

## 3. Build and deploy on the matching BSP

For a reproducible build, download **Driver Package (BSP) Sources** and **Bootlin Toolchain GCC 9.3** from the R35.5.0 release page. Inside `public_sources.tbz2`, extract `Linux_for_Tegra/source/public/nvidia-jetson-optee-source.tbz2`, then extract that nested archive. It contains `optee/optee_os` and `optee/optee_client`. Install the build prerequisites in your workstation environment:

```bash
python -m pip install pyelftools pycryptodome cryptography
PYTHON3=python bash secure_sface/build_r35_5.sh /absolute/path/to/extracted/optee /absolute/path/to/toolchain/bin/aarch64-buildroot-linux-gnu-
```

This tested script builds only the `ta_dev_kit` target, the client library needed for linking, the TA and bridge. It does not rebuild/install firmware, need a StMM image, or change the Jetson. It sets `PLATFORM=tegra`, `PLATFORM_FLAVOR=t234` and float support. The source bundle's full `optee_src_build.sh` workflow is unnecessary for these user-TA artifacts. The generated model files from Step 2 must already exist.

Once the R35.5.0 TA kit and client development files are available, use your actual absolute paths:

```bash
# Build workstation: matching AArch64 cross compiler and TA kit.
make -C secure_sface/ta TA_DEV_KIT_DIR=/absolute/path/to/export-ta_arm64 CROSS_COMPILE=/absolute/path/to/aarch64-toolchain-prefix-

# Jetson: native C compiler and client development export.
make -C secure_sface/host OPTEE_CLIENT_EXPORT=/absolute/path/to/optee-client-export
```

`MODEL_DIR=/absolute/path/to/generated` overrides the generated directory in either build. The real TA build requires actual GlobalPlatform headers/libraries, not the test substitute. The bridge links to `libteec`.

Install `secure_sface/ta/91e80c62-c52a-4b3c-93b5-7f874cdc25a4.ta` into your `tee-supplicant` TA directory, commonly `/lib/optee_armtz`. For that configuration, run on the Jetson after copying the built TA:

```bash
sudo install -m 0644 secure_sface/ta/91e80c62-c52a-4b3c-93b5-7f874cdc25a4.ta /lib/optee_armtz/
```

Use signing configuration accepted by the installed OP-TEE image. Make `libteec.so` visible to the loader and give the notebook account the needed TEE device access. Run one benchmark session at a time initially. The bridge checks the model identifier returned by the TA when opening it.

| Failure code | Next check |
| --- | --- |
| `0xffff0008` (item not found) | TA UUID/file, supplicant search directory/service |
| `0xffff000c` (out of memory) | Secure heap/carveout and other TAs, not Linux free RAM |
| `0xffff000f` (security) | Signing compatibility or modified/mismatched weight blocks |
| `0xffff0007` (bad state) | Interrupted/out-of-order inference; open a fresh session |

## 4. Run the notebook on the Jetson

Keep the Jetson's OpenCV installation for image loading; CUDA support is not needed. Inference uses TA kernels regardless of that OpenCV build.

```bash
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -c 'import cv2; print(cv2.__version__)'
python -m jupyterlab jetson_sface.ipynb
```

Put the aligned input at `images/aligned_face.png`. Select the power rail after inspecting `tegrastats --interval 100`; `VDD_IN` is the initial choice. Stop that manual check with Ctrl-C. If telemetry requires permissions, configure access on the device; the notebook never invokes sudo.

The equivalent command is:

```bash
python secure_benchmark.py --image images/aligned_face.png --output results/secure-01
```

Defaults: 2 warmups, at least 10 measured inferences and at least 30 seconds. `--no-power` disables only energy reporting; inference and masking still require OP-TEE. Missing TA/library support fails without falling back. Choose a new output directory for each run.

## Measurements and outputs

`pipeline_ms` uses a high-resolution monotonic host timer and includes secure preprocessing, model computation, encoding, random masking, weight transfers/hash verification, TEE transitions and buffer clearing. File loading, alignment, session opening and result export are excluded.

TA phase counters separate preprocessing, weight copy/hash, inference kernels, encoding and masking. They use millisecond `TEE_GetSystemTime` counters; summing many short intervals is coarse. A zero phase value is not zero cost. They exclude some framework/transition/clearing overhead and need not sum to `pipeline_ms`.

Energy integrates instantaneous selected-rail power over the repeated loop with trapezoids and interpolated boundaries. It includes idle power, host/TEE activity and measurement overhead. It is not process-only energy or an independent energy measurement of each tiny masking call. Timestamps are host receipt times. Missing rails, too few samples and long gaps fail. Energy per operation divides total joules by completed operations.

Record power mode (`sudo nvpmodel -q`), clock policy, cooling, temperature and background work in `NOTES`. Device/L4T metadata are captured. Repeat whole runs to assess variation; p95 latency is not a confidence interval.

Outputs: `summary.json`, `timings.csv`, `masked_embedding.json` and, when enabled, `power.csv` and `tegrastats.log`. Masked coordinates are decimal strings to retain all 64 bits in JSON. Raw embeddings and pads are never exported by the TA.

## Obscura integration and comparison baselines

Encoding is `q = int(feature * 256) mod 2**64`; masking is `Delta = (q + delta) mod 2**64`. The scale, truncation and ring match the repository's semi-honest path. Each coordinate receives a fresh independent TEE-generated pad, discarded after use. No extra L2 normalization is added.

The experiment does not generate Obscura's correlated dealer shares/triples. Its masked packet cannot directly replace existing dealer material. Provisioning matching shares and protocol state requires additional work; never reuse pads across queries.

`masking_baseline.ipynb`, `benchmark.py` and `optee/` retain the earlier comparison with Linux inference. They **do not meet** the full-TEE requirement. See `BASELINE_README.md` only when deliberately running that comparison.

Sources: [NVIDIA R35.5.0 OP-TEE](https://docs.nvidia.com/jetson/archives/r35.5.0/DeveloperGuide/SD/Security/OpTee.html), [NVIDIA tegrastats](https://docs.nvidia.com/jetson/archives/r35.5.0/DeveloperGuide/AT/JetsonLinuxDevelopmentTools/TegrastatsUtility.html), [OP-TEE TA builds](https://optee.readthedocs.io/en/latest/building/trusted_applications.html).
