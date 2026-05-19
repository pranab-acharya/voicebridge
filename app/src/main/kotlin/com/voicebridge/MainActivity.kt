package com.voicebridge

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.PowerManager
import android.provider.Settings
import android.widget.Button
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat

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

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        requestMissingPermissions()
        requestBatteryExemption()
        startService()

        findViewById<Button>(R.id.btnStartService).setOnClickListener { startService() }
    }

    private fun requestMissingPermissions() {
        val missing = REQUIRED.filter {
            checkSelfPermission(it) != PackageManager.PERMISSION_GRANTED
        }.toTypedArray()
        if (missing.isNotEmpty())
            ActivityCompat.requestPermissions(this, missing, REQ_PERMS)
    }

    private fun requestBatteryExemption() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            val pm = getSystemService(PowerManager::class.java)
            if (!pm.isIgnoringBatteryOptimizations(packageName)) {
                startActivity(Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS).apply {
                    data = Uri.parse("package:$packageName")
                })
            }
        }
    }

    private fun startService() {
        val intent = Intent(this, VoiceBridgeService::class.java)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O)
            startForegroundService(intent)
        else
            startService(intent)
        findViewById<TextView>(R.id.tvStatus).text =
            "Service running — connect USB cable to laptop"
    }

    override fun onRequestPermissionsResult(
        requestCode: Int, permissions: Array<out String>, grantResults: IntArray
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == REQ_PERMS) {
            val denied = permissions.zip(grantResults.toList())
                .filter { it.second != PackageManager.PERMISSION_GRANTED }
                .map { it.first }
            if (denied.isNotEmpty())
                findViewById<TextView>(R.id.tvStatus).text =
                    "Missing permissions: ${denied.joinToString { it.substringAfterLast('.') }}"
        }
    }
}
