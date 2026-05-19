package com.voicebridge

object NativeBridge {
    init {
        System.loadLibrary("voicebridge")
    }

    external fun initRingBuffer(): Boolean
    external fun initEncoder(sampleRate: Int, bitrate: Int, complexity: Int): Boolean
    external fun destroyEncoder()
    external fun ringBufferWrite(samples: ShortArray): Boolean
    external fun encodeNextFrame(): ByteArray?
    external fun ringBufferAvailable(): Int
}
