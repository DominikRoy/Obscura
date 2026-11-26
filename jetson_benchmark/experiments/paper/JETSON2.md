# Run Obscura with Jetson 2 as the wireless device

Jetson 1 is the drone. It runs the standalone SFace experiment, initiates every verification, calls its TA for P/R and measures its VDD_IN rail. Jetson 2 is the wireless device (WD). It receives the masked probe, evaluates the original two share functions and replies to Jetson 1. Its setup consists of Python, TNO and its own dealer delivery. The trusted workstation prepares separate files for the two roles. [Original-code walkthrough](README.md#follow-one-verification-in-the-source)

| Machine | Input to transfer | Output |
| --- | --- | --- |
| Trusted dealer | Existing Jetson 1 dealer key, public probe image and repository test vectors | Two role-specific pickle files and a sealed frame |
| Jetson 1, drone | `drone.pkl`, sealed frame and matching public image | SFace trace, TA heap peak, protocol timings, drone energy and decision bits |
| Jetson 2, WD | `wd.pkl` | Two shares per probe and local share-computation time, both returned to the drone |

## 1. Use the same revision on all three machines

For a first checkout on either board use the command below. For an existing checkout, fetch the branch, switch to it and fast-forward. Record the same commit hash on the dealer and both boards. The repository includes the labeled pairs and their stored embeddings.

```bash
git clone --branch feature/jetson-tee-benchmark https://github.com/DominikRoy/Obscura.git ~/Documents/Obscura
```

```bash
cd ~/Documents/Obscura
git fetch origin feature/jetson-tee-benchmark
git switch feature/jetson-tee-benchmark
git pull --ff-only origin feature/jetson-tee-benchmark
git rev-parse HEAD
cd jetson_benchmark/experiments
```

Commands below start in `jetson_benchmark/experiments` unless specified. Use Bash. The hardware build targets Orin Nano, L4T R35.5.0, Python 3.8 on Jetson 1.

## 2. Set up the WD on Jetson 2

```bash
python3 -m venv ../.paper-venv
source ../.paper-venv/bin/activate
python -m pip install --upgrade pip
python -m pip install 'numpy==1.24.3' cryptography -r B/requirements.txt
python paper/two_board.py wd --help
```

If venv creation reports that ensurepip is missing, install the distribution's `python3-venv` package. The WD command uses the Python implementation of the original gates and TNO 4.8.1. It has no TA build, commissioning, camera, image, or power-sensor setup.

## 3. Check the already commissioned drone on Jetson 1

Activate the existing experiment environment (for this setup, `source ../.dataset-venv/bin/activate`). Check the hardware session, Linux reference library and power rail before spending a one-use slot. These commands use the publicly distributed model weights and signed experiment TA.

```bash
cat /etc/nv_tegra_release
(cd ../dist && sha256sum -c jetson_sface_r35.5.0.tar.gz.sha256)
tar -C .. -xzf ../dist/jetson_sface_r35.5.0.tar.gz --strip-components=1 jetson_benchmark/secure_sface/generated
(cd prebuilt && sha256sum -c SHA256SUMS)
tar -xzf prebuilt/orin-r35.5.0.tar.gz
./build.sh plain
UUID=85fe4e6b-839b-4024-8474-00c4de898504
sha256sum "build/ta/$UUID.ta" "/lib/optee_armtz/$UUID.ta"
python -c 'from run import Session; s=Session(False); s.close(); print("Opened hardware TA")'
python - <<'PY'
import time
from ina_meter import InputRail
with InputRail() as meter:
    now = time.monotonic()
    print(meter.trace(now, now)[-1])
PY
```

The two TA files should have digest `121933284e231bacf49ae33d0df34413b856d7e05ee5ee85d1ab3c823b4c6a7c`. If the installed file is missing or differs, install the verified paper build with `sudo install -m 0644 "build/ta/$UUID.ta" /lib/optee_armtz/` and repeat the checks. Keep the existing commissioning key. The meter prints timestamp, millivolts, milliamps and acquisition duration. If access has expired after reboot, grant the benchmark group read access to the VDD_IN attributes on Jetson 1, then rerun the meter check.

```bash
for label in /sys/class/hwmon/hwmon*/in*_label; do
  if [ "$(sudo cat "$label")" = VDD_IN ]; then
    dir=$(dirname "$label")
    ch=$(basename "$label" _label)
    sudo chgrp "$(id -gn)" "$label" "$dir/${ch}_input" "$dir/curr${ch#in}_input"
    sudo chmod g+r "$label" "$dir/${ch}_input" "$dir/curr${ch#in}_input"
  fi
done
```

## 4. Generate and distribute fresh input on the workstation

Use the dealer environment with NumPy, cryptography, OpenCV and `B/requirements.txt`. Set `DEALER_KEY` to the existing key commissioned on Jetson 1. Set `GATEWAY` to your SSH jump host. The example uses the original LFW probe used for the archived extraction table. Run from the experiments directory on the workstation.

```bash
umask 077
mkdir -p lab
DEALER_KEY=/path/to/existing-jetson1-dealer.key
GATEWAY=user@gateway
DRONE=client@192.168.0.103
WD=server@192.168.0.105
IMAGE=../../ppface/lfw/Valeri_Bure/Valeri_Bure_0001.jpg
TRIAL=$(mktemp -d "$PWD/lab/distributed.XXXXXX")
NAME=$(basename "$TRIAL")
REMOTE="Documents/Obscura/jetson_benchmark/experiments/lab/$NAME"
python ../../obscura-protocol/dealer.py jetson "$DEALER_KEY" "$TRIAL/roles"
python paper/sface_fresh.py seal "$DEALER_KEY" "$IMAGE" "$TRIAL/frame"
cp "$IMAGE" "$TRIAL/probe.jpg"
ssh -J "$GATEWAY" "$DRONE" "mkdir -p -m 700 '$REMOTE'"
ssh -J "$GATEWAY" "$WD" "mkdir -p -m 700 '$REMOTE'"
scp -o "ProxyJump=$GATEWAY" -r "$TRIAL/roles/drone.pkl" "$TRIAL/probe.jpg" "$TRIAL/frame" "$DRONE:$REMOTE/"
scp -o "ProxyJump=$GATEWAY" "$TRIAL/roles/wd.pkl" "$WD:$REMOTE/"
echo "$NAME"
```

Keep the dealer key on the trusted workstation. Existing role-specific SQLite deliveries from earlier runs are also accepted. The WD receives the masked gallery, its share seed, complementary product shares and the authentication material for its role. Both boards' clones contain the public reference test vectors. Published fixtures support reproducibility.

For a short connectivity test first, add `--limit-per-split 3` to the dealer command. Expect 27 completed pair/settings. Generate fresh material in a new trial directory and omit the limit for the full tables. Each slot and sealed frame is one-use.

## 5. Run the two experiments

**Jetson 1, measurement terminal.** Activate the drone environment. Set `NAME` to the basename printed by the dealer. Run SFace once in Linux and once inside OP-TEE on the same decoded pixels. Run the isolated mask calibration before starting protocol traffic.

```bash
NAME=distributed.REPLACE_WITH_PRINTED_SUFFIX
IN="lab/$NAME"
OUT="../results/$NAME"
mkdir -p "$OUT"
git rev-parse HEAD > "$OUT/revision.txt"
cat /etc/nv_tegra_release > "$OUT/l4t-drone.txt"
sudo nvpmodel -q > "$OUT/power-mode-drone.txt"
python paper/sface_fresh.py run "$IN/probe.jpg" "$IN/frame" "$OUT/sface.json"
python paper/mask_cost.py "$OUT/mask-energy.json"
```

**Jetson 2, WD terminal.** Set the same `NAME`. Leave this command running until the drone completes.

```bash
source ../.paper-venv/bin/activate
NAME=distributed.REPLACE_WITH_PRINTED_SUFFIX
python paper/two_board.py wd "lab/$NAME/wd.pkl"
```

Wait for `WD ready on loopback port 61754`. The WD stores consumed slots under `~/.local/state/obscura-paper-wd/`. Retain that state between runs.

**Jetson 1, second terminal.** Open this tunnel **from the drone to the WD**. Both directions are needed because TNO runs an HTTP listener at each endpoint. Use the SSH identity and password prompt on your own terminal. Keep the tunnel open.

```bash
ssh -NT -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 \
  -L 127.0.0.1:61754:127.0.0.1:61754 \
  -R 127.0.0.1:61753:127.0.0.1:61753 server@192.168.0.105
```

**Jetson 1, measurement terminal.** Start the initiator and write the two paper tables. Leave both boards otherwise idle. Record the WD revision, board model, power mode, and whether the link used Wi-Fi or Ethernet with the results. The round trip includes SSH transport.

```bash
python paper/two_board.py drone "$IN/drone.pkl" "$OUT"
python paper/report.py "$OUT/lan-groups.sqlite" "$OUT/summary.csv" \
  --per-pair "$OUT/pairs.csv" --tables "$OUT/sface.json" "$OUT/tables.md"
cat "$OUT/tables.md"
```

For the 27-row connectivity test, replace the full-population report command with this count. The drone verifies each decision during collection.

```bash
python - "$OUT/lan-groups.sqlite" <<'PY'
import json, sqlite3, sys
with sqlite3.connect(sys.argv[1]) as db:
    print(sum(len(json.loads(rows)) for rows, in db.execute("SELECT rows FROM results")))
PY
```

If a connection drops, stop the old role processes, keep the output database and WD journal, and generate **new, matching protocol deliveries** on the dealer. Start both roles with the new inputs, pointing the drone at the previous output directory. It skips committed groups. For an interrupted SFace invocation, seal a fresh frame. If a port is occupied, check for a previous tunnel or loopback benchmark.

### Direct HTTP over the experiment LAN

For a direct network measurement, prepare a fresh trial and use the same artifact revision on both boards. Use these role commands in place of the tunneled WD and drone commands in step 5. SSH can still provide the interactive terminals. The first IP is the local listener, the second is its peer.

```bash
# Jetson 2 (WD)
python paper/two_board.py wd "lab/$NAME/wd.pkl" --lan 192.168.0.105 192.168.0.103
# Jetson 1 (drone)
python paper/two_board.py drone "$IN/drone.pkl" "$OUT" --lan 192.168.0.103 192.168.0.105
```

The WD accepts TCP 61754 from the drone and the drone accepts TCP 61753 from the WD. Both boards must route directly to one another using the specified source addresses. With the WD listening, the drone can check the forward path with `curl --noproxy '*' --max-time 5 http://192.168.0.105:61754/`. A completed batch checks both directions. This mode sends ordinary HTTP on the lab network and removes SSH encryption and peer authentication from the benchmark data path. Use a trusted experiment LAN. The result database records the selected addresses and rejects resumes using a different transport.

## 6. Interpret and independently verify the tables

* **SFace table.** Rows give face preparation, SFace forward and the complete interval from decoded pixels to the raw embedding for each environment. On Linux the first interval ends at crop return. In the TA it ends when the trusted camera command returns after detection, alignment and tensor initialization. The forward interval on Jetson 1 includes weight copies, hash checks and command transitions. The secure total starts after decryption in private memory and ends at embedding readiness. The heap figure is the allocator peak for the TA over the extraction, in bytes. A short stage may have latency and too few independent sensor readings for energy.
* **Protocol table.** L, P and R each need 5,092 audited pairs. The row reports median stage times and end-to-end online latency. The WD share time is included in the round trip. Energy is gross **Jetson 1** VDD_IN joules per covered verification, amortized over online batches after setup. A system-wide two-device energy claim would need a second synchronized meter. Preserve the raw `lan-groups.sqlite`, `sface.json`, `mask-energy.json`, CSVs and board metadata.
* **Audit.** The report recomputes decisions from the repository banks, checks full split membership, unique slots and timer partitions, and re-integrates the saved rail samples. A full correctness run prints **15,276 distinct verified rows**. Use the reported energy coverage to determine how many had valid batch measurements.
* **Reference.** The existing Jetson 1 archive measured both parties on one board. To reproduce its tables on a workstation without either board, run the commands below. The archive records total SFace latency, Linux 801.68 ms and OP-TEE 1,229.00 ms, and a peak TA heap of 7,397,392 bytes. New hardware measurements supply the stage breakdown.

```bash
AUDIT=$(mktemp -d)
gzip -dc paper/pair-traces-jetson1.sqlite.gz > "$AUDIT/groups.sqlite"
python paper/report.py "$AUDIT/groups.sqlite" "$AUDIT/summary.csv" \
  --tables paper/sface-final-jetson1.json "$AUDIT/tables.md"
cat "$AUDIT/tables.md"
```
