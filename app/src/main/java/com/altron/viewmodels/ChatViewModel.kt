package com.altron.viewmodels

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.LiveData
import androidx.lifecycle.MutableLiveData
import com.altron.chat.ChatManager
import com.altron.models.Message
import com.altron.models.MessageType

class ChatViewModel(application: Application) : AndroidViewModel(application) {
    
    private val chatManager: ChatManager = ChatManager.getInstance()
    
    // LiveData for messages
    private val _messages = MutableLiveData<List<Message>>()
    val messages: LiveData<List<Message>> = _messages
    
    // LiveData for new messages
    private val _newMessage = MutableLiveData<Message?>()
    val newMessage: LiveData<Message?> = _newMessage
    
    // LiveData for loading state
    private val _isLoading = MutableLiveData<Boolean>()
    val isLoading: LiveData<Boolean> = _isLoading
    
    // LiveData for error messages
    private val _errorMessage = MutableLiveData<String?>()
    val errorMessage: LiveData<String?> = _errorMessage
    
    // LiveData for message sent status
    private val _messageSent = MutableLiveData<Boolean>()
    val messageSent: LiveData<Boolean> = _messageSent
    
    private var currentConversationId: String = ""
    private var currentSenderId: String = ""
    private var currentReceiverId: String = ""
    
    fun initialize(senderId: String, receiverId: String) {
        currentSenderId = senderId
        currentReceiverId = receiverId
        currentConversationId = getConversationId(senderId, receiverId)
        
        // Start listening to messages
        chatManager.startListeningToMessages(senderId, receiverId)
        
        // Add message listener
        chatManager.addMessageListener(currentConversationId) { messages ->
            _messages.postValue(messages)
        }
    }
    
    fun fetchMessages() {
        _isLoading.postValue(true)
        _errorMessage.postValue(null)
        
        chatManager.fetchMessages(currentSenderId, currentReceiverId) { messages ->
            _isLoading.postValue(false)
            _messages.postValue(messages)
        }
    }
    
    fun sendMessage(content: String, type: MessageType = MessageType.TEXT) {
        if (content.isBlank() && type == MessageType.TEXT) {
            _errorMessage.postValue("Message cannot be empty")
            return
        }
        
        _isLoading.postValue(true)
        _errorMessage.postValue(null)
        
        chatManager.sendMessage(currentSenderId, currentReceiverId, content, type) { success, message ->
            _isLoading.postValue(false)
            _messageSent.postValue(success)
            if (success && message != null) {
                _newMessage.postValue(message)
            } else {
                _errorMessage.postValue("Failed to send message")
            }
        }
    }
    
    fun markMessagesAsRead() {
        chatManager.markMessagesAsRead(currentReceiverId, currentSenderId)
    }
    
    fun deleteMessage(messageId: String) {
        chatManager.deleteMessage(messageId) { success ->
            if (!success) {
                _errorMessage.postValue("Failed to delete message")
            }
        }
    }
    
    fun sendCallMessage(callType: String, duration: Long, isMissed: Boolean) {
        chatManager.sendCallMessage(
            currentSenderId, 
            currentReceiverId, 
            callType, 
            duration, 
            isMissed
        ) { success ->
            if (!success) {
                _errorMessage.postValue("Failed to send call message")
            }
        }
    }
    
    private fun getConversationId(userId1: String, userId2: String): String {
        return if (userId1 < userId2) "$userId1-$userId2" else "$userId2-$userId1"
    }
    
    fun cleanup() {
        chatManager.stopListeningToMessages(currentConversationId)
        chatManager.removeMessageListener(currentConversationId) { }
    }
    
    override fun onCleared() {
        super.onCleared()
        cleanup()
    }
}
