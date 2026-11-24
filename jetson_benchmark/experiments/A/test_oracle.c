/* Public-fixture oracle. Build only for the workstation test process. */
#include <stdlib.h>
#include <string.h>
#include "model.h"
int test_extract(const unsigned char *bgr, const unsigned char *blob, float *y) {
    float *a = calloc(SF_BUFFER_FLOATS, sizeof(float)), *b = calloc(SF_BUFFER_FLOATS, sizeof(float));
    if (!a || !b) {
        free(a);
        free(b);
        return -1;
    }
    float *src = a, *dst = b;
    sf_input(bgr, src);
    int r = 0;
    for (unsigned i = 0; i < SF_STEP_COUNT; ++i) {
        const struct sf_step *s = sf_steps + i;
        if (sf_step_run(s, (const float *)(blob + s->offset), &src, &dst)) {
            r = -1;
            break;
        }
    }
    if (!r)
        memcpy(y, src, 128 * sizeof(float));
    free(a);
    free(b);
    return r;
}
