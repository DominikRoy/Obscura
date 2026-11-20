# Validation and remaining hardware check

Target: NVIDIA Orin Nano, Jetson Linux R35.5.0 (JetPack 5.1.3 BSP).

Completed locally:

- Exported the pinned OpenCV SFace FP32 checkpoint, SHA-256
  `0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79`.
- Compared all 128 output coordinates of the portable C kernels against ONNX
  Runtime 1.32.0 on four synthetic crops: zero, constant 127, seeded random pixels
  and a horizontal gradient. Largest absolute error: **8.821487426757812e-06**.
  The fixed-point coordinates were identical for all four inputs. This does not
  guarantee identical quantization at all floating-point rounding boundaries.
- Executed the real TA source against a test-only host GlobalPlatform substitute
  with undefined-behavior sanitization: valid inference/masking, bad parameter
  lengths/types, finish-before-inference, modified weight rejection, state reset
  after failure and repeated-finish rejection passed. This is not hardware TEE
  execution, and the deterministic test RNG is not linked into the real TA.
- Passed 17 Python tests, including telemetry integration, masking arithmetic,
  output formats, notebook syntax and failure without a baseline fallback.
- Built the TA kit from NVIDIA's actual R35.5.0 source archive, platform `tegra`,
  flavor `t234`, with `CFG_TA_FLOAT_SUPPORT=y`. Compiled and linked the user TA
  and Linux bridge using NVIDIA's recommended Buildroot GCC 9.3.0 toolchain.
  The TA is signed with the source bundle's default development TA key.
- Confirmed the bridge and TA ELF files target AArch64. The bridge depends on
  `libteec.so.1` and `libc.so.6`, not OpenCV or a normal-world inference runtime.

`generated/native_validation.json` holds the numerical report;
`generated/build_manifest.json` identifies packaged artifacts. The synthetic test
images contain no user biometric information. The packaged weights are public.

The user's target diagnostics confirm TEE client/private devices, a running
`tee-supplicant`, and installed `libteec`. `/dev/tee0` needs client-account access.

Still required on the Jetson:

1. Install the TA with signing accepted by the running OP-TEE and grant client
   device access as described in the parent README.
2. Run `python3 secure_sface/probe.py` to establish real invocation, memory
   allocation and inference completion on the board.
3. Run the notebook with aligned face inputs and actual `tegrastats` power samples.
4. For publication, validate representative face embeddings/recognition behavior,
   repeat runs under recorded power/thermal settings and confirm model provenance.

No Jetson latency, energy, recognition accuracy or production security result is
claimed by the local checks. The current code does not provide protected camera
capture, remote attestation, or correlated two-party dealer preprocessing.
