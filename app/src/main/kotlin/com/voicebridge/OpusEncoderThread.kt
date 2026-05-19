package com.voicebridge

import android.util.Log
import java.util.concurrent.LinkedBlockingQueue
import java.util.concurrent.atomic.AtomicBoolean

class OpusEncoderThread(
    private val encodedQueue: LinkedBlockingQueue<ByteArray>
) : Thread("OpusEncoderThread") {

    companion object {
        private const val TAG       = "OpusEncoderThread"
        private const val IDLE_NS   = 500_000L   // 0.5 ms park when ring is empty
    }

    private val running = AtomicBoolean(false)

    override fun run() {
        running.set(true)
        Log.i(TAG, "Encoder thread started")

        while (running.get()) {
            val encoded = NativeBridge.encodeNextFrame()
            if (encoded != null && encoded.isNotEmpty()) {
                // DTX: 1-2 byte silence packet — still enqueue so USB thread sends heartbeat timing
                encodedQueue.offer(encoded)
            } else {
                // Ring buffer empty — park briefly to avoid busy-spin
                java.util.concurrent.locks.LockSupport.parkNanos(IDLE_NS)
            }
        }

        Log.i(TAG, "Encoder thread stopped")
    }

    fun stopEncoding() {
        running.set(false)
    }
}
