# Validation evidence and reproduction

## Plaintext CondEval using stored embeddings

The executed upstream file had SHA-256 `9ffeb06c873c0144c407f9b91a734da4ddd8dcdb660d448b7d0fa6ebffcdf4f5`. It imported this checkout's `common.constants` and `common.helper`. These select the 1,000 LFW pair rows from `veri_test1.txt`, the stored bank `new_emb1.txt`, scale 256, and tau squared 0.11368578. It matched **972 of 1,000 labels**. Its total counts both true accepts and true rejects. The A integer oracle had **zero disagreements** with its floating comparison on those inputs. This is a stored-input reference run. [Original evaluator](https://github.com/nann-cheng/CondEval/blob/main/plainEval.py)

From the experiments directory, a reproducible check of that exact upstream content is:

```bash
tmp_plain=$(mktemp -d)
curl -fL https://raw.githubusercontent.com/nann-cheng/CondEval/main/plainEval.py -o "$tmp_plain/plainEval.py"
(cd "$tmp_plain" && echo '9ffeb06c873c0144c407f9b91a734da4ddd8dcdb660d448b7d0fa6ebffcdf4f5  plainEval.py' | sha256sum -c -) && PYTHONPATH=../.. python "$tmp_plain/plainEval.py"
python A/oracle.py
```

## Fresh DroneFace probes

The separate extraction experiment used the gallery vectors in `embeddings_droneface_raw_sface9.txt` and the first 15 genuine and first 15 impostor rows in `veri_balanced_cosine9sface.txt`. These are **30 pair trials, 15 distinct probe images and 11 distinct reference keys**. Every trial ran image preparation and probe extraction. A gallery embedding was always loaded from the existing bank. Versions included DeepFace 0.0.93, NumPy 1.24.3 and TensorFlow 2.13.1 on workstation Python 3.11. The TA code ran through the explicit native validation backend. C's GPU worker was emulated by a separate integer matrix multiplication on the CPU.

| Native result | A | B | C, one-layer pilot | Q, quantized CPU |
| --- | ---: | ---: | ---: | ---: |
| Trials | 30 | 30 | 30 | 30 |
| Correct decisions | 18 | 18 | 18 | 18 |
| False accepts | 0 | 0 | 0 | 0 |
| False rejects | 12 | 12 | 12 | 12 |

Every A decision agreed with independent plaintext evaluation of its freshly extracted probe. B agreed with A on all 30. C agreed with Q on all 30 and changed zero final decisions relative to B on this subset. Using stored probe embeddings with the same references, pair rows and threshold also produced these same 30 decisions. This small deterministic subset, with repeated probes, is a regression fixture. The 972/1,000 LFW result has a different dataset and input path. Neither result establishes general accuracy or GPU numerical equivalence across the corpus. [Per-pair decisions](validation.csv)

From the experiments directory, with the benchmark Python dependencies installed and public images available:

```bash
./build.sh native
mkdir -p lab
python setup_slot.py keygen lab/test.key
python A/pairs.py enroll --key lab/test.key --threshold-profile lfw --out lab/enrolled
python A/pairs.py run --native-key lab/test.key --enrollment lab/enrolled --report lab/a30.json
python compare_native.py --ppface ../../ppface --pairs lab/enrolled/pairs.json --output lab/paired.json
python -m pip install -r B/requirements.txt
python check.py --ppface ../../ppface
```

Use fresh paths for each run. In the paired suite the test process can inspect all test-role inputs. In the separate one-frame `check.py` run, the CLI executed party 0 and party 1 as separate processes connected through TNO 4.8.1 HTTP pools on loopback for B, C, and Q. The test checks both directional application and serialized byte counts against the other party. The 30-pair suite validates arithmetic separately from the network transport. That fixture uses the supplied 112×112 DroneFace crop directly, independently of DeepFace. With reference k the four decisions were match; with reference c the A decision was no match. B reproduced all 128 live FP32 fixed-point coordinates in the test harness. C and Q agreed on all 128 quantized-control coordinates. Compared with the FP32 baseline, **122 of 128 encoded coordinates changed** on that direct-crop fixture. Private intermediate vectors stay out of the recorded report. An altered C layer result and a second use of its slot were both rejected. Tests also cover zero vectors, opposite signs and the largest permitted coordinate magnitudes.

## Jetson build and outstanding measurements

Cross-built the TA with NVIDIA R35.5 OP-TEE public sources, Tegra t234, TA float support and the ARM64 buildroot toolchain. The experimental TA requests a 12 MiB heap and 32 KiB stack. The CUDA worker cross-built using NVIDIA's R35.5 x86-hosted nvcc 11.4.315 and AArch64 CUDA runtime 11.4.298, targeting Orin SM87. The two Linux libraries are ELF AArch64, and the CUDA library links `libcudart.so.11.0`. The archive is checksummed. The original SFace TA has a different UUID.

The workstation has no OP-TEE device node or NVIDIA GPU. Device TA loading, available secure heap, provisioning persistence on that device, actual CUDA execution, real two-machine latency and drone energy remain to be verified on the Jetson. The 5.573 J baseline predates these experiment binaries and has a different measurement window.

## Decision placement on the workstation

Tested the batch commands with two independent TNO role processes over loopback on an Intel Core Ultra 7 255U, Python 3.11. The public 112×112 crop and enrolled reference k described above were identical for every setting. Each setting used one warmup and five measured invocations. All 36 invocations gave the same match. The native TA regression also checked both B decision alternatives against an impostor reference, rejected a modified encrypted peer share and rejected a second TA decision call. [Recorded trial rows](decision_native_trials.csv) · [Batch reproduction and Jetson measurement windows](DECISION_TRIALS.md)

| Setting | Median crop through decision (ms) | Median masked packet through decision (ms) |
| --- | ---: | ---: |
| A | 223.45 | — |
| B-linux | 225.67 | 5.44 |
| B-tee | 226.16 | 5.25 |
| B-mpc | 231.63 | 11.78 |
| C, simulated GPU worker | 236.38 | 10.79 |
| Q, CPU control | 233.44 | 10.48 |

In B-mpc, median local dot-sign evaluation was 0.329 ms, margin comparison including its exchange was 1.717 ms, and the Boolean AND including its exchange was 0.821 ms. B-linux's local scalar decision took 0.008 ms and the B-tee native dispatcher call took 0.055 ms. Local timing excludes secure-world transitions on hardware; the network was loopback. No power measurement was taken. Treat these as preliminary workstation measurements. Jetson GPU speed, energy, and real two-device latency require the hardware run.

## Dataset thresholds

The original loopback timing and 30-pair validation used the LFW squared threshold of 0.11368578. The updated dealer also supports the DroneFace value of 0.062476 documented in the [original Obscura setup](../../README.md#change-dataset). These two thresholds were fixed before this comparison. Both were evaluated on the same labeled pairs and inputs.

For fresh probes, the workstation ran DeepFace 0.0.93 preparation and the TA's FP32 C kernels via the test harness on all 1,364 unique probe images in file 9. Each stored gallery reference and fresh probe was encoded at scale 256. The table uses the actual integer decision predicate. File 11 is the easier subset. FA counts accepted impostors and FR counts rejected genuine pairs. Each row set has equally many genuine and impostor pairs.

| Probe source | Pairs | LFW profile correct | DroneFace profile correct | FA before → after | FR before → after |
| --- | ---: | ---: | ---: | ---: | ---: |
| Full DroneFace, fresh | 2,728 | 1,972 (72.29%) | 2,111 (77.38%) | 30 → 125 | 726 → 492 |
| Easy DroneFace, fresh | 1,364 | 1,005 (73.68%) | 1,067 (78.23%) | 12 → 61 | 347 → 236 |
| Full DroneFace, stored | 2,728 | 1,972 (72.29%) | 2,113 (77.46%) | 30 → 123 | 726 → 492 |
| Easy DroneFace, stored | 1,364 | 1,005 (73.68%) | 1,067 (78.23%) | 12 → 61 | 347 → 236 |

The fresh-probe table measures the FP32 extraction path on the workstation. The control and GPU settings quantize one layer and require their own corpus evaluation. The six-setting native regression checks a public pair whose decision flips between the two thresholds for both extraction paths. For LFW, the stored reference result remains 972/1,000 with its original profile.

To measure A end to end on the Jetson, start in the experiments directory on the trusted dealer with the existing commissioning key. Use a fresh enrollment directory for each profile. This example uses all 1,364 pairs per class in file 9.

```bash
python A/pairs.py enroll --key "$DEALER_KEY" --threshold-profile droneface \
  --bank ../../data/embeddings_droneface_raw_sface9.txt \
  --pairs ../../data/veri_balanced_cosine9sface.txt --per-class 1364 \
  --out lab/full-droneface-enrolled
```

Transfer the resulting enrollment directory to the drone. With the updated experiment TA installed, run in the drone's experiments directory, substituting the directory where you placed the enrollment and your local image root. The report contains correctness, false-accept and false-reject counts, and each pair's decision. Repeat with an independently prepared `--threshold-profile lfw` enrollment and a different report path for the original operating point.

```bash
mkdir -p ../results
python A/pairs.py run --ppface ../../ppface --enrollment ~/full-droneface-enrolled \
  --report ../results/full-droneface-accuracy.json
```
