package com.voicebridge

import android.app.*
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.net.Uri
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.os.PowerManager
import android.telecom.TelecomManager
import android.telephony.TelephonyManager
import android.util.Log
import androidx.core.app.NotificationCompat
import java.util.concurrent.LinkedBlockingQueue
import java.util.concurrent.atomic.AtomicInteger
import java.util.concurrent.atomic.AtomicLong

class VoiceBridgeService : Service() {

    companion object {
        private const val TAG         = "VoiceBridgeService"
        private const val CH_ID       = "voicebridge_service"
        private const val NOTIF_ID    = 1
        private const val SAMPLE_RATE = 16_000
        private const val BITRATE     = 16_000
        private const val COMPLEXITY  = 3

        const val ACTION_STATUS = "com.voicebridge.STATUS"
        const val ACTION_STOP   = "com.voicebridge.STOP"

        // Static flag so MainActivity can read state instantly on resume
        @Volatile var isRunning = false
    }

    private val txFrames = AtomicInteger(0)
    private val txBytes  = AtomicLong(0L)
    private var callStartMs      = 0L
    private var activeCallNumber = ""

    private val encodedQueue = object : LinkedBlockingQueue<ByteArray>(256) {
        override fun offer(e: ByteArray): Boolean {
            val accepted = super.offer(e)
            if (accepted) {
                txFrames.incrementAndGet()
                txBytes.addAndGet(e.size.toLong())
            }
            return accepted
        }
    }

    private var captureThread:  AudioCaptureThread?  = null
    private var encoderThread:  OpusEncoderThread?   = null
    private var usbWriteThread: UsbWriteThread?      = null
    private var usbManager:     UsbAccessoryManager? = null
    private var tcpServer:      DebugTcpServer?      = null
    private var callReceiver:   CallStateReceiver?   = null
    private var wakeLock:       PowerManager.WakeLock? = null

    private var capturing = false

    private val statusHandler = Handler(Looper.getMainLooper())
    private val statusTick = object : Runnable {
        override fun run() {
            broadcastStatus(running = true)
            statusHandler.postDelayed(this, 1_000L)
        }
    }

    // ── Lifecycle ──────────────────────────────────────────────────────────────

    override fun onCreate() {
        super.onCreate()
        isRunning = true
        createNotificationChannel()
        NativeBridge.initRingBuffer()

        val pm = getSystemService(Context.POWER_SERVICE) as PowerManager
        wakeLock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "VoiceBridge::WakeLock")

        setupUsb()
        if (BuildConfig.DEBUG) startTcpServer()
        registerCallReceiver()

        statusHandler.post(statusTick)
        Log.i(TAG, "Service created")
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            stopForeground(STOP_FOREGROUND_REMOVE)
            stopSelf()
            return START_NOT_STICKY
        }
        startForeground(NOTIF_ID, buildNotification("Ready — waiting for call"))
        return START_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onDestroy() {
        isRunning = false
        statusHandler.removeCallbacks(statusTick)
        // Send a final broadcast so the UI reacts immediately
        broadcastStatus(running = false)
        stopCapture()
        usbWriteThread?.stopWriting()
        usbManager?.release()
        tcpServer?.stopServer()
        callReceiver?.let { try { unregisterReceiver(it) } catch (_: Exception) {} }
        wakeLock?.let { if (it.isHeld) it.release() }
        NativeBridge.destroyEncoder()
        Log.i(TAG, "Service destroyed")
        super.onDestroy()
    }

    // ── Status broadcast ───────────────────────────────────────────────────────

    private fun broadcastStatus(running: Boolean) {
        val durationSec = if (capturing && callStartMs > 0)
            (System.currentTimeMillis() - callStartMs) / 1000L else 0L

        sendBroadcast(Intent(ACTION_STATUS).apply {
            putExtra("service_running", running)
            putExtra("call_active",     capturing)
            putExtra("number",          activeCallNumber)
            putExtra("duration_s",      durationSec)
            putExtra("tx_frames",       txFrames.get())
            putExtra("tx_bytes",        txBytes.get())
            putExtra("usb_connected",   usbManager?.isConnected ?: false)
            putExtra("tcp_connected",   tcpServer?.hasClient ?: false)
        })
    }

    // ── TCP debug server ───────────────────────────────────────────────────────

    private fun startTcpServer() {
        tcpServer = DebugTcpServer(port = 7654, encodedQueue = encodedQueue).also { it.start() }
        Log.i(TAG, "TCP debug server started on port 7654")
    }

    // ── Setup ──────────────────────────────────────────────────────────────────

    private fun setupUsb() {
        usbManager = UsbAccessoryManager(this).apply {
            initialize { cmd ->
                when (cmd) {
                    is ControlCommand.Dial   -> dialNumber(cmd.number)
                    is ControlCommand.Hangup -> hangup()
                }
            }
        }
        usbWriteThread = UsbWriteThread(encodedQueue, usbManager!!).also { it.start() }
    }

    private fun registerCallReceiver() {
        callReceiver = CallStateReceiver(
            onCallStarted = { number -> startCapture(number) },
            onCallEnded   = {
                stopCapture()
                usbWriteThread?.sendCallEnd()
                tcpServer?.sendPacket(PacketProtocol.buildCallEnd(0))
            },
            onCallHeld    = { pauseCapture() }
        )
        registerReceiver(callReceiver, IntentFilter(TelephonyManager.ACTION_PHONE_STATE_CHANGED))
    }

    // ── Capture control ────────────────────────────────────────────────────────

    private fun startCapture(number: String) {
        if (capturing) return
        if (!NativeBridge.initEncoder(SAMPLE_RATE, BITRATE, COMPLEXITY)) {
            Log.e(TAG, "initEncoder failed"); return
        }
        txFrames.set(0)
        txBytes.set(0L)
        callStartMs = System.currentTimeMillis()
        activeCallNumber = number

        usbWriteThread?.sendCallStart(number)
        tcpServer?.sendPacket(PacketProtocol.buildCallStart(0, number))

        captureThread = AudioCaptureThread {
            Log.w(TAG, "Ring buffer overflow — frame dropped")
        }.also { it.start() }
        encoderThread = OpusEncoderThread(encodedQueue).also { it.start() }

        capturing = true
        wakeLock?.acquire(4 * 60 * 60 * 1000L)
        notify("Capturing call${if (number.isNotBlank()) " — $number" else ""}")
        Log.i(TAG, "Capture started (number=$number)")
    }

    private fun stopCapture() {
        if (!capturing) return
        captureThread?.stopCapture()
        encoderThread?.stopEncoding()
        captureThread = null
        encoderThread = null
        NativeBridge.destroyEncoder()
        capturing = false
        callStartMs = 0L
        activeCallNumber = ""
        if (wakeLock?.isHeld == true) wakeLock?.release()
        notify("Ready — waiting for call")
        Log.i(TAG, "Capture stopped")
    }

    private fun pauseCapture() {
        captureThread?.stopCapture()
        captureThread = null
        Log.i(TAG, "Capture paused (call held / call-waiting)")
    }

    // ── Telephony ──────────────────────────────────────────────────────────────

    private fun dialNumber(number: String) {
        startActivity(Intent(Intent.ACTION_CALL, Uri.parse("tel:$number")).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK
        })
    }

    private fun hangup() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            @Suppress("DEPRECATION")
            (getSystemService(Context.TELECOM_SERVICE) as TelecomManager).endCall()
        }
    }

    // ── Notifications ──────────────────────────────────────────────────────────

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val ch = NotificationChannel(
                CH_ID, "VoiceBridge Service", NotificationManager.IMPORTANCE_LOW
            ).apply { description = "Foreground audio streaming service" }
            getSystemService(NotificationManager::class.java).createNotificationChannel(ch)
        }
    }

    private fun buildNotification(text: String): Notification {
        val pi = PendingIntent.getActivity(
            this, 0, Intent(this, MainActivity::class.java), PendingIntent.FLAG_IMMUTABLE
        )
        return NotificationCompat.Builder(this, CH_ID)
            .setContentTitle("VoiceBridge")
            .setContentText(text)
            .setSmallIcon(android.R.drawable.ic_btn_speak_now)
            .setContentIntent(pi)
            .setOngoing(true)
            .build()
    }

    private fun notify(text: String) {
        getSystemService(NotificationManager::class.java)
            .notify(NOTIF_ID, buildNotification(text))
    }
}
