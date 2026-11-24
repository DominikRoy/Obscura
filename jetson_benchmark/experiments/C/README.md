# C — one Slalom-style GPU layer followed by the B verifier

C uses the same dealer-generated final probe mask and two-party decision as B. The normal-world GPU sees a blinded activation. The intervention is limited to SFace's `conv_9_conv2d`, a 512-to-512 pointwise convolution on 14 × 14 positions; 51,380,224 multiply-accumulates. This one-layer pilot is a new implementation for OP-TEE and CUDA. The authors' repository targets Intel SGX and TensorFlow 1.8 and describes its own implementation as a performance prototype. [Slalom repository](https://github.com/ftramer/slalom) · [Paper, Figure 1](https://arxiv.org/pdf/1806.03287#page=5)

## Setup

1. The trusted dealer runs the B setup with mode C and distributes the final embedding mask in the TA's encrypted box. The C layer mask R below is independent of delta_y.
2. The TA loads and SHA-256 checks the pinned weight blocks 53–55, quantizes the convolution weights to signed integers using scale 256 and nearest rounding with ties away from zero, and keeps the original FP32 bias. Q performs the same quantization.
3. In setup the TA samples one uniform R per input element in the prime field with p = 2147483647 and computes U = W R. For two independent secret random output-channel vectors v it also computes vᵀW. This pilot keeps the one-use material in volatile secure memory. New setup is charged per frame, even with unchanged public model weights.

## Online

1. The original secure FP32 runtime executes the preceding steps. The TA quantizes that layer's input X and checks a conservative per-frame bound using the largest quantized weight-row L1 norm. An out-of-range value aborts the frame to prevent ambiguous signed decoding.
2. The TA exports X + R modulo p. The CUDA worker processes only the blinded 512 × 196 matrix and public quantized weights. It returns Z = W(X + R) modulo p using bounded signed 64-bit accumulators. Matrix layout is channel-major.
3. The TA copies Z once into private memory, validates the field elements, and subtracts U. It checks vᵀ(Z − U) = (vᵀW)X for both secret projections at every spatial location. It aborts on any failed check, decodes the signed values, rescales and adds the FP32 bias in private memory. Under ideal fresh uniform challenges, a fixed incorrect matrix passes both checks with probability at most 1/p² for this invocation. Timing leakage, denial of service, and hardware side channels are outside this implementation's validation.
4. All subsequent layers run in the TA. The final masked packet and B/C comparison are identical in format and arithmetic. For Q, a secure-CPU convolution evaluates the very same quantized weights/input and skips the GPU. Compare B versus Q for quantization effects and C versus Q for delegation effects. Plain FP32 B versus C alone combines both changes.

## Run

Use the installation and commissioning instructions in the main guide. The prebuilt package includes the Orin `sm_87` worker linked to `libcudart.so.11.0`. To compile it locally on a Jetson with the CUDA toolkit, run `./build.sh cuda`.

```bash
# Trusted dealer
python setup_slot.py prepare --mode C --key lab/dealer.key \
  --bank ../../data/embeddings_droneface_raw_sface9.txt \
  --reference ../DnHFaces/open_data_set/trio_cam/k_cam_0_porF_00.jpg --out lab/c01

# Drone after private distribution
python run.py --box lab/c01/ta.box --party0 lab/c01/party0.json \
  --image ../../ppface/DnHFaces/open_data_set/photos_all_faces/k_gp_3_ef_27.jpg \
  --output ../results/C-k-01

# Peer through both SSH forwards described in B
python B/mpc.py lab/c01/party1.json --connect 127.0.0.1 61501
```

Repeat all three commands with a freshly generated Q slot, consistently changing the directory and output name. Use matching images, power settings and network conditions. Include TA preprocessing energy and correction-generation time when discussing drone battery costs. The application currently allocates and transfers public GPU weights per invocation. No on-device speedup or accuracy-preservation claim follows from cross-compilation or one successful decision.
