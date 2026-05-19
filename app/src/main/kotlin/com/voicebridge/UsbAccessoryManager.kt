package com.voicebridge

import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.hardware.usb.UsbAccessory
import android.hardware.usb.UsbManager
import android.os.ParcelFileDescriptor
import android.util.Log
import java.io.FileInputStream
import java.io.FileOutputStream
import java.io.IOException

class UsbAccessoryManager(private val ctx: Context) {

    companion object {
        private const val TAG              = "UsbAccessoryManager"
        private const val ACTION_PERMISSION = "com.voicebridge.USB_PERMISSION"
    }

    private val usbManager = ctx.getSystemService(Context.USB_SERVICE) as UsbManager
    private var pfd: ParcelFileDescriptor? = null
    private var output: FileOutputStream? = null
    private var input:  FileInputStream?  = null
    private var controlCb: ((ControlCommand) -> Unit)? = null

    private val permReceiver = object : BroadcastReceiver() {
        override fun onReceive(c: Context, intent: Intent) {
            if (intent.action != ACTION_PERMISSION) return
            val granted = intent.getBooleanExtra(UsbManager.EXTRA_PERMISSION_GRANTED, false)
            val acc     = intent.getParcelableExtra<UsbAccessory>(UsbManager.EXTRA_ACCESSORY)
            if (granted && acc != null) openAccessory(acc)
            else Log.w(TAG, "USB permission denied")
        }
    }

    fun initialize(onControl: (ControlCommand) -> Unit) {
        controlCb = onControl
        ctx.registerReceiver(
            permReceiver,
            IntentFilter(ACTION_PERMISSION),
            Context.RECEIVER_NOT_EXPORTED
        )
        connectToAccessory()
    }

    fun connectToAccessory() {
        val list = usbManager.accessoryList
        if (list.isNullOrEmpty()) { Log.i(TAG, "No USB accessory attached"); return }
        val acc = list[0]
        if (usbManager.hasPermission(acc)) openAccessory(acc)
        else {
            val pi = PendingIntent.getBroadcast(
                ctx, 0, Intent(ACTION_PERMISSION), PendingIntent.FLAG_IMMUTABLE
            )
            usbManager.requestPermission(acc, pi)
        }
    }

    private fun openAccessory(acc: UsbAccessory) {
        pfd = usbManager.openAccessory(acc) ?: run {
            Log.e(TAG, "openAccessory returned null"); return
        }
        output = FileOutputStream(pfd!!.fileDescriptor)
        input  = FileInputStream(pfd!!.fileDescriptor)
        Log.i(TAG, "USB accessory open: ${acc.manufacturer} / ${acc.model}")
        launchControlReader()
    }

    private fun launchControlReader() {
        // Thread(String, Runnable) is Java 19+; use Thread(group, runnable, name) instead
        Thread(null, {
            val buf = ByteArray(512)
            while (true) {
                try {
                    val n = input?.read(buf) ?: break
                    if (n <= 0) continue
                    PacketProtocol.parseControlPacket(buf.copyOf(n))
                        ?.let { controlCb?.invoke(it) }
                } catch (e: IOException) {
                    Log.w(TAG, "Control reader closed: ${e.message}")
                    break
                }
            }
        }, "UsbControlReader").also { it.isDaemon = true }.start()
    }

    fun getOutputStream(): FileOutputStream? = output

    fun onDisconnect() {
        output = null
        input  = null
        try { pfd?.close() } catch (_: Exception) {}
        pfd = null
        Log.i(TAG, "USB accessory disconnected")
    }

    fun release() {
        onDisconnect()
        try { ctx.unregisterReceiver(permReceiver) } catch (_: Exception) {}
    }
}
