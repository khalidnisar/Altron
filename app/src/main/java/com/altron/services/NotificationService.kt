package com.altron.services

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.os.Build
import androidx.core.app.NotificationCompat
import com.altron.R
import com.altron.models.Message
import com.altron.models.MessageType
import com.altron.ui.activities.ChatActivity
import com.altron.ui.activities.MainActivity

class NotificationService(private val context: Context) {
    
    companion object {
        private const val MESSAGE_CHANNEL_ID = "message_channel"
        private const val CALL_CHANNEL_ID = "call_channel"
        private const val GENERAL_CHANNEL_ID = "general_channel"
        
        private var instance: NotificationService? = null
        
        fun getInstance(context: Context): NotificationService {
            if (instance == null) {
                instance = NotificationService(context)
            }
            return instance!!
        }
    }
    
    private val notificationManager: NotificationManager by lazy {
        context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
    }
    
    init {
        createNotificationChannels()
    }
    
    private fun createNotificationChannels() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            // Message channel
            val messageChannel = NotificationChannel(
                MESSAGE_CHANNEL_ID,
                "Messages",
                NotificationManager.IMPORTANCE_HIGH
            ).apply {
                description = "New message notifications"
                enableLights(true)
                enableVibration(true)
            }
            
            // Call channel
            val callChannel = NotificationChannel(
                CALL_CHANNEL_ID,
                "Calls",
                NotificationManager.IMPORTANCE_MAX
            ).apply {
                description = "Call notifications"
                enableLights(true)
                enableVibration(true)
                setSound(null, null) // Handle call sounds separately
            }
            
            // General channel
            val generalChannel = NotificationChannel(
                GENERAL_CHANNEL_ID,
                "General",
                NotificationManager.IMPORTANCE_DEFAULT
            ).apply {
                description = "General notifications"
            }
            
            notificationManager.createNotificationChannel(messageChannel)
            notificationManager.createNotificationChannel(callChannel)
            notificationManager.createNotificationChannel(generalChannel)
        }
    }
    
    fun showMessageNotification(message: Message, senderName: String) {
        val intent = Intent(context, ChatActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK
            putExtra("receiverId", message.senderId)
            putExtra("receiverName", senderName)
        }
        
        val pendingIntent = PendingIntent.getActivity(
            context, 
            message.messageId.hashCode(), 
            intent, 
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        
        val notificationId = message.messageId.hashCode()
        
        val notification = NotificationCompat.Builder(context, MESSAGE_CHANNEL_ID)
            .setContentTitle(senderName)
            .setContentText(getMessageContent(message))
            .setSmallIcon(R.mipmap.ic_launcher)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setContentIntent(pendingIntent)
            .setAutoCancel(true)
            .setShowWhen(true)
            .build()
        
        notificationManager.notify(notificationId, notification)
    }
    
    fun showNewContactNotification(contactName: String) {
        val intent = Intent(context, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK
        }
        
        val pendingIntent = PendingIntent.getActivity(
            context, 
            0, 
            intent, 
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        
        val notification = NotificationCompat.Builder(context, GENERAL_CHANNEL_ID)
            .setContentTitle("New Contact")
            .setContentText("$contactName added you as a contact")
            .setSmallIcon(R.mipmap.ic_launcher)
            .setPriority(NotificationCompat.PRIORITY_DEFAULT)
            .setContentIntent(pendingIntent)
            .setAutoCancel(true)
            .build()
        
        notificationManager.notify(System.currentTimeMillis().toInt(), notification)
    }
    
    fun showMissedCallNotification(callerName: String, callId: String) {
        val intent = Intent(context, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK
        }
        
        val pendingIntent = PendingIntent.getActivity(
            context, 
            callId.hashCode(), 
            intent, 
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        
        val notification = NotificationCompat.Builder(context, CALL_CHANNEL_ID)
            .setContentTitle("Missed Call")
            .setContentText("Missed call from $callerName")
            .setSmallIcon(R.mipmap.ic_launcher)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setContentIntent(pendingIntent)
            .setAutoCancel(true)
            .build()
        
        notificationManager.notify(callId.hashCode(), notification)
    }
    
    fun showIncomingCallNotification(callerName: String, callId: String) {
        val intent = Intent(context, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK
            putExtra("callId", callId)
            putExtra("isIncoming", true)
        }
        
        val pendingIntent = PendingIntent.getActivity(
            context, 
            callId.hashCode(), 
            intent, 
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        
        val notification = NotificationCompat.Builder(context, CALL_CHANNEL_ID)
            .setContentTitle("Incoming Call")
            .setContentText("$callerName is calling")
            .setSmallIcon(R.mipmap.ic_launcher)
            .setPriority(NotificationCompat.PRIORITY_MAX)
            .setFullScreenIntent(pendingIntent, true)
            .setAutoCancel(false)
            .setOngoing(true)
            .addAction(R.mipmap.ic_launcher, "Answer", pendingIntent)
            .build()
        
        notificationManager.notify(callId.hashCode(), notification)
    }
    
    fun cancelNotification(notificationId: Int) {
        notificationManager.cancel(notificationId)
    }
    
    fun cancelAllNotifications() {
        notificationManager.cancelAll()
    }
    
    private fun getMessageContent(message: Message): String {
        return when (message.type) {
            MessageType.TEXT -> message.content
            MessageType.IMAGE -> "📷 Photo"
            MessageType.VIDEO -> "🎥 Video"
            MessageType.AUDIO -> "🎵 Audio"
            MessageType.CALL -> "📞 Call"
            MessageType.CALL_ENDED -> "📞 Call ended"
        }
    }
}
