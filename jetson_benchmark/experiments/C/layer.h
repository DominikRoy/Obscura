/* Pinned conv_9_conv2d. Layout is [channel][spatial position]. */
#define CH 512
#define PIX 196
#define ELEMS (CH * PIX)
#define FIRST 53
#define AFTER 56
#define PRIME INT64_C(2147483647)
#define SCALE 256
#define CHECKS 2
struct pilot {
    int16_t weights[CH][CH];
    float bias[CH];
    uint32_t r[ELEMS], correction[ELEMS];
    uint32_t v[CHECKS][CH], wv[CHECKS][CH];
    unsigned loaded;
    int ready, pending;
    int64_t max_l1;
};
static uint32_t field(int64_t x) {
    int64_t v = x % PRIME;
    return (uint32_t)(v < 0 ? v + PRIME : v);
}
static void random_field(uint32_t *out, unsigned n) {
    TEE_GenerateRandom(out, n * sizeof(*out));
    for (unsigned i = 0; i < n; ++i) {
        while (out[i] >= 2 * (uint32_t)PRIME)
            TEE_GenerateRandom(out + i, sizeof(*out));
        out[i] %= PRIME;
    }
}
static int quantize(float v, int32_t *q) {
    double z = (double)v * SCALE;
    if (!(z >= -32767 && z <= 32767))
        return 0;
    *q = (int32_t)(z < 0 ? z - 0.5 : z + 0.5);
    return 1;
}
static TEE_Result load_tile(struct state *s, struct pilot *g, void *data, size_t n) {
    if (g->loaded >= AFTER - FIRST)
        return TEE_ERROR_BAD_STATE;
    const struct sf_step *t = &sf_steps[FIRST + g->loaded];
    if (n != t->bytes || t->ci != CH || t->co != CH || t->oh * t->ow != PIX ||
        t->begin + t->count > CH || t->kernel != 1 || n > SF_BLOCK_BYTES)
        return TEE_ERROR_BAD_PARAMETERS;
    uint8_t digest[32];
    size_t length = sizeof(digest);
    TEE_MemMove(s->block, data, n);
    TEE_Result r = TEE_DigestDoFinal(s->hash, s->block, n, digest, &length);
    if (r || TEE_MemCompare(digest, t->digest, 32))
        return TEE_ERROR_SECURITY;
    for (unsigned i = 0; i < t->count; ++i) {
        int64_t l1 = 0;
        for (unsigned j = 0; j < CH; ++j) {
            int32_t w;
            if (!quantize(s->block[i * CH + j], &w))
                return TEE_ERROR_BAD_FORMAT;
            g->weights[t->begin + i][j] = w;
            l1 += w < 0 ? -w : w;
        }
        if (l1 > g->max_l1)
            g->max_l1 = l1;
        g->bias[t->begin + i] = s->block[t->count * CH + i];
    }
    ++g->loaded;
    return TEE_SUCCESS;
}
static void prepare_gpu(struct pilot *g) {
    random_field(g->r, ELEMS);
    for (unsigned k = 0; k < CHECKS; ++k) {
        random_field(g->v[k], CH);
        for (unsigned j = 0; j < CH; ++j) {
            int64_t sum = 0;
            for (unsigned i = 0; i < CH; ++i)
                sum += (int64_t)g->v[k][i] * g->weights[i][j];
            g->wv[k][j] = field(sum);
        }
    }
    for (unsigned i = 0; i < CH; ++i)
        for (unsigned p = 0; p < PIX; ++p) {
            int64_t sum = 0;
            for (unsigned j = 0; j < CH; ++j)
                sum += (int64_t)g->weights[i][j] * g->r[j * PIX + p];
            g->correction[i * PIX + p] = field(sum);
        }
    g->ready = 1;
}
static TEE_Result layer_input(struct state *s, struct pilot *g, uint32_t *out) {
    /* The input tensor remains private. Keep quantized X exactly in FP32. */
    for (unsigned i = 0; i < ELEMS; ++i) {
        int32_t q;
        if (!quantize(s->x[i], &q) || (q < 0 ? -(int64_t)q : q) * g->max_l1 > PRIME / 2)
            return TEE_ERROR_BAD_FORMAT;
        s->x[i] = (float)q;
        if (out)
            out[i] = field((int64_t)q + g->r[i]);
    }
    g->pending = 1;
    return TEE_SUCCESS;
}
static void advance_layer(struct state *s) {
    float *tmp = s->x;
    s->x = s->y;
    s->y = tmp;
    s->next = AFTER;
}
static TEE_Result accept_gpu(struct state *s, struct pilot *g, void *input) {
    uint32_t *z = (uint32_t *)s->block;
    TEE_MemMove(z, input, ELEMS * sizeof(*z));
    for (unsigned i = 0; i < ELEMS; ++i) {
        if (z[i] >= PRIME)
            return TEE_ERROR_BAD_FORMAT;
        z[i] = field((int64_t)z[i] - g->correction[i]);
    }
    for (unsigned k = 0; k < CHECKS; ++k)
        for (unsigned p = 0; p < PIX; ++p) {
            int64_t lhs = 0, rhs = 0;
            for (unsigned i = 0; i < CH; ++i) {
                lhs += field((int64_t)g->v[k][i] * z[i * PIX + p]);
                rhs += (int64_t)g->wv[k][i] * (int32_t)s->x[i * PIX + p];
            }
            if (field(lhs) != field(rhs))
                return TEE_ERROR_SECURITY;
        }
    for (unsigned i = 0; i < ELEMS; ++i) {
        int64_t val = z[i] > PRIME / 2 ? (int64_t)z[i] - PRIME : z[i];
        s->y[i] = (float)((double)val / (SCALE * SCALE) + g->bias[i / PIX]);
    }
    advance_layer(s);
    g->pending = 0;
    return TEE_SUCCESS;
}
static void cpu_control(struct state *s, struct pilot *g) {
    for (unsigned i = 0; i < CH; ++i)
        for (unsigned p = 0; p < PIX; ++p) {
            int64_t sum = 0;
            for (unsigned j = 0; j < CH; ++j)
                sum += (int64_t)g->weights[i][j] * (int32_t)s->x[j * PIX + p];
            s->y[i * PIX + p] = (float)((double)sum / (SCALE * SCALE) + g->bias[i]);
        }
    advance_layer(s);
    g->pending = 0;
}
