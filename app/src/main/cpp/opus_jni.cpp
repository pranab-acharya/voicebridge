#include <jni.h>
#include <android/log.h>
#include <cstdint>
#include <cstring>

#include "ring_buffer.h"
#include "opus.h"

#define TAG  "VoiceBridgeJNI"
#define LOGI(...) __android_log_print(ANDROID_LOG_INFO,  TAG, __VA_ARGS__)
#define LOGE(...) __android_log_print(ANDROID_LOG_ERROR, TAG, __VA_ARGS__)

// Max encoded frame size per the Opus spec
#define MAX_OPUS_FRAME_BYTES 1275

static RingBuffer  g_ring;
static OpusEncoder *g_encoder = nullptr;

extern "C" {

JNIEXPORT jboolean JNICALL
Java_com_voicebridge_NativeBridge_initRingBuffer(JNIEnv *, jobject) {
    ring_buffer_init(&g_ring);
    LOGI("Ring buffer initialized (%d slots)", RING_SLOTS);
    return JNI_TRUE;
}

JNIEXPORT jboolean JNICALL
Java_com_voicebridge_NativeBridge_initEncoder(JNIEnv *, jobject,
                                              jint sample_rate,
                                              jint bitrate,
                                              jint complexity) {
    if (g_encoder) {
        opus_encoder_destroy(g_encoder);
        g_encoder = nullptr;
    }
    int err;
    g_encoder = opus_encoder_create(sample_rate, 1, OPUS_APPLICATION_VOIP, &err);
    if (err != OPUS_OK || !g_encoder) {
        LOGE("opus_encoder_create failed: %s", opus_strerror(err));
        return JNI_FALSE;
    }
    opus_encoder_ctl(g_encoder, OPUS_SET_BITRATE(bitrate));
    opus_encoder_ctl(g_encoder, OPUS_SET_COMPLEXITY(complexity));
    opus_encoder_ctl(g_encoder, OPUS_SET_DTX(1));           // skip silence frames
    opus_encoder_ctl(g_encoder, OPUS_SET_INBAND_FEC(0));
    opus_encoder_ctl(g_encoder, OPUS_SET_SIGNAL(OPUS_SIGNAL_VOICE));
    LOGI("Opus encoder ready: %d Hz  %d bps  complexity %d  DTX on",
         sample_rate, bitrate, complexity);
    return JNI_TRUE;
}

JNIEXPORT void JNICALL
Java_com_voicebridge_NativeBridge_destroyEncoder(JNIEnv *, jobject) {
    if (g_encoder) {
        opus_encoder_destroy(g_encoder);
        g_encoder = nullptr;
        LOGI("Opus encoder destroyed");
    }
}

// Returns false when ring buffer is full (caller should drop the frame)
JNIEXPORT jboolean JNICALL
Java_com_voicebridge_NativeBridge_ringBufferWrite(JNIEnv *env, jobject,
                                                   jshortArray samples) {
    if (env->GetArrayLength(samples) < SAMPLES_PER_FRAME) return JNI_FALSE;
    jshort *ptr = env->GetShortArrayElements(samples, nullptr);
    bool ok = ring_buffer_write(&g_ring, reinterpret_cast<int16_t *>(ptr));
    env->ReleaseShortArrayElements(samples, ptr, JNI_ABORT);
    return ok ? JNI_TRUE : JNI_FALSE;
}

// Reads one frame from ring buffer, encodes it, returns encoded bytes or null
JNIEXPORT jbyteArray JNICALL
Java_com_voicebridge_NativeBridge_encodeNextFrame(JNIEnv *env, jobject) {
    int16_t pcm[SAMPLES_PER_FRAME];
    if (!ring_buffer_read(&g_ring, pcm)) return nullptr;
    if (!g_encoder)                      return nullptr;

    uint8_t encoded[MAX_OPUS_FRAME_BYTES];
    int len = opus_encode(g_encoder, pcm, SAMPLES_PER_FRAME, encoded, MAX_OPUS_FRAME_BYTES);
    if (len <= 0) {
        LOGE("opus_encode error: %s", opus_strerror(len));
        return nullptr;
    }
    // DTX: Opus returns 1-2 bytes for silence — still forward so receiver can track timing
    jbyteArray result = env->NewByteArray(len);
    env->SetByteArrayRegion(result, 0, len, reinterpret_cast<jbyte *>(encoded));
    return result;
}

JNIEXPORT jint JNICALL
Java_com_voicebridge_NativeBridge_ringBufferAvailable(JNIEnv *, jobject) {
    return static_cast<jint>(ring_buffer_available(&g_ring));
}

}  // extern "C"
