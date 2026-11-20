#include <tee_internal_api.h>
#include <tee_internal_api_extensions.h>
#include "protocol.h"
#include "model.h"

struct state {
    float *a, *b, *x, *y, *block;
    uint32_t next;
    int active;
    TEE_OperationHandle hash;
    struct sf_metrics metrics;
};

static uint64_t milliseconds(void)
{
    TEE_Time now;
    TEE_GetSystemTime(&now);
    return (uint64_t)now.seconds * 1000 + now.millis;
}

static void reset(struct state *s)
{
    if (s->a) sf_wipe(s->a, SF_BUFFER_FLOATS * sizeof(float));
    if (s->b) sf_wipe(s->b, SF_BUFFER_FLOATS * sizeof(float));
    if (s->block) sf_wipe(s->block, SF_BLOCK_BYTES);
    s->active = 0;
    s->next = 0;
    s->x = s->a;
    s->y = s->b;
}

TEE_Result TA_CreateEntryPoint(void) { return TEE_SUCCESS; }
void TA_DestroyEntryPoint(void) {}

void TA_CloseSessionEntryPoint(void *session)
{
    struct state *s = session;
    if (!s) return;
    reset(s);
    if (s->hash != TEE_HANDLE_NULL) TEE_FreeOperation(s->hash);
    TEE_Free(s->a);
    TEE_Free(s->b);
    TEE_Free(s->block);
    sf_wipe(s, sizeof(*s));
    TEE_Free(s);
}

TEE_Result TA_OpenSessionEntryPoint(uint32_t types, TEE_Param params[4], void **session)
{
    (void)params;
    *session = NULL;
    if (types != TEE_PARAM_TYPES(TEE_PARAM_TYPE_NONE, TEE_PARAM_TYPE_NONE,
                                TEE_PARAM_TYPE_NONE, TEE_PARAM_TYPE_NONE))
        return TEE_ERROR_BAD_PARAMETERS;
    struct state *s = TEE_Malloc(sizeof(*s), TEE_MALLOC_FILL_ZERO);
    if (!s) return TEE_ERROR_OUT_OF_MEMORY;
    s->hash = TEE_HANDLE_NULL;
    s->a = TEE_Malloc(SF_BUFFER_FLOATS * sizeof(float), TEE_MALLOC_FILL_ZERO);
    s->b = TEE_Malloc(SF_BUFFER_FLOATS * sizeof(float), TEE_MALLOC_FILL_ZERO);
    s->block = TEE_Malloc(SF_BLOCK_BYTES, TEE_MALLOC_FILL_ZERO);
    if (!s->a || !s->b || !s->block) {
        TA_CloseSessionEntryPoint(s);
        return TEE_ERROR_OUT_OF_MEMORY;
    }
    TEE_Result result = TEE_AllocateOperation(&s->hash, TEE_ALG_SHA256, TEE_MODE_DIGEST, 0);
    if (result != TEE_SUCCESS) { TA_CloseSessionEntryPoint(s); return result; }
    s->x = s->a;
    s->y = s->b;
    *session = s;
    return TEE_SUCCESS;
}

static TEE_Result invoke(struct state *s, uint32_t command, uint32_t types, TEE_Param p[4])
{
    uint32_t input_types = TEE_PARAM_TYPES(TEE_PARAM_TYPE_MEMREF_INPUT, TEE_PARAM_TYPE_NONE,
                                         TEE_PARAM_TYPE_NONE, TEE_PARAM_TYPE_NONE);
    if (command == SF_INFO) {
        if (types != TEE_PARAM_TYPES(TEE_PARAM_TYPE_MEMREF_OUTPUT, TEE_PARAM_TYPE_NONE,
                                     TEE_PARAM_TYPE_NONE, TEE_PARAM_TYPE_NONE)) return TEE_ERROR_BAD_PARAMETERS;
        if (p[0].memref.size < 32) { p[0].memref.size = 32; return TEE_ERROR_SHORT_BUFFER; }
        if (!p[0].memref.buffer) return TEE_ERROR_BAD_PARAMETERS;
        TEE_MemMove(p[0].memref.buffer, sf_model_digest, 32);
        p[0].memref.size = 32;
        return TEE_SUCCESS;
    }
    if (command == SF_BEGIN) {
        if (types != input_types || p[0].memref.size != SF_CROP_BYTES || !p[0].memref.buffer)
            return TEE_ERROR_BAD_PARAMETERS;
        reset(s);
        TEE_MemFill(&s->metrics, 0, sizeof(s->metrics));
        uint64_t start = milliseconds();
        TEE_MemMove(s->block, p[0].memref.buffer, SF_CROP_BYTES);
        sf_input((const unsigned char *)s->block, s->x);
        sf_wipe(s->block, SF_CROP_BYTES);
        s->metrics.preprocess_ms = milliseconds() - start;
        s->active = 1;
        return TEE_SUCCESS;
    }
    if (command == SF_STEP) {
        if (types != input_types || !p[0].memref.buffer) return TEE_ERROR_BAD_PARAMETERS;
        if (!s->active || s->next >= SF_STEP_COUNT) return TEE_ERROR_BAD_STATE;
        const struct sf_step *step = &sf_steps[s->next];
        if (p[0].memref.size != step->bytes) return TEE_ERROR_BAD_PARAMETERS;
        uint64_t start = milliseconds();
        /* Check the private copy, then use that same copy. This prevents a shared
           memory race between hash verification and computation. */
        TEE_MemMove(s->block, p[0].memref.buffer, step->bytes);
        unsigned char digest[32];
        size_t length = sizeof(digest);
        TEE_Result result = TEE_DigestDoFinal(s->hash, s->block, step->bytes, digest, &length);
        if (result != TEE_SUCCESS) return result;
        if (length != 32 || TEE_MemCompare(digest, step->digest, 32)) return TEE_ERROR_SECURITY;
        s->metrics.weights_ms += milliseconds() - start;
        start = milliseconds();
        if (sf_step_run(step, s->block, &s->x, &s->y)) return TEE_ERROR_NOT_SUPPORTED;
        s->metrics.inference_ms += milliseconds() - start;
        ++s->next;
        return TEE_SUCCESS;
    }
    if (command == SF_FINISH) {
        if (types != TEE_PARAM_TYPES(TEE_PARAM_TYPE_MEMREF_OUTPUT, TEE_PARAM_TYPE_MEMREF_OUTPUT,
                                     TEE_PARAM_TYPE_NONE, TEE_PARAM_TYPE_NONE)) return TEE_ERROR_BAD_PARAMETERS;
        if (!s->active || s->next != SF_STEP_COUNT) return TEE_ERROR_BAD_STATE;
        if (p[0].memref.size < SF_DIMENSION * sizeof(uint64_t) || p[1].memref.size < sizeof(s->metrics)) {
            p[0].memref.size = SF_DIMENSION * sizeof(uint64_t);
            p[1].memref.size = sizeof(s->metrics);
            return TEE_ERROR_SHORT_BUFFER;
        }
        if (!p[0].memref.buffer || !p[1].memref.buffer) return TEE_ERROR_BAD_PARAMETERS;
        uint64_t values[SF_DIMENSION], pads[SF_DIMENSION];
        uint64_t start = milliseconds();
        if (sf_encode(s->x, values)) {
            sf_wipe(values, sizeof(values));
            return TEE_ERROR_BAD_FORMAT;
        }
        s->metrics.encode_ms = milliseconds() - start;
        start = milliseconds();
        TEE_GenerateRandom(pads, sizeof(pads));
        for (size_t i = 0; i < SF_DIMENSION; ++i) values[i] += pads[i];
        s->metrics.mask_ms = milliseconds() - start;
        /* Only masked values and timing counters leave the secure world. */
        TEE_MemMove(p[0].memref.buffer, values, sizeof(values));
        TEE_MemMove(p[1].memref.buffer, &s->metrics, sizeof(s->metrics));
        p[0].memref.size = sizeof(values);
        p[1].memref.size = sizeof(s->metrics);
        sf_wipe(values, sizeof(values));
        sf_wipe(pads, sizeof(pads));
        reset(s);
        return TEE_SUCCESS;
    }
    return TEE_ERROR_NOT_SUPPORTED;
}

TEE_Result TA_InvokeCommandEntryPoint(void *session, uint32_t command, uint32_t types, TEE_Param params[4])
{
    struct state *s = session;
    if (!s) return TEE_ERROR_BAD_STATE;
    TEE_Result result = invoke(s, command, types, params);
    if (result != TEE_SUCCESS) reset(s); /* Failed runs cannot later export stale state. */
    return result;
}
