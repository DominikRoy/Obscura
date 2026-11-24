# Dataset extraction in OP-TEE and the Obscura integration proposal

The requested entry point is `dataset_embeddings_tee.ipynb`. It loops over real
LFW and DroneFace images and calls the existing OP-TEE application for every
SFace inference. It never calls `DeepFace.represent` or exports raw embeddings.
For the one-frame experiment, start with `frame_extraction_tee.ipynb`.

## What the supplied notebook actually does

Cell numbers below are **zero-based positions in the notebook JSON**, including
empty cells, not the execution counts displayed by Jupyter.

| Source | Purpose |
| --- | --- |
| `../ppface/pyscripts/Untitled.ipynb`, cells 0, 3, 6, 7 | Cell 0 samples LFW paths. Cell 3 extracts two vectors. Cell 6 defines `get_new_emb()`, which executes 500 iterations with an impostor and an accepted genuine pair per iteration. It stores vectors by path in `my_dict` and writes `new_emb10.txt` and `veri_test10.txt`. Cell 7 calls the entire function twice. Its second random run can overwrite the numbered files. |
| `../ppface/pyscripts/pffrocd.py`, `get_embedding`, line 304 | The wrapper is `np.array(DeepFace.represent(img_path=imagepath, model_name="SFace", enforce_detection=False)[0]["embedding"], dtype=dtype)`. |
| `Untitled.ipynb`, cell 5 | `plain_convert_raw` multiplies each coordinate by 256 and uses Python `int`, truncating toward zero. This is encoding, not neural inference. |
| `Untitled.ipynb`, cells 31–37 | Other experiments, mainly ArcFace, threshold selection and template fusion. They must not be mixed into the final 128-dimensional SFace experiment. |
| `Untitled.ipynb`, cells 38, 40, 41 | SFace versions. The inner `embed(path)` function performs `DeepFace.represent(...)[0]["embedding"]`. Cell 38 uses `trio_gp`; cells 40/41 use `trio_cam`. Cell 40 enables the easy-probe filter; cell 41 includes all matching probes. |
| `Untitled.ipynb`, cells 40/41, final section | `json.dump({k: v.tolist() for k, v in emb_cache.items()}, fh)` writes raw, unnormalized floats to `embeddings_droneface_raw_sface11.txt` / `...9.txt`. These are JSON dictionaries despite the `.txt` suffix. |
| `../ppface/pyscripts/extract_embedding.py` | Single-image SFace extraction; exports one float per line. This format differs from the JSON dictionaries consumed by Obscura. |
| `../ppface/pyscripts/Untitled1.ipynb` | One empty cell. |

The active final cells do **not** use `droneface_sface_tf.keras` or `.h5`.
The custom model load is commented out. The associated fine-tuning script builds
a different MobileNetV2-based network with 512-dimensional features; it is not
the 128-dimensional OpenCV SFace model deployed in the TA.

The notebook sets `DETECTOR="yolov8"`, but never passes that variable to the
active `DeepFace.represent` calls. Their effective default is OpenCV detection,
with alignment enabled, base input normalization, and `enforce_detection=False`.
That last option can use the entire image when no face is detected. `[0]` selects
the first returned face if there are multiple faces. The new code preserves these
choices and records face count/confidence so fallback cases can be reviewed.

The original package versions are not recorded, so exact reproduction of every
old embedding cannot be claimed. The new preparation adapter explicitly uses
DeepFace **0.0.93** and records versions, preparation-source hashes, cascade hashes,
source-image hashes and prepared-pixel hashes. Its steps follow the upstream
[representation code](https://github.com/serengil/deepface/blob/v0.0.93/deepface/modules/representation.py)
and [SFace input conversion](https://github.com/serengil/deepface/blob/v0.0.93/deepface/models/facial_recognition/SFace.py).
Only the resulting pixels are sent to the TA. The recognition model is never
loaded or executed by DeepFace in this workflow.

### Problems in the original evaluation loops

- LFW labels in `get_new_emb()` come from `DeepFace.verify`, not directly from
  identity ground truth. Genuine pairs are resampled until the model accepts
  them, and an image may be paired with itself. These are biased evaluation
  choices, not an independent accuracy measurement.
- LFW share arrays are reassigned on every iteration. The share text files at
  the end contain only the last iteration's vectors. They are not Obscura dealer
  preprocessing.
- DroneFace templates average the raw portrait embeddings, then log one portrait
  filename as the template key. The final cache exports the individual portrait
  at that key, not the average. In `data/veri_balanced_cosine9sface.txt`, the first
  row's distance is `0.659137`; the three-portrait mean reproduces `0.65913713`,
  while looking up its exported single portrait gives `0.63708341`.
- Threshold selection and reported accuracy use the same pairs. A publication
  experiment needs separate calibration/evaluation data and documented splits.
- Old pickle caches are not bound to model/preprocessing versions. The new TEE
  dataset loop performs inference every time and does not reuse these caches.

## Current dataset inventory

Confirmed locally by filename enumeration, without running recognition:

| Selection | Images | Subjects |
| --- | ---: | ---: |
| LFW, every image | 13,233 | 5,749 |
| DroneFace `trio_cam` + all matching probes | 1,397 (33 + 1,364) | 11 |
| DroneFace `trio_cam` + easy probes | 715 (33 + 682) | 11 |

The default follows cell 41, using `trio_cam` and all probes. LFW enumerates
all images once rather than recomputing embeddings for sampled pairs. Keys retain
the old `../lfw/...` and `../DnHFaces/...` spelling as identifiers, independently
of the dataset's absolute location. Images and datasets are not copied into Git.

For an extraction run on the images of a **specific Obscura experiment**, set
`PAIR_FILES` in the notebook or use `--pairs` on the command line. The loop checks
the two path columns against the dataset inventory, deduplicates them and keeps
the same ordering as the full run. It uses only the image names from the pair
list. For DroneFace it also includes the other portraits of each referenced
gallery subject, since the original comparison used their mean. Each portrait
still gets its own masked output.

| Supplied pair file in `data/` | Verification rows | Distinct keys in rows | Images for extraction |
| --- | ---: | ---: | ---: |
| `veri_test1.txt` (LFW) | 1,000 | 1,603 | 1,603 |
| `veri_balanced_cosine9sface.txt` (DroneFace, all probes) | 2,728 | 1,375 | 1,397 |
| `veri_balanced_cosine11sface.txt` (DroneFace, easy probes) | 1,364 | 693 | 715 |

For example, from the repository's `jetson_benchmark` directory, use
`python dataset_tee.py --dataset lfw --ppface ../ppface --pairs ../data/veri_test1.txt --list-only`.
Omit `--list-only` and add `--output results/lfw_veri1` to run that selection.
When a probe appears in two verification rows, this extraction loop measures
it once. The future protocol will allocate separate preprocessing for the two
verification sessions.

## Run on the Jetson

From the **repository root on the Jetson**, download the 1,364 camera replay
frames directly. The downloader works with the system Python 3.8 and checks
every image against the workstation dataset.

```bash
python3 jetson_benchmark/fetch_images.py probes
```

Use `droneface` to add both portrait galleries, `lfw` for the 13,233 LFW images,
or `all` for both datasets. The default destination is the repository's
`ppface` folder, which the notebook discovers from the nested installation.
Rerunning verifies and reuses completed folders. To keep a different local
copy alongside these images, pass `--dest` and set the notebook's `PPFACE`
to the printed path.

DroneFace uses byte-range requests to retrieve the selected JPEGs and the
included license from the [authors' archive](https://hjhsu.github.io/DroneFace/).
LFW uses the original `lfw.tgz` archive and the checksum published in
[scikit-learn's LFW loader](https://github.com/scikit-learn/scikit-learn/blob/main/sklearn/datasets/_lfw.py).

Use the installation that already passed `secure_sface/probe.py`. Copy
`dist/jetson_frame_update_r35.5.0.tar.gz` to the directory on the Jetson where
the probe succeeded. Close running notebook kernels before applying the update,
then run the following command in that directory.

```bash
tar -xzf jetson_frame_update_r35.5.0.tar.gz
```

This update includes the two notebooks and an AArch64 Linux client library that
timestamps the existing commands. It uses the installed TA and generated SFace
weights from the original R35.5.0 package. It also works when applied directly
over that package. Keep the `ppface` datasets in a separate directory.

Face preparation needs DeepFace 0.0.93 in the notebook's Python environment.
Use an isolated environment to keep this experiment separate from other Jetson
packages. For the target's Python 3.8, a CPU preparation environment can be created
with these version constraints (package installation itself has not been verified
on the remote Jetson):

```bash
sudo apt-get update
sudo apt-get install -y libhdf5-dev pkg-config build-essential python3-dev
python3 -m venv --system-site-packages .dataset-venv
source .dataset-venv/bin/activate
python -m pip install --upgrade pip
HDF5_DIR=/usr/lib/aarch64-linux-gnu/hdf5/serial python -m pip install -r requirements-datasets.txt
python -c 'import h5py; print(h5py.version.info)'
python -c 'from dataset_tee import preprocessing_info; print(preprocessing_info()["versions"])'
python -m ipykernel install --user --name obscura-datasets --display-name "Obscura TEE datasets"
```

If a previous install stopped at `libhdf5.so: cannot open shared object file`,
install the apt packages above, reactivate the existing environment and retry
the pip install with `HDF5_DIR`. The import check prints the HDF5 version
loaded by Python.

From your existing Jupyter installation select **Obscura TEE datasets** as the
kernel. TensorFlow is a dependency of this
DeepFace release; its presence does not move SFace inference out of OP-TEE.
The selected DeepFace detector uses OpenCV in Linux. The installed OpenCV must
provide its Haar cascade data. No separate recognition ONNX download is needed
here: the TA uses the already-exported pinned SFace weight bundle.

### One camera frame at a time

For this experiment the input directory on the Jetson is
`ppface/DnHFaces/open_data_set/photos_all_faces/`. Point the notebook's `PPFACE`
at the enclosing `ppface` directory. Open `frame_extraction_tee.ipynb` with
`jupyter lab frame_extraction_tee.ipynb`. The first run processes one DroneFace probe
image. The second run measures 30 distinct probe images after two warmups.
The files are replayed in filename order. Linux simulates frame delivery and
performs face detection and alignment. Each 112 × 112 crop is copied into secure
RAM, where SFace computes its 128 floats. Linux can read the source images in
this simulation. The raw vector stays in the TA through scaling and masking.
The two runs have independent result directories.

Equivalent terminal commands from the updated installation are below. The
runner looks for `ppface` in parent directories. Use `--ppface` if it is elsewhere.
Each output directory must be new.

```bash
python dataset_tee.py --dataset droneface --probes-only --profile-extraction --limit 1 --warmup 0 --output results/one_frame_01
python dataset_tee.py --dataset droneface --probes-only --profile-extraction --limit 30 --warmup 2 --output results/frame_batch_01
```

If only privileged `tegrastats` shows `VDD_IN`, run the following commands
in one terminal from the benchmark directory with the virtual environment
active. The optional launcher in `jetson_power/` starts the sensor on demand
and streams its output directly to the existing parser. Python runs as the
benchmark user. The privileged helper stops its own sensor when the
launcher closes its control pipe. Refresh sudo credentials before starting.

```bash
sudo -v
PATH="$PWD/jetson_power:$PATH" python - <<'PYTHON'
from power import Tegrastats
import time
m = Tegrastats(interval_ms=100)
m.start()
try:
    m.wait_until(time.monotonic() + 1)
    print("VDD_IN samples:", len(m.samples), "latest watts:", m.samples[-1][1])
finally:
    m.stop()
PYTHON
```

After the check succeeds, use the same launcher for the batch:

```bash
RUN="results/drone_$(date +%Y%m%d_%H%M%S)"
PATH="$PWD/jetson_power:$PATH" python dataset_tee.py --dataset droneface --probes-only --profile-extraction --interval-ms 100 --limit 30 --warmup 2 --output "$RUN"
```

| Recorded value | How to report it |
| --- | --- |
| `ta_inference_ms` | Mean and median of the TA's elapsed SFace layer times. The TA sums timers with millisecond resolution. |
| `extraction_ms` | Mean and median elapsed time from submitting the prepared crop (`SF_BEGIN`) to the return of the last model step. Includes input preparation in the TA, TEE transitions, and authenticated weight streaming. `SF_FINISH` then scales, masks, returns the masked result and clears the buffers. |
| `module_extraction_j` | Mean and median of the per-frame energy estimates with valid power traces. Each integrates instantaneous `VDD_IN` samples between that frame's two Linux monotonic timestamps, interpolating the endpoints. This includes module idle power and other system activity. Report the number of valid frames alongside the result. |
| Secure RAM and storage | Report the fixed **6,946,808 bytes** of working buffers once. The session allocates two 802,816-float activation buffers and a 524,280-byte weight buffer. The raw 512-byte embedding occupies part of an activation buffer. The TA requests an 8 MiB heap and 16 KiB stack and writes **0 bytes per frame** to persistent secure storage. These are sizes from the build. A measured high-water mark for total secure RAM would require allocator/OS instrumentation. |

`frames.csv` has one row per frame, including timing, energy, reading count and
secure workspace size. `power.csv` and the frame start/end columns share a time
origin. The default rail sampling interval is 100 ms. A missing boundary, fewer
than three in-window readings, or a gap exceeding three sampling intervals
leaves that frame's energy empty and records a reason. In `summary.json`,
`frame_extraction.module_extraction_j` summarizes valid frames. The separate
`power` field covers the entire batch including Linux image preparation and
record writes. Keep the Jetson power mode, clocks, cooling and background load
consistent for comparisons. NVIDIA documents `VDD_IN` as total module input
power. [Orin Nano power rails](https://docs.nvidia.com/jetson/archives/r35.5.0/DeveloperGuide/SD/PlatformPowerAndPerformance/JetsonOrinNanoSeriesJetsonOrinNxSeriesAndJetsonAgxOrinSeries.html#jetson-orin-nx-series-and-jetson-orin-nano-series)

### Full dataset runs

First inspect the dataset locations (requires NumPy, but not DeepFace or a TEE):

```bash
python dataset_tee.py --dataset droneface --ppface ../ppface --list-only
python dataset_tee.py --dataset lfw --ppface ../ppface --list-only
```

The notebook searches for `ppface` beside its ancestor directories, including
when launched from the extracted `dist/jetson_test` directory. If needed, set
`PPFACE` to the real folder. For terminal examples replace `../ppface` with the
actual path when using that nested installation. Run the notebook's
40-image smoke batch for both datasets. Then change `LIMIT_PER_DATASET=None` and
rerun from configuration for the full loops. The equivalent terminal commands are:

```bash
python dataset_tee.py --dataset droneface --ppface ../ppface --output results/droneface_smoke --limit 40
python dataset_tee.py --dataset lfw --ppface ../ppface --output results/lfw_smoke --limit 40

python dataset_tee.py --dataset droneface --ppface ../ppface --output results/droneface_all
python dataset_tee.py --dataset lfw --ppface ../ppface --output results/lfw_all
```

Use a new output directory each time. `--offset` and `--limit` select deterministic
chunks for long runs. `--easy-probes` selects the 715-image DroneFace variant.
`--no-power` explicitly disables energy reporting but still requires actual OP-TEE.
An error aborts the run; previously completed records remain in `records.jsonl`.
Each rerun invokes the TA again with fresh masks; masked records are not an
inference cache or reusable protocol slots.

The earlier hardware probe took about 1.1 seconds per invocation. At that rate,
13,233 LFW inferences alone take about four hours, before Linux preparation and
thermal effects. Start with the smoke batch and estimate from its actual timings.

### Outputs and their limits

- `masked_embeddings_lfw.txt` / `masked_embeddings_droneface.txt`: JSON envelopes
  with model hash, ring/scale, and image-key to 128 masked-coordinate mappings.
  Coordinates are decimal strings to preserve uint64 precision.
- `records.jsonl`: one completed image per line, masked values, source/prepared
  hashes, subject/role, face diagnostics, Linux preparation time and TA timings.
- `manifest.json`: selected inputs, versions, model metadata and run status.
- `summary.json`: aggregate timing and optional module power/energy.
- `power.csv` and `tegrastats.log`: underlying telemetry when enabled.

`ta_inference_ms` is the secure neural-kernel time; `pipeline_ms` includes the
entire host-to-TEE call and its transfers/hash checks/encoding/masking/clearing.
Short TA phases can read zero because the secure counters are in milliseconds.
Energy covers the whole measured dataset loop, including Linux image preparation
and record writes. It is not energy exclusively attributable to the TEE.

For per-frame energy through the last SFace layer, set `profile_extraction=True`
in the dataset runner or use the frame notebook above. Isolating the energy
consumed by the neural kernels alone would require finer instrumentation.

**These masked files cannot replace `data/new_emb1.txt`.** The old loader expects
raw floats; the current TA discards its independent random pads and exports no
correlated dealer material. The envelope explicitly marks
`obscura_dealer_compatible: false`. This workflow changes neither TA masking nor
Obscura's wire/import/export behavior. It does not export raw vectors to make the
old loader work.

The dataset images remain on the Linux filesystem and preparation runs in Linux.
The inferred features and intermediate neural activations stay inside OP-TEE.
Putting the dataset and detection/alignment entirely inside the trusted boundary,
or connecting an exclusively trusted camera, is an additional implementation.

## Obscura: current code and proposed integration (not implemented here)

The requested boundary is to explain this change before implementing it. The
following is the proposed next change; `common`, `data`, `obscura-protocol` and
the TA masking commands have not been modified by this dataset work.

### Current data flow

1. `common/constants.py` loads `data/new_emb1.txt` and `data/veri_test1.txt` at
   import time. It is currently configured for LFW, 1,000 pairs, 64-bit input
   arithmetic and scale 256. Merely generating a DroneFace file does not select it.
2. Pair rows contain `label key0 key1 distance`. The dealer uses `key0` as `v`
   (live probe, called `y` in this conversation) and `key1` as `s` (reference).
   The old DroneFace notebook writes gallery first, probe second. Cosine is
   symmetric, but those roles matter when the live input moves into the drone TEE.
3. `common/helper.py::plain_convert_raw` uses `int(value * 256)`. `convert_raw`
   adds `2**96` to negatives; subsequent 64-bit modular operations reduce them to
   the corresponding `q mod 2**64`. Do not use nearest rounding, extra L2
   normalization, or scale already-masked values a second time.
4. `dealer.py::genOffline` creates masks, additive shares and correlated products
   (`s_v`, `s_s`, **`v_v` already exists**), scalar-output masks and FSS material.
   It writes `data/64/offline.pkl{party}-{index}`.
5. Party 0's pickle currently contains both `non_vec_v` (plaintext encoded probe)
   and `in_v_drone` (the complete probe mask). Those files are normal-world data,
   not secure provisioning. The dealer also prints the plaintext vector.
6. `obscura.py::getFirstRoundMessageDrone` masks the probe in ordinary Python.
   The active inner-product function omits output-wire masking. The live norm
   path and FSS comparison round are commented out; party 0 reconstructs the
   inner product/reference norm, computes `v·v` from plaintext, and compares
   locally. `obscura_energy.py` has the same structural shortcuts.

Having constants named `MALICIOUS` or a `v_v` field does not mean the active
experiment implements the complete malicious-secure or full comparison protocol.

### Proposed setup phase

Use `y` for the live feature vector and `q_y` for its encoded vector. In the ring
`R = Z/(2**64)`, a trusted dealer prepares a fresh full mask `delta_y`, splits it
as `delta_y_0 + delta_y_1 = delta_y mod 2**64`, and prepares the input-mask products
and scalar gate material for that **same** setup slot.

- Provision full `delta_y` confidentially and authentically to the TA, bound to a
  slot ID, model hash, scale, vector dimension and intended protocol/session.
  The host may transport an encrypted package but must not receive the plaintext
  full mask. A plaintext pickle followed by a TEE call does not satisfy this.
- Deliver only the appropriate share and correlated material to each computing
  party. Under the existing numbering, party 0 is the drone host and party 1 is
  the peer. Each learns its own share; neither gets both shares or the full mask.
- Include `delta_s*delta_y`, `delta_s**2` and `delta_y**2` coordinate shares, plus
  the output-mask correlations for squaring the inner product and multiplying
  the two norms. Independently generated generic triples cannot simply be put
  into these named fields; they must implement this circuit's masking convention.
- Give each party its share of `vv_out`. The current dealer instead places the
  entire `vv_out` mask with party 0 and zero with party 1. This must change with
  the secure norm path; simply uncommenting that path is insufficient.
- Bind preprocessing to a single use, consume it before releasing output, and
  handle failures/restarts without reusing masks. Persistent slot storage alone
  does not prove protection against rollback; this needs a device-backed or
  protocol-backed freshness mechanism. Review the fixed FSS seed as well.

### Proposed online phase

1. Receive the authenticated input through the agreed trusted input path.
2. Extract raw SFace features in the TA. If reproducing DroneFace mean templates,
   average the raw enrollment features inside the trusted boundary, assign a
   distinct template identifier, then encode once. Do not average the current
   independently masked output files or silently substitute one portrait.
3. Encode with `q_y[j] = int(y[j] * 256) mod 2**64` inside the TA.
4. Consume the matching setup slot and compute
   `Delta_y[j] = q_y[j] + delta_y[j] mod 2**64` inside the TA.
5. Export only a versioned packet containing `Delta_y` and public identifiers
   needed to select the matching setup material. No raw `y`, `q_y`, full mask,
   plaintext norm, or both mask shares are exported. Party-specific shares belong
   to private setup delivery, not one common public output file.
   On reading the packet, verify its origin and integrity and match the slot ID,
   reference, model, scale, ring and dimension to the private setup record.
   Parse exactly 128 unsigned 64-bit coordinates. Use them directly as the
   masked input to both parties' first round. Reject unknown or consumed slots.
   The packet loader must bypass the raw-float loader and its scaling step.
6. The parties load their corresponding shares and run the full masked circuit.
   For the live self-product, a party's masked-output share has the form

   ```text
   u_i = [i=0] * sum(Delta_y[j]^2)
         - 2 * sum(Delta_y[j] * delta_y_i[j])
         + sum(share_i(delta_y[j]^2))
         + share_i(output_mask_y_norm)       (mod 2^64)
   ```

   Adding `u_0` and `u_1` yields the masked norm. The dealer's `v_v` contains the
   input-mask square shares needed here. Keep the corresponding cross product,
   reference norm, inner-product square and norm-product gates masked too.
7. Restore and test the FSS/sign/threshold circuit so only the intended decision
   is revealed. The fixed-point scale, threshold calibration, integer truncation,
   modular wraparound and signed comparisons must be checked together. In
   particular, avoid converting 64-bit ring values through floating-point
   division during truncation.

Before enabling this, compare the entire secure decision with an independent
plaintext reference over selected real pairs and boundary cases. Rebuild all
preprocessing after changing input roles, templates, masks, model or constants;
do not reuse existing `data/64` pickle files. A malicious-security claim also
requires the appropriate authentication/checks, not only Beaver material.

Knowing `Delta_y` and the full `delta_y` recovers `q_y` by subtraction. Knowing
both additive mask shares does the same. A single independent share together
with `Delta_y` does not disclose `q_y` in the non-colluding one-time-mask model;
that observation alone is not a proof of the entire implemented protocol.

## Validation status of this addition

Dataset enumeration and automated host tests can run on the workstation. They
check selection, per-image invocation, prepared color order, masked-only output,
uint64 serialization, failure reporting and no Linux inference fallback. They
do not constitute hardware validation of this new dataset loop. The user has
already demonstrated real invocation of the existing TA on a synthetic crop;
the new real-image dataset smoke run must still be executed on the Jetson.
