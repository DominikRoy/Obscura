# A — enrolled x and one live probe y

1. The owner selects the existing stored reference x. It truncates each coordinate multiplied by 256 toward zero and seals the resulting vector in an authenticated enrollment box.
2. The TA validates the box and installs x as session input before reading the frame. Linux detects and aligns the face via the existing DeepFace preparation path.
3. The client streams the crop and pinned model blocks. The existing TA code verifies each block and runs SFace on its private activation buffers. It extracts y once per trial and encodes y with the same scale.
4. The TA returns one decision byte. With integer vectors, let d = x·y, a = x·x and b = y·y. Accept when d ≥ 0 and 100000000 d² ≥ 11368578 ab. This is the exact rational form of Obscura's configured squared threshold 0.11368578. The upstream evaluator uses a floating reciprocal. Zero vectors follow its inclusive comparisons. Coordinates outside ±32767 are rejected to keep every intermediate within the documented 128-bit bound. [CondEval plaintext evaluator](https://github.com/nann-cheng/CondEval/blob/main/plainEval.py)

The configuration uses the repository threshold for comparison across all experiments. Dataset-specific threshold calibration is a separate accuracy experiment. The native oracle checks exact-rational and upstream binary-floating decisions on the same stored pairs.

## One trial

Run the setup command on the dealer from `jetson_benchmark/experiments`. Deliver only `lab/a/ta.box` to the Jetson. The next command runs on the Jetson with the delivered box at the indicated path.

```bash
python setup_slot.py prepare --mode A --key lab/dealer.key \
  --bank ../../data/embeddings_droneface_raw_sface9.txt \
  --reference ../DnHFaces/open_data_set/trio_cam/k_cam_0_porF_00.jpg --out lab/a

python run.py --box lab/a/ta.box \
  --image ../../ppface/DnHFaces/open_data_set/photos_all_faces/k_gp_3_ef_27.jpg \
  --output ../results/A-k-01
```

Add `--power` when using your working power sampler. This A enrollment can be reused for subsequent probes against the same x.

## Thirty trials with extraction

The dealer prepares enrollment boxes for the first 15 genuine and first 15 impostor rows in the pinned DroneFace pair file. Deliver the `lab/a30` folder to the Jetson. Its manifest contains public pair metadata and labels; labels are used only for reporting.

```bash
python A/pairs.py enroll --key lab/dealer.key --per-class 15 --out lab/a30
python A/pairs.py run --enrollment lab/a30 --ppface ../../ppface --report ../results/A-30.json
```

Use a writable existing parent directory for the report. Every trial extracts y from its image, even when the same probe is compared with multiple references. The report records each decision and crop digest.
