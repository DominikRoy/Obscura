/* TEST ONLY: host API substitute. Never use as a TA development kit. */
#ifndef TEST_TEE_API_H
#define TEST_TEE_API_H
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <openssl/sha.h>
typedef uint32_t TEE_Result;
typedef void *TEE_OperationHandle;
typedef struct { uint32_t seconds, millis; } TEE_Time;
typedef union { struct { void *buffer; size_t size; } memref; struct { uint32_t a, b; } value; } TEE_Param;
#define TEE_SUCCESS 0
#define TEE_ERROR_BAD_PARAMETERS 0xffff0006
#define TEE_ERROR_BAD_STATE 0xffff0007
#define TEE_ERROR_NOT_SUPPORTED 0xffff000a
#define TEE_ERROR_OUT_OF_MEMORY 0xffff000c
#define TEE_ERROR_SECURITY 0xffff000f
#define TEE_ERROR_SHORT_BUFFER 0xffff0010
#define TEE_ERROR_BAD_FORMAT 0xffff0005
#define TEE_PARAM_TYPE_NONE 0
#define TEE_PARAM_TYPE_MEMREF_INPUT 5
#define TEE_PARAM_TYPE_MEMREF_OUTPUT 6
#define TEE_PARAM_TYPES(a,b,c,d) ((a)|((b)<<4)|((c)<<8)|((d)<<12))
#define TEE_HANDLE_NULL NULL
#define TEE_MALLOC_FILL_ZERO 0
#define TEE_ALG_SHA256 1
#define TEE_MODE_DIGEST 1
static inline void *TEE_Malloc(size_t size, uint32_t hint) { (void)hint; return calloc(1, size); }
static inline void TEE_Free(void *p) { free(p); }
static inline void TEE_MemMove(void *d, const void *s, size_t n) { memmove(d, s, n); }
static inline void TEE_MemFill(void *d, uint32_t v, size_t n) { memset(d, v, n); }
static inline int TEE_MemCompare(const void *a, const void *b, size_t n) { return memcmp(a, b, n); }
static inline void TEE_GetSystemTime(TEE_Time *t) { t->seconds = (uint32_t)time(NULL); t->millis = 0; }
/* Deterministic pad only to check masking arithmetic in this host test. */
static inline void TEE_GenerateRandom(void *p, size_t n) { memset(p, 0x5a, n); }
static inline TEE_Result TEE_AllocateOperation(TEE_OperationHandle *h, uint32_t a, uint32_t m, uint32_t k) {
    (void)a; (void)m; (void)k; *h = (void *)1; return TEE_SUCCESS;
}
static inline void TEE_FreeOperation(TEE_OperationHandle h) { (void)h; }
static inline TEE_Result TEE_DigestDoFinal(TEE_OperationHandle h, const void *p, size_t n, void *d, size_t *length) {
    (void)h; if (*length < 32) return TEE_ERROR_SHORT_BUFFER;
    SHA256(p, n, d); *length = 32; return TEE_SUCCESS;
}
#endif
