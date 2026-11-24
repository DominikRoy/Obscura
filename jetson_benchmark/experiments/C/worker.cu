// All inputs to this process are public weights or blinded field elements.
#include <cuda_runtime.h>
#include <stdint.h>
__global__ void pointwise(const int16_t *w, const uint32_t *x, uint32_t *out) {
    unsigned pos = blockIdx.x * blockDim.x + threadIdx.x;
    if (pos >= 512 * 196)
        return;
    unsigned row = pos / 196, p = pos % 196;
    int64_t sum = 0;
    for (unsigned j = 0; j < 512; ++j)
        sum += (int64_t)w[row * 512 + j] * x[j * 196 + p];
    int64_t v = sum % 2147483647;
    out[pos] = (uint32_t)(v < 0 ? v + 2147483647 : v);
}
extern "C" int blinded_conv(const int16_t *w, const uint32_t *x, uint32_t *z) {
    int16_t *dw = nullptr;
    uint32_t *dx = nullptr, *dz = nullptr;
    const size_t wb = 512 * 512 * 2, n = 512 * 196 * 4;
    cudaError_t r = cudaMalloc(&dw, wb);
    if (!r)
        r = cudaMalloc(&dx, n);
    if (!r)
        r = cudaMalloc(&dz, n);
    if (!r)
        r = cudaMemcpy(dw, w, wb, cudaMemcpyHostToDevice);
    if (!r)
        r = cudaMemcpy(dx, x, n, cudaMemcpyHostToDevice);
    if (!r) {
        pointwise<<<(512 * 196 + 255) / 256, 256>>>(dw, dx, dz);
        r = cudaGetLastError();
    }
    if (!r)
        r = cudaMemcpy(z, dz, n, cudaMemcpyDeviceToHost);
    cudaFree(dz);
    cudaFree(dx);
    cudaFree(dw);
    return r;
}
