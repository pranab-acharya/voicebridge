package com.voicebridge

import android.util.Log
import java.io.IOException
import java.io.OutputStream
import java.net.ServerSocket
import java.net.Socket
import java.util.concurrent.LinkedBlockingQueue
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicInteger

/**
 * TCP server that mirrors the AOAv2 packet stream for ADB-forward testing.
 *
 * On the laptop:  adb forward tcp:7654 tcp:7654
 * Then run:       python voicebridge.py --transport tcp
 */
class DebugTcpServer(
    private val port: Int = 7654,
    private val encodedQueue: LinkedBlockingQueue<ByteArray>,
) : Thread("DebugTcpServer") {

    companion object {
        private const val TAG = "DebugTcpServer"
        private const val HEARTBEAT_MS = 2_000L
    }

    private val running     = AtomicBoolean(false)
    private val seq         = AtomicInteger(0)
    private var serverSocket: ServerSocket? = null
    private var activeStream: OutputStream? = null

    override fun run() {
        running.set(true)
        try {
            serverSocket = ServerSocket(port)
            Log.i(TAG, "TCP debug server listening on port $port")

            while (running.get()) {
                val client: Socket = try {
                    serverSocket!!.accept()
                } catch (e: IOException) {
                    if (running.get()) Log.e(TAG, "Accept error: ${e.message}")
                    break
                }
                Log.i(TAG, "Laptop connected: ${client.inetAddress}")
                serveClient(client)
                Log.i(TAG, "Laptop disconnected")
            }
        } catch (e: Exception) {
            Log.e(TAG, "Server error: ${e.message}")
        }
    }

    private fun serveClient(client: Socket) {
        val out = client.getOutputStream()
        activeStream = out
        var lastHb = System.currentTimeMillis()

        while (running.get() && !client.isClosed) {
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
                Log.w(TAG, "Client write error: ${e.message}")
                break
            }
        }
        activeStream = null
        try { client.close() } catch (_: Exception) {}
    }

    /** Send a pre-built packet (CALL_START / CALL_END) directly to the connected laptop. */
    fun sendPacket(packet: ByteArray) {
        try { activeStream?.let { it.write(packet); it.flush() } } catch (_: IOException) {}
    }

    fun stopServer() {
        running.set(false)
        try { serverSocket?.close() } catch (_: IOException) {}
    }
}
