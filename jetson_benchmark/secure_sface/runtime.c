/* Portable FP32 CPU kernels. No normal-world callbacks or activation export. */
#include "runtime.h"

void sf_wipe(void *buffer, size_t size)
{
    volatile unsigned char *p = buffer;
    while (size--) *p++ = 0;
}

void sf_input(const unsigned char *bgr, float *input)
{
    for (size_t p = 0; p < 112 * 112; ++p)
        for (size_t c = 0; c < 3; ++c)
            input[c * 112 * 112 + p] = bgr[p * 3 + 2 - c];
}

static void convolution(const struct sf_step *s, const float *weights, const float *x, float *y)
{
    const size_t in_plane = s->h * s->w, out_plane = s->oh * s->ow;
    const size_t group_in = s->ci / s->groups, group_out = s->co / s->groups;
    const size_t row = group_in * s->kernel * s->kernel;
    const float *bias = weights + s->count * row;
    for (size_t local = 0; local < s->count; ++local) {
        size_t oc = s->begin + local, base_channel = (oc / group_out) * group_in;
        float *dst = y + oc * out_plane;
        const float *filter = weights + local * row;
        if (s->kernel == 1 && s->stride == 1 && s->pad == 0) {
            for (size_t p = 0; p < out_plane; ++p) dst[p] = bias[local];
            for (size_t ic = 0; ic < group_in; ++ic) {
                const float *src = x + (base_channel + ic) * in_plane;
                float weight = filter[ic];
                for (size_t p = 0; p < out_plane; ++p) dst[p] += src[p] * weight;
            }
        } else {
            for (size_t oy = 0; oy < s->oh; ++oy) {
                for (size_t ox = 0; ox < s->ow; ++ox) {
                    float sum = bias[local];
                    for (size_t ic = 0; ic < group_in; ++ic) {
                        for (size_t ky = 0; ky < s->kernel; ++ky) {
                            int iy = (int)(oy * s->stride + ky) - (int)s->pad;
                            if (iy < 0 || iy >= (int)s->h) continue;
                            for (size_t kx = 0; kx < s->kernel; ++kx) {
                                int ix = (int)(ox * s->stride + kx) - (int)s->pad;
                                if (ix < 0 || ix >= (int)s->w) continue;
                                size_t wi = (ic * s->kernel + ky) * s->kernel + kx;
                                size_t xi = (base_channel + ic) * in_plane + (size_t)iy * s->w + (size_t)ix;
                                sum += x[xi] * filter[wi];
                            }
                        }
                    }
                    dst[oy * s->ow + ox] = sum;
                }
            }
        }
    }
}

int sf_step_run(const struct sf_step *s, const float *weights, float **input, float **output)
{
    float *x = *input, *y = *output;
    size_t plane = s->h * s->w, length = s->ci * plane;
    switch (s->kind) {
    case 0:
        for (size_t i = 0; i < length; ++i) x[i] -= weights[0];
        break;
    case 1:
        for (size_t i = 0; i < length; ++i) x[i] *= weights[0];
        break;
    case 2:
        for (size_t c = 0; c < s->ci; ++c) {
            float gamma = weights[c], beta = weights[s->ci + c];
            float mean = weights[2 * s->ci + c], invstd = weights[3 * s->ci + c];
            for (size_t i = 0; i < plane; ++i) {
                size_t p = c * plane + i;
                x[p] = ((x[p] - mean) * invstd) * gamma + beta;
            }
        }
        break;
    case 3:
        for (size_t c = 0; c < s->ci; ++c)
            for (size_t i = 0; i < plane; ++i) {
                size_t p = c * plane + i;
                if (x[p] < 0) x[p] *= weights[c];
            }
        break;
    case 4:
        convolution(s, weights, x, y);
        break;
    case 5:
        for (size_t local = 0; local < s->count; ++local) {
            float sum = weights[s->count * s->ci + local];
            for (size_t i = 0; i < s->ci; ++i) sum += x[i] * weights[local * s->ci + i];
            y[s->begin + local] = sum;
        }
        break;
    default:
        return -1;
    }
    if (s->kind >= 4 && s->last) { *input = y; *output = x; }
    return 0;
}

int sf_encode(const float *features, uint64_t *encoded)
{
    for (size_t i = 0; i < 128; ++i) {
        double scaled = (double)features[i] * 256.0;
        /* Reject NaN, infinities and out-of-range values before the integer cast. */
        if (!(scaled >= -9223372036854775808.0 && scaled < 9223372036854775808.0)) return -1;
        encoded[i] = (uint64_t)(int64_t)scaled;
    }
    return 0;
}
