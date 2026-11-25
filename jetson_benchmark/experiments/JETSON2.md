# Run the verification benchmark across two Jetsons

Keep the camera simulation, SFace TA, GPU worker and party 0 on **Jetson 1**. Move party 1 to **Jetson 2**. This changes where the second party spends CPU time and makes the messages cross the network. A runs on Jetson 1 alone. The workstation is the trusted dealer.

| Machine | Install | Receives for this run |
| --- | --- | --- |
| Workstation | Obscura, Python, cryptography | Existing dealer key and enrolled reference x |
| Jetson 1, drone | Existing R35.5.0 dataset environment, model, experiment TA, bridge, CUDA worker, TNO | Drone directory and one probe photo |
| Jetson 2, peer | Obscura checkout, Python 3.8+ with venv and TNO | Peer directory |

## 1. Publish and pull the same revision

On the workstation, from the repository root, run:

```bash
git branch --show-current
git status --short
git log -3 --oneline
git push origin feature/jetson-tee-benchmark
git rev-parse HEAD
git ls-remote origin refs/heads/feature/jetson-tee-benchmark
```

Compare the two hashes. Push the branch commits as a unit. They contain the image fetcher, experiment sources and requirements, reproducible model bundle, signed lab TA, bridge and CUDA worker, timing wrapper, and guides. Private setup files live outside Git. Keep the dealer key, role material, photos, masked packets, results and local virtual environments off the staging list. The original public-fixture embedding bank is already part of the repository.

From the workstation, use two separate SSH terminals. These examples use the lab LAN addresses. Set the gateway to your existing login or SSH alias.

```bash
export GATEWAY='user@gateway'
ssh -J "$GATEWAY" client@192.168.0.103
# In a second workstation terminal, set GATEWAY there too
ssh -J "$GATEWAY" server@192.168.0.105
```

On **each Jetson** with an existing checkout:

```bash
cd ~/Documents/Obscura
git status --short
git fetch origin feature/jetson-tee-benchmark
git switch feature/jetson-tee-benchmark
git pull --ff-only origin feature/jetson-tee-benchmark
git rev-parse HEAD
```

If the peer has no checkout, run this on the peer instead:

```bash
mkdir -p ~/Documents
git clone --single-branch --branch feature/jetson-tee-benchmark https://github.com/DominikRoy/Obscura.git ~/Documents/Obscura
git -C ~/Documents/Obscura rev-parse HEAD
```

Both hashes must match the workstation revision you intend to test. If Git reports local edits or divergent history, preserve them and use a fresh checkout for this experiment.

## 2. Set up the peer on Jetson 2

```bash
cd ~/Documents/Obscura/jetson_benchmark/experiments
python3 -m venv ~/.venvs/obscura-peer
source ~/.venvs/obscura-peer/bin/activate
python -m pip install -r B/requirements.txt
python -c 'from B.comparison import ComparisonTree; from tno.mpc.communication import Pool; print("Peer imports OK")'
python trials.py peer --help
```

If venv creation reports that ensurepip is missing, install the Ubuntu package with `sudo apt-get install python3-venv`, then rerun the commands. Party 1 runs Python. There is nothing to compile or commission on Jetson 2 in this role.

## 3. Check the drone on Jetson 1

```bash
cd ~/Documents/Obscura/jetson_benchmark
source .dataset-venv/bin/activate
python check_jetson.py
cd experiments
python -m pip install -r B/requirements.txt
(cd ../dist && sha256sum -c jetson_sface_r35.5.0.tar.gz.sha256)
tar -C .. -xzf ../dist/jetson_sface_r35.5.0.tar.gz --strip-components=1 jetson_benchmark/secure_sface/generated
(cd prebuilt && sha256sum -c SHA256SUMS)
tar -xzf prebuilt/orin-r35.5.0.tar.gz
UUID=85fe4e6b-839b-4024-8474-00c4de898504
cmp -s "build/ta/$UUID.ta" "/lib/optee_armtz/$UUID.ta" || sudo install -m 0644 "build/ta/$UUID.ta" /lib/optee_armtz/
ldd build/bridge.so
ldd build/gpu.so
python -c 'from run import Session; session = Session(False); session.close(); print("Experiment TA opened")'
```

Resolve any missing shared library before the batch. The probe opens the experiment UUID. It does not spend a slot. Jetson 1 already has its experiment commissioning key. Use the matching dealer key for the next step. If preparing a *different* drone for the first time, follow the trusted commissioning steps in [the experiment README](README.md). The dataset environment and image fetching instructions are in [the dataset workflow](../DATASET_WORKFLOW.md).

### Optional source rebuild for the drone

The signed package above is the shortest route to the same binary. To rebuild, use an x86-64 Linux build machine and NVIDIA's R35.5.0 BSP sources and Bootlin GCC 9.3 toolchain. Extract the toolchain. Inside `public_sources.tbz2` extract `Linux_for_Tegra/source/public/nvidia-jetson-optee-source.tbz2`, then unpack that archive. The resulting directory contains `optee/optee_os` and `optee/optee_client`. [NVIDIA release downloads](https://developer.nvidia.com/embedded/jetson-linux-r3550)

From the build machine's experiments directory, substitute the two absolute paths:

```bash
tar -C .. -xzf ../dist/jetson_sface_r35.5.0.tar.gz --strip-components=1 jetson_benchmark/secure_sface/generated
python3 -m venv ~/.venvs/obscura-build
source ~/.venvs/obscura-build/bin/activate
python -m pip install pyelftools pycryptodome cryptography
export PYTHON3="$VIRTUAL_ENV/bin/python"
export OPTEE_SRC=/absolute/path/to/optee
export CROSS_COMPILE=/absolute/path/to/toolchain/bin/aarch64-buildroot-linux-gnu-
export BUILD_ROOT="$HOME/.cache/obscura-r355-sdk"
bash ../secure_sface/build_r35_5.sh "$OPTEE_SRC" "$CROSS_COMPILE" "$BUILD_ROOT"
export TA_DEV_KIT_DIR="$BUILD_ROOT/ta-kit/export-ta_arm64"
export OPTEE_CLIENT_EXPORT="$BUILD_ROOT/client-export"
./build.sh jetson
UUID=85fe4e6b-839b-4024-8474-00c4de898504
scp -J "$GATEWAY" "build/ta/$UUID.ta" build/bridge.so client@192.168.0.103:~/
```

On Jetson 1 with the matching CUDA 11.4 toolkit, from the experiments directory:

```bash
mkdir -p build/ta
UUID=85fe4e6b-839b-4024-8474-00c4de898504
install -m 0644 "$HOME/$UUID.ta" build/ta/
install -m 0755 ~/bridge.so build/
sudo install -m 0644 "build/ta/$UUID.ta" /lib/optee_armtz/
export PATH="/usr/local/cuda-11.4/bin:$PATH"
./build.sh cuda
sha256sum "build/ta/$UUID.ta" build/bridge.so build/gpu.so
```

Use the three newly built binaries together. The TA uses the lab SDK signing configuration. This procedure builds userspace artifacts and requires an already working R35.5 OP-TEE installation. Record the source revision and resulting hashes for comparison.

## 4. Generate fresh slots on the trusted workstation

From `jetson_benchmark/experiments`, use a Python environment with cryptography. Export the path to the **existing Jetson 1 dealer key**. For the original workstation checkout the path below is the key used for the loopback run. For another checkout substitute the secure location of that same key.

```bash
umask 077
export DEALER_KEY="$PWD/lab/jetson1-loopback-VvQWVqnC/dealer.key"
test -r "$DEALER_KEY" || exit 1
export BATCH="twojetson-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p lab
python3 trials.py prepare --key "$DEALER_KEY" --threshold-profile droneface \
  --bank ../../data/embeddings_droneface_raw_sface9.txt \
  --reference ../DnHFaces/open_data_set/trio_cam/k_cam_0_porF_00.jpg \
  --warmups 1 --repeats 5 --out "lab/$BATCH"
scp -J "$GATEWAY" -r "lab/$BATCH/drone" "client@192.168.0.103:~/drone-$BATCH"
scp -J "$GATEWAY" -r "lab/$BATCH/peer" "server@192.168.0.105:~/peer-$BATCH"
echo "$BATCH"
```

The original Jetson 1 timing runs used the LFW threshold. To reproduce their decision policy, select `--threshold-profile lfw` when preparing those slots. Use the printed batch name on both devices. This creates 36 trials, with one warmup and five measured repeats for each of six settings. Each invocation gets a fresh slot. For a retry after a partial run, return here with a fresh batch name and material. Keep the two recipients' material separate.

## 5. Start the tunnel, then the peer, then the drone

**Jetson 2, terminal 1.** This SSH login goes from the peer to the drone on the lab LAN. Keep it open. The four loopback listeners carry TNO data and batch coordination in both directions.

```bash
ssh -N -o ExitOnForwardFailure=yes \
  -L 127.0.0.1:61501:127.0.0.1:61501 -R 127.0.0.1:61502:127.0.0.1:61502 \
  -L 127.0.0.1:61503:127.0.0.1:61503 -R 127.0.0.1:61504:127.0.0.1:61504 \
  client@192.168.0.103
```

**Jetson 2, terminal 2.**

```bash
cd ~/Documents/Obscura/jetson_benchmark/experiments
source ~/.venvs/obscura-peer/bin/activate
BATCH='paste-the-printed-batch-name'
python trials.py peer --peer-material "$HOME/peer-$BATCH"
```

**Jetson 1.** Once the peer prints `Peer batch ready`, run in your interactive SSH terminal. This aligns the public probe once before timing, then sends the same crop through a new TA session for each trial. Set `IMAGE` to the actual location on this board if the dataset is elsewhere.

```bash
cd ~/Documents/Obscura/jetson_benchmark/experiments
source ../.dataset-venv/bin/activate
BATCH='paste-the-printed-batch-name'
IMAGE="../../ppface/DnHFaces/open_data_set/photos_all_faces/k_gp_3_ef_27.jpg"
CROP="$HOME/drone-$BATCH/probe.bgr"
PYTHONPATH=.. python -c 'from pathlib import Path; import sys; from dataset_tee import prepare_face; crop,_=prepare_face(Path(sys.argv[1])); Path(sys.argv[2]).write_bytes(crop.tobytes())' "$IMAGE" "$CROP"
wc -c "$CROP"
sha256sum "$CROP"
sudo -v
timeout 3s ../jetson_power/tegrastats --interval 100 | head -n 5
# Check that VDD_IN appears before continuing.
export PATH="$PWD/../jetson_power:$PATH"
python trials.py run --drone "$HOME/drone-$BATCH" --prepared-bgr "$CROP" \
  --power --profile-operations --output "../results/$BATCH"
```

Expected crop length is 37,632 bytes. For the published loopback comparison the SHA-256 was `0ac1fa0be8a34813bd8e1e71fa254db2906fc704956edbf1d6b17e2df288b952`. A different crop changes the experimental input. On sudo configurations that isolate credentials per process, the noninteractive power helper may lack access to VDD_IN. The preflight above lets you check the rail before spending any slots. If the rail only appears under interactive sudo, the following alternative uses one privileged reader and an unprivileged follower per trial. In the drone terminal, run this before the batch, check the rail, then run the same `python trials.py run` command above with the new PATH. Keep the SSH session open.

```bash
METER_DIR=$(mktemp -d)
export OBSCURA_RAIL_LOG="$METER_DIR/rail.log"
sudo -v
sudo -n timeout 45m /usr/bin/stdbuf -oL /usr/bin/tegrastats --interval 100 > "$OBSCURA_RAIL_LOG" &
cat > "$METER_DIR/tegrastats" <<'SH'
#!/bin/sh
exec /usr/bin/tail -n 0 -s 0.02 -f "$OBSCURA_RAIL_LOG"
SH
chmod 700 "$METER_DIR/tegrastats"
export PATH="$METER_DIR:$PATH"
sleep 1
tail -n 2 "$OBSCURA_RAIL_LOG"
```

This alternative fixes sampling at 100 ms, the interval used by the experiment runner. The single reader stops after 45 minutes. If power sampling is unavailable, omit `--power` for a timing-only batch and label it accordingly. A failed run can consume slots. Stop the tunnel with Ctrl-C after both batch processes exit.

## 6. Validate the run and read the results

On the drone, in the experiments directory and the same shell:

```bash
python trials.py summary "../results/$BATCH"
python - "../results/$BATCH" <<'PY'
import json, sys
from pathlib import Path
root = Path(sys.argv[1])
manifest = json.loads((root / 'trials.json').read_text())
for trial in manifest:
    path = root / trial['name']
    rec = json.loads((path / 'summary.json').read_text())
    calls = json.loads((path / 'op-times.json').read_text())['calls']
    assert rec['backend'] == 'OP-TEE'
    assert calls['weight_and_kernel'] == (169 if rec['setting'] in ('C','Q') else 172)
    if rec['setting'] == 'C':
        assert rec['gpu_worker'] == 'CUDA' and calls['cuda_worker'] == 1
    if rec['setting'] != 'A':
        peer = json.loads((path / 'peer-summary.json').read_text())
        assert (peer['slot'],peer['decision']) == (rec['slot'],rec['decision'])
print(len(manifest), 'hardware trials checked')
PY
```

`medians.json` records counts, medians and means excluding warmups. For this recipe expect five measured trials per setting. `summary` checks agreement within the FP32 group and within the quantized group for each repeat. The same public probe tests repeatability. To measure verification accuracy, use labeled pairs. In a profiled run, `medians.json → setting → operation_ms` gives mean and median elapsed milliseconds per operation. The per-trial `op-times.json` contains elapsed **nanoseconds** and call counts. `summary.json` gives online latency in **milliseconds**, setup in **seconds**, and integrated drone **joules** when power samples cover the window. The masked packet and individual trial files stay in the private results directory.

Compare the two-board run to the [Jetson 1 loopback medians](measurements/jetson1-loopback-operation-medians-ms.csv). Record both board models, power modes (`sudo nvpmodel -q`), thermal state, revision, crop digest and LAN/tunnel configuration. Splitting parties changes both network latency and which CPU the drone's VDD_IN meter covers. A second synchronized meter is needed for combined two-board energy. TA heap and stack settings are budgets. This suite does not instrument peak secure RAM or storage filesystem overhead.
