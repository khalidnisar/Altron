package com.altron.chat

import android.util.Log
import com.altron.models.Message
import com.altron.models.MessageStatus
import com.altron.models.MessageType
import com.altron.network.TailscaleManager
import com.altron.utils.EncryptionUtils
import com.google.firebase.firestore.FirebaseFirestore
import com.google.firebase.firestore.Query
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.tasks.await

class ChatManager {
    
    companion object {
        private const val TAG = "ChatManager"
        private var instance: ChatManager? = null
        
        fun getInstance(): ChatManager {
            if (instance == null) {
                instance = ChatManager()
            }
            return instance!!
        }
    }
    
    private val firestore: FirebaseFirestore = FirebaseFirestore.getInstance()
    private val messagesCollection = firestore.collection("messages")
    
    // Message listeners per conversation
    private val messageListeners: MutableMap<String, MutableList<(List<Message>) -> Unit>> = mutableMapOf()
    
    fun addMessageListener(conversationId: String, listener: (List<Message>) -> Unit) {
        if (!messageListeners.containsKey(conversationId)) {
            messageListeners[conversationId] = mutableListOf()
        }
        messageListeners[conversationId]?.add(listener)
    }
    
    fun removeMessageListener(conversationId: String, listener: (List<Message>) -> Unit) {
        messageListeners[conversationId]?.remove(listener)
    }
    
    private fun notifyMessageUpdate(conversationId: String, messages: List<Message>) {
        messageListeners[conversationId]?.forEach { it(messages) }
    }
    
    fun sendMessage(
        senderId: String,
        receiverId: String,
        content: String,
        type: MessageType = MessageType.TEXT,
        callback: (Boolean, Message?) -> Unit
    ) {
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val messageId = generateMessageId()
                val timestamp = System.currentTimeMillis()
                
                // Encrypt the message content
                val encryptedContent = if (type == MessageType.TEXT) {
                    EncryptionUtils.encrypt(content)
                } else {
                    content // For media, we store the URL/path
                }
                
                val message = Message(
                    messageId = messageId,
                    senderId = senderId,
                    receiverId = receiverId,
                    content = encryptedContent,
                    type = type,
                    status = MessageStatus.SENDING,
                    timestamp = timestamp,
                    isEncrypted = true
                )
                
                // Save to Firestore
                val messageRef = messagesCollection.document(messageId)
                messageRef.set(message.toMap()).await()
                
                // Update status to SENT
                messageRef.update("status", MessageStatus.SENT.name).await()
                
                // Try to send via Tailscale for faster delivery
                sendViaTailscale(senderId, receiverId, message)
                
                callback(true, message)
                
                // Update conversation
                updateConversation(senderId, receiverId, message)
                
            } catch (e: Exception) {
                Log.e(TAG, "Failed to send message", e)
                callback(false, null)
            }
        }
    }
    
    private fun sendViaTailscale(senderId: String, receiverId: String, message: Message) {
        CoroutineScope(Dispatchers.IO).launch {
            try {
                // Get receiver's Tailscale info
                val usersCollection = firestore.collection("users")
                val receiverSnapshot = usersCollection.document(receiverId).get().await()
                
                if (receiverSnapshot.exists()) {
                    val receiverNodeId = receiverSnapshot.getString("tailscaleNodeId") ?: ""
                    
                    if (receiverNodeId.isNotEmpty() && TailscaleManager.isTailscaleConnected()) {
                        // Convert message to bytes
                        val messageBytes = EncryptionUtils.serializeMessage(message)
                        
                        // Send via Tailscale
                        TailscaleManager.sendDataToPeer(receiverNodeId, messageBytes) { success ->
                            if (success) {
                                // Update status to DELIVERED
                                messagesCollection.document(message.messageId)
                                    .update("status", MessageStatus.DELIVERED.name)
                            }
                        }
                    }
                }
            } catch (e: Exception) {
                Log.e(TAG, "Failed to send via Tailscale", e)
            }
        }
    }
    
    fun fetchMessages(senderId: String, receiverId: String, callback: (List<Message>) -> Unit) {
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val conversationId = getConversationId(senderId, receiverId)
                
                val query = messagesCollection
                    .whereIn("messageId", listOf(senderId, receiverId))
                    .whereEqualTo("senderId", senderId)
                    .whereEqualTo("receiverId", receiverId)
                    .orderBy("timestamp", Query.Direction.ASCENDING)
                    .limit(50)
                
                val results = query.get().await()
                
                val messages = results.documents.mapNotNull { doc ->
                    Message.fromMap(doc.data!!)
                }
                
                // Also get messages in reverse direction
                val reverseQuery = messagesCollection
                    .whereEqualTo("senderId", receiverId)
                    .whereEqualTo("receiverId", senderId)
                    .orderBy("timestamp", Query.Direction.ASCENDING)
                    .limit(50)
                
                val reverseResults = reverseQuery.get().await()
                val reverseMessages = reverseResults.documents.mapNotNull { doc ->
                    Message.fromMap(doc.data!!)
                }
                
                // Combine and sort by timestamp
                val allMessages = (messages + reverseMessages).sortedBy { it.timestamp }
                
                notifyMessageUpdate(conversationId, allMessages)
                callback(allMessages)
                
                // Mark messages as read
                markMessagesAsRead(receiverId, senderId)
                
            } catch (e: Exception) {
                Log.e(TAG, "Failed to fetch messages", e)
                callback(emptyList())
            }
        }
    }
    
    fun markMessagesAsRead(receiverId: String, senderId: String) {
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val query = messagesCollection
                    .whereEqualTo("receiverId", receiverId)
                    .whereEqualTo("senderId", senderId)
                    .whereEqualTo("status", MessageStatus.DELIVERED.name)
                
                val results = query.get().await()
                
                for (doc in results.documents) {
                    doc.reference.update("status", MessageStatus.READ.name).await()
                }
            } catch (e: Exception) {
                Log.e(TAG, "Failed to mark messages as read", e)
            }
        }
    }
    
    fun updateMessageStatus(messageId: String, status: MessageStatus) {
        CoroutineScope(Dispatchers.IO).launch {
            try {
                messagesCollection.document(messageId)
                    .update("status", status.name)
                    .await()
            } catch (e: Exception) {
                Log.e(TAG, "Failed to update message status", e)
            }
        }
    }
    
    fun deleteMessage(messageId: String, callback: (Boolean) -> Unit) {
        CoroutineScope(Dispatchers.IO).launch {
            try {
                messagesCollection.document(messageId).delete().await()
                callback(true)
            } catch (e: Exception) {
                Log.e(TAG, "Failed to delete message", e)
                callback(false)
            }
        }
    }
    
    fun sendCallMessage(
        callerId: String,
        receiverId: String,
        callType: String,
        duration: Long,
        isMissed: Boolean,
        callback: (Boolean) -> Unit
    ) {
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val messageId = generateMessageId()
                val timestamp = System.currentTimeMillis()
                
                val message = Message(
                    messageId = messageId,
                    senderId = callerId,
                    receiverId = receiverId,
                    content = if (isMissed) "Missed $callType call" else "$callType call",
                    type = if (isMissed) MessageType.CALL else MessageType.CALL_ENDED,
                    status = MessageStatus.SENT,
                    timestamp = timestamp,
                    isEncrypted = false,
                    callDuration = if (!isMissed) duration else null,
                    callType = callType
                )
                
                messagesCollection.document(messageId).set(message.toMap()).await()
                
                callback(true)
                
                // Update conversation
                updateConversation(callerId, receiverId, message)
                
            } catch (e: Exception) {
                Log.e(TAG, "Failed to send call message", e)
                callback(false)
            }
        }
    }
    
    private fun updateConversation(senderId: String, receiverId: String, message: Message) {
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val conversationId = getConversationId(senderId, receiverId)
                val conversationsCollection = firestore.collection("conversations")
                
                val conversationData = mapOf(
                    "conversationId" to conversationId,
                    "participants" to listOf(senderId, receiverId),
                    "lastMessage" to message.content,
                    "lastMessageTimestamp" to message.timestamp,
                    "lastMessageType" to message.type.name,
                    "lastMessageSenderId" to message.senderId,
                    "unreadCount" to 0
                )
                
                conversationsCollection.document(conversationId)
                    .set(conversationData)
                    .await()
                
            } catch (e: Exception) {
                Log.e(TAG, "Failed to update conversation", e)
            }
        }
    }
    
    private fun getConversationId(userId1: String, userId2: String): String {
        return if (userId1 < userId2) "$userId1-$userId2" else "$userId2-$userId1"
    }
    
    private fun generateMessageId(): String {
        return "msg_${System.currentTimeMillis()}_${(Math.random() * 1000).toInt()}"
    }
    
    // Start listening to new messages in real-time
    fun startListeningToMessages(senderId: String, receiverId: String) {
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val conversationId = getConversationId(senderId, receiverId)
                
                // Listen for new messages from sender to receiver
                messagesCollection
                    .whereEqualTo("senderId", senderId)
                    .whereEqualTo("receiverId", receiverId)
                    .addSnapshotListener { snapshot, error ->
                        if (error != null) {
                            Log.e(TAG, "Error listening to messages", error)
                            return@addSnapshotListener
                        }
                        
                        if (snapshot != null) {
                            val messages = snapshot.documents.mapNotNull { doc ->
                                Message.fromMap(doc.data!!)
                            }
                            notifyMessageUpdate(conversationId, messages)
                        }
                    }
                
                // Listen for new messages from receiver to sender
                messagesCollection
                    .whereEqualTo("senderId", receiverId)
                    .whereEqualTo("receiverId", senderId)
                    .addSnapshotListener { snapshot, error ->
                        if (error != null) {
                            Log.e(TAG, "Error listening to messages", error)
                            return@addSnapshotListener
                        }
                        
                        if (snapshot != null) {
                            val messages = snapshot.documents.mapNotNull { doc ->
                                Message.fromMap(doc.data!!)
                            }
                            notifyMessageUpdate(conversationId, messages)
                        }
                    }
                
            } catch (e: Exception) {
                Log.e(TAG, "Failed to start listening to messages", e)
            }
        }
    }
    
    fun stopListeningToMessages(conversationId: String) {
        // Remove listeners
        messageListeners.remove(conversationId)
    }
}
