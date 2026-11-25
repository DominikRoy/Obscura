# Per-pair time, energy and secure heap

The full comparison has 5,092 labeled pairs. LFW file 1 supplies 1,000, DroneFace file 9 supplies 2,728 and file 11 supplies 1,364. Each row of each input file is run independently in A, B-linux, B-tee and B-mpc on Jetson 1. A repeated probe or a pair shared by two splits receives fresh hardware measurements. The completion condition is 20,368 valid pair-setting rows.

## Measurements in a row

* `split`, one-based `pair_row`, `gallery`, `probe`, `label` and `setting` identify the verification. The gallery embedding is already enrolled.
* `private_pixels_to_embedding_ms` measures time from private pixels already available in the TA to the raw SFace embedding. `frame_to_decision_ms` also includes frame ingestion and the setting's final decision. The two TNO parties use separate Linux processes on one board. The model weights and network connections stay available across trials. Every measured trial opens a fresh hardware TA session and receives fresh slot material. Model weight copies and per-block verification still take place inside each timed extraction.
* The meter reads the INA3221 channel labeled VDD_IN. Each sample records input voltage (mV), current (mA), the midpoint of the two sysfs reads on the Linux monotonic clock and the read duration. It polls every 100 ms. A read spanning over 20 ms is discarded. Watts = mV × mA / 1,000,000. Both energy columns use trapezoidal integration with interpolated endpoints. The board must supply samples bracketing each window, at least three samples inside, and no gap above 300 ms across the integration window. The TA timestamps are mapped to the meter clock using the calibration in CAMERA.md. Energy includes everything drawing from the Jetson module input during the window.
* `ta_heap_at_private_pixels_bytes` and `ta_heap_private_window_peak_bytes` come from the OP-TEE **user TA allocator** (`malloc_get_stats` with `CFG_WITH_STATS=y`). At private-pixel entry the TA reads bytes already allocated and resets its high-water counter. At extraction end it reports the larger of the initial live bytes and the allocator's recorded maximum. The 12 MiB configured heap is a capacity. Occupied TA heap includes live frame, model workspace and allocator accounting. TA code, stack, OP-TEE core memory and normal-world RSS are outside this measurement. For the camera simulator the private ciphertext copy remains live at entry, so the measurement includes that allocation. This is volatile memory. No persistent embedding bytes are written. Each hybrid slot consumes a persistent spent marker.
* A trial enters the public table only if both energy windows pass, the TA returns measured heap values and the decision completes. An invalid attempt stays in the results database with its reason and waveform. A repeat re-runs the **same labeled pair and setting** with independently generated dealer material. The accepted row contains time, energy and memory from one invocation. Filtering for meter quality can select for particular scheduling conditions, so retain attempt counts when reporting results.

## Running and resuming

1. On the trusted workstation, run from the experiments directory. The default creates 205 immutable SQLite shards with two independent attempts per pair and setting. Keep these shards private. For this loopback experiment each shard contains both parties' material, encrypted setup boxes and sealed frames. The dealer key stays on the trusted workstation.

   ```bash
   python full_pairs_dealer.py --key "$DEALER_KEY" --out lab/full-pairs/material
   ```

2. Transfer the closed shards to the Jetson into `lab/full-pairs/material`. Install the signed TA from the current `prebuilt/orin-r35.5.0.tar.gz`. To rebuild the statistics variant from NVIDIA's matching R35.5 OP-TEE source tree, build its TA development kit with `PLATFORM=tegra-t234 CFG_ARM64_core=y CFG_WITH_STATS=y CFG_USER_TA_TARGETS=ta_arm64` and the matching cross toolchain (`make ... ta_dev_kit`). Use that kit's `export-ta_arm64` as `TA_DEV_KIT_DIR` for `./build.sh jetson`. The statistics-enabled allocator links into the user TA. The running Jetson OP-TEE OS can use the installed TA without a firmware reflash.

3. Give the benchmark account read access to the VDD_IN channel's label, input-voltage and input-current attributes on the INA3221 hwmon device. Hardware monitor numbering can change across boots. On the Jetson from this experiment those attributes were `/sys/class/hwmon/hwmon4/{in1_label,in1_input,curr1_input}`. Group read permissions suffice. Confirm that the label reads `VDD_IN`.

4. Run with the Jetson dataset environment's Python.

   ```bash
   python full_pairs.py run --material lab/full-pairs/material --out ../results/full-pairs
   ```

   The collector commits a slot reservation before invocation, follows the four settings in a rotating order for each pair, and atomically records the waveform and measurements after each attempt. On restart, the same command skips accepted rows and consumed slots. A lock enforces one collector per output directory. The outcome database is `attempts.sqlite`. A result with state `started` may have been interrupted and its slot remains spent.

5. Export a coverage snapshot. During an active run this includes pending pairs in `missing.csv`. Exit code 2 means coverage is incomplete. After a completed pass, any remaining rows can be retried with fresh material.

   ```bash
   python full_pairs.py export --out ../results/full-pairs
   ```

   For each additional pass, copy the completed pass's `missing.csv` to the dealer, increase the generation number and prepare just those rows. Transfer the new shards and rerun step 4 with the same result directory.

   ```bash
   python full_pairs_dealer.py --key "$DEALER_KEY" --out lab/full-pairs/material \
     --missing missing.csv --generation 1
   ```

   The final `per_pair.csv` has one accepted measurement per key and `missing.csv` contains just its header. The exporter checks agreement across the four decisions. Raw per-attempt power samples are stored as zlib-compressed JSON in the database. Each sample contains seconds from frame submission, mV, mA and sensor-read seconds. The original 184-trial comparison in CAMERA.md remains a separate measurement series.

6. Audit completeness against the original split files and independently integrate both energy windows from the stored voltage/current samples. A full audit fails on incomplete coverage, differing decisions, invalid heap measurements or a trace mismatch.

   ```bash
   python full_pairs_audit.py ../results/full-pairs --report ../results/full-pairs/audit.json
   ```
