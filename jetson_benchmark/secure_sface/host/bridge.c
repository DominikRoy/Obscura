#include <stdint.h>
#include <stdlib.h>
#include <string.h>
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

uint32_t secure_sface_run(void *handle, const unsigned char *crop, size_t crop_bytes,
                         const unsigned char *weights, size_t weight_bytes,
                         uint64_t *masked, struct sf_metrics *metrics)
{
    if (!handle || !crop || !weights || !masked || !metrics || crop_bytes != SF_CROP_BYTES || weight_bytes != SF_BLOB_BYTES)
        return TEEC_ERROR_BAD_PARAMETERS;
    struct connection *c = handle;
    TEEC_Operation op = {0};
    uint32_t origin;
    op.paramTypes = TEEC_PARAM_TYPES(TEEC_MEMREF_TEMP_INPUT, TEEC_NONE, TEEC_NONE, TEEC_NONE);
    op.params[0].tmpref.buffer = (void *)crop;
    op.params[0].tmpref.size = crop_bytes;
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
    memset(&op, 0, sizeof(op));
    op.paramTypes = TEEC_PARAM_TYPES(TEEC_MEMREF_TEMP_OUTPUT, TEEC_MEMREF_TEMP_OUTPUT, TEEC_NONE, TEEC_NONE);
    op.params[0].tmpref.buffer = masked;
    op.params[0].tmpref.size = SF_DIMENSION * sizeof(uint64_t);
    op.params[1].tmpref.buffer = metrics;
    op.params[1].tmpref.size = sizeof(*metrics);
    return TEEC_InvokeCommand(&c->session, SF_FINISH, &op, &origin);
}
