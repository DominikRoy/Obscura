# Jetson comparison for the revised Obscura paper

Start with the [original-code walkthrough](#follow-one-verification-in-the-source), then follow the [Jetson 2 setup, checks and table-generation commands](JETSON2.md). The [Jetson 1 tables](results.md) provide reference measurements.

The study has two experiments. The extraction experiment compares one image on the Linux CPU and in a real OP-TEE trusted application. The verification experiment starts with the stored FP32 vectors and measures every labeled pair in LFW file 1 (1,000), DroneFace file 9 (2,728) and DroneFace file 11 (1,364). Each of the three protocols evaluates all 5,092 pairs. File 11 is a subset and these counts describe trials, including repeated images.

## Follow one image through SFace

1. The trusted workstation calls `sensor_pixels()` to decode the public photo and `seal_frame()` to encrypt and authenticate the simulated camera frame for a single slot. Jetson 1 receives the sealed frame and a copy of the public photo for the matched Linux control. This tests processing from private pixels onward; a dedicated physical camera path is an assumption. [Input and frame format](../camera/input.py) · [Experiment entry point](sface_fresh.py)
2. For the Linux measurement, `Reference.extract_pixels()` calls the C function `frame_crop()` to detect, align and crop a 112 × 112 BGR face. It passes the crop to `test_extract()`, which forms the model input and runs the FP32 SFace weights to produce 128 floats. [Linux call sequence](../camera_accuracy.py#L49) · [FP32 reference](../A/test_oracle.c)
3. For the TEE measurement, `Session(False)` opens the hardware client bridge. `Model.extract()` sends `CAMERA_BEGIN`. The TA's `begin_frame()` authenticates and opens the frame in private memory, records the start time, calls the same `frame_crop()`, then calls `sf_input()`. Linux sends the public model blocks with `STEP`. The TA checks each block and executes the model step on its private activations. After the last step it records embedding readiness. The raw vector stays in the TA. The harness calls `FINISH` to close out the standalone slot after the timing endpoint. [Host commands](../run.py#L145) · [Trusted frame handling and command dispatch](../ta/experiment.c#L315)
4. The host reads the TA's timestamps and heap counters and aligns them with the drone's VDD_IN samples. The table distinguishes face preparation, model forward and total elapsed time. The protocol trials below load the stored probe embedding anew for each pair. This keeps SFace latency separate from online verification latency. [Clock mapping and heap query](../run.py#L67) · [Table generator](report.py)

## Follow one verification in the source

Start with the original drone entry point. It masks the probe, computes the drone's two output shares, and sends the masked probe to the wireless device (WD). The WD evaluates the same two gates with its own shares and sends them back. In the Jetson driver, `one()` shows the same round in order, with timing boundaries and two choices of where to execute an operation. [Original drone round](../../../obscura-protocol/obscura.py#L216) · [Jetson drone round](compare.py#L122) · [Jetson WD round](compare.py#L83)

| Operation | Original Obscura / L | P — TEE masking | R — TEE masking and reconstruction |
| --- | --- | --- | --- |
| Form dealer products for the $xy$ and $xx$ gates | `Dealer.maskProducts` | Same Python function | Same Python function |
| Mask the fixed-point probe | `Server.maskProbe` | TA `MASK_STORED` | Same TA command, also accumulates the probe norm |
| Compute the two output shares on **each** party | `Server.getFirstRoundMessage` → `innerProductWithMul` | Same Python functions | Same Python functions |
| WD reply | Two additive shares | Same two shares | Same two shares, padded and authenticated for the TA |
| Open the two sums and decide | `Server.reconstructDecision` | Same Python function | TA `DECIDE` returns one bit |

The original CLI and Jetson driver import the same party and dealer arithmetic. The Jetson harness adds stored-vector selection, stage timers and slot-tagged TNO messages. Run `dealer.py` with no arguments for the original per-pair pickle files, which include additional FSS material. Run `dealer.py jetson` for the distributed paper experiment. It writes one versioned pickle per role covering L, P and R. Each pickle holds the masked gallery and its role’s share material. The drone delivery also carries sealed TA batches for P and R. Each role indexes its own delivery in memory before timing. The packet carrying the masked probe is created online. Existing SQLite inputs from the measured release are accepted. The results database stores timings, decisions and rail samples. [Pickle layout and reader](role_pickle.py) L sends the original list representation. P and R add authenticated packet handling. R evaluates the threshold in compiled C using integer cross-multiplication. [Original dealer](../../../obscura-protocol/dealer.py#L84) · [Jetson material](material.py#L43) · [Original Linux decision](../../../obscura-protocol/obscura.py#L221) · [TA masking and reconstruction](../ta/experiment.c) · [TA threshold](../A/decision.h)

The archived measurements ran both roles on one Orin Nano Developer Kit using TNO HTTP over loopback. The [two-board runner](two_board.py) calls the same drone and WD round functions from separate processes on different boards. See the [wireless-device runbook](JETSON2.md) for the dealer deliveries, SSH transport and table generator. Linux supplies the stored probe in all three protocols. Images, camera transfer and SFace are outside the verification timings.

### Read one original multiplication gate

1. **Enrollment and setup.** The first path in a paper pair names the enrolled gallery vector $x$, the second the live probe $y$. The historical CLI uses the reverse ordering for its original fixtures. The dealer chooses masks $a=\delta_x$ and $b=\delta_y$ and forms $X=x+a$ coordinatewise. Each party gets $X$, one additive share of each mask, and one share of each coordinatewise product $ab$ and $a^2$. Both dealer entry points call `Dealer.shareInputGates`. The original `gen_SS_tuple` produces each input mask and its two shares; `gen_SS_with_Val` shares each coordinatewise product. Fresh role pickles contain the appropriate share columns. Version 1 seed-based inputs remain readable. Two shares of a value add back to it modulo $2^{64}$. In the original source these four share arrays are `in_s`, `in_v`, `s_v`, and `s_s`. The paper fixture's `server()` loads those same circuit fields. [Original setup](../../../obscura-protocol/dealer.py) · [Benchmark setup](material.py) · [Role initialization](compare.py)
2. **Mask the live probe.** `plain_convert_raw` first computes `int(v * 256)` for each float, truncating toward zero. Hereafter $x$ and $y$ denote the fixed-point integer vectors. The drone computes $Y=y+b$ and sends $Y$ to the WD. In L this is a Python list. In P and R the TA authenticates the outgoing masked coordinates, and the WD checks the tag before evaluating a gate. Linux already knows $y$ in each stored-vector experiment. [Conversion and vector addition](../../../common/helper.py) · [Trusted mask command](../ta/experiment.c#L226)
3. **Evaluate shares.** Read `innerProductWithMul` in order. Only party 0 contributes $X_iY_i$. Each party $j$ subtracts $Y_i a_{j,i}$ and $X_i b_{j,i}$, adds its local product share $(ab)_{j,i}$, and sums over coordinates. Summing the two parties' results therefore gives $\sum_i (X_i-a_i)(Y_i-b_i)=x\cdot y$. The second call uses $X$ on both input wires, the same reference-mask share twice, and the $a^2$ share. Its two outputs sum to $x\cdot x$. These are the two calls inside `getFirstRoundMessage` on **both** devices in **all three** settings. [Original gate](../../../obscura-protocol/obscura.py#L147) · [Two gate calls](../../../obscura-protocol/obscura.py#L207)
4. **Return shares and decide.** The WD sends its two scalar shares back. The drone adds the corresponding shares in the ring, interprets the inner product as signed, and uses its own probe norm $y\cdot y$. It accepts when the inner product is nonnegative and its square meets the dataset's squared cosine threshold multiplied by both squared norms. L and P call the original Python reconstruction function. R supplies local shares and the protected WD reply to `DECIDE`; the TA verifies the reply and releases the decision bit. [Linux reconstruction](../../../obscura-protocol/obscura.py#L221) · [Trusted reconstruction](../ta/experiment.c#L279)

For a two-coordinate check, use encoded $x=(2,-1)$, $y=(3,1)$, $a=(4,5)$, $b=(6,2)$. The public wires are $X=(6,4)$ and $Y=(9,3)$. Summing both roles' first output gives $66-51-44+34=5=x\cdot y$. The second gives $52-88+41=5=x\cdot x$. The drone's probe norm is 10. The dot product is positive and the squared cosine is $25/(5\times10)=0.5$, which passes both configured squared thresholds. The production circuit applies the same expressions to 128 coordinates.

### Verify the overlap

From `jetson_benchmark/experiments`, use the experiment Python environment with TNO, NumPy and cryptography and the native build dependencies in the experiment runbook.

```bash
./build.sh native
python paper/check_overlap.py
python paper/check_groups.py
```

The first check replays all 1,000 original `data/64` fixture pairs. A SHA-256 digest pins the original ordered transcript at commit `60ae87d6`, covering all 128 masked coordinates, both parties' two shares and the decision for each pair. For identical public fixture inputs, it compares P and R with those intermediates and runs their real TA command source under the native test backend. The second check exercises authenticated group consumption and rejected invalid messages. The full two-process native run also agreed with the archived Jetson decisions on all 15,276 pair-setting records.

The saved latency and energy tables and binary release archive correspond to `60ae87d6`. Use a checkout of that revision to reproduce the measured driver. The checks above exercise the shared-source revision from a full repository checkout.

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

The historical CLI reads an already encoded probe from its circuit. The Jetson runner times conversion from a stored float embedding explicitly. Both Linux decision paths compute the two sign checks in the original order. [Original fixed-point and ring helpers](../../../common/helper.py) · [TA setup and MAC implementation](../ta/keys.h)

## Reading the tables

* Per-pair times use the Linux monotonic performance counter. Online latency begins immediately before scaling and ends when the decision is available to the drone. The five disjoint stages are scaling, masking, drone shares, WD round trip and reconstruction/decision. The WD’s own share time is a diagnostic inside the round trip. Stage medians need not sum to the median total.
* VDD_IN measures the entire module. A 100 ms rail interval is too coarse for an individual millisecond verification or a single mask. Each measured batch uses consecutive online verifications after setup. The energy window includes slot activation, Python iteration and normal host activity. Joules per pair equal total measured batch joules divided by the number of covered pairs. Each trace must bracket both endpoints, contain at least three interior samples and meet the existing gap limit. The CSV lists energy coverage separately.
* The isolated masking calibration performs repeated **128-coordinate additions** on synthetic public inputs, reusing warm buffers and small integer offsets. It compares the production Linux Python helper with the compiled C addition loop used by the TA. Three blocks per implementation allow separate amortized arithmetic time and module energy. This experiment excludes protocol authentication, transport and per-probe TEE entry overhead, and measures different languages. It cannot attribute a speed difference solely to TEE placement.
* Under the stated input placement Linux observes both $q$ and $Y$, so it can derive the full live mask as $(Y-q)\bmod 2^{64}$. P still reveals $x\cdot y$ and $x\cdot x$ to drone Linux. R changes where these two scalars are opened. Claims about a compromised host must also specify whether the WD is independent, which inputs can be chosen, whether earlier messages were recorded and how one-use state survives rollback. [Manuscript correction](lemma2.md)

## Reproduce the one-board loopback comparison on a commissioned Jetson

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
