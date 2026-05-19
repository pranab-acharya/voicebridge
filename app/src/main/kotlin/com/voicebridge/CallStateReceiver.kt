package com.voicebridge

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.telephony.TelephonyManager
import android.util.Log

class CallStateReceiver(
    private val onCallStarted: (String) -> Unit,
    private val onCallEnded:   () -> Unit,
    private val onCallHeld:    () -> Unit
) : BroadcastReceiver() {

    companion object { private const val TAG = "CallStateReceiver" }

    private var prevState = TelephonyManager.CALL_STATE_IDLE

    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != TelephonyManager.ACTION_PHONE_STATE_CHANGED) return

        val stateStr = intent.getStringExtra(TelephonyManager.EXTRA_STATE) ?: return
        // EXTRA_INCOMING_NUMBER deprecated in API 29; no public replacement for broadcast receivers
        @Suppress("DEPRECATION")
        val number = intent.getStringExtra(TelephonyManager.EXTRA_INCOMING_NUMBER) ?: ""

        val state = when (stateStr) {
            TelephonyManager.EXTRA_STATE_RINGING  -> TelephonyManager.CALL_STATE_RINGING
            TelephonyManager.EXTRA_STATE_OFFHOOK  -> TelephonyManager.CALL_STATE_OFFHOOK
            else                                  -> TelephonyManager.CALL_STATE_IDLE
        }

        Log.d(TAG, "state=$stateStr  prev=$prevState  number=$number")

        when {
            state == TelephonyManager.CALL_STATE_OFFHOOK
                    && prevState != TelephonyManager.CALL_STATE_OFFHOOK -> onCallStarted(number)

            state == TelephonyManager.CALL_STATE_IDLE
                    && prevState != TelephonyManager.CALL_STATE_IDLE    -> onCallEnded()

            // Incoming call-waiting while on a call → hold
            state == TelephonyManager.CALL_STATE_RINGING
                    && prevState == TelephonyManager.CALL_STATE_OFFHOOK -> onCallHeld()
        }

        prevState = state
    }
}
