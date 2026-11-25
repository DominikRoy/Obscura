#ifndef EXP_DECISION_H
#define EXP_DECISION_H
#include <stdint.h>

/* The dimension and input bound leave room for both scaled products in 128 bits. */
#define EXP_DIM 128
#define EXP_BOUND 32767
#define EXP_DEN 100000000u
#define EXP_LFW_NUM 11368578u
#define EXP_DRONEFACE_NUM 6247600u

static inline int coordinate_ok(int64_t x) { return x >= -EXP_BOUND && x <= EXP_BOUND; }

static inline int decide_terms(int64_t dot, uint64_t xx, uint64_t yy, uint32_t numerator) {
    const int64_t bound = (int64_t)EXP_DIM * EXP_BOUND * EXP_BOUND;
    if (dot < -bound || dot > bound || xx > (uint64_t)bound || yy > (uint64_t)bound)
        return -1;
    typedef unsigned __int128 wide;
    return dot >= 0 && (wide)EXP_DEN * (wide)dot * (wide)dot >= (wide)numerator * xx * yy;
}

static inline int plain_decision(const int64_t *x, const int64_t *y, uint32_t numerator) {
    int64_t dot = 0, xx = 0, yy = 0;
    for (unsigned i = 0; i < EXP_DIM; ++i) {
        if (!coordinate_ok(x[i]) || !coordinate_ok(y[i]))
            return -1;
        dot += x[i] * y[i];
        xx += x[i] * x[i];
        yy += y[i] * y[i];
    }
    return decide_terms(dot, xx, yy, numerator);
}
#endif
