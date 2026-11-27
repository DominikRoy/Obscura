/* Reuse the exact private state and authenticated FP32 inference path. The
 * experiment dispatcher exposes its own commands; never delegate SF_FINISH. */
#include <tee_internal_api.h>
TEE_Result base_open(uint32_t, TEE_Param[4], void **);
void base_close(void *);
TEE_Result base_dispatch(void *, uint32_t, uint32_t, TEE_Param[4]);
#define TA_OpenSessionEntryPoint base_open
#define TA_CloseSessionEntryPoint base_close
#define TA_InvokeCommandEntryPoint base_dispatch
#include "../../secure_sface/ta/secure_ta.c"
#undef TA_OpenSessionEntryPoint
#undef TA_CloseSessionEntryPoint
#undef TA_InvokeCommandEntryPoint
#ifdef EXP_NATIVE
#include <openssl/rand.h>
#include <stdlib.h>
static void native_random(void *p, size_t n) {
    if (RAND_bytes(p, n) != 1)
        abort();
}
#define TEE_GenerateRandom native_random
#endif
#ifdef EXP_HEAP_STATS
#include <malloc.h>
#endif
#include "frame.h"
#include "decision.h"
#include "keys.h"
#include "layer.h"

enum { PROVISION = 10, SETUP, BEGIN, STEP, FINISH, TILE, OFFLINE, BLIND, ACCEPT, CONTROL, DECIDE, CAMERA_BEGIN, CAMERA_TIMING, CAMERA_HEAP, MASK_STORED, MASK_BENCH, GROUP_SETUP, GROUP_NEXT };
struct experiment {
    struct state *s;
    struct pilot *gpu;
    uint8_t *group;
    size_t group_size, group_offset, record_size;
    int failed;
    uint8_t mode, id[16], mac[32];
    uint32_t numerator;
    uint64_t private_pixels_ms, embedding_ready_ms;
    uint64_t heap_at_pixels, heap_peak;
    uint64_t input[EXP_DIM], probe_norm;
    uint8_t pad[24], peer_auth[32], packet_tag[32];
    int started, ended, awaiting_decision, camera;
};
/* Hardware uses the same millisecond timer as the SFace TA. The native
 * test shim's other clock has one-second resolution. */
static uint64_t camera_ms(void) {
#ifdef EXP_NATIVE
    struct timespec now;
    clock_gettime(CLOCK_MONOTONIC, &now);
    return (uint64_t)now.tv_sec * 1000 + now.tv_nsec / 1000000;
#else
    return milliseconds();
#endif
}
TEE_Result TA_OpenSessionEntryPoint(uint32_t types, TEE_Param p[4], void **session) {
    (void)p;
    if (types != TEE_PARAM_TYPES(0, 0, 0, 0)) return TEE_ERROR_BAD_PARAMETERS;
    struct experiment *e = TEE_Malloc(sizeof(*e), TEE_MALLOC_FILL_ZERO);
    if (!e) return TEE_ERROR_OUT_OF_MEMORY;
    *session = e;
    return TEE_SUCCESS;
}
void TA_CloseSessionEntryPoint(void *session) {
    struct experiment *e = session;
    if (!e)
        return;
    base_close(e->s);
    if (e->group) {
        sf_wipe(e->group, e->group_size);
        TEE_Free(e->group);
    }
    if (e->gpu) {
        sf_wipe(e->gpu, sizeof(*e->gpu));
        TEE_Free(e->gpu);
    }
    sf_wipe(e, sizeof(*e));
    TEE_Free(e);
}
#define IO(in, out) TEE_PARAM_TYPES(in, out, TEE_PARAM_TYPE_NONE, TEE_PARAM_TYPE_NONE)
#define I TEE_PARAM_TYPE_MEMREF_INPUT
#define O TEE_PARAM_TYPE_MEMREF_OUTPUT
#define N TEE_PARAM_TYPE_NONE

static TEE_Result setup(struct experiment *e, void *data, size_t n) {
    uint8_t box[BOX_HEAD + 1112 + BOX_TAG], plain[1112];
    if (n != BOX_HEAD + 1024 + BOX_TAG && n != BOX_HEAD + 1056 + BOX_TAG && n != sizeof(box))
        return TEE_ERROR_BAD_PARAMETERS;
    TEE_MemMove(box, data, n);
    unsigned len = n - BOX_HEAD - BOX_TAG;
    TEE_Result r = unseal(box, len, plain);
    if (!r) {
        uint8_t mode = box[0] & 0x7f;
        e->camera = box[0] >> 7;
        if (e->camera && (mode == 'C' || mode == 'c' || mode == 'Q' || mode == 'q')) {
            sf_wipe(plain, sizeof(plain));
            return TEE_ERROR_BAD_FORMAT;
        }
        e->numerator = EXP_LFW_NUM;
        if (mode >= 'a' && mode <= 'z') {
            mode -= 'a' - 'A';
            e->numerator = EXP_DRONEFACE_NUM;
        }
        if (e->camera && (mode == 'P' || mode == 'R')) {
            sf_wipe(plain, sizeof(plain));
            return TEE_ERROR_BAD_FORMAT;
        }
        if (mode == 'A' && len == 1024) {
            for (unsigned j = 0; j < EXP_DIM; ++j) {
                int64_t val;
                TEE_MemMove(&val, plain + j * 8, 8);
                if (!coordinate_ok(val))
                    r = TEE_ERROR_BAD_FORMAT;
            }
        } else if (((mode == 'B' || mode == 'H' || mode == 'C' || mode == 'Q' || mode == 'P') && len == 1056) ||
                   ((mode == 'T' || mode == 'R') && len == 1112)) {
            r = spend(box + 1); /* Consume before making any probe-dependent output. */
            TEE_MemMove(e->mac, plain + 1024, 32);
            if (!r && (mode == 'T' || mode == 'R')) {
                TEE_MemMove(e->pad, plain + 1056, 24);
                TEE_MemMove(e->peer_auth, plain + 1080, 32);
            }
            if (!r && (mode == 'C' || mode == 'Q')) {
                e->gpu = TEE_Malloc(sizeof(*e->gpu), TEE_MALLOC_FILL_ZERO);
                if (!e->gpu)
                    r = TEE_ERROR_OUT_OF_MEMORY;
            }
        } else
            r = TEE_ERROR_BAD_FORMAT;
        if (!r && mode != 'P' && mode != 'R') {
            void *base = NULL;
            TEE_Param none[4] = {0};
            r = base_open(IO(N, N), none, &base);
            e->s = base;
        }
        if (!r) {
            e->mode = mode;
            TEE_MemMove(e->id, box + 1, 16);
            TEE_MemMove(e->input, plain, 1024);
        }
    }
    sf_wipe(plain, sizeof(plain));
    return r;
}
/* All records are dealer-authenticated and consumed strictly in order.
 * Reserving the whole batch first burns its unread tail on session loss. */
static TEE_Result group_setup(struct experiment *e, const void *in, size_t n) {
    if (n <= BOX_HEAD + BOX_TAG || n > BOX_HEAD + BOX_TAG + 256u * 1128u)
        return TEE_ERROR_BAD_PARAMETERS;
    size_t bytes = n - BOX_HEAD - BOX_TAG;
    uint8_t *box = TEE_Malloc(n, 0);
    uint8_t *plain = TEE_Malloc(bytes, 0);
    TEE_Result r = TEE_ERROR_OUT_OF_MEMORY;
    if (!box || !plain) goto end;
    TEE_MemMove(box, in, n);
    uint8_t kind = box[0];
    uint8_t recon = kind == 'K' || kind == 'k';
    size_t record = recon ? 1128 : 1072;
    r = TEE_ERROR_BAD_FORMAT;
    if ((!recon && kind != 'J' && kind != 'j') || bytes % record || bytes / record > 256)
        goto end;
    r = unseal(box, bytes, plain);
    if (!r) r = spend(box + 1);
    if (!r) {
        e->group = plain;
        plain = NULL;
        e->group_size = bytes;
        e->record_size = record;
        e->mode = recon ? 'R' : 'P';
        e->numerator = kind >= 'a' ? EXP_DRONEFACE_NUM : EXP_LFW_NUM;
        e->ended = 1; /* GROUP_NEXT activates the first record. */
    }
end:
    if (plain) sf_wipe(plain, bytes);
    TEE_Free(plain);
    TEE_Free(box);
    return r;
}

static TEE_Result group_next(struct experiment *e) {
    if (!e->ended || e->awaiting_decision || e->group_offset >= e->group_size)
        return TEE_ERROR_BAD_STATE;
    uint8_t *record = e->group + e->group_offset;
    TEE_MemMove(e->id, record, 16);
    TEE_MemMove(e->input, record+16, 1024);
    TEE_MemMove(e->mac, record+1040, 32);
    if (e->mode == 'R') {
        TEE_MemMove(e->pad, record+1072, 24);
        TEE_MemMove(e->peer_auth, record+1096, 32);
    }
    sf_wipe(record, e->record_size);
    e->group_offset += e->record_size;
    e->probe_norm = 0;
    e->ended = 0;
    return TEE_SUCCESS;
}

/* Same 128 unsigned ring additions in online MASK_STORED and its public
 * throughput measurement. The barrier makes every timed output observable. */
static __attribute__((noinline)) void mask_ring(uint64_t *y, const uint64_t *delta) {
    for (unsigned i = 0; i < EXP_DIM; ++i) y[i] += delta[i];
    __asm__ volatile("" : : "r"(y) : "memory");
}
static TEE_Result output_mask(struct experiment *e, uint64_t *y, void *out) {
    uint8_t packet[1072], mac[32];
    TEE_MemMove(packet, e->id, 16);
    mask_ring(y, e->input);
    TEE_MemMove(packet + 16, y, 1024);
    size_t size = 1040;
    if (e->numerator == EXP_DRONEFACE_NUM) packet[size++] = 'D';
    TEE_Result r = tag(e->mac, packet, size, mac);
    if (!r) {
        TEE_MemMove(packet + 1040, mac, 32);
        TEE_MemMove(out, packet, sizeof(packet));
        if (e->mode == 'T' || e->mode == 'R') {
            TEE_MemMove(e->packet_tag, mac, 32);
            e->awaiting_decision = 1;
        }
    }
    sf_wipe(packet, sizeof(packet));
    sf_wipe(mac, sizeof(mac));
    return r;
}

static TEE_Result mask_stored(struct experiment *e, const void *in, void *out, size_t out_size) {
    uint64_t q[EXP_DIM];
    TEE_MemMove(q, in, sizeof(q));
    TEE_Result r = TEE_ERROR_BAD_FORMAT;
    for (unsigned i = 0; i < EXP_DIM; ++i) {
        if (!coordinate_ok((int64_t)q[i])) goto done;
        if (e->mode == 'R' || out_size == 1080) e->probe_norm += q[i] * q[i];
    }
    r = output_mask(e, q, out);
    /* The first 1072 bytes are forwarded to the WD. P's norm stays on the drone. */
    if (!r && out_size == 1080)
        TEE_MemMove((uint8_t *)out + 1072, &e->probe_norm, sizeof(e->probe_norm));
done:
    sf_wipe(q, sizeof(q));
    e->ended = !e->awaiting_decision;
    return r;
}

static TEE_Result mask_bench(void *out) {
    uint64_t work[EXP_DIM] = {0}, delta[EXP_DIM];
    for (unsigned i = 0; i < EXP_DIM; ++i) delta[i] = i + 1;
    uint64_t start = camera_ms();
    for (unsigned i = 0; i < 1000000; ++i) mask_ring(work, delta);
    uint64_t result[2] = {camera_ms() - start, work[EXP_DIM-1]};
    TEE_MemMove(out, result, sizeof(result));
    return TEE_SUCCESS;
}
static TEE_Result finish(struct experiment *e, void *output, size_t n) {
    uint64_t y[EXP_DIM];
    TEE_Result r = TEE_ERROR_BAD_FORMAT;
    if (sf_encode(e->s->x, y))
        goto done;
    for (unsigned i = 0; i < EXP_DIM; ++i)
        if (!coordinate_ok((int64_t)y[i]))
            goto done;
    if (e->mode == 'A' && n == 1) {
        int64_t xq[EXP_DIM], yq[EXP_DIM];
        TEE_MemMove(xq, e->input, sizeof(xq));
        TEE_MemMove(yq, y, sizeof(yq));
        uint8_t bit = plain_decision(xq, yq, e->numerator);
        sf_wipe(xq, sizeof(xq));
        sf_wipe(yq, sizeof(yq));
        TEE_MemMove(output, &bit, 1);
        r = TEE_SUCCESS;
    } else if (e->mode != 'A' && n == 1072) {
        r = output_mask(e, y, output);
    }
done:
    sf_wipe(y, sizeof(y));
    reset(e->s);
    e->ended = !e->awaiting_decision;
    return r;
}

/* Linux supplies its own shares and relays the peer ciphertext and tag.
 * Authenticate a private copy before unmasking; accept exactly one request. */
static TEE_Result decide(struct experiment *e, void *input, void *out) {
    uint64_t local[3], peer[3];
    uint8_t message[16+32+24], expected[32], supplied[32], diff = 0;
    uint8_t *bytes = input;
    size_t share_bytes = e->mode == 'R' ? 16 : 24;
    TEE_MemMove(local, bytes, share_bytes);
    TEE_MemMove(message, e->id, 16);
    TEE_MemMove(message+16, e->packet_tag, 32);
    TEE_MemMove(message+48, bytes+share_bytes, share_bytes);
    TEE_MemMove(supplied, bytes+2*share_bytes, 32);
    TEE_Result r = tag(e->peer_auth, message, 48+share_bytes, expected);
    if (!r) {
        for (unsigned i = 0; i < 32; ++i)
            diff |= expected[i] ^ supplied[i];
        if (diff)
            r = TEE_ERROR_SECURITY;
    }
    if (!r) {
        for (unsigned i = 0; i < share_bytes; ++i)
            message[48+i] ^= e->pad[i];
        TEE_MemMove(peer, message+48, share_bytes);
        int bit = decide_terms((int64_t)(local[0]+peer[0]), local[1]+peer[1], (e->mode == 'R' ? e->probe_norm : local[2]+peer[2]), e->numerator);
        if (bit < 0)
            r = TEE_ERROR_BAD_FORMAT;
        else
            *(uint8_t *)out = (uint8_t)bit;
    }
    sf_wipe(local, sizeof(local));
    sf_wipe(peer, sizeof(peer));
    sf_wipe(message, sizeof(message));
    sf_wipe(e->pad, sizeof(e->pad));
    sf_wipe(e->peer_auth, sizeof(e->peer_auth));
    return r;
}
/* The camera simulator supplies only an authenticated, slot-bound ciphertext.
 * Keep coordinates, pixels and intermediate crops entirely in TA memory. */
static TEE_Result begin_frame(struct experiment *e, void *input, size_t size) {
    const size_t overhead = BOX_HEAD + BOX_TAG;
    if (!input || size < overhead + 7 || size > overhead + 4 + 3*FRAME_MAX_PIXELS)
        return TEE_ERROR_BAD_PARAMETERS;
    size_t bytes = size - overhead;
    uint8_t *box = TEE_Malloc(size, 0);
    uint8_t *plain = TEE_Malloc(bytes, 0);
    void *scratch = TEE_Malloc(frame_detector_bytes(), 0);
    TEE_Result result = TEE_ERROR_OUT_OF_MEMORY;
    if (!box || !plain || !scratch) goto done;
    TEE_MemMove(box, input, size);
    result = TEE_ERROR_SECURITY;
    if (box[0] != 'F' || TEE_MemCompare(box+1, e->id, 16)) goto done;
    result = unseal(box, bytes, plain);
    if (result) goto done;
    unsigned w = plain[0] | ((unsigned)plain[1] << 8);
    unsigned h = plain[2] | ((unsigned)plain[3] << 8);
    result = TEE_ERROR_BAD_FORMAT;
    if (!w || !h || w>FRAME_MAX_SIDE || h>FRAME_MAX_SIDE || bytes != 4u+3u*w*h)
        goto done;
    struct state *s = e->s;
#ifdef EXP_HEAP_STATS
    struct malloc_stats heap;
    malloc_get_stats(&heap);
    e->heap_at_pixels = heap.allocated;
    malloc_reset_stats();
#endif
    e->private_pixels_ms = camera_ms();
    if (frame_crop(plain+4, w, h, (uint32_t *)s->a, (uint32_t *)s->b,
                   SF_BUFFER_FLOATS, scratch, (uint8_t *)s->block, NULL)) goto done;
    s->x=s->a; s->y=s->b; s->next=0;
    sf_input((uint8_t *)s->block, s->x);
    sf_wipe(s->block, SF_CROP_BYTES);
    e->started=1; s->active=1;
    result=TEE_SUCCESS;
done:
    if (plain) sf_wipe(plain,bytes);
    if (scratch) sf_wipe(scratch,frame_detector_bytes());
    TEE_Free(scratch); TEE_Free(plain); TEE_Free(box);
    return result;
}

static TEE_Result dispatch(struct experiment *e, uint32_t cmd, uint32_t t, TEE_Param p[4]) {
    /* Read-only timing after setup, including after FINISH/DECIDE. Authentication
     * and inference error handling still close the session to protocol commands. */
    if (cmd == CAMERA_TIMING && e->mode && e->camera && t == IO(N, O) &&
        p[1].memref.buffer && p[1].memref.size == 3 * sizeof(uint64_t)) {
        uint64_t stamps[] = {camera_ms(), e->private_pixels_ms, e->embedding_ready_ms};
        TEE_MemMove(p[1].memref.buffer, stamps, sizeof(stamps));
        return TEE_SUCCESS;
    }
    if (cmd == CAMERA_HEAP && e->camera && e->embedding_ready_ms && t == IO(N, O) &&
        p[1].memref.buffer && p[1].memref.size == 2 * sizeof(uint64_t)) {
        uint64_t sizes[] = {e->heap_at_pixels, e->heap_peak};
        TEE_MemMove(p[1].memref.buffer, sizes, sizeof(sizes));
        return TEE_SUCCESS;
    }
    if (e->failed) return TEE_ERROR_BAD_STATE;
    if (cmd == GROUP_SETUP && !e->mode && t == IO(I, N) && p[0].memref.buffer)
        return group_setup(e, p[0].memref.buffer, p[0].memref.size);
    if (cmd == GROUP_NEXT && e->group && t == IO(N, N)) return group_next(e);
    if (e->ended)
        return TEE_ERROR_BAD_STATE;
    void *in = p[0].memref.buffer, *out = p[1].memref.buffer;
    size_t ni = p[0].memref.size, no = p[1].memref.size;
    if (e->awaiting_decision) {
        e->awaiting_decision = 0;
        e->ended = 1;
        if (cmd == DECIDE && t == IO(I, O) && in && ni == (e->mode == 'R' ? 64u : 80u) && out && no == 1)
            return decide(e, in, out);
        return TEE_ERROR_BAD_STATE;
    }
    if (cmd == PROVISION && !e->mode && t == IO(I, N) && in && ni == 32)
        return provision(in);
    if (cmd == SETUP && !e->mode && t == IO(I, N) && in)
        return setup(e, in, ni);
    if (cmd == MASK_BENCH && !e->mode && t == IO(N, O) && out && no == 16)
        return mask_bench(out);
    if (e->mode == 'P' || e->mode == 'R') {
        if (cmd == MASK_STORED && t == IO(I, O) && in && ni == 1024 && out &&
            (no == 1072 || (e->mode == 'P' && no == 1080)))
            return mask_stored(e, in, out, no);
        return TEE_ERROR_BAD_STATE;
    }
    if (!e->mode)
        return TEE_ERROR_BAD_STATE;
    struct state *s = e->s;
    struct pilot *g = e->gpu;
    if (!e->started && cmd == TILE && g && t == IO(I, N) && in)
        return load_tile(s, g, in, ni);
    if (!e->started && cmd == OFFLINE && g && !g->ready && g->loaded == AFTER - FIRST &&
        t == IO(N, N)) {
        if (e->mode == 'C')
            prepare_gpu(g);
        else
            g->ready = 1;
        return TEE_SUCCESS;
    }
    if (e->camera && !e->started && cmd == CAMERA_BEGIN && t == IO(I, N))
        return begin_frame(e, in, ni);
    if (!e->camera && !e->started && cmd == BEGIN && (!g || g->ready) && t == IO(I, N)) {
        e->started = 1;
        return invoke(s, SF_BEGIN, t, p);
    }
    if (!e->started || !s->active)
        return TEE_ERROR_BAD_STATE;
    if (g && s->next == FIRST) {
        if (e->mode == 'Q' && cmd == CONTROL && t == IO(N, N)) {
            TEE_Result r = layer_input(s, g, NULL);
            if (!r)
                cpu_control(s, g);
            return r;
        }
        if (e->mode == 'C' && !g->pending && cmd == BLIND && t == IO(N, O) && out && no == ELEMS * 4)
            return layer_input(s, g, out);
        if (e->mode == 'C' && g->pending && cmd == ACCEPT && t == IO(I, N) && in && ni == ELEMS * 4)
            return accept_gpu(s, g, in);
        return TEE_ERROR_BAD_STATE;
    }
    if (cmd == STEP && t == IO(I, N)) {
        TEE_Result r = invoke(s, SF_STEP, t, p);
        if (!r && e->camera && s->next == SF_STEP_COUNT) {
            e->embedding_ready_ms = camera_ms();
#ifdef EXP_HEAP_STATS
            struct malloc_stats heap;
            malloc_get_stats(&heap);
            /* Reset starts the counter at zero. Include already-live blocks. */
            e->heap_peak = heap.max_allocated > e->heap_at_pixels ?
                           heap.max_allocated : e->heap_at_pixels;
#endif
        }
        return r;
    }
    if (cmd == FINISH && s->next == SF_STEP_COUNT && t == IO(N, O) && out)
        return finish(e, out, no);
    return TEE_ERROR_BAD_STATE;
}
TEE_Result TA_InvokeCommandEntryPoint(void *session, uint32_t cmd, uint32_t t, TEE_Param p[4]) {
    struct experiment *e = session;
    if (!e)
        return TEE_ERROR_BAD_STATE;
    TEE_Result r = dispatch(e, cmd, t, p);
    if (r) {
        e->failed = 1;
        if (e->s) reset(e->s);
        e->ended = 1;
    }
    return r;
}
#ifdef EXP_NATIVE
TEE_Result exp_open(void **h) {
    TEE_Param p[4] = {0};
    return TA_OpenSessionEntryPoint(IO(N, N), p, h);
}
void exp_close(void *h) { TA_CloseSessionEntryPoint(h); }
TEE_Result exp_call(void *h, uint32_t cmd, void *in, size_t ni, void *out, size_t no) {
    TEE_Param p[4] = {0};
    p[0].memref.buffer = in;
    p[0].memref.size = ni;
    p[1].memref.buffer = out;
    p[1].memref.size = no;
    return TA_InvokeCommandEntryPoint(h, cmd, IO(ni ? I : N, no ? O : N), p);
}
#endif
