#define _POSIX_C_SOURCE 200809L
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <tee_client_api.h>
#include "protocol.h"
#include "model.h"

struct connection { TEEC_Context context; TEEC_Session session; };

void secure_sface_close(void *handle)
{
    struct connection *c = handle;
    if (!c) return;
    TEEC_CloseSession(&c->session);
    TEEC_FinalizeContext(&c->context);
    free(c);
}

uint32_t secure_sface_open(void **handle)
{
    if (!handle) return TEEC_ERROR_BAD_PARAMETERS;
    *handle = NULL;
    struct connection *c = calloc(1, sizeof(*c));
    if (!c) return TEEC_ERROR_OUT_OF_MEMORY;
    TEEC_Result r = TEEC_InitializeContext(NULL, &c->context);
    if (r != TEEC_SUCCESS) { free(c); return r; }
    TEEC_UUID uuid = SF_UUID;
    uint32_t origin;
    r = TEEC_OpenSession(&c->context, &c->session, &uuid, TEEC_LOGIN_PUBLIC, NULL, NULL, &origin);
    if (r != TEEC_SUCCESS) { TEEC_FinalizeContext(&c->context); free(c); return r; }
    unsigned char model_digest[32];
    TEEC_Operation op = {0};
    op.paramTypes = TEEC_PARAM_TYPES(TEEC_MEMREF_TEMP_OUTPUT, TEEC_NONE, TEEC_NONE, TEEC_NONE);
    op.params[0].tmpref.buffer = model_digest;
    op.params[0].tmpref.size = sizeof(model_digest);
    r = TEEC_InvokeCommand(&c->session, SF_INFO, &op, &origin);
    if (r == TEEC_SUCCESS && (op.params[0].tmpref.size != 32 || memcmp(model_digest, sf_model_digest, 32)))
        r = TEEC_ERROR_SECURITY;
    if (r != TEEC_SUCCESS) { secure_sface_close(c); return r; }
    *handle = c;
    return TEEC_SUCCESS;
}

const char *secure_sface_model_sha256(void) { return SF_MODEL_SHA256; }

static int clock_ns(uint64_t *result)
{
    struct timespec t;
    if (clock_gettime(CLOCK_MONOTONIC, &t) != 0) return -1;
    *result = (uint64_t)t.tv_sec * UINT64_C(1000000000) + (uint64_t)t.tv_nsec;
    return 0;
}

/* window, when supplied, uses the same Linux clock as the power sampler.
   SF_FINISH scales and masks the private features after the measured interval. */
static uint32_t run_frame(void *handle, const unsigned char *crop, size_t crop_bytes,
                          const unsigned char *weights, size_t weight_bytes,
                          uint64_t *masked, struct sf_metrics *metrics, uint64_t *window)
{
    if (!handle || !crop || !weights || !masked || !metrics || crop_bytes != SF_CROP_BYTES || weight_bytes != SF_BLOB_BYTES)
        return TEEC_ERROR_BAD_PARAMETERS;
    struct connection *c = handle;
    TEEC_Operation op = {0};
    uint32_t origin;
    op.paramTypes = TEEC_PARAM_TYPES(TEEC_MEMREF_TEMP_INPUT, TEEC_NONE, TEEC_NONE, TEEC_NONE);
    op.params[0].tmpref.buffer = (void *)crop;
    op.params[0].tmpref.size = crop_bytes;
    if (window && clock_ns(&window[0])) return TEEC_ERROR_GENERIC;
    TEEC_Result r = TEEC_InvokeCommand(&c->session, SF_BEGIN, &op, &origin);
    if (r != TEEC_SUCCESS) return r;
    for (size_t i = 0; i < SF_STEP_COUNT; ++i) {
        memset(&op, 0, sizeof(op));
        op.paramTypes = TEEC_PARAM_TYPES(TEEC_MEMREF_TEMP_INPUT, TEEC_NONE, TEEC_NONE, TEEC_NONE);
        op.params[0].tmpref.buffer = (void *)(weights + sf_steps[i].offset);
        op.params[0].tmpref.size = sf_steps[i].bytes;
        r = TEEC_InvokeCommand(&c->session, SF_STEP, &op, &origin);
        if (r != TEEC_SUCCESS) return r;
    }
    if (window && clock_ns(&window[1])) return TEEC_ERROR_GENERIC;
    memset(&op, 0, sizeof(op));
    op.paramTypes = TEEC_PARAM_TYPES(TEEC_MEMREF_TEMP_OUTPUT, TEEC_MEMREF_TEMP_OUTPUT, TEEC_NONE, TEEC_NONE);
    op.params[0].tmpref.buffer = masked;
    op.params[0].tmpref.size = SF_DIMENSION * sizeof(uint64_t);
    op.params[1].tmpref.buffer = metrics;
    op.params[1].tmpref.size = sizeof(*metrics);
    return TEEC_InvokeCommand(&c->session, SF_FINISH, &op, &origin);
}

uint32_t secure_sface_run(void *handle, const unsigned char *crop, size_t crop_bytes,
                          const unsigned char *weights, size_t weight_bytes,
                          uint64_t *masked, struct sf_metrics *metrics)
{
    return run_frame(handle, crop, crop_bytes, weights, weight_bytes, masked, metrics, NULL);
}

uint32_t secure_sface_run_profiled(void *handle, const unsigned char *crop, size_t crop_bytes,
                                   const unsigned char *weights, size_t weight_bytes,
                                   uint64_t *masked, struct sf_metrics *metrics, uint64_t window[2])
{
    if (!window) return TEEC_ERROR_BAD_PARAMETERS;
    return run_frame(handle, crop, crop_bytes, weights, weight_bytes, masked, metrics, window);
}
