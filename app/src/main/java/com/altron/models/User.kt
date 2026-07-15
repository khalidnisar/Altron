package com.altron.models

import java.io.Serializable

data class User(
    val userId: String = "",
    val phoneNumber: String = "",
    val displayName: String = "",
    val profileImageUrl: String = "",
    val tailscaleNodeId: String = "",
    val tailscaleIp: String = "",
    val qrCode: String = "",
    val contacts: List<String> = emptyList(),
    val createdAt: Long = System.currentTimeMillis(),
    val lastSeen: Long = System.currentTimeMillis(),
    val isOnline: Boolean = false,
    val status: String = ""
) : Serializable {
    fun toMap(): Map<String, Any> {
        return mapOf(
            "userId" to userId,
            "phoneNumber" to phoneNumber,
            "displayName" to displayName,
            "profileImageUrl" to profileImageUrl,
            "tailscaleNodeId" to tailscaleNodeId,
            "tailscaleIp" to tailscaleIp,
            "qrCode" to qrCode,
            "contacts" to contacts,
            "createdAt" to createdAt,
            "lastSeen" to lastSeen,
            "isOnline" to isOnline,
            "status" to status
        )
    }
    
    companion object {
        fun fromMap(map: Map<String, Any>): User {
            return User(
                userId = map["userId"] as? String ?: "",
                phoneNumber = map["phoneNumber"] as? String ?: "",
                displayName = map["displayName"] as? String ?: "",
                profileImageUrl = map["profileImageUrl"] as? String ?: "",
                tailscaleNodeId = map["tailscaleNodeId"] as? String ?: "",
                tailscaleIp = map["tailscaleIp"] as? String ?: "",
                qrCode = map["qrCode"] as? String ?: "",
                contacts = (map["contacts"] as? List<String>) ?: emptyList(),
                createdAt = map["createdAt"] as? Long ?: System.currentTimeMillis(),
                lastSeen = map["lastSeen"] as? Long ?: System.currentTimeMillis(),
                isOnline = map["isOnline"] as? Boolean ?: false,
                status = map["status"] as? String ?: ""
            )
        }
    }
}
