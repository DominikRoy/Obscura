#include <stdint.h>
#include <stdlib.h>
#include <tee_client_api.h>
#include "../obscura_ta.h"

struct connection { TEEC_Context context; TEEC_Session session; };

uint32_t obscura_open(void **handle)
{
    if (!handle) return TEEC_ERROR_BAD_PARAMETERS;
    *handle = NULL;
    struct connection *c = calloc(1, sizeof(*c));
    if (!c) return TEEC_ERROR_OUT_OF_MEMORY;
    TEEC_Result result = TEEC_InitializeContext(NULL, &c->context);
    if (result != TEEC_SUCCESS) { free(c); return result; }
    TEEC_UUID uuid = OBSCURA_UUID;
    uint32_t origin;
    result = TEEC_OpenSession(&c->context, &c->session, &uuid,
                             TEEC_LOGIN_PUBLIC, NULL, NULL, &origin);
    if (result != TEEC_SUCCESS) {
        TEEC_FinalizeContext(&c->context);
        free(c);
        return result;
    }
    *handle = c;
    return TEEC_SUCCESS;
}

uint32_t obscura_mask(void *handle, const uint64_t *input, uint64_t *output)
{
    if (!handle || !input || !output) return TEEC_ERROR_BAD_PARAMETERS;
    struct connection *c = handle;
    TEEC_Operation op = {0};
    op.paramTypes = TEEC_PARAM_TYPES(TEEC_MEMREF_TEMP_INPUT, TEEC_MEMREF_TEMP_OUTPUT,
                                   TEEC_NONE, TEEC_NONE);
    op.params[0].tmpref.buffer = (void *)input;
    op.params[0].tmpref.size = OBSCURA_DIMENSION * sizeof(uint64_t);
    op.params[1].tmpref.buffer = output;
    op.params[1].tmpref.size = OBSCURA_DIMENSION * sizeof(uint64_t);
    uint32_t origin;
    return TEEC_InvokeCommand(&c->session, OBSCURA_MASK, &op, &origin);
}

void obscura_close(void *handle)
{
    if (!handle) return;
    struct connection *c = handle;
    TEEC_CloseSession(&c->session);
    TEEC_FinalizeContext(&c->context);
    free(c);
}
