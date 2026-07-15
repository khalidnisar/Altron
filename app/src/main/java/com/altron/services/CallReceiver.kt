package com.altron.services

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.telephony.TelephonyManager
import android.util.Log

class CallReceiver : BroadcastReceiver() {
    
    companion object {
        private const val TAG = "CallReceiver"
    }
    
    override fun onReceive(context: Context, intent: Intent) {
        when (intent.action) {
            TelephonyManager.ACTION_PHONE_STATE_CHANGED -> {
                handlePhoneStateChange(context, intent)
            }
        }
    }
    
    private fun handlePhoneStateChange(context: Context, intent: Intent) {
        try {
            val state = intent.getStringExtra(TelephonyManager.EXTRA_STATE)
            val phoneNumber = intent.getStringExtra(TelephonyManager.EXTRA_INCOMING_NUMBER)
            
            when (state) {
                TelephonyManager.EXTRA_STATE_RINGING -> {
                    Log.d(TAG, "Phone ringing: $phoneNumber")
                    // Handle incoming phone call
                    // You could check if this is an Altron user and show notification
                }
                TelephonyManager.EXTRA_STATE_OFFHOOK -> {
                    Log.d(TAG, "Phone offhook")
                    // Handle call started
                }
                TelephonyManager.EXTRA_STATE_IDLE -> {
                    Log.d(TAG, "Phone idle")
                    // Handle call ended
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error handling phone state change", e)
        }
    }
}
