# Revised Obscura measurements on Jetson 1

The NVIDIA Orin Nano Developer Kit ran L4T R35.5.0 with kernel `5.10.192-tegra` and the `schedutil` CPU frequency governor. Each protocol covered all 5,092 labeled pairs. The two online roles communicated through TNO HTTP on loopback on this board. The [LaTeX insert](paper-insert.tex) contains both main tables and a manuscript paragraph on masking and Lemma 2. The reference was the gallery vector and the live probe was the second entry in each pair manifest.

## Standalone SFace extraction

One paired observation on the LFW image `Valeri_Bure_0001.jpg`, from decoded BGR pixels to the raw 128-coordinate embedding. Both programs run detection, alignment, cropping and the same CPU SFace FP32 kernels. The TA authenticates streamed weights. File decoding, simulated camera decryption, scaling and masking lie outside the window.

| Execution | Time (ms) | Module energy (J) | Interior rail samples | Peak TA heap |
| --- | ---: | ---: | ---: | ---: |
| Linux CPU | 801.68 | 4.060 | 8 | TA unused |
| OP-TEE secure CPU | 1229.00 | 6.139 | 13 | 7,397,392 B (7.05 MiB) |

The allocator measurement includes live camera buffers at the private-pixels boundary. The TA has a configured 12 MiB heap and 32 KiB stack. Total enclave RAM and stack peak were uninstrumented. Values describe this one image and build. [Final-build extraction trace](sface-final-jetson1.json) · [Earlier same-image cross-check](sface-jetson1.json)

## Stored embedding to verification decision

Median milliseconds across the same 5,092 inputs per setting. The round trip includes peer computation. The WD share column measures part of that round trip. Energy is gross module input averaged per verification across measured online batches.

| Setting | Scale | Mask stage | Drone shares | WD shares | WD round trip | Reconstruct + decide | Total online | mJ / verification |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Original Obscura | 0.041 | 0.049 | 0.727 | 0.630 | 3.964 | 0.046 | 4.831 | 25.93 |
| TEE masking | 0.044 | 0.257 | 0.734 | 0.626 | 3.845 | 0.045 | 4.935 | 26.44 |
| TEE masking + reconstruction | 0.045 | 0.228 | 0.737 | 0.628 | 3.958 | 0.247 | 5.221 | 27.68 |

The mask stage in P and R includes the command transition, copying, range checks and output authentication. R also computes the live norm in that stage. Its final command authenticates and opens the WD reply. L and P reconstruct in Linux. Separately measured stage medians need not add to the total median. The batch-energy window includes activation of the next one-use slot and loop overhead. It excludes group setup.

| Split | Setting | Decisions correct / trials | Online median (ms) | Online mean (ms) | Pairs covered by valid batch trace | mJ / verification |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| lfw1 | Original Obscura | 972 / 1000 | 4.697 | 4.919 | 1000 / 1000 | 25.91 |
| lfw1 | TEE masking | 972 / 1000 | 4.881 | 5.039 | 1000 / 1000 | 26.54 |
| lfw1 | TEE masking + reconstruction | 972 / 1000 | 5.115 | 5.278 | 1000 / 1000 | 27.62 |
| drone9 | Original Obscura | 2113 / 2728 | 4.708 | 4.885 | 2728 / 2728 | 25.72 |
| drone9 | TEE masking | 2113 / 2728 | 4.864 | 4.963 | 2728 / 2728 | 26.11 |
| drone9 | TEE masking + reconstruction | 2113 / 2728 | 5.133 | 5.272 | 2728 / 2728 | 27.55 |
| drone11 | Original Obscura | 1067 / 1364 | 4.890 | 4.996 | 1364 / 1364 | 26.37 |
| drone11 | TEE masking | 1067 / 1364 | 5.111 | 5.142 | 1364 / 1364 | 27.03 |
| drone11 | TEE masking + reconstruction | 1067 / 1364 | 5.282 | 5.348 | 1364 / 1364 | 27.99 |

All output bits were checked against their plaintext fixed-point results. The correct/trials column compares these outputs with identity labels. These accuracies describe the stored-vector benchmark, independent of the one-frame extraction measurement. [Means, medians and coverage by split](summary-jetson1.csv) · [Per-pair timing records and raw batch samples](pair-traces-jetson1.sqlite.gz)

## Isolated masking arithmetic

Each operation adds 128 fixed-point coordinates to a 128-coordinate mask in the 64-bit ring. Three sustained blocks were measured on synthetic public inputs per implementation. Times and energy below use total elapsed time or integrated module joules divided by the total operation count. Linux uses its Python production helper and the TA uses its compiled production C addition loop. Language, call overhead and execution environment all affect this comparison.

| Implementation | Operations | Time per vector (µs) | Module energy per vector (µJ) |
| --- | ---: | ---: | ---: |
| Linux Python | 162,816 | 36.981 | 185.579 |
| TA C | 43,000,000 | 0.143 | 0.692 |

The TA timer measures the C loop inside a command. The energy window also includes the host’s batched invocations. The 100 ms rail sampler cannot resolve an individual verification, reconstruction command or vector addition. All reported joules are whole-module input, including baseline power. [Masking calibration traces](mask-energy-jetson1.json) · [Method and reproduction](README.md) · [Lemma 2 correction](lemma2.md)
