# Follow one verification from the photo to the decision

For full-frame input to A and the three B settings, use the [sealed camera runbook](CAMERA.md). Its TA performs face detection, alignment, cropping and SFace. Earlier crop-based measurements use a Linux-prepared input.

The online input is a **new image of y**. The gallery embedding **x** is already enrolled. In the original crop pipeline described below, Python selects the crop, calls the trusted application (TA) and schedules network messages. In the sealed-frame pipeline, the TA selects the crop. The C code in the TA computes the 128 float coordinates of y. For the hybrid settings, the TA also converts those floats to integers and masks them **before** Linux receives the embedding packet.

| Setting (internal mode) | Where y is computed | What leaves the TA at FINISH | Where the verification ends |
| --- | --- | --- | --- |
| A (A) | Secure CPU, FP32 SFace | One decision bit | TA calculates dot product, norms, both comparisons and AND |
| B-linux (H) | Same as A | Masked embedding and tag | Both parties calculate scalar shares. Drone Linux reconstructs all three scalars and decides |
| B-tee (T) | Same as A | Same packet | Both parties calculate scalar shares. TA reconstructs scalars and decides |
| B-mpc (B) | Same as A | Same packet | Two parties compare and AND on shares, then open one decision |
| C (C) | One quantized pointwise convolution on blinded data on the GPU, remaining steps on secure CPU | Same packet | Same B-mpc verifier |
| Q (Q) | Same quantized convolution on the secure CPU, remaining steps as in C | Same packet | Same B-mpc verifier |

## 1. Dealer setup and the two online roles

| Function | Input → output and purpose |
| --- | --- |
| `trials.setup` | Looks up the requested reference key in the embedding bank. Rotates setting order across repetitions. Calls the dealer separately for every slot, including warmups. Writes a manifest for each recipient. |
| `A.oracle.encode` | 128 reference floats → 128 signed integers. Multiply each by 256 and truncate toward zero. Enforce the experiment's coordinate bound of 32767. |
| `setup_slot.prepare` | Select a new 16-byte slot ID and 12-byte nonce. For A pack x. For B/C/Q call `B.mpc.distribute`. AES-GCM encrypt the TA input using the commissioning key and bind the model, mode, slot and protocol domain as associated data. |
| `B.mpc.inner / split / distribute` | Compute inner products and additive shares. Generate fresh full masks dx and dy. Give each party masked X = x + dx, its shares of dx and dy, and shares of ⟨dx,dy⟩, ⟨dx,dx⟩ and ⟨dy,dy⟩. Only the TA box carries full dy for online masking. Both parties receive the slot packet MAC key. |
| `distribute`, mode-specific | B-linux ends setup there. For B-tee add a private pad and a separate authentication key to the TA box and the peer. For MPC generate ring-conversion and sign keys, two arithmetic Beaver triples and one Boolean AND triple. C/Q use this MPC material too. |
| `B.comparison.keys` | Generate and pack the two DCF keys for each dealer threshold. The DCF (distributed comparison function) lets parties evaluate complementary shares of a threshold test on a public masked input. |
| `setup_slot.exclusive` | Create private output files with exclusive creation. Party 0 receives its JSON and the TA box. Party 1 receives its own JSON. |
| `trials.peer_trials / drone_trials / run` | Start per-trial processes and coordinate over ports 61503/61504. Skip party 1 for A. Verify slot IDs in completed peer reports. `B.mpc.peer_pool` opens the TNO transport used by both the coordinator and the online parties. |

## 2. What actually runs in the TEE

The entry path for **each command** is `run.Session.call → bridge.c exp_call → TEEC_InvokeCommand → TA_InvokeCommandEntryPoint → dispatch`. Follow these files in order: [Python invoker](run.py), [Linux OP-TEE client](ta/bridge.c), [experiment dispatcher](ta/experiment.c), [base trusted model driver](../secure_sface/ta/secure_ta.c), [numerical kernels](../secure_sface/runtime.c).

| Step / function | Inputs, operations and result |
| --- | --- |
| `run.main → Session.__init__ → exp_open` | Linux loads bridge.so and opens the experiment UUID with libteec. The TA's `TA_OpenSessionEntryPoint` allocates session state and the private activation buffers. A hardware error stops the run. |
| `Model.__init__` | Read the generated manifest and weight blob and check its digest on the host. Split it into 172 scheduled weight/operation blocks. Private TA verification below is independent of the host check. |
| `Session.call(SETUP) → setup → unseal` | Copy and authenticate the dealer box inside the TA. In A load x. In the hybrid modes load full dy and the packet MAC key, call `spend` to record the used slot, and load any mode-specific material. `keys.h` implements one-time provisioning, key loading, AEAD and MAC operations via OP-TEE. |
| `Model.setup` | For C/Q only, submit three pinned weight tiles with TILE and finalize their preparation with OFFLINE. See section 5. |
| `dataset_tee.prepare_face` | Linux detects and aligns the first face and supplies packed 112×112 BGR uint8 pixels. With `--prepared-bgr`, Linux reads the precomputed 37,632-byte crop. In both cases the camera stream is simulated. Linux has access to those pixels. |
| `Model.extract → BEGIN → invoke(SF_BEGIN) → sf_input` | TA copies the crop into private memory and converts pixel layout/values into its input tensor. |
| `Model.extract → STEP → invoke(SF_STEP) → sf_step_run` | For each ordinary step the TA copies the block once, checks SHA-256 against its compiled table, then runs the operation using that same copy. Convolution calls `convolution`. Activations persist inside the session. The last step leaves a 128-float embedding in the private activation buffer. |
| `Model.extract → FINISH → finish → sf_encode` | TA multiplies each float by 256 and truncates toward zero. Coordinate limits are checked. A passes x and y to `plain_decision`. Hybrid settings add dy coordinate by coordinate modulo 2⁶⁴, then MAC the slot ID and 1,024 masked bytes. The result is 1,072 bytes including ID and tag. |
| `finish / reset / Session.close / exp_close` | Copy the authorized result to the host and wipe working buffers. B-tee retains the minimum state for DECIDE in the same session. Close and release session memory. |

The earlier extraction-only TA has its own FINISH path and UUID. The experiment's dispatcher delegates the old BEGIN and STEP handlers only. Secure persistent storage holds the experiment commissioning key and spent-slot objects for hybrid modes. The three B settings compute yy from dealer correlations outside the TA. They do **not** implement an alternative in which the TA outputs yy.

## 3. A and the meaning of the returned bit

`A/decision.h:21–31 plain_decision` accumulates d = ⟨x,y⟩, xx = ⟨x,x⟩ and yy = ⟨y,y⟩. `decide_terms` checks bounds and accepts exactly when both d ≥ 0 and 100000000 × d² ≥ numerator × xx × yy. The comparisons include equality. For a zero vector this predicate accepts when both sides are zero, matching the implemented algebra. An application that rejects empty/degenerate features would need a separate input rule. The authenticated dealer profile sets the numerator to 11368578 for LFW or 6247600 for DroneFace. Cheng's plaintext script supplies the predicate structure and reads both vectors from files. This A changes the live input, the arithmetic and the execution site. [Decision code](A/decision.h) · [Cheng plaintext, lines 35–52](https://github.com/nann-cheng/CondEval/blob/fb6f5a7d4a4138ee8be81e72b643edbded1586ef/plainEval.py#L35-L52)

## 4. B, from masked coordinates to the decision

For each role i, square brackets below mean its private additive share. The masked vectors X and Y are public to the parties. The formulas are evaluated modulo 2⁶⁴. Only role 0 inserts the public term, so adding the parties' results reconstructs the scalar exactly once.

| B/mpc.py lines | Function and result |
| --- | --- |
| 103–160 | `peer_pool` creates TNO HTTP endpoints on loopback. `Exchange.__call__` sends and receives a slot- and sequence-bound authenticated message. `mac` and `tno_counts` supply the tag and transport counters. SSH forwards these endpoints between machines. |
| 201–222 | `verify` validates the packet, unpacks Y and computes [d] = public ⟨X,Y⟩ − ⟨X,[dy]⟩ − ⟨Y,[dx]⟩ + [⟨dx,dy⟩]. For [yy] use public ⟨Y,Y⟩ − 2⟨Y,[dy]⟩ + [⟨dy,dy⟩]. The analogous expression gives [xx]. This is how the dealer supports the self-products. |
| 163–199, 223–226 | **B-linux** uses `scalar_decision`. Peer sends its three shares to drone Linux, which adds its own, interprets signed d, checks bounds, compares and sends the result. The host learns d, xx and yy as well as the bit. |
| Same Python function, TA lines 149–180 | **B-tee** encrypts the peer's three shares with the one-slot XOR pad and authenticates them against the masked embedding packet. Linux relays them and its own shares via DECIDE. TA `decide` checks the MAC, unmasks, recombines and calls `decide_terms`. Both parties learn the bit. |
| 227–234 | **B-mpc** opens masked scalars. `B.comparison.evaluate` returns shares of the wrap/carry when lifting from 64- to 128-bit arithmetic. |
| 235–242 | `nonnegative` uses the public high bit, a DCF share for the lower-bit borrow, and a share of the mask's high bit. This gives XOR shares of d ≥ 0. |
| 243–251 | Two arithmetic Beaver products compute d² and xx·yy. For each product the parties open operand differences from fresh dealer masks and locally combine their triple shares and the public correction. |
| 252–257 | Form the signed margin. Mask and open it, then call `nonnegative` for XOR shares of margin ≥ 0. |
| 258–265 | Use one Boolean Beaver triple to AND the two secret sign bits. Open the XOR shares of the **final** bit. Each party acknowledges its result. The two individual sign bits stay shared. |
| 268–end | `consume` creates a per-party spent marker. Peer `main` receives the packet, calls the same verifier, checks agreement, and returns its timing and communication counts. |

The protocol assumes a trusted dealer, fresh setup material, and non-colluding semi-honest parties. The packet authentication key is shared with both parties. It cannot prove TA origin against a malicious party holding that key. B-tee authenticates the peer's scalar shares to the TA, while the drone supplies its own shares. The plaintext decision and its privacy implications are different from revealing three scalars. All settings deliberately deliver a decision to the drone. [MPC code](B/mpc.py) · [TA decision](ta/experiment.c)

## 5. C and its control Q

| Function | Where | Operation |
| --- | --- | --- |
| `load_tile / quantize` | TA | Check the pinned tiles (indices 53–55) for SFace conv_9_conv2d. Quantize weights with scale 256, round to nearest with ties away from zero, retain bias. This layer conversion differs from truncation of the final embedding. |
| `field / random_field / prepare_gpu` | TA, C setup | In the prime field p = 2³¹−1, sample fresh activation mask R, compute W·R, choose two secret projection vectors v and precompute vᵀW. This R is independent of the dealer's embedding mask dy. |
| `layer_input` | TA, C or Q | Quantize the live activation, check a bound for signed decoding. For C export only its sum with R. |
| `cuda_worker → blinded_conv → pointwise` | Linux and GPU, C | Allocate device buffers, copy public weights and the blinded activation, compute W·(activation + R) mod p, copy the result back and free the buffers. |
| `accept_gpu / advance_layer` | TA, C | Copy the answer privately, subtract W·R, check two random projections, decode, rescale, add bias, and advance to model step 56. Failure aborts the frame. |
| `cpu_control / advance_layer` | TA, Q | Compute the same quantized convolution directly in secure memory. This gives a comparison with the same quantization and no GPU transfer. |
| `Model.extract → finish → B.mpc.verify` | TA then both parties | Resume the remaining FP32 SFace steps. Both C and Q use the B-mpc final embedding mask and decision. |

C implements the Slalom idea for **one** SFace linear layer on Orin. The original Slalom prototype uses SGX/TensorFlow. The TA layer and CUDA worker in this repo are a separate implementation. Compare C with Q to isolate delegation and Q with B-mpc to see the effect of changing the layer arithmetic. [Slalom paper](https://arxiv.org/abs/1806.03287) · [Authors' implementation](https://github.com/ftramer/slalom) · [TA layer](C/layer.h) · [CUDA worker](C/worker.cu)

## 6. Measurement, test functions and origins

`profile_run.main` wraps the same session and CUDA callbacks used by the hardware runner. `timed_call` accumulates wall times by command and measures BEGIN through entry to FINISH. `timed_cuda` includes copies and allocation. `record` sums durations and counts calls. `trials.summarize` checks paired decisions and computes means and medians after warmup. Timings of nested operations overlap. The loopback median for B-mpc was 1,138.93 ms through extraction, 6.91 ms for FINISH, and 32.03 ms from the masked packet through acknowledgment. FINISH includes encoding, masking, authentication and wiping. The timer does not resolve mask addition alone. [Full measured table for all six settings](measurements/jetson1-loopback-operation-medians-ms.csv)

`A.oracle.terms / decision` form the Python reference. `A.pairs.enroll / evaluate` prepare labeled enrollments and evaluate photos. `A/test_oracle.c:test_extract` exposes floats in a workstation-only oracle. `check.reference_probe / checked_pair / circuit_cases / run_case / decision_variants / rejected_gpu` test the kernel result, shared arithmetic, decision placements and rejection paths. `compare_native.main` runs paired controls on public inputs. `ta/native_keys.h` provides native substitutes for the storage and crypto API. These are validation entry points, separate from the hardware call chain.

**Source lineage.** For the historical hardware-run revision `620f12cf`, read the [line-by-line source index](SOURCE_LINES.csv) alongside the code. Its paths start at the repository root. Each experiment executable/build source line has an entry, including imports and declarations. The file and line identify what was shipped. The symbol identifies the enclosing function. A design reference identifies a mathematical or API relationship. A literal match identifies identical text in a source we compared. For the new files we recorded one longest contiguous exact-text match of at least three lines containing at least two substantive lines, against the checked local predecessors, the pinned CondEval Python checkout and the saved operation profiler. Boilerplate can match by coincidence. An empty literal-reference cell means attribution beyond Git history and the listed design dependency is unverified. For direct includes, the original file supplies the compiled lines verbatim. Git history establishes when this project acquired a line. It cannot establish who first conceived or wrote an uncredited line.

| Component | Verifiable origin and what changed |
| --- | --- |
| SFace checkpoint and inference | Weights originate from OpenCV Zoo's December 2021 FP32 checkpoint, SHA-256 `0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79`. Existing `secure_sface/export_model.py` generates the schedule, digest table and blob. `ta/kernels.c:1` compiles the earlier repository runtime verbatim. `ta/experiment.c:7–13` includes the earlier trusted driver with renamed entry points. Both earlier source files date to repository commit `ec4debea`. [OpenCV Zoo SFace](https://github.com/opencv/opencv_zoo/tree/main/models/face_recognition_sface) |
| Input convention | In the local historical `ppface/pyscripts/Untitled.ipynb`, cell 38 line 47 calls `DeepFace.represent`. Cells 39, 41 and 42 call it at line 77 and write an embedding cache at line 201 (cells counted from one including markdown). The benchmark reuses `dataset_tee.prepare_face:140–163` for Linux preprocessing. The experiment does its live inference in the TA. |
| Quantization and verification | `common/helper.py:50–65` and `common/constants.py:116–119` supply Obscura's truncation rule and threshold. Cheng's `plainEval.py:35–52` describes the two comparisons. `A/oracle.py` and `A/decision.h` implement the configured decision using integer cross-multiplication. |
| MPC and TNO | Obscura's `obscura-protocol/obscura.py` and `cheng.py` are references for the masked-wire and TNO workflow. The experiment builds new dealer slots and a distinct circuit. It imports TNO for communication and implements its own wide multiplication, sign adaptation, AND and output routing. Cheng's naive semi-honest server has a two-comparison and multiplication path. Its optimized server uses a conditional-evaluation construction. Their online transcripts and benchmark numbers are not interchangeable. [Naive server](https://github.com/nann-cheng/CondEval/blob/fb6f5a7d4a4138ee8be81e72b643edbded1586ef/naive-sh-protocol/server.py#L195-L256) · [Optimized server](https://github.com/nann-cheng/CondEval/blob/fb6f5a7d4a4138ee8be81e72b643edbded1586ef/semi-honest-protocol/server.py#L201-L232) |
| Exact Cheng reuse | The repository's complete 683-line `libfss/fss.py` matches Cheng's pinned file byte for byte, SHA-256 `9eda162891f05c39965bd00b7b179a7eb9e733a2fa94321b376dc71957510c49`. Local line n = upstream line n. `B/comparison.py` loads a private module instance, overrides root sampling and the tree PRG/group conversion, and calls the inherited `DCF.keyGen:229` and `DCF.eval:349`. The historical file on disk remains identical, including code paths the experiment never calls. [Pinned upstream file](https://github.com/nann-cheng/CondEval/blob/fb6f5a7d4a4138ee8be81e72b643edbded1586ef/libfss/fss.py) |
| Hardware adapters and pilot | Experiment-specific TA commands, Python runners, dealer box, decision placements and CUDA pilot first appear on this branch in `229e4539`. OP-TEE supplies the client/internal APIs and TA build kit. Slalom supplies the blinded linear-layer and verification design. The operation profiler was adapted from the wrapper used in the saved Jetson 1 operation batch. |
