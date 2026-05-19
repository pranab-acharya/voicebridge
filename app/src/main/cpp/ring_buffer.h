#pragma once

// Lock-free SPSC ring buffer — 32 slots × 320 samples × 2 bytes = 20 KB
// Written in C++11 atomics so it compiles cleanly from a C++ TU.

#include <atomic>
#include <cstdint>
#include <cstring>

#define RING_SLOTS        32
#define SAMPLES_PER_FRAME 320
#define BYTES_PER_SAMPLE  2
#define FRAME_BYTES       (SAMPLES_PER_FRAME * BYTES_PER_SAMPLE)

struct RingFrame {
    uint8_t data[FRAME_BYTES];
};

struct RingBuffer {
    RingFrame frames[RING_SLOTS];
    std::atomic<uint32_t> write_pos{0};
    std::atomic<uint32_t> read_pos{0};
};

inline void ring_buffer_init(RingBuffer *rb) {
    rb->write_pos.store(0, std::memory_order_relaxed);
    rb->read_pos.store(0,  std::memory_order_relaxed);
}

// Called from producer thread only
inline bool ring_buffer_write(RingBuffer *rb, const int16_t *samples) {
    uint32_t wp = rb->write_pos.load(std::memory_order_relaxed);
    uint32_t rp = rb->read_pos.load(std::memory_order_acquire);
    if (wp - rp >= RING_SLOTS) return false;  // full
    memcpy(rb->frames[wp % RING_SLOTS].data, samples, FRAME_BYTES);
    rb->write_pos.store(wp + 1u, std::memory_order_release);
    return true;
}

// Called from consumer thread only
inline bool ring_buffer_read(RingBuffer *rb, int16_t *out) {
    uint32_t rp = rb->read_pos.load(std::memory_order_relaxed);
    uint32_t wp = rb->write_pos.load(std::memory_order_acquire);
    if (rp == wp) return false;  // empty
    memcpy(out, rb->frames[rp % RING_SLOTS].data, FRAME_BYTES);
    rb->read_pos.store(rp + 1u, std::memory_order_release);
    return true;
}

inline uint32_t ring_buffer_available(RingBuffer *rb) {
    uint32_t wp = rb->write_pos.load(std::memory_order_acquire);
    uint32_t rp = rb->read_pos.load(std::memory_order_acquire);
    return wp - rp;
}
