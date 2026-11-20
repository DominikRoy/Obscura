/* Native protocol tests. This executable is not a trusted application. */
#include <assert.h>
#include <stdio.h>
#include "tee_internal_api.h"
#include "protocol.h"
#include "model.h"
TEE_Result TA_OpenSessionEntryPoint(uint32_t, TEE_Param[4], void **);
TEE_Result TA_InvokeCommandEntryPoint(void *, uint32_t, uint32_t, TEE_Param[4]);
void TA_CloseSessionEntryPoint(void *);

int main(int argc, char **argv)
{
    assert(argc == 2);
    unsigned char *blob = malloc(SF_BLOB_BYTES);
    FILE *file = fopen(argv[1], "rb");
    assert(file && blob && fread(blob, 1, SF_BLOB_BYTES, file) == SF_BLOB_BYTES);
    fclose(file);
    TEE_Param p[4] = {0};
    void *session = NULL;
    const uint32_t input_types = TEE_PARAM_TYPES(5, 0, 0, 0);
    const uint32_t output_types = TEE_PARAM_TYPES(6, 6, 0, 0);
    assert(TA_OpenSessionEntryPoint(input_types, p, &session) == TEE_ERROR_BAD_PARAMETERS);
    assert(TA_OpenSessionEntryPoint(0, p, &session) == TEE_SUCCESS);
    uint64_t masked[128];
    struct sf_metrics metrics;
    p[0].memref.buffer = masked; p[0].memref.size = sizeof(masked);
    p[1].memref.buffer = &metrics; p[1].memref.size = sizeof(metrics);
    assert(TA_InvokeCommandEntryPoint(session, SF_FINISH, output_types, p) == TEE_ERROR_BAD_STATE);

    unsigned char crop[SF_CROP_BYTES];
    for (size_t i = 0; i < sizeof(crop); ++i) crop[i] = (unsigned char)(i % 251);
    p[0].memref.buffer = crop; p[0].memref.size = sizeof(crop) - 1;
    assert(TA_InvokeCommandEntryPoint(session, SF_BEGIN, input_types, p) == TEE_ERROR_BAD_PARAMETERS);
    p[0].memref.size = sizeof(crop);
    assert(TA_InvokeCommandEntryPoint(session, SF_BEGIN, input_types, p) == TEE_SUCCESS);
    p[0].memref.buffer = blob; p[0].memref.size = sf_steps[0].bytes;
    blob[0] ^= 1;
    assert(TA_InvokeCommandEntryPoint(session, SF_STEP, input_types, p) == TEE_ERROR_SECURITY);
    blob[0] ^= 1;
    assert(TA_InvokeCommandEntryPoint(session, SF_STEP, input_types, p) == TEE_ERROR_BAD_STATE);
    p[0].memref.buffer = crop; p[0].memref.size = sizeof(crop);
    assert(TA_InvokeCommandEntryPoint(session, SF_BEGIN, input_types, p) == TEE_SUCCESS);
    for (size_t i = 0; i < SF_STEP_COUNT; ++i) {
        p[0].memref.buffer = blob + sf_steps[i].offset;
        p[0].memref.size = sf_steps[i].bytes;
        assert(TA_InvokeCommandEntryPoint(session, SF_STEP, input_types, p) == TEE_SUCCESS);
    }
    memset(masked, 0, sizeof(masked));
    p[0].memref.buffer = masked; p[0].memref.size = sizeof(masked);
    p[1].memref.buffer = &metrics; p[1].memref.size = sizeof(metrics);
    assert(TA_InvokeCommandEntryPoint(session, SF_FINISH, output_types, p) == TEE_SUCCESS);
    assert(TA_InvokeCommandEntryPoint(session, SF_FINISH, output_types, p) == TEE_ERROR_BAD_STATE);
    TA_CloseSessionEntryPoint(session);

    /* Independently run the kernels and verify the final add/quantize boundary. */
    float *a = calloc(SF_BUFFER_FLOATS, sizeof(float)), *b = calloc(SF_BUFFER_FLOATS, sizeof(float));
    assert(a && b);
    float *x = a, *y = b;
    sf_input(crop, x);
    for (size_t i = 0; i < SF_STEP_COUNT; ++i)
        assert(!sf_step_run(&sf_steps[i], (const float *)(blob + sf_steps[i].offset), &x, &y));
    uint64_t q[128];
    assert(!sf_encode(x, q));
    for (size_t i = 0; i < 128; ++i) assert(masked[i] - UINT64_C(0x5a5a5a5a5a5a5a5a) == q[i]);
    free(a); free(b); free(blob);
    puts("PASS: native TA parameter/state/hash checks and complete inference-to-mask flow (not hardware)");
    return 0;
}
