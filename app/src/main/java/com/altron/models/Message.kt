package com.altron.models

import java.io.Serializable

enum class MessageType {
    TEXT, IMAGE, VIDEO, AUDIO, CALL, CALL_ENDED
}

enum class MessageStatus {
    SENDING, SENT, DELIVERED, READ, FAILED
}

data class Message(
    val messageId: String = "",
    val senderId: String = "",
    val receiverId: String = "",
    val content: String = "",
    val type: MessageType = MessageType.TEXT,
    val status: MessageStatus = MessageStatus.SENDING,
    val timestamp: Long = System.currentTimeMillis(),
    val isEncrypted: Boolean = true,
    val replyToMessageId: String? = null,
    val callDuration: Long? = null, // For call messages
    val callType: String? = null // "voice" or "video"
) : Serializable {
    fun toMap(): Map<String, Any> {
        val map = mutableMapOf(
            "messageId" to messageId,
            "senderId" to senderId,
            "receiverId" to receiverId,
            "content" to content,
            "type" to type.name,
            "status" to status.name,
            "timestamp" to timestamp,
            "isEncrypted" to isEncrypted,
            "replyToMessageId" to (replyToMessageId ?: "")
        )
        callDuration?.let { map["callDuration"] = it }
        callType?.let { map["callType"] = it }
        return map
    }
    
    companion object {
        fun fromMap(map: Map<String, Any>): Message {
            return Message(
                messageId = map["messageId"] as? String ?: "",
                senderId = map["senderId"] as? String ?: "",
                receiverId = map["receiverId"] as? String ?: "",
                content = map["content"] as? String ?: "",
                type = try {
                    MessageType.valueOf(map["type"] as? String ?: "TEXT")
                } catch (e: Exception) {
                    MessageType.TEXT
                },
                status = try {
                    MessageStatus.valueOf(map["status"] as? String ?: "SENDING")
                } catch (e: Exception) {
                    MessageStatus.SENDING
                },
                timestamp = map["timestamp"] as? Long ?: System.currentTimeMillis(),
                isEncrypted = map["isEncrypted"] as? Boolean ?: true,
                replyToMessageId = map["replyToMessageId"] as? String,
                callDuration = map["callDuration"] as? Long,
                callType = map["callType"] as? String
            )
        }
    }
}
