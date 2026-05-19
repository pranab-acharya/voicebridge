package com.voicebridge

import android.Manifest
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.PowerManager
import android.provider.Settings
import android.view.View
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import com.voicebridge.databinding.ActivityMainBinding

class MainActivity : AppCompatActivity() {

    companion object {
        private const val REQ_PERMS = 1
        private val REQUIRED = arrayOf(
            Manifest.permission.RECORD_AUDIO,
            Manifest.permission.READ_PHONE_STATE,
            Manifest.permission.CALL_PHONE,
        ).let {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O)
                it + Manifest.permission.ANSWER_PHONE_CALLS
            else it
        }
    }

    private lateinit var binding: ActivityMainBinding

    private val statusReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            if (intent.action != VoiceBridgeService.ACTION_STATUS) return
            applyStatus(
                serviceRunning = intent.getBooleanExtra("service_running", false),
                callActive     = intent.getBooleanExtra("call_active", false),
                usbConn        = intent.getBooleanExtra("usb_connected", false),
                tcpConn        = intent.getBooleanExtra("tcp_connected", false),
                number         = intent.getStringExtra("number") ?: "",
                durationSec    = intent.getLongExtra("duration_s", 0L),
                txFrames       = intent.getIntExtra("tx_frames", 0),
                txBytes        = intent.getLongExtra("tx_bytes", 0L),
            )
        }
    }

    // ── Lifecycle ──────────────────────────────────────────────────────────────

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        binding.btnToggleService.setOnClickListener { toggleService() }
        binding.btnBattery.setOnClickListener { openBatterySettings() }

        requestMissingPermissions()
        // Auto-start on first launch if not already running
        if (!VoiceBridgeService.isRunning) startVoiceBridgeService()
    }

    override fun onResume() {
        super.onResume()
        // Sync immediately from static flag — no waiting for first broadcast
        syncFromStaticFlag()
        refreshPermissionDots()

        val filter = IntentFilter(VoiceBridgeService.ACTION_STATUS)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU)
            registerReceiver(statusReceiver, filter, RECEIVER_NOT_EXPORTED)
        else
            @Suppress("UnspecifiedRegisterReceiverFlag")
            registerReceiver(statusReceiver, filter)
    }

    override fun onPause() {
        super.onPause()
        try { unregisterReceiver(statusReceiver) } catch (_: Exception) {}
    }

    // ── Toggle ─────────────────────────────────────────────────────────────────

    private fun toggleService() {
        if (VoiceBridgeService.isRunning) {
            startService(Intent(this, VoiceBridgeService::class.java).apply {
                action = VoiceBridgeService.ACTION_STOP
            })
        } else {
            startVoiceBridgeService()
        }
    }

    private fun startVoiceBridgeService() {
        val intent = Intent(this, VoiceBridgeService::class.java)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O)
            startForegroundService(intent)
        else
            startService(intent)
    }

    // ── State sync ─────────────────────────────────────────────────────────────

    private fun syncFromStaticFlag() {
        val running = VoiceBridgeService.isRunning
        binding.btnToggleService.text = if (running) "Stop Service" else "Start Service"
        setDot(binding.dotService, running)
        binding.tvServiceStatus.text = if (running) "Running" else "Stopped"
        if (!running) {
            // Clear transport dots immediately when service is known stopped
            setDot(binding.dotUsb, false)
            setDot(binding.dotTcp, false)
            binding.tvUsbStatus.text = "Disconnected"
            binding.tvTcpStatus.text = "No client"
            binding.cardCall.visibility = View.GONE
        }
    }

    private fun applyStatus(
        serviceRunning: Boolean,
        callActive: Boolean,
        usbConn: Boolean,
        tcpConn: Boolean,
        number: String,
        durationSec: Long,
        txFrames: Int,
        txBytes: Long,
    ) {
        binding.btnToggleService.text = if (serviceRunning) "Stop Service" else "Start Service"

        setDot(binding.dotService, serviceRunning)
        binding.tvServiceStatus.text = when {
            !serviceRunning -> "Stopped"
            callActive      -> "Capturing call audio"
            else            -> "Ready — waiting for call"
        }

        setDot(binding.dotUsb, usbConn)
        binding.tvUsbStatus.text = if (usbConn) "Connected" else "Disconnected"

        setDot(binding.dotTcp, tcpConn)
        binding.tvTcpStatus.text = if (tcpConn) "Laptop connected" else "No client"

        binding.cardCall.visibility = if (callActive) View.VISIBLE else View.GONE
        if (callActive) {
            binding.tvCallNumber.text = if (number.isBlank()) "Unknown" else number
            val min = durationSec / 60
            val sec = durationSec % 60
            binding.tvCallDuration.text = "$min:${sec.toString().padStart(2, '0')}"
            binding.tvStatFrames.text = txFrames.toString()
            binding.tvStatBytes.text = formatBytes(txBytes)
            val kbps = if (durationSec > 0) txBytes * 8.0 / durationSec / 1000.0 else 0.0
            binding.tvStatKbps.text = "%.1f".format(kbps)
        }
    }

    // ── Permissions ────────────────────────────────────────────────────────────

    private fun requestMissingPermissions() {
        val missing = REQUIRED.filter {
            checkSelfPermission(it) != PackageManager.PERMISSION_GRANTED
        }.toTypedArray()
        if (missing.isNotEmpty())
            ActivityCompat.requestPermissions(this, missing, REQ_PERMS)
    }

    override fun onRequestPermissionsResult(
        requestCode: Int, permissions: Array<out String>, grantResults: IntArray
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == REQ_PERMS) refreshPermissionDots()
    }

    private fun refreshPermissionDots() {
        fun granted(perm: String) = ContextCompat.checkSelfPermission(this, perm) == PackageManager.PERMISSION_GRANTED
        setDot(binding.dotPermAudio, granted(Manifest.permission.RECORD_AUDIO))
        setDot(binding.dotPermPhone, granted(Manifest.permission.READ_PHONE_STATE))
        setDot(binding.dotPermCall,  granted(Manifest.permission.CALL_PHONE))
        val pm = getSystemService(PowerManager::class.java)
        val battOk = Build.VERSION.SDK_INT < Build.VERSION_CODES.M ||
                pm.isIgnoringBatteryOptimizations(packageName)
        setDot(binding.dotPermBattery, battOk)
    }

    // ── Helpers ────────────────────────────────────────────────────────────────

    private fun openBatterySettings() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            startActivity(Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS).apply {
                data = Uri.parse("package:$packageName")
            })
        }
    }

    private fun setDot(dot: View, active: Boolean) {
        dot.background.setTint(
            ContextCompat.getColor(this, if (active) R.color.colorSuccess else R.color.colorError)
        )
    }

    private fun formatBytes(bytes: Long): String = when {
        bytes >= 1_048_576 -> "%.1f MB".format(bytes / 1_048_576.0)
        bytes >= 1_024     -> "%.1f KB".format(bytes / 1_024.0)
        else               -> "$bytes B"
    }
}
