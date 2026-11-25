# Jetson comparison for the revised Obscura paper

See the [hardware timing, energy and memory tables](results.md).

The study has two experiments. The extraction experiment compares one image on the Linux CPU and in a real OP-TEE trusted application. The verification experiment starts with the stored FP32 vectors and measures every labeled pair in LFW file 1 (1,000), DroneFace file 9 (2,728) and DroneFace file 11 (1,364). Each of the three protocols evaluates all 5,092 pairs. File 11 is a subset and these counts describe trials, including repeated images.

| Implementation | Mask 128 fixed-point coordinates | Evaluate the two parties’ shares | Reconstruct and decide |
| --- | --- | --- | --- |
| L, original Obscura online arithmetic | Drone Linux, Python | Drone and wireless-device Linux roles | Drone Linux |
| P, TEE masking | Drone TA | Same two Linux roles | Drone Linux |
| R, TEE masking and reconstruction | Drone TA | Same two Linux roles | Drone TA |

Both roles run as separate processes on one Orin Nano Developer Kit using TNO HTTP over loopback. Transport latency is specific to that topology. Linux supplies the stored probe for every protocol. The images, camera transfer and SFace are outside the verification timings.

## From frame to embedding

1. The trusted dealer decodes the selected image as BGR, applies the common sensor envelope, seals the pixels for an experiment slot and records their digest. The Linux control uses the same decoded pixels. File I/O, JPEG decode and camera decryption precede the compared windows.
2. Linux calls `Reference.extract_pixels`, which runs the native `frame_crop`, including face/eye detection, alignment and fallback, then `test_extract`, which calls `sf_input` and all scheduled `sf_step_run` operations. The weights are resident before timing.
3. On the secure path, `Session.call` uses the AArch64 `bridge.so` to invoke `TEEC_InvokeCommand`. The TA starts its timer after frame authentication/decryption, runs the same frame front end, then receives and verifies public weight blocks before running the FP32 kernels. The last step stamps completion with the raw 128-float result still in TA memory. The hardware result includes inter-command elapsed time. The subsequent fixed-point encoding and decision are outside this window.
4. The instrumented TA reads `malloc_get_stats` when private pixels become available and after the final step. The reported peak includes live buffers at the start of the window, including the simulated camera buffers. `TA_DATA_SIZE` and `TA_STACK_SIZE` are configured capacities. Stack high-water, OP-TEE core memory and whole-system peak RAM were not measured. A single image gives a paired observation. Estimating an extraction distribution requires repeated inputs.

Source entry points are [Linux frame extraction](../camera_accuracy.py), [CPU model loop](../A/test_oracle.c), [trusted camera and model commands](../ta/experiment.c), [client bridge](../ta/bridge.c) and [SFace kernels](../../secure_sface/runtime.c).

## From stored probe to decision

1. The dealer takes the first image path as the enrolled reference and the second as the live probe. In DroneFace these are the gallery portrait and the drone photograph. The historical LFW timing dealer reads the two columns in the opposite order. The cosine decision is symmetric, but the reference norm and the identity of the live probe depend on the order.
2. For each pair and each setting, the dealer makes fresh additive shares of two independent mask vectors in the 64-bit ring and coordinatewise correlations for their product and for the squared reference mask. Each role gets the masked reference, its mask shares and its correlation shares. This reproduces the two products actually used by the original online path. The performance fixture omits unused offline FSS keys. The long-term commissioning key stays with the dealer and TA.
3. For P and R the dealer authenticates and encrypts a sequence of distinct slot records with AES-GCM. The TA opens a group once and reserves its identifier in secure storage. `GROUP_NEXT` consumes the next record in order. Abandoning a session burns the remaining records. The paper tables exclude session creation, group authentication, the secure-storage reservation and role preparation from online latency and online energy. The dedicated setup column in the CSV measures the session and group command.
4. Linux calls the repository’s `plain_convert_raw` on the stored probe, computing $q_i=\mathrm{trunc}(256y_i)$. L calls the original Python `vec_add`. P and R call `MASK_STORED`, which privately copies and validates the 128 signed values, computes $Y_i=(q_i+\delta_{y,i})\bmod 2^{64}$, and returns the slot ID, masked coordinates and an HMAC-SHA-256 tag. R also accumulates the probe squared norm here. Mask-command timing includes Python packing/unpacking, the world transition, checks, HMAC and copying.
5. Both Linux roles call the original `Server.getFirstRoundMessage` and `innerProductWithMul`. The drone sends its masked vector to the WD. The WD returns its two additive output shares, one for the inner product and one for the reference squared norm. P and R verify the mask-packet tag at the WD. In R the WD pads the two shares with a one-use pad and authenticates the reply against the slot and packet tag. These integrity operations use OP-TEE's internal cryptographic API and Python’s `hmac`. The baseline uses the original list messages, while P and R use packed authenticated messages.
6. L and P reconstruct the two scalars in Linux and compute the probe norm locally. R invokes `DECIDE` with local shares and the protected WD reply. The TA checks the reply, reconstructs the two scalars, applies the decision and returns one bit. L and P use the original floating reciprocal threshold formula. R uses an integer cross-multiplication for the same thresholds. The report checks every bit against the fixed-point oracle. The squared thresholds are 0.11368578 for LFW and 0.062476 for DroneFace.

The baseline keeps Obscura’s online share functions, ring helpers and message direction. The harness adds timers, moves stored-probe scaling into a separate reported stage, prepares only the correlations used, and factors the mask from the drone’s share evaluation. The Linux predicate can short-circuit on a negative dot product. This is an instrumented implementation of the original protocol, with its own setup and benchmark driver. [Original dealer](../../../obscura-protocol/dealer.py) · [Original parties](../../../obscura-protocol/obscura.py) · [Fixed-point and ring helpers](../../../common/helper.py) · [Measured calls](compare.py) · [TA commands](../ta/experiment.c) · [Setup and MAC implementation](../ta/keys.h)

## Reading the tables

* Per-pair times use the Linux monotonic performance counter. Online latency begins immediately before scaling and ends when the decision is available to the drone. The five disjoint stages are scaling, masking, drone shares, WD round trip and reconstruction/decision. The WD’s own share time is a diagnostic inside the round trip. Stage medians need not sum to the median total.
* VDD_IN measures the entire module. A 100 ms rail interval is too coarse for an individual millisecond verification or a single mask. Each measured batch uses consecutive online verifications after setup. The energy window includes slot activation, Python iteration and normal host activity. Joules per pair equal total measured batch joules divided by the number of covered pairs. Each trace must bracket both endpoints, contain at least three interior samples and meet the existing gap limit. The CSV lists energy coverage separately.
* The isolated masking calibration performs repeated **128-coordinate additions** on synthetic public inputs, reusing warm buffers and small integer offsets. It compares the production Linux Python helper with the compiled C addition loop used by the TA. Three blocks per implementation allow separate amortized arithmetic time and module energy. This experiment excludes protocol authentication, transport and per-probe TEE entry overhead, and measures different languages. It cannot attribute a speed difference solely to TEE placement.
* Under the stated input placement Linux observes both $q$ and $Y$, so it can derive the full live mask as $(Y-q)\bmod 2^{64}$. P still reveals $x\cdot y$ and $x\cdot x$ to drone Linux. R changes where these two scalars are opened. Claims about a compromised host must also specify whether the WD is independent, which inputs can be chosen, whether earlier messages were recorded and how one-use state survives rollback. [Manuscript correction](lemma2.md)

## Reproduce on a commissioned Jetson

Use the R35.5.0 setup, dataset Python environment and model weights from the [Jetson experiment runbook](../README.md). Run the following from `jetson_benchmark/experiments`. The dealer and the Jetson use separate commands. Set `DEALER_KEY` on the trusted workstation to the existing commissioning key. Choose fresh material and output paths for a new independent run.

On the trusted workstation, prepare the two-role **loopback lab fixture** and the sealed extraction frame.

```bash
umask 077
mkdir -p lab
python paper/material.py "$DEALER_KEY" lab/gallery-trial.sqlite
python paper/sface_fresh.py seal "$DEALER_KEY" ../../ppface/lfw/Valeri_Bure/Valeri_Bure_0001.jpg lab/sface-trial
```

The lab reads stored public test embeddings and keeps both role materials on one board. Its outputs establish performance and functionality.

Transfer the generated SQLite file and sealed directory into `experiments/lab/` on the Jetson. That database contains both parties’ benchmark materials. A deployment with separate parties requires separate deliveries. Keep the dealer key on the workstation.

On the Jetson, install the signed TA and build the Linux control.

```bash
source ../.dataset-venv/bin/activate
(cd prebuilt && sha256sum -c SHA256SUMS)
tar -xzf prebuilt/orin-r35.5.0.tar.gz
sudo install -m 0644 build/ta/85fe4e6b-839b-4024-8474-00c4de898504.ta /lib/optee_armtz/
./build.sh plain
mkdir -p ../results/gallery-trial
```

With `VDD_IN` voltage and current readable, run each measurement sequentially and audit the result.

```bash
python paper/sface_fresh.py run ../../ppface/lfw/Valeri_Bure/Valeri_Bure_0001.jpg lab/sface-trial ../results/gallery-trial/sface.json
python paper/mask_cost.py ../results/gallery-trial/mask-energy.json
python paper/compare.py lab/gallery-trial.sqlite ../results/gallery-trial
python paper/report.py ../results/gallery-trial/groups.sqlite ../results/gallery-trial/summary.csv --per-pair ../results/gallery-trial/pairs.csv
```

The runner commits one complete measured group at a time. After interruption, generate a **fresh material database** with the same manifest and point the runner to it with the existing output directory. It skips completed groups and processes outstanding groups with fresh reservations. Retain the inputs, results database and sensor traces locally to audit individual rows. The results database contains timing records and public pair identifiers. Keep the material database separate.

To read the archived hardware results and export one line per verification, run from the same experiments directory.

```bash
gzip -dc paper/pair-traces-jetson1.sqlite.gz > /tmp/obscura-gallery-results.sqlite
python paper/report.py /tmp/obscura-gallery-results.sqlite /tmp/obscura-gallery-summary.csv --per-pair /tmp/obscura-gallery-pairs.csv
```

For a source build, use `./build.sh jetson` with the R35.5 ARM64 TA development kit built with `CFG_WITH_STATS=y`, the OP-TEE client export and the cross compiler. The heap-enabled TA used for the protocol run has SHA-256 `121933284e231bacf49ae33d0df34413b856d7e05ee5ee85d1ab3c823b4c6a7c`. [Cross-build instructions](../JETSON2.md)
