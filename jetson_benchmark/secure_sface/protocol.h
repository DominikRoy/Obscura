#ifndef SF_PROTOCOL_H
#define SF_PROTOCOL_H
#include <stdint.h>
#define SF_UUID { 0x91e80c62, 0xc52a, 0x4b3c, {0x93, 0xb5, 0x7f, 0x87, 0x4c, 0xdc, 0x25, 0xa4} }
#define SF_INFO 0
#define SF_BEGIN 1
#define SF_STEP 2
#define SF_FINISH 3
#define SF_CROP_BYTES (112 * 112 * 3)
#define SF_DIMENSION 128
struct sf_metrics {
    uint64_t preprocess_ms, weights_ms, inference_ms, encode_ms, mask_ms;
};
#endif
