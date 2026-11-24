# B — secure extraction and dealer-assisted two-party verification

The [four-setting Jetson runbook](../DECISION_TRIALS.md) runs A, B-linux, B-tee and B-mpc plus the C/Q extraction comparison.

**Setup rule.** The dealer generates the full, fresh `delta_y` during setup, before the drone receives the probe. The dealer puts the full value in the TA's AES-GCM box. Each computing party gets only its own share of each private mask and correlation. The trusted dealer knows enrollment x and takes no part in online verification.

## What changed from the current Obscura proof of concept

| Previous path | Experiment B |
| --- | --- |
| Dealer reads x and y from disk. Party 0's pickle includes the encoded probe and full probe mask. | `setup_slot.py` needs only x, generates `delta_y`, and emits three recipient-specific files. The TA alone receives the encrypted full probe mask on the drone. |
| Linux computes the first masked probe message. The earlier benchmark TA picks a pad independently of the dealer. | The experiment TA authenticates the slot, computes y, truncates y × 256, and adds the matching dealer mask in the 64-bit ring. |
| The online path computes y·y from the plaintext probe. | Dealer generates shares of the sums of the per-coordinate mask products for x·y, x·x and **y·y**, including the probe mask multiplied by itself. |
| The active implementation reconstructs intermediate values and compares locally. | The two parties retain secret shares throughout the verification circuit and reconstruct the decision bit. |
| Old FSS keys, fixed seeds, pickle layouts and truncation parameters belong to the earlier circuit. | This circuit reuses the repository DCF tree algorithm with fresh cryptographic root randomness and domain-separated SHAKE expansion. It uses a 128-bit comparison margin for the exact A predicate. Each role receives serialized keys in its own JSON file. |

## Setup and online steps

1. **Enroll x.** The dealer encodes the 128 floats with the same scale and bound as A. Let qx denote that vector. Generate independent full masks delta_x and delta_y in Z/(2^64). Give both parties public X = qx + delta_x. Split each mask additively. Each party receives independently randomized shares of the three mask-product sums, two scalar Beaver triples, comparison masks and FSS keys, and one Boolean AND triple.
2. **Distribute by recipient.** Give `ta.box` and `party0.json` to the drone. Give only `party1.json` to the peer. Keep `dealer.key` with the dealer after trusted commissioning. The authenticated box binds the mode, slot ID, pinned model digest and encoding policy. A fresh per-slot HMAC key authenticates the masked packet and online messages. Both computing parties know this HMAC key. This is a semi-honest comparison, with no malicious-party or public-attestation claim.
3. **Consume the setup slot.** The TA authenticates and decrypts its box and claims its slot in private storage before accepting the probe. Each party creates its own exclusive spent marker before online use. A failed trial needs fresh material. Restoring a previous storage state breaks the one-use assumption; keep each party's material and ledger together on durable storage.
4. **Extract and mask y in the TA.** The TA computes qy and releases Y = qy + delta_y modulo 2^64 plus slot metadata and an authentication tag. Linux stores the authenticated packet after verification. Linux sees the replayed source photo in this experiment.
5. **Form secret shares of the three inner products.** With Dx = delta_x and Dy = delta_y, party i calculates its share of d = x·y as `[i=0] X·Y − X·Dy_i − Y·Dx_i + share_i(Dx·Dy)`. The norm shares use the corresponding square identity. This uses the dealer's self-product correlations. Each sum stays shared.
6. **Convert and compare.** To lift a shared 64-bit residue v, open only z = v + r modulo 2^64, with r fresh and secret. Distributed comparison keys share the carry `[z < r]`. Then v = z − r + 2^64 × carry in the wider ring. Another distributed comparison on the low bits supplies the dot-product sign. Two Beaver multiplications compute d² and (x·x)(y·y). Form the scaled difference from A and obtain its sign using a second masked comparison. A Boolean Beaver AND joins the two conditions. Only the final bit is opened. Negative dot products already fail the first condition; for a nonnegative dot product the coordinate bound keeps the signed comparison margin within 128 bits.
7. **Record performance.** The drone sends the masked packet to the peer and waits for decision acknowledgment. Both processes report the decision, slot and interaction count. The drone reports crop-to-decision latency, setup latency, and measurements when power sampling is enabled. The application byte counters include the authenticated packet and round payloads. The `tno_bytes_sent` and `tno_bytes_received` counters measure the corresponding TNO serialized messages. Both sets exclude the startup greeting and HTTP, TCP and SSH overhead. The peer separately reports elapsed time after receipt of the packet. Its energy requires a separate meter.

## Run one pair

On the drone and wireless device, install the experiment transport in the active Python environment from the experiments directory.

```bash
python -m pip install -r B/requirements.txt
```

Both parties use the asynchronous TNO HTTP Pool API used in the repository's Obscura and Cheng runners. Version 4.8.1 supports the Jetson's Python 3.8. Each round carries its authenticated payload as bytes, including 128-bit ring elements encoded inside the payload. The pool serializes that payload. The TNO connection terminates at the Python processes on the two devices. [TNO release and API](https://pypi.org/project/tno.mpc.communication/4.8.1/)

From the experiments directory on the dealer:

```bash
python setup_slot.py prepare --mode B --key lab/dealer.key \
  --bank ../../data/embeddings_droneface_raw_sface9.txt \
  --reference ../DnHFaces/open_data_set/trio_cam/k_cam_0_porF_00.jpg --out lab/b01
```

Use private, authenticated delivery to place the files on their respective devices. The commands assume the same relative paths on each device. The controller prints a waiting message after setup.

```bash
# Drone, with ta.box and party0.json only
python run.py --box lab/b01/ta.box --party0 lab/b01/party0.json \
  --image ../../ppface/DnHFaces/open_data_set/photos_all_faces/k_gp_3_ef_27.jpg \
  --output ../results/B-k-01
```

Both TNO parties listen on loopback, with the drone on port 61501 and the peer on 61502. On the peer, create both SSH forwards with the same port numbers on each side so TNO can identify each sender. Keep this terminal open. In another peer terminal run party 1. The experiment waits up to 180 seconds for the peer.

```bash
ssh -N -o ExitOnForwardFailure=yes -L 127.0.0.1:61501:127.0.0.1:61501 -R 127.0.0.1:61502:127.0.0.1:61502 client@JETSON_HOST
# On the peer, from its experiments directory
python B/mpc.py lab/b01/party1.json --connect 127.0.0.1 61501
```

For a public-fixture loopback test with both roles on one machine, connect directly to 61501. Use separate devices for a distributed measurement. Keep the raw bank and dealer files off the operational drone when evaluating the reference-privacy assumption.
