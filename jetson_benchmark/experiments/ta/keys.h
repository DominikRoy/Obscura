/* Called only with private buffers. The sole bootstrap is an exclusive create
 * in a trusted commissioning environment. Subsequent Linux callers see boxes. */
#define BOX_AAD 17
#define BOX_HEAD (BOX_AAD + 12)
#define BOX_TAG 16
static const char box_domain[] = "obscura-v1/SFace128/trunc256/tau2=11368578e-8/";
#define AAD_BYTES (sizeof(box_domain) - 1 + 32 + BOX_AAD)
static void box_aad(uint8_t *out, const uint8_t *box) {
    TEE_MemMove(out, box_domain, sizeof(box_domain) - 1);
    TEE_MemMove(out + sizeof(box_domain) - 1, sf_model_digest, 32);
    TEE_MemMove(out + sizeof(box_domain) - 1 + 32, box, BOX_AAD);
}
#ifndef EXP_NATIVE
#ifndef EXP_STORAGE
#define EXP_STORAGE TEE_STORAGE_PRIVATE
#endif
static const char key_name[] = "dealer-aes256-v1";

static TEE_Result provision(const uint8_t *key) {
    TEE_ObjectHandle obj;
    TEE_Result r =
        TEE_CreatePersistentObject(EXP_STORAGE, key_name, sizeof(key_name), TEE_DATA_FLAG_ACCESS_READ,
                                   TEE_HANDLE_NULL, key, 32, &obj);
    if (!r)
        TEE_CloseObject(obj);
    return r;
}
static TEE_Result operation(const uint8_t *key, uint32_t type, uint32_t alg, uint32_t mode,
                            TEE_OperationHandle *op) {
    TEE_ObjectHandle obj = TEE_HANDLE_NULL;
    TEE_Attribute attr;
    TEE_Result r = TEE_AllocateTransientObject(type, 256, &obj);
    if (r)
        return r;
    TEE_InitRefAttribute(&attr, TEE_ATTR_SECRET_VALUE, (void *)key, 32);
    r = TEE_PopulateTransientObject(obj, &attr, 1);
    if (!r)
        r = TEE_AllocateOperation(op, alg, mode, 256);
    if (!r)
        r = TEE_SetOperationKey(*op, obj);
    TEE_FreeTransientObject(obj);
    return r;
}
static TEE_Result unseal(uint8_t *box, size_t n, uint8_t *plain) {
    uint8_t key[32], aad[AAD_BYTES];
    box_aad(aad, box);
    size_t count = 0;
    TEE_ObjectHandle obj;
    TEE_OperationHandle op = TEE_HANDLE_NULL;
    TEE_Result r = TEE_OpenPersistentObject(EXP_STORAGE, key_name, sizeof(key_name),
                                            TEE_DATA_FLAG_ACCESS_READ | TEE_DATA_FLAG_SHARE_READ, &obj);
    if (r)
        return r;
    r = TEE_ReadObjectData(obj, key, sizeof(key), &count);
    TEE_CloseObject(obj);
    if (!r && count != 32)
        r = TEE_ERROR_SECURITY;
    if (!r)
        r = operation(key, TEE_TYPE_AES, TEE_ALG_AES_GCM, TEE_MODE_DECRYPT, &op);
    sf_wipe(key, sizeof(key));
    if (!r)
        r = TEE_AEInit(op, box + BOX_AAD, 12, 128, sizeof(aad), n);
    if (!r) {
        size_t used = n;
        TEE_AEUpdateAAD(op, aad, sizeof(aad));
        r = TEE_AEDecryptFinal(op, box + BOX_HEAD, n, plain, &used, box + BOX_HEAD + n, BOX_TAG);
        if (!r && used != n)
            r = TEE_ERROR_SECURITY;
    }
    if (op != TEE_HANDLE_NULL)
        TEE_FreeOperation(op);
    return r;
}
static TEE_Result spend(const uint8_t *id) {
    TEE_ObjectHandle obj;
    TEE_Result r = TEE_CreatePersistentObject(EXP_STORAGE, id, 16, TEE_DATA_FLAG_ACCESS_READ,
                                              TEE_HANDLE_NULL, NULL, 0, &obj);
    if (!r)
        TEE_CloseObject(obj);
    return r;
}
static TEE_Result tag(const uint8_t *key, const uint8_t *data, size_t n, uint8_t *out) {
    TEE_OperationHandle op = TEE_HANDLE_NULL;
    TEE_Result r = operation(key, TEE_TYPE_HMAC_SHA256, TEE_ALG_HMAC_SHA256, TEE_MODE_MAC, &op);
    if (!r) {
        size_t len = 32;
        TEE_MACInit(op, NULL, 0);
        r = TEE_MACComputeFinal(op, data, n, out, &len);
    }
    if (op != TEE_HANDLE_NULL)
        TEE_FreeOperation(op);
    return r;
}
#else
#include "native_keys.h"
#endif
