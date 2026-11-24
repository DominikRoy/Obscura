# Run the four verification settings and the GPU comparison

| Setting | Inputs to the decision | Who computes the decision |
| --- | --- | --- |
| A | The TA has enrolled x and extracts live y | TA computes the dot product, norms, signs and AND |
| B-linux | Both parties compute shares of the three scalars after secure extraction and masking | The drone host receives the peer shares, reconstructs dot, xx and yy, and runs the plaintext predicate |
| B-tee | Same shared arithmetic as B-linux | The TA reconstructs the scalars, checks both comparisons and returns one bit |
| B-mpc | Same shared arithmetic as B-linux | Both parties evaluate shared comparisons and a Boolean Beaver AND, then open the decision |
| C | One blinded convolution on the GPU and remaining SFace layers in the TA | Same B-mpc decision |
| Q | C's quantized convolution computed on the secure CPU | Same B-mpc decision |

All four main settings use the same FP32 extraction and an already-enrolled reference. The probe norm yy is computed from the same dealer correlations in all three B runs. Linux can read the original photo and aligned crop in this camera simulation. Linux learns the three plaintext scalars in B-linux. Keep that disclosure explicit in any comparison.

For B-tee the dealer puts a fresh 24-byte pad and a distinct 32-byte MAC key in the TA's authenticated slot box and the peer's private material. The peer masks its three 64-bit shares with the pad and authenticates them with HMAC-SHA256 over the slot identifier, masked embedding packet tag and masked shares. Linux relays them alongside its own three shares. The TA authenticates a private copy, unmasks, adds the shares modulo 2^64, validates scalar bounds, and returns the decision from one invocation. The peer also receives the decision. Neither the pad nor that key is distributed to the drone host. The protocol assumes non-colluding semi-honest parties, trusted setup, and fresh slots. A malicious drone could substitute its own scalar shares. The single-use check follows the storage and rollback assumptions in the [main guide](README.md).

## Install on each device

Start from the existing Obscura checkout. Copy the refreshed overlay and SHA-256 file to each device. From the checkout's `jetson_benchmark` directory, run the following on the drone and peer. Adjust the archive directory if needed.

```bash
(cd ~ && sha256sum -c obscura-abc-r35.5.0.tar.gz.sha256)
tar -xzf ~/obscura-abc-r35.5.0.tar.gz
source .dataset-venv/bin/activate
cd experiments
python -m pip install -r B/requirements.txt
```

The peer can also use a regular Python environment with the TNO requirement. On the **drone only**, install the updated TA before using B-tee.

```bash
(cd prebuilt && sha256sum -c SHA256SUMS)
tar -xzf prebuilt/orin-r35.5.0.tar.gz
sudo install -m 0644 build/ta/85fe4e6b-839b-4024-8474-00c4de898504.ta /lib/optee_armtz/
```

Use the existing experiment commissioning key if this experiment UUID was already commissioned. For first-time commissioning, follow the [trusted dealer and Jetson setup](README.md). The older extraction-only probe used a different UUID.

## Prepare on the trusted dealer

Run from the experiments directory. Use your existing dealer key and a fresh output folder. This example repeats one public probe/reference pair to measure performance. With five repetitions and one warmup per setting it creates 36 trials.

```bash
python trials.py prepare --key lab/dealer.key \
  --bank ../../data/embeddings_droneface_raw_sface9.txt \
  --reference ../DnHFaces/open_data_set/trio_cam/k_cam_0_porF_00.jpg \
  --warmups 1 --repeats 5 --out lab/tonight01
scp -r lab/tonight01/drone client@JETSON_HOST:~/obscura-drone-tonight01
scp -r lab/tonight01/peer USER@PEER_HOST:~/obscura-peer-tonight01
```

Replace the hostnames and use fresh destination names. The two folders are recipient-specific. Keep the dealer key on the dealer after trusted commissioning.

## Start the peer, then the drone

From a **peer** terminal create a tunnel to the drone. Ports 61501 and 61502 carry the measured TNO protocol. Ports 61503 and 61504 coordinate when each batch process should start and retrieve a report after the measured exchange. The tunnel uses loopback listeners. For the batch, close any older single-trial tunnel that uses the same ports.

```bash
ssh -N -o ExitOnForwardFailure=yes \
  -L 127.0.0.1:61501:127.0.0.1:61501 -R 127.0.0.1:61502:127.0.0.1:61502 \
  -L 127.0.0.1:61503:127.0.0.1:61503 -R 127.0.0.1:61504:127.0.0.1:61504 \
  client@JETSON_HOST
```

In a second **peer** terminal, from the experiments directory and activated environment, run:

```bash
python trials.py peer --peer-material ~/obscura-peer-tonight01
```

Once the peer prints `Peer batch ready`, run on the **drone** in the experiments directory. The source image is used by each trial. Refresh sudo in this terminal if needed for the VDD_IN sampler.

```bash
sudo -v
PATH="$PWD/../jetson_power:$PATH" python trials.py run \
  --drone ~/obscura-drone-tonight01 \
  --image ../../ppface/DnHFaces/open_data_set/photos_all_faces/k_gp_3_ef_27.jpg \
  --power --output ../results/tonight01
cat ../results/tonight01/medians.json
```

Each run uses fresh preprocessing. For another batch or a retry after failure, prepare fresh material and use a new output directory. Record Jetson power mode, clocks, cooling, and network setup alongside the reports. SSH forwarding contributes real latency to these end-to-end measurements.

## Read the numbers

- `crop_to_decision_ms` measures the aligned crop through the drone's final decision and, in B/C/Q, the peer acknowledgment. Alignment, model file reads, connection establishment, and slot setup are outside this window.
- `masked_packet_to_decision_ms` measures masked packet delivery, both parties' arithmetic and network exchanges, and acknowledgment. In A the TA returns the decision directly, so this field is empty.
- For B-linux and B-tee, `scalar_decision_ms` times reconstruction and the predicate inside Linux or the final TA call, respectively. For B-mpc, `dot_sign_local_ms` uses the already-opened masked dot wire. `margin_sign_with_exchange_ms` and `and_with_exchange_ms` each include their corresponding TNO exchange. Ring conversion, multiplication and final-bit reveal have other costs.
- `module_crop_to_decision_j` and `module_setup_j` are Jetson VDD_IN energies. Consult the valid sample count for each mean or median. A 100 ms power sampling interval cannot resolve individual millisecond-scale gates. Report the setup cost separately, especially for C. Peer energy requires a separate meter.
- The batch checks paired decisions for A/B and for C/Q before reporting. This same-image run measures repeatability. Estimating verification accuracy requires a separate labeled set.

For a single B trial with the existing [B commands](B/README.md), add `--decision linux`, `--decision tee`, or `--decision mpc` to the dealer's `setup_slot.py prepare --mode B` command. Both online runners select the variant from their per-slot material.
