package com.voicebridge

import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.util.Log
import java.util.concurrent.atomic.AtomicBoolean

class AudioCaptureThread(
    private val onOverflow: () -> Unit
) : Thread("AudioCaptureThread") {

    companion object {
        private const val TAG            = "AudioCaptureThread"
        private const val SAMPLE_RATE    = 16000
        private const val SAMPLES        = 320   // 20 ms frame at 16 kHz
        private const val RECLAIM_DELAY  = 500L
    }

    private val running = AtomicBoolean(false)
    private var record: AudioRecord? = null

    override fun run() {
        val minBuf = AudioRecord.getMinBufferSize(
            SAMPLE_RATE,
            AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT
        )
        val bufSize = maxOf(minBuf, SAMPLES * 2 * 8)  // keep ~8 frames in driver buffer

        record = AudioRecord(
            MediaRecorder.AudioSource.VOICE_COMMUNICATION,
            SAMPLE_RATE,
            AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT,
            bufSize
        )

        if (record!!.state != AudioRecord.STATE_INITIALIZED) {
            Log.e(TAG, "AudioRecord failed to initialise")
            return
        }

        record!!.startRecording()
        running.set(true)
        Log.i(TAG, "Audio capture started")

        val frame = ShortArray(SAMPLES)

        while (running.get()) {
            val n = record!!.read(frame, 0, SAMPLES, AudioRecord.READ_BLOCKING)
            when {
                n == SAMPLES -> {
                    if (!NativeBridge.ringBufferWrite(frame)) onOverflow()
                }
                n == AudioRecord.ERROR_DEAD_OBJECT -> {
                    Log.w(TAG, "AudioRecord dead — stopping (service will restart)")
                    running.set(false)
                }
                n < 0 -> Log.e(TAG, "AudioRecord.read error: $n")
            }
        }

        record?.stop()
        record?.release()
        record = null
        Log.i(TAG, "Audio capture stopped")
    }

    fun stopCapture() {
        running.set(false)
        record?.stop()
    }
}
