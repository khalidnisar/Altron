package com.altron.models

import java.io.Serializable

enum class CallStatus {
    RINGING, CONNECTED, DISCONNECTED, MISSED, REJECTED
}

enum class CallType {
    VOICE, VIDEO
}

data class Call(
    val callId: String = "",
    val callerId: String = "",
    val receiverId: String = "",
    val callType: CallType = CallType.VOICE,
    val status: CallStatus = CallStatus.RINGING,
    val startTime: Long = System.currentTimeMillis(),
    val endTime: Long? = null,
    val duration: Long? = null,
    val isIncoming: Boolean = false,
    val tailscaleIp: String = "",
    val peerConnectionId: String = ""
) : Serializable {
    fun toMap(): Map<String, Any> {
        val map = mutableMapOf(
            "callId" to callId,
            "callerId" to callerId,
            "receiverId" to receiverId,
            "callType" to callType.name,
            "status" to status.name,
            "startTime" to startTime,
            "isIncoming" to isIncoming,
            "tailscaleIp" to tailscaleIp,
            "peerConnectionId" to peerConnectionId
        )
        endTime?.let { map["endTime"] = it }
        duration?.let { map["duration"] = it }
        return map
    }
    
    companion object {
        fun fromMap(map: Map<String, Any>): Call {
            return Call(
                callId = map["callId"] as? String ?: "",
                callerId = map["callerId"] as? String ?: "",
                receiverId = map["receiverId"] as? String ?: "",
                callType = try {
                    CallType.valueOf(map["callType"] as? String ?: "VOICE")
                } catch (e: Exception) {
                    CallType.VOICE
                },
                status = try {
                    CallStatus.valueOf(map["status"] as? String ?: "RINGING")
                } catch (e: Exception) {
                    CallStatus.RINGING
                },
                startTime = map["startTime"] as? Long ?: System.currentTimeMillis(),
                endTime = map["endTime"] as? Long,
                duration = map["duration"] as? Long,
                isIncoming = map["isIncoming"] as? Boolean ?: false,
                tailscaleIp = map["tailscaleIp"] as? String ?: "",
                peerConnectionId = map["peerConnectionId"] as? String ?: ""
            )
        }
    }
}
