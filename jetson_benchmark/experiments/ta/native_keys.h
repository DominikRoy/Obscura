/* Native validation only. Keys and spent-slot history last for one process. */
#include <openssl/evp.h>
#include <openssl/hmac.h>
static uint8_t native_key[32], spent_ids[256][16];
static unsigned spent_count;
static int initialized;
static TEE_Result provision(const uint8_t *key) {
    if (initialized)
        return TEE_ERROR_BAD_STATE;
    memcpy(native_key, key, 32);
    initialized = 1;
    return TEE_SUCCESS;
}
static TEE_Result unseal(uint8_t *box, size_t n, uint8_t *plain) {
    EVP_CIPHER_CTX *ctx = EVP_CIPHER_CTX_new();
    uint8_t aad[AAD_BYTES];
    box_aad(aad, box);
    int len;
    int ok = initialized && ctx &&
             EVP_DecryptInit_ex(ctx, EVP_aes_256_gcm(), NULL, native_key, box + BOX_AAD) &&
             EVP_DecryptUpdate(ctx, NULL, &len, aad, sizeof(aad)) &&
             EVP_DecryptUpdate(ctx, plain, &len, box + BOX_HEAD, (int)n) &&
             EVP_CIPHER_CTX_ctrl(ctx, EVP_CTRL_GCM_SET_TAG, 16, box + BOX_HEAD + n) &&
             EVP_DecryptFinal_ex(ctx, plain + len, &len);
    EVP_CIPHER_CTX_free(ctx);
    return ok ? TEE_SUCCESS : TEE_ERROR_SECURITY;
}
static TEE_Result spend(const uint8_t *id) {
    for (unsigned i = 0; i < spent_count; ++i)
        if (!memcmp(spent_ids[i], id, 16))
            return TEE_ERROR_BAD_STATE;
    if (spent_count == 256)
        return TEE_ERROR_BAD_STATE;
    memcpy(spent_ids[spent_count++], id, 16);
    return TEE_SUCCESS;
}
static TEE_Result tag(const uint8_t *key, const uint8_t *data, size_t n, uint8_t *out) {
    return HMAC(EVP_sha256(), key, 32, data, n, out, NULL) ? TEE_SUCCESS : TEE_ERROR_SECURITY;
}
