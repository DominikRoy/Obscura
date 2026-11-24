# Obscura A, B and C on Orin Nano

The [four-setting Jetson runbook](DECISION_TRIALS.md) runs A, B-linux, B-tee and B-mpc plus the C/Q extraction comparison.

All three experiments start with an enrolled 128-coordinate SFace reference **x**. During verification, Linux prepares one incoming probe image and the experiment TA computes **y**. The default runner opens a real OP-TEE session. Use the explicitly named native backend only for workstation validation.

| Configuration | Extraction | Final decision |
| --- | --- | --- |
| [A](A/README.md) | FP32 SFace entirely on the secure CPU | Plaintext CondEval predicate inside the TA |
| [B](B/README.md) | Same FP32 path, followed by dealer-provisioned masking | Two semi-honest parties using dealer correlations and function secret sharing (FSS) |
| [C](C/README.md) | One blinded and verified 1×1 convolution on the normal-world GPU, remaining SFace steps on the secure CPU | Same two parties and arithmetic as B |
| Q, experimental control | Same quantized convolution as C on the secure CPU | Same two parties and arithmetic as B |

## Inputs and trust

On the dealer, the DroneFace example reads only the **gallery** key from the stored embedding bank as x. The DroneFace pair file places the gallery first and the probe second. The online runner reads the **probe image**. It never accepts a saved raw y vector. Linux sees the file and aligned crop in this camera simulation. Protecting the frame from a compromised Linux host requires trusted camera input.

The dealer knows enrollment x and the full one-use mask delta_y. Trust it to keep setup secrets and remain separate from the online roles. An entity that sees both the full mask and the masked vector can recover the encoded probe. The TA and dealer share an AES-256 commissioning key. The lab bootstrap assumes a trusted OS and operator at initial commissioning. Deliver the key through a trusted temporary medium or equivalent controlled channel and keep its permanent copy at the dealer. The TA stores its copy privately using exclusive create. Do not leave a dealer workspace or either party's counterpart material on the operational drone.

Use the release's development signing key only for laboratory deployment. Hardware-backed rollback protection and attested secure input/provisioning require a deployment-specific assessment. A signed TA and a successful session establish execution evidence at a different level from remote attestation. REE-backed secure storage is susceptible to rollback by a hostile host. The build accepts `EXPERIMENT_RPMB=y` on a platform with provisioned RPMB; confirm support before using it. Snapshot restoration of the default storage invalidates the one-use confidentiality assumption.

## Install on your Jetson

Run from the repository on the Jetson with the existing dataset environment and R35.5.0 OP-TEE installation. The prebuilt bundle contains the distinct experiment TA, AArch64 client bridge, and CUDA 11.4 SM87 worker. It contains no templates or keys. Keep the existing benchmark TA installed.

```bash
cd ~/Documents/Obscura/jetson_benchmark
source .dataset-venv/bin/activate
cd experiments
(cd prebuilt && sha256sum -c SHA256SUMS)
tar -xzf prebuilt/orin-r35.5.0.tar.gz
sudo install -m 0644 build/ta/85fe4e6b-839b-4024-8474-00c4de898504.ta /lib/optee_armtz/
```

If the generated model files are missing, extract them from the original benchmark bundle from the experiments directory.

```bash
tar -C .. -xzf ../dist/jetson_sface_r35.5.0.tar.gz --strip-components=1 jetson_benchmark/secure_sface/generated
```

On the trusted dealer, create a private key once. On the Jetson, perform the second command once during trusted commissioning using the securely delivered 32-byte key file. A second attempt to initialize the same TA fails by design. Set `COMMISSIONING_KEY` to the actual temporary path in your environment.

```bash
# Dealer
umask 077
mkdir -p lab
python setup_slot.py keygen lab/dealer.key

# Jetson during commissioning only
python run.py --commission "$COMMISSIONING_KEY"
```

Follow [A](A/README.md) for the first decision. Then run [B](B/README.md) and [C](C/README.md) on the same pair. Use fresh setup slots for every B/C/Q trial, including warmups and retries. Both online parties need the TNO communication dependency from `python -m pip install -r B/requirements.txt` in the experiments directory. The peer also needs the repository's Python source. It can run on a second machine without a TEE or CUDA.

## Measurements

`run.py --power` uses the existing 100 ms VDD_IN sampler. Use the same working single-terminal sampler PATH as in your baseline if privileged telemetry is required. Use a new output directory. The application resets its mode for each new session.

| Output | Window or content |
| --- | --- |
| `setup_seconds`, `module_setup_j` | TA setup from consuming the enrollment/slot box through trusted preprocessing. Includes C's blinding-correction computation. Dealer generation is separate. |
| `crop_to_ta_result_ms` | Prepared crop through A's local decision or B/C/Q's authenticated masked packet. |
| `crop_to_decision_ms`, `module_crop_to_decision_j` | Prepared crop through the decision, including the online MPC exchange and decision acknowledgment for B/C/Q. Session open, image alignment, peer connection and setup are outside the window. |
| `summary.json`, `power.csv` | Decision, timing, energy quality, application-level communication, and raw module-power trace when enabled. Power totals apply to the drone module. |
| `masked_packet.bin` | B/C/Q only. 16-byte slot ID, 128 little-endian masked uint64 values, 32-byte HMAC. The file contains neither share nor pad. |

Report setup and online costs separately, include valid sample counts, pair the same probe/reference rows across configurations, and record the Jetson power mode and thermal conditions. An empty energy field carries an explicit coverage reason. The original 5.573 J median measured extraction only under the older TA. Measure A again for a crop-to-decision comparison. Q isolates the effect of changing one layer's arithmetic. The C pilot includes CUDA allocation, weight upload and synchronization in the online window.

## Rebuild and validate

```bash
./build.sh native
python A/oracle.py
python check.py --ppface ../../ppface
```

Install `B/requirements.txt` for the two-process check. The native checks require a C compiler, OpenSSL development headers, NumPy, Pillow and Python cryptography. They execute the same TA dispatcher and FP32 kernels via a test-only OP-TEE API substitute. C uses an independent CPU field-matrix worker in that mode. A standalone public-fixture oracle can inspect the test-host embedding. The hardware library exports only the experiment protocol.

For a source rebuild, supply the R35.5 OP-TEE ARM64 development kit, client header/library export, cross-compiler prefix if building off the Jetson, and Python with the kit's signing dependencies. The original benchmark's `secure_sface/build_r35_5.sh` documents how to generate these SDK directories.

```bash
./build.sh jetson
# On a CUDA 11.4 Orin Nano development system with nvcc on PATH
./build.sh cuda
```

The checked-in prebuilt GPU worker was cross-compiled with NVIDIA's 11.4.315 nvcc and R35.5 AArch64 CUDA runtime headers, targeting SM87 with shared cudart. See [validation results](VALIDATION.md) for the commands, corpus, trust boundaries and outstanding hardware checks.

## Transfer to a Jetson with an existing Obscura checkout

The small workstation overlay in `jetson_benchmark/dist/obscura-abc-r35.5.0.tar.gz` contains these sources, the three guides, the public decision CSV and the prebuilt package. It can be copied directly to the remote Jetson without a Git push. Run the first command on the workstation, substituting the SSH destination, then the remaining commands on the Jetson.

```bash
scp jetson_benchmark/dist/obscura-abc-r35.5.0.tar.gz client@JETSON_HOST:~/
# Jetson
cd ~/Documents/Obscura/jetson_benchmark
tar -xzf ~/obscura-abc-r35.5.0.tar.gz
cd experiments
```

Continue with installation above. The overlay relies on your existing repository's model bundle, dataset code and `libfss/fss.py`. A peer machine can use the same repository and overlay for `B/mpc.py`. Transfer private preprocessing material separately to its intended recipient.
