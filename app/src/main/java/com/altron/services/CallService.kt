package com.altron.services

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.media.AudioManager
import android.os.Build
import android.os.IBinder
import android.util.Log
import androidx.core.app.NotificationCompat
import com.altron.AltronApp
import com.altron.R
import com.altron.calls.CallManager
import com.altron.models.Call
import com.altron.models.CallStatus
import com.altron.ui.activities.CallActivity

class CallService : Service() {
    
    companion object {
        private const val TAG = "CallService"
        private const val NOTIFICATION_CHANNEL_ID = "call_channel"
        private const val NOTIFICATION_ID = 1001
        private const val ACTION_START_CALL = "start_call"
        private const val ACTION_END_CALL = "end_call"
        
        private var isRunning = false
        
        fun start(context: Context) {
            if (!isRunning) {
                val intent = Intent(context, CallService::class.java)
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                    context.startForegroundService(intent)
                } else {
                    context.startService(intent)
                }
                isRunning = true
            }
        }
        
        fun stop(context: Context) {
            val intent = Intent(context, CallService::class.java)
            context.stopService(intent)
            isRunning = false
        }
    }
    
    private lateinit var callManager: CallManager
    private lateinit var audioManager: AudioManager
    private lateinit var notificationManager: NotificationManager
    
    override fun onCreate() {
        super.onCreate()
        Log.d(TAG, "CallService created")
        
        callManager = CallManager.getInstance(this)
        audioManager = getSystemService(AUDIO_SERVICE) as AudioManager
        notificationManager = getSystemService(NOTIFICATION_SERVICE) as NotificationManager
        
        createNotificationChannel()
        
        // Set up call state listener
        callManager.addCallStateCallback { call ->
            handleCallStateChange(call)
        }
    }
    
    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        Log.d(TAG, "CallService started")
        
        intent?.let { handleIntent(it) }
        
        // Start as foreground service
        startForeground(NOTIFICATION_ID, createNotification())
        
        return START_STICKY
    }
    
    private fun handleIntent(intent: Intent) {
        when (intent.action) {
            ACTION_START_CALL -> {
                val callerId = intent.getStringExtra("callerId") ?: ""
                val receiverId = intent.getStringExtra("receiverId") ?: ""
                val callType = intent.getStringExtra("callType") ?: "VOICE"
                
                // Start call
                com.altron.models.CallType.values().firstOrNull { it.name == callType }?.let { type ->
                    callManager.startCall(callerId, receiverId, type) { success, call ->
                        if (success) {
                            showCallNotification(call!!)
                        }
                    }
                }
            }
            ACTION_END_CALL -> {
                val callId = intent.getStringExtra("callId") ?: ""
                callManager.endCall(callId) { success ->
                    if (success) {
                        updateNotification("Call ended")
                    }
                }
            }
        }
    }
    
    private fun handleCallStateChange(call: Call) {
        when (call.status) {
            CallStatus.RINGING -> {
                showCallNotification(call)
                // Play ringing tone
                playRingingTone()
            }
            CallStatus.CONNECTED -> {
                updateNotification("Call connected")
                stopRingingTone()
            }
            CallStatus.DISCONNECTED -> {
                updateNotification("Call ended")
                stopRingingTone()
                // Remove notification after a delay
                android.os.Handler(mainLooper).postDelayed({
                    notificationManager.cancel(NOTIFICATION_ID)
                }, 3000)
            }
            CallStatus.MISSED -> {
                showMissedCallNotification(call)
                stopRingingTone()
            }
            CallStatus.REJECTED -> {
                updateNotification("Call rejected")
                stopRingingTone()
                android.os.Handler(mainLooper).postDelayed({
                    notificationManager.cancel(NOTIFICATION_ID)
                }, 3000)
            }
        }
    }
    
    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                NOTIFICATION_CHANNEL_ID,
                "Call Notifications",
                NotificationManager.IMPORTANCE_HIGH
            ).apply {
                description = "Notifications for incoming and outgoing calls"
                setSound(null, null) // We'll handle call sounds separately
                enableVibration(true)
            }
            
            notificationManager.createNotificationChannel(channel)
        }
    }
    
    private fun createNotification(): Notification {
        return NotificationCompat.Builder(this, NOTIFICATION_CHANNEL_ID)
            .setContentTitle("Altron Call Service")
            .setContentText("Call service is running")
            .setSmallIcon(R.mipmap.ic_launcher)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .build()
    }
    
    private fun showCallNotification(call: Call) {
        val intent = Intent(this, CallActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK
            putExtra("callId", call.callId)
            putExtra("isIncoming", call.isIncoming)
        }
        
        val pendingIntent = PendingIntent.getActivity(
            this, 
            0, 
            intent, 
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        
        val notification = NotificationCompat.Builder(this, NOTIFICATION_CHANNEL_ID)
            .setContentTitle(if (call.isIncoming) "Incoming Call" else "Outgoing Call")
            .setContentText(if (call.isIncoming) "${call.callerId} is calling" else "Calling ${call.receiverId}")
            .setSmallIcon(R.mipmap.ic_launcher)
            .setPriority(NotificationCompat.PRIORITY_MAX)
            .setFullScreenIntent(pendingIntent, true)
            .setAutoCancel(false)
            .setOngoing(true)
            .addAction(R.mipmap.ic_launcher, "Answer", pendingIntent)
            .build()
        
        notificationManager.notify(NOTIFICATION_ID, notification)
    }
    
    private fun showMissedCallNotification(call: Call) {
        val intent = Intent(this, CallActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK
            putExtra("callId", call.callId)
            putExtra("isMissed", true)
        }
        
        val pendingIntent = PendingIntent.getActivity(
            this, 
            0, 
            intent, 
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        
        val notification = NotificationCompat.Builder(this, NOTIFICATION_CHANNEL_ID)
            .setContentTitle("Missed Call")
            .setContentText("Missed call from ${call.callerId}")
            .setSmallIcon(R.mipmap.ic_launcher)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setContentIntent(pendingIntent)
            .setAutoCancel(true)
            .build()
        
        notificationManager.notify(NOTIFICATION_ID + 1, notification)
    }
    
    private fun updateNotification(text: String) {
        val notification = NotificationCompat.Builder(this, NOTIFICATION_CHANNEL_ID)
            .setContentTitle("Altron Call")
            .setContentText(text)
            .setSmallIcon(R.mipmap.ic_launcher)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setOngoing(true)
            .build()
        
        notificationManager.notify(NOTIFICATION_ID, notification)
    }
    
    private fun playRingingTone() {
        try {
            audioManager.mode = AudioManager.MODE_RINGTONE
            audioManager.isSpeakerphoneOn = true
            // In a real app, you would play a ringing tone here
        } catch (e: Exception) {
            Log.e(TAG, "Failed to play ringing tone", e)
        }
    }
    
    private fun stopRingingTone() {
        try {
            audioManager.mode = AudioManager.MODE_NORMAL
            // Stop any ringing tone
        } catch (e: Exception) {
            Log.e(TAG, "Failed to stop ringing tone", e)
        }
    }
    
    override fun onDestroy() {
        super.onDestroy()
        Log.d(TAG, "CallService destroyed")
        
        // Clean up
        callManager.cleanup()
        isRunning = false
    }
    
    override fun onBind(intent: Intent?): IBinder? {
        return null
    }
}
