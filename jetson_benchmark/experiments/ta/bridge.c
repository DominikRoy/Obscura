#include <stdint.h>
#include <stdlib.h>
#include <tee_client_api.h>
#include "user_ta_header_defines.h"

struct client {
    TEEC_Context ctx;
    TEEC_Session session;
};
uint32_t exp_open(void **handle) {
    struct client *c = calloc(1, sizeof(*c));
    if (!c)
        return TEEC_ERROR_OUT_OF_MEMORY;
    TEEC_UUID uuid = TA_UUID;
    TEEC_Result r = TEEC_InitializeContext(NULL, &c->ctx);
    if (!r) {
        r = TEEC_OpenSession(&c->ctx, &c->session, &uuid, TEEC_LOGIN_PUBLIC, NULL, NULL, NULL);
        if (r)
            TEEC_FinalizeContext(&c->ctx);
    }
    if (r)
        free(c);
    else
        *handle = c;
    return r;
}
uint32_t exp_call(void *handle, uint32_t cmd, const void *in, size_t ni, void *out, size_t no) {
    struct client *c = handle;
    TEEC_Operation op = {0};
    op.paramTypes = TEEC_PARAM_TYPES(ni ? TEEC_MEMREF_TEMP_INPUT : TEEC_NONE,
                                     no ? TEEC_MEMREF_TEMP_OUTPUT : TEEC_NONE, TEEC_NONE, TEEC_NONE);
    op.params[0].tmpref.buffer = (void *)in;
    op.params[0].tmpref.size = ni;
    op.params[1].tmpref.buffer = out;
    op.params[1].tmpref.size = no;
    return TEEC_InvokeCommand(&c->session, cmd, &op, NULL);
}
void exp_close(void *handle) {
    struct client *c = handle;
    TEEC_CloseSession(&c->session);
    TEEC_FinalizeContext(&c->ctx);
    free(c);
}
