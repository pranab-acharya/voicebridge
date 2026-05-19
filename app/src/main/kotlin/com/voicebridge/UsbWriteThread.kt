package com.voicebridge

import android.util.Log
import java.io.IOException
import java.util.concurrent.LinkedBlockingQueue
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicInteger

class UsbWriteThread(
    private val encodedQueue: LinkedBlockingQueue<ByteArray>,
    private val usb: UsbAccessoryManager
) : Thread("UsbWriteThread") {

    companion object {
        private const val TAG               = "UsbWriteThread"
        private const val HEARTBEAT_MS      = 2_000L
        private const val RECONNECT_DELAY   = 1_000L
    }

    private val running = AtomicBoolean(false)
    private val seq     = AtomicInteger(0)

    override fun run() {
        running.set(true)
        var lastHb = System.currentTimeMillis()
        Log.i(TAG, "USB write thread started")

        while (running.get()) {
            val out = usb.getOutputStream()
            if (out == null) {
                sleep(RECONNECT_DELAY)
                usb.connectToAccessory()
                continue
            }
            try {
                val encoded = encodedQueue.poll(100, TimeUnit.MILLISECONDS)
                if (encoded != null) {
                    out.write(PacketProtocol.buildPacket(
                        PacketProtocol.TYPE_AUDIO_FRAME, seq.getAndIncrement(), encoded
                    ))
                    out.flush()
                }
                val now = System.currentTimeMillis()
                if (now - lastHb >= HEARTBEAT_MS) {
                    out.write(PacketProtocol.buildHeartbeat(seq.getAndIncrement()))
                    out.flush()
                    lastHb = now
                }
            } catch (e: IOException) {
                Log.e(TAG, "USB write failed: ${e.message}")
                usb.onDisconnect()
            }
        }
        Log.i(TAG, "USB write thread stopped")
    }

    fun sendCallStart(number: String) = writeAsync(
        PacketProtocol.buildCallStart(seq.getAndIncrement(), number)
    )

    fun sendCallEnd() = writeAsync(
        PacketProtocol.buildCallEnd(seq.getAndIncrement())
    )

    private fun writeAsync(packet: ByteArray) {
        Thread {
            try {
                usb.getOutputStream()?.let { it.write(packet); it.flush() }
            } catch (e: IOException) {
                Log.e(TAG, "Async write failed: ${e.message}")
            }
        }.also { it.isDaemon = true }.start()
    }

    fun stopWriting() { running.set(false) }
}
