#ifndef OBSCURA_FRAME_H
#define OBSCURA_FRAME_H
#include <stddef.h>
#include <stdint.h>
#define FRAME_MAX_SIDE 1024
#define FRAME_MAX_PIXELS (640 * 480)
struct frame_info {
  int faces, eyes, x, y, w, h;
};
size_t frame_detector_bytes(void);
int frame_crop(const uint8_t *, int, int, uint32_t *, uint32_t *, size_t,
               void *, uint8_t *, struct frame_info *);
#endif
