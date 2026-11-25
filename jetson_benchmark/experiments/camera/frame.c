/* Secure CPU front end. The two preallocated SFace activation buffers serve as
 * integral-image scratch until the aligned input tensor is ready. */
#include "frame.h"
#include <stdint.h>
#include <string.h>

struct rect {
  int x, y, w, h;
};
struct feature_rect {
  uint8_t x, y, w, h;
  int8_t weight;
};
struct stump {
  float cut, left, right;
  struct feature_rect r[3];
};
struct stage {
  unsigned count;
  float cut;
};
struct cascade {
  unsigned window, count;
  const struct stage *stage;
  const struct stump *tree;
};
#include "cascades.h"

static int nearest(double x) { return (int)(x + 0.5); }
static int clamp(int x, int lo, int hi) {
  return x < lo ? lo : x > hi ? hi : x;
}
static double root(double x) { return __builtin_sqrt(x); }

static unsigned gray(const uint8_t *bgr, int w, int h, int x, int y) {
  if (x < 0 || x >= w || y < 0 || y >= h)
    return 0;
  const uint8_t *p = bgr + 3 * (w * y + x);
  return (1868u * p[0] + 9617u * p[1] + 4899u * p[2] + 8192) >> 14;
}

static uint32_t area(const uint32_t *p, int stride, int x, int y, int w,
                     int h) {
  p += y * stride + x;
  return p[h * stride + w] - p[h * stride] - p[w] + p[0];
}

/* This uses a bilinear image pyramid. The variance and feature sums use
 * unsigned integral images. Local sums fit in 32 bits even if a prefix wraps.
 */
static void integrals(const uint8_t *image, int w, int h, struct rect roi,
                      uint32_t *sum, uint32_t *sq, int sw, int sh) {
  int stride = sw + 1;
  memset(sum, 0, stride * sizeof(*sum));
  memset(sq, 0, stride * sizeof(*sq));
  for (int y = 0; y < sh; ++y) {
    double py = (y + 0.5) * roi.h / sh - 0.5;
    if (py < 0)
      py = 0;
    int iy = (int)py, y0 = roi.y + iy, y1 = roi.y + clamp(iy + 1, 0, roi.h - 1);
    double fy = py - iy;
    uint32_t row = 0, row2 = 0;
    int dst = (y + 1) * stride;
    sum[dst] = sq[dst] = 0;
    for (int x = 0; x < sw; ++x) {
      double px = (x + 0.5) * roi.w / sw - 0.5;
      if (px < 0)
        px = 0;
      int ix = (int)px, x0 = roi.x + ix,
          x1 = roi.x + clamp(ix + 1, 0, roi.w - 1);
      double fx = px - ix;
      double top =
          (1 - fx) * gray(image, w, h, x0, y0) + fx * gray(image, w, h, x1, y0);
      double bot =
          (1 - fx) * gray(image, w, h, x0, y1) + fx * gray(image, w, h, x1, y1);
      unsigned v = nearest((1 - fy) * top + fy * bot);
      row += v;
      row2 += v * v;
      sum[dst + x + 1] = sum[dst - stride + x + 1] + row;
      sq[dst + x + 1] = sq[dst - stride + x + 1] + row2;
    }
  }
}

static int classify(const struct cascade *c, const uint32_t *sum,
                    const uint32_t *sq, int stride) {
  int side = c->window - 2, n = side * side;
  double s = area(sum, stride, 1, 1, side, side);
  double variance = (double)n * area(sq, stride, 1, 1, side, side) - s * s;
  if (variance <= (double)n * n * 100)
    return 0;
  float norm = (float)root(variance);
  const struct stump *tree = c->tree;
  for (unsigned i = 0; i < c->count; ++i) {
    double score = 0;
    for (unsigned j = 0; j < c->stage[i].count; ++j, ++tree) {
      int val = 0;
      for (int k = 0; k < 3 && tree->r[k].w; ++k) {
        const struct feature_rect *r = tree->r + k;
        val += r->weight * (int)area(sum, stride, r->x, r->y, r->w, r->h);
      }
      score += val < tree->cut * norm ? tree->left : tree->right;
    }
    if (score < c->stage[i].cut)
      return -(int)i;
  }
  return 1;
}

#define MAX_HITS 2048
struct hit {
  struct rect r;
  int parent;
};
struct cluster {
  int n, x, y, size;
};
struct workspace {
  struct hit hit[MAX_HITS];
  struct cluster groups[MAX_HITS];
};
size_t frame_detector_bytes(void) { return sizeof(struct workspace); }

static int leader(struct hit *hit, int i) {
  while (hit[i].parent != i) {
    hit[i].parent = hit[hit[i].parent].parent;
    i = hit[i].parent;
  }
  return i;
}

static int grouped(struct workspace *tmp, int count, struct rect best[2]) {
  memset(tmp->groups, 0, (size_t)count * sizeof(tmp->groups[0]));
  for (int i = 0; i < count; ++i) {
    struct rect a = tmp->hit[i].r;
    for (int j = 0; j < i; ++j) {
      struct rect b = tmp->hit[j].r;
      double eps = .2 * (a.w < b.w ? a.w : b.w);
      int left = a.x - b.x, top = a.y - b.y, right = left + a.w - b.w,
          bottom = top + a.h - b.h;
      if (left >= -eps && left <= eps && right >= -eps && right <= eps &&
          top >= -eps && top <= eps && bottom >= -eps && bottom <= eps)
        tmp->hit[leader(tmp->hit, i)].parent = leader(tmp->hit, j);
    }
  }
  for (int i = 0; i < count; ++i) {
    struct cluster *g = tmp->groups + leader(tmp->hit, i);
    g->n++;
    g->x += tmp->hit[i].r.x;
    g->y += tmp->hit[i].r.y;
    g->size += tmp->hit[i].r.w;
  }
  best[0].w = best[1].w = 0;
  int found = 0;
  for (int i = 0; i < count; ++i) {
    struct cluster g = tmp->groups[i];
    if (g.n <= 10)
      continue;
    int side = nearest((double)g.size / g.n);
    struct rect r = {nearest((double)g.x / g.n), nearest((double)g.y / g.n),
                     side, side};
    if (r.w > best[0].w) {
      best[1] = best[0];
      best[0] = r;
    } else if (r.w > best[1].w)
      best[1] = r;
    ++found;
  }
  return found;
}

static int detect(const struct cascade *c, const uint8_t *image, int w, int h,
                  struct rect roi, uint32_t *sum, uint32_t *sq,
                  struct workspace *tmp, struct rect out[2]) {
  int hits = 0;
  for (double scale = 1;; scale *= 1.1) {
    int sw = nearest(roi.w / scale), sh = nearest(roi.h / scale),
        side = nearest(c->window * scale);
    if (sw < (int)c->window || sh < (int)c->window)
      break;
    integrals(image, w, h, roi, sum, sq, sw, sh);
    int step = scale >= 2 ? 1 : 2;
    for (int y = 0; y + (int)c->window <= sh; y += step) {
      for (int x = 0; x + (int)c->window <= sw; x += step) {
        int off = y * (sw + 1) + x;
        int result = classify(c, sum + off, sq + off, sw + 1);
        if (result == 0)
          x += step;
        if (result != 1)
          continue;
        if (hits == MAX_HITS)
          return -1;
        tmp->hit[hits] = (struct hit){
            {nearest(x * scale), nearest(y * scale), side, side}, hits};
        ++hits;
      }
    }
  }
  int n = grouped(tmp, hits, out);
  for (int i = 0; i < n && i < 2; ++i) {
    out[i].x += roi.x;
    out[i].y += roi.y;
  }
  return n;
}

static double sample(const uint8_t *image, int w, int h, double x, double y,
                     int c) {
  if (x < -.5 || y < -.5 || x > w - .5 || y > h - .5)
    return 0;
  if (x < 0)
    x = 0;
  if (y < 0)
    y = 0;
  int ix = (int)x, iy = (int)y, jx = clamp(ix + 1, 0, w - 1),
      jy = clamp(iy + 1, 0, h - 1);
  double fx = x - ix, fy = y - iy;
  double a = (1 - fx) * image[3 * (iy * w + ix) + c] +
             fx * image[3 * (iy * w + jx) + c];
  double b = (1 - fx) * image[3 * (jy * w + ix) + c] +
             fx * image[3 * (jy * w + jx) + c];
  return (1 - fy) * a + fy * b;
}

int frame_crop(const uint8_t *image, int w, int h, uint32_t *sum, uint32_t *sq,
               size_t words, void *scratch, uint8_t *crop,
               struct frame_info *info) {
  if (w < 1 || h < 1 || w > FRAME_MAX_SIDE || h > FRAME_MAX_SIDE ||
      w * h > FRAME_MAX_PIXELS)
    return -1;
  int bx = w / 2, by = h / 2;
  /* Preserve the notebook's black border for normal dataset frames, keep the
   * integral images within the preallocated TA buffers for larger sensors. */
  if ((size_t)(w + 2 * bx + 1) * (h + 2 * by + 1) > words) {
    bx = 0;
    by = 0;
  }
  if ((size_t)(w + 2 * bx + 1) * (h + 2 * by + 1) > words)
    return -1;
  struct rect roi = {-bx, -by, w + 2 * bx, h + 2 * by}, faces[2] = {0},
              eyes[2] = {0};
  int n = detect(&face, image, w, h, roi, sum, sq, scratch, faces);
  if (n < 0)
    return -1;
  struct rect r = n ? faces[0] : (struct rect){0, 0, w, h};
  if (n && (size_t)(r.w + 1) * (r.h + 1) > words)
    return -1;
  int ne = n ? detect(&eye, image, w, h, r, sum, sq, scratch, eyes) : 0;
  if (ne < 0)
    return -1;
  double cs = 1, sn = 0;
  if (ne >= 2) {
    double dx = eyes[1].x + eyes[1].w / 2 - eyes[0].x - eyes[0].w / 2;
    double dy = eyes[1].y + eyes[1].h / 2 - eyes[0].y - eyes[0].h / 2;
    if (dx < 0) {
      dx = -dx;
      dy = -dy;
    }
    double len = root(dx * dx + dy * dy);
    if (len > 0) {
      cs = dx / len;
      sn = dy / len;
    }
  }
  int rw = r.w >= r.h ? 112 : clamp((112 * r.w) / r.h, 1, 112);
  int rh = r.h >= r.w ? 112 : clamp((112 * r.h) / r.w, 1, 112);
  memset(crop, 0, 112 * 112 * 3);
  for (int y = 0; y < rh; ++y)
    for (int x = 0; x < rw; ++x) {
      double u = ((x + .5) / rw - .5) * r.w, v = ((y + .5) / rh - .5) * r.h;
      double sx = r.x + (r.w - 1) * .5 + cs * u - sn * v,
             sy = r.y + (r.h - 1) * .5 + sn * u + cs * v;
      int pos = ((y + (112 - rh) / 2) * 112 + x + (112 - rw) / 2) * 3;
      for (int c = 0; c < 3; ++c)
        crop[pos + c] = nearest(sample(image, w, h, sx, sy, c));
    }
  if (info)
    *info = (struct frame_info){n, ne, r.x, r.y, r.w, r.h};
  return 0;
}
