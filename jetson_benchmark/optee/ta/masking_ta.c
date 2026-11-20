#include <stdint.h>
#include <tee_internal_api.h>
#include <tee_internal_api_extensions.h>
#include <obscura_ta.h>

static void wipe(void *buffer, size_t size)
{
    volatile unsigned char *p = buffer;
    while (size--) *p++ = 0;
}

TEE_Result TA_CreateEntryPoint(void) { return TEE_SUCCESS; }
void TA_DestroyEntryPoint(void) {}

TEE_Result TA_OpenSessionEntryPoint(uint32_t types, TEE_Param params[4], void **session)
{
    (void)params;
    *session = NULL;
    return types == TEE_PARAM_TYPES(TEE_PARAM_TYPE_NONE, TEE_PARAM_TYPE_NONE,
                                   TEE_PARAM_TYPE_NONE, TEE_PARAM_TYPE_NONE)
        ? TEE_SUCCESS : TEE_ERROR_BAD_PARAMETERS;
}

void TA_CloseSessionEntryPoint(void *session) { (void)session; }

TEE_Result TA_InvokeCommandEntryPoint(void *session, uint32_t command,
                                      uint32_t types, TEE_Param params[4])
{
    (void)session;
    if (command != OBSCURA_MASK)
        return TEE_ERROR_NOT_SUPPORTED;
    if (types != TEE_PARAM_TYPES(TEE_PARAM_TYPE_MEMREF_INPUT, TEE_PARAM_TYPE_MEMREF_OUTPUT,
                                TEE_PARAM_TYPE_NONE, TEE_PARAM_TYPE_NONE))
        return TEE_ERROR_BAD_PARAMETERS;
    const size_t size = OBSCURA_DIMENSION * sizeof(uint64_t);
    if (params[0].memref.size != size || !params[0].memref.buffer)
        return TEE_ERROR_BAD_PARAMETERS;
    if (params[1].memref.size < size) {
        params[1].memref.size = size;
        return TEE_ERROR_SHORT_BUFFER;
    }
    if (!params[1].memref.buffer)
        return TEE_ERROR_BAD_PARAMETERS;

    /* Copy into secure memory before touching input. The original normal-world
       input is still observable there; this TA does not protect inference. */
    uint64_t values[OBSCURA_DIMENSION], pads[OBSCURA_DIMENSION];
    TEE_MemMove(values, params[0].memref.buffer, size);
    TEE_GenerateRandom(pads, size);
    for (size_t i = 0; i < OBSCURA_DIMENSION; ++i)
        values[i] += pads[i]; /* uint64_t wraparound implements Z_(2^64) */
    TEE_MemMove(params[1].memref.buffer, values, size);
    params[1].memref.size = size;
    wipe(pads, size);
    wipe(values, size);
    return TEE_SUCCESS;
}
