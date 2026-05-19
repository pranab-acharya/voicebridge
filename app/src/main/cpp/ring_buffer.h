#ifndef RING_BUFFER_H
#define RING_BUFFER_H

#include <stdint.h>
#include <stdbool.h>
#include <stdatomic.h>
#include <string.h>

// Lock-free SPSC ring buffer — 32 slots × 320 samples × 2 bytes = 20 KB
#define RING_SLOTS        32
#define SAMPLES_PER_FRAME 320
#define BYTES_PER_SAMPLE  2
#define FRAME_BYTES       (SAMPLES_PER_FRAME * BYTES_PER_SAMPLE)

typedef struct {
    uint8_t data[FRAME_BYTES];
} RingFrame;

typedef struct {
    RingFrame        frames[RING_SLOTS];
    _Atomic uint32_t write_pos;
    _Atomic uint32_t read_pos;
} RingBuffer;

static inline void ring_buffer_init(RingBuffer *rb) {
    atomic_init(&rb->write_pos, 0u);
    atomic_init(&rb->read_pos,  0u);
}

// Called from producer thread only
static inline bool ring_buffer_write(RingBuffer *rb, const int16_t *samples) {
    uint32_t wp = atomic_load_explicit(&rb->write_pos, memory_order_relaxed);
    uint32_t rp = atomic_load_explicit(&rb->read_pos,  memory_order_acquire);
    if (wp - rp >= RING_SLOTS) return false;  // full
    memcpy(rb->frames[wp % RING_SLOTS].data, samples, FRAME_BYTES);
    atomic_store_explicit(&rb->write_pos, wp + 1u, memory_order_release);
    return true;
}

// Called from consumer thread only
static inline bool ring_buffer_read(RingBuffer *rb, int16_t *out) {
    uint32_t rp = atomic_load_explicit(&rb->read_pos,  memory_order_relaxed);
    uint32_t wp = atomic_load_explicit(&rb->write_pos, memory_order_acquire);
    if (rp == wp) return false;  // empty
    memcpy(out, rb->frames[rp % RING_SLOTS].data, FRAME_BYTES);
    atomic_store_explicit(&rb->read_pos, rp + 1u, memory_order_release);
    return true;
}

static inline uint32_t ring_buffer_available(RingBuffer *rb) {
    uint32_t wp = atomic_load_explicit(&rb->write_pos, memory_order_acquire);
    uint32_t rp = atomic_load_explicit(&rb->read_pos,  memory_order_acquire);
    return wp - rp;
}

#endif  // RING_BUFFER_H
