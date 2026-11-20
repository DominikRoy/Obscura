#ifndef SF_RUNTIME_H
#define SF_RUNTIME_H
#include <stddef.h>
#include <stdint.h>
struct sf_step {
    uint32_t kind, ci, h, w, co, oh, ow, begin, count, kernel, stride, pad, groups, last;
    uint32_t offset, bytes;
    unsigned char digest[32];
};
void sf_input(const unsigned char *bgr, float *input);
int sf_step_run(const struct sf_step *step, const float *weights, float **input, float **output);
int sf_encode(const float *features, uint64_t *encoded);
void sf_wipe(void *buffer, size_t size);
#endif
