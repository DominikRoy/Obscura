# Full-frame verification on Jetson 1

Run this path to give A, B-linux, B-tee and B-mpc a complete simulated camera frame. The trusted workstation stands in for the camera. Only that workstation opens the source image. Jetson Linux relays an authenticated ciphertext through libteec. A real CSI camera would require its own trusted capture, DMA isolation and provisioning design. Source photos that were previously copied onto a Jetson remain accessible in that location.

## Reevaluation on Jetson 1

We executed 172 real OP-TEE verifications on the Orin Nano R35.5.0. The measurements include 164 non-warmup trials. Both TNO parties ran on this one Jetson. Each trace records one camera invocation, 172 weight-and-kernel invocations and one FINISH. The paired settings agreed in every group. The raw reports are in the six named camera directories under `jetson_benchmark/results` on Jetson 1. [Public per-trial values](measurements/camera-jetson1.csv)

### Original drone scene, 640×480

Five timed repetitions per setting followed one warmup. Values below are medians. Camera preparation includes the secure input/decryption, face and eye search, crop and tensor conversion. The native detector found one face and no eye pair in this scene. Different stages have separate medians. The last column gives the number of runs with a usable VDD_IN trace.

| Setting | Camera prep (ms) | SFace blocks (ms) | FINISH (ms) | Decision after FINISH (ms) | Frame to decision (ms) | Module J to decision | Energy n/5 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| A | 424.7 | 1122.0 | 6.72 | inside FINISH | 1555.1 | 7.92 | 2/5 |
| B-linux | 451.4 | 1111.7 | 6.73 | 14.3 | 1588.0 | 7.94 | 2/5 |
| B-tee | 426.3 | 1116.9 | 6.70 | 14.5 | 1568.0 | 7.97 | 4/5 |
| B-mpc | 426.9 | 1111.4 | 6.70 | 31.0 | 1591.5 | 8.06 | 4/5 |

### Accuracy and the notebook comparison

On the Jetson we used the first five genuine and five impostor rows of each split for all four configurations. Each setting gave 9/10 correct on LFW, 8/10 on DroneFace 9 and 7/10 on DroneFace 11. For all 120 labeled hardware decisions, the audit checked the bit against a freshly computed workstation prediction using the same TA kernels. The samples were chosen in file order. Use the following larger corpus results for accuracy. File 11 overlaps file 9.

With x kept at its stored enrollment and y extracted from each full dataset image on the workstation, the native C front end and SFace kernels produced these results. The decision thresholds were fixed in advance. The stored comparison uses corresponding archived x and y. [Counts, detector outcomes and notebook comparisons](measurements/camera-native-accuracy.json)

| Split | Pairs | Stored | New camera path | False accepts / false rejects | Decisions changed | Whole-frame fallback / distinct probes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| LFW file 1 | 1,000 | 97.20% | 95.90% | 10 / 31 | 39 | 17 / 938 |
| DroneFace file 9 | 2,728 | 77.46% | 77.49% | 124 / 490 | 29 | 707 / 1,364 |
| DroneFace file 11 | 1,364 | 78.23% | 78.23% | 60 / 237 | 12 | 347 / 682 |

We also invoked the original `DeepFace.represent(..., model_name="SFace", enforce_detection=False)[0]` on eight public probes per split. None of these selected 128-coordinate fixed-point vectors matched exactly. Median cosine similarities between the two fixed-point vectors were 0.9798, 0.9996 and 0.9977 for LFW, DroneFace 9 and DroneFace 11 respectively. The minimum was 0.1457 on the LFW sample. Different face selection and resampling can materially change the result even with the same SFace weights and encoding. These data do not establish equal accuracy on the full LFW benchmark or on live drone video.

The named TA allocations for the 640×480 input total 8,863,789 bytes during face preparation. Across the measured scene runs the Jetson Python runner reached 112,792–119,092 KiB peak RSS. Total secure allocator high-water usage and filesystem metadata size were uninstrumented.

## Follow one invocation

| Stage | Code | Input and output |
| --- | --- | --- |
| Camera simulation | `camera/input.py:sensor_pixels`, `seal_frame` | Decode the whole JPEG into BGR on the trusted workstation. Optionally reduce the simulated sensor resolution with aspect ratio preserved. Encrypt the full pixels and dimensions under AES-256-GCM using the commissioned experiment key, a random nonce and the slot ID. |
| Dealer setup | `trials.py:setup`, `setup_slot.py:prepare`, `ta/experiment.c:setup` | A receives the pre-enrolled fixed-point x. For B, the dealer provisions a fresh full δy into the TA and separate correlated material to each party. The authenticated setup mode binds this session to the sealed-frame command. |
| Invoke the TA | `run.py:Session.call`, `Model.extract`, `ta/bridge.c:exp_call` | User space issues TEEC_InvokeCommand(CAMERA_BEGIN) with the encrypted frame. The notebook can launch this same Python runner. |
| Prepare the full frame | `ta/experiment.c:begin_frame`, `camera/frame.c:frame_crop` | The TA takes a private snapshot, verifies the tag and slot, decrypts, runs the frontal-face Haar cascade and eye cascade, selects the largest grouped face, rotates when two eyes are found, and samples a letterboxed 112×112 BGR crop. `sf_input` converts the crop into the model input tensor. These intermediates stay in TA RAM. |
| Extract y | `run.py:Model.extract`, `secure_sface/ta/secure_ta.c`, `secure_sface/runtime.c:sf_step_run` | For each STEP the TA copies a public weight block from Linux, hashes the private copy and runs its FP32 kernel. The last STEP leaves 128 raw floats in the TA. |
| Encode and finish | `secure_sface/runtime.c:sf_encode`, `ta/experiment.c:finish` | Compute qᵢ = trunc(256 yᵢ), the rule from `common/helper.py:plain_convert_raw` and `common/constants.py:CONVERSION_FACTOR`. A computes the integer predicate against x and releases one bit. Each B setting releases a slot ID, 128 values Yᵢ = (qᵢ + δyᵢ) mod 2⁶⁴ and a tag. |
| Decide in B | `B/mpc.py:verify`, `scalar_decision`, `ta/experiment.c:decide` | Parties first form shares of x·y, x·x and y·y. B-linux opens these three scalars on the drone. B-tee reconstructs the scalars and computes the predicate in the TA. B-mpc uses masked comparisons, dealer multiplication correlations and a shared AND, and releases the final bit. |

This camera model trusts the simulator with the lab dealer key. Use the simulator on the trusted workstation only. A camera endpoint with a dedicated capture key, device attestation and capture freshness would have different provisioning. Each B slot is spent once. A enrollment permits another invocation of a previously recorded valid frame for the same slot.

The TA accepts at most 307,200 pixels and a maximum side of 1,024. The frontal-face and eye cascade coefficients come from the two OpenCV XMLs named in `camera/export_cascades.py`. The generated header contains their digests and `camera/LICENSE.txt` contains the source notices. The C scanner, grouping and resampling code was written for the TA. It reuses activation memory, uses bilinear interpolation, and selects the largest face. The notebook uses DeepFace/OpenCV's first result and PIL's bicubic rotation. The TA uses the whole frame when no face is detected, following the notebook's permissive evaluation policy. A no-detection frame can therefore receive a verification decision. Detection and eye counts in the accuracy report come from the workstation reference. The TA keeps these details private.

## Reproduce the run

1. On the trusted workstation, enter `jetson_benchmark/experiments`. Use the existing trusted dealer key, the dataset environment and a fresh private output directory. This example takes five genuine and five impostor rows in file order. Every protocol receives the same input per row and independent dealer material.

   ```bash
   python trials.py prepare --key "$DEALER_KEY" \
     --bank ../../data/embeddings_droneface_raw_sface9.txt \
     --camera-pairs ../../data/veri_balanced_cosine9sface.txt \
     --images ../../ppface --per-class 5 --out lab/my-camera-batch
   ```

   For file 11, change both filenames to the file 11 versions. For LFW use `new_emb1.txt` and `veri_test1.txt`. To run each entire split, use 1,364, 682 and 500 pairs per class for DroneFace 9, DroneFace 11 and LFW 1 respectively. New output paths prevent accidental reuse. The dataset provider already cropped the DroneFace faces in these pair files. LFW also supplies curated face images. Detection still receives every pixel of each supplied file.

2. To measure a complete original drone scene, prepare a separate fixed-frame batch. This downsamples the full 3,680×2,760 photo to 640×480 on the simulated sensor. The TA receives all 640×480 pixels. The group photo has multiple possible subjects, so use it for timing. The detector selects one face.

   ```bash
   python trials.py prepare --key "$DEALER_KEY" \
     --bank ../../data/embeddings_droneface_raw_sface9.txt \
     --reference ../DnHFaces/open_data_set/trio_cam/c_cam_0_porF_00.jpg \
     --camera-image ../../ppface/DnHFaces/open_data_set/photos_all/cd_gp_0_eo_30.JPG \
     --sensor-max-side 640 --warmups 1 --repeats 5 --out lab/my-scene
   ```

3. Transfer the generated drone and peer directories to their respective hosts. For the single-Jetson loopback benchmark, put both under the same batch directory on Jetson 1. This topology measures local TNO costs and lets the machine holding both role directories read both parties' material. A two-party privacy experiment requires separate hosts. The trusted workstation keeps the raw source frames and dealer key.

4. On the Jetson, enter `jetson_benchmark/experiments`, activate `../.dataset-venv` and verify the release. The existing commissioning key remains valid. Run the install command when deploying the new TA build.

   ```bash
   (cd prebuilt && sha256sum -c SHA256SUMS)
   tar -xzf prebuilt/orin-r35.5.0.tar.gz
   UUID=85fe4e6b-839b-4024-8474-00c4de898504
   sudo install -m 0644 "build/ta/$UUID.ta" "/lib/optee_armtz/$UUID.ta"
   sha256sum "build/ta/$UUID.ta" "/lib/optee_armtz/$UUID.ta"
   ```

   To compile from source use `./build.sh jetson` with the R35.5 ARM64 SDK variables described in JETSON2.md. The experimental TA is lab-signed. Retain the generated model weights required by the existing benchmark.

5. Start the 100 ms VDD_IN reader and verify samples as in the power section of JETSON2.md. In two Jetson terminals with the dataset environment active, run the peer first and then the drone. The drone terminal must inherit the working meter on PATH.

   ```bash
   python trials.py peer --peer-material lab/my-camera-batch/peer
   ```

   ```bash
   python trials.py run --drone lab/my-camera-batch/drone --profile-operations \
     --power --output ../results/my-camera-batch
   ```

   The notebook `camera_protocols.ipynb` runs both commands in a single Jetson kernel. Select an unused batch. For two devices, use the TNO port forwards in JETSON2.md and deploy only the matching role to each device.

6. Read `medians.json` and each trial's `summary.json`, `op-times.json` and `power.csv`. The benchmark times frame submission through the last STEP, then through the final decision. SFace STEP time includes block copies, integrity checks and OP-TEE calls. Setup, file I/O, sensor decoding/encryption and offline dealer work precede the timed window. Power is integrated **module** input energy, including Linux, both colocated roles and idle consumption. Incomplete sampling produces a missing energy value and reduces the reported sample count. Per-operation timings include the libteec transitions. The combined CAMERA_BEGIN pays for authentication, face preparation and tensor setup. FINISH combines encoding with A's comparison or B's masking and MAC.

7. Reproduce the full workstation accuracy check from the same directory using the build's native reference kernels and the stored enrolled x. The optional notebook check invokes the original DeepFace operation on a deterministic subset with the pinned DeepFace environment and SFace weights installed. All reports contain aggregates.

   ```bash
   ./build.sh native
   python check_camera.py
   python camera_accuracy.py --images ../../ppface --notebook-samples 8 --output /tmp/camera-accuracy.json
   ```

## Memory accounting

The TA reserves a 12 MiB heap and a 32 KiB stack. Its SFace workspace uses 6,946,808 bytes. During CAMERA_BEGIN the TA reuses its two activation arrays as integral-image buffers and the weight block as crop space. It additionally allocates 73,728 bytes for detection, the sealed frame private copy and the authenticated plaintext. The two frame buffers together take 2 × (4 + 3 × width × height) + 45 bytes. They are released before model execution. The raw 512-byte embedding occupies existing workspace. This accounts for named allocations. Allocator, cryptographic operation and TA runtime overhead require separate peak instrumentation. Linux runner maximum RSS is a distinct high-water mark reported in KiB. The TA writes zero embedding bytes to persistent storage. B creates one empty spent-slot object per trial. The backend incurs metadata/storage overhead for this object.
