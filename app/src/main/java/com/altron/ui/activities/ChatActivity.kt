package com.altron.ui.activities

import android.content.Intent
import android.os.Bundle
import android.text.Editable
import android.text.TextWatcher
import android.view.View
import android.widget.EditText
import android.widget.ImageButton
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.ViewModelProvider
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import com.altron.R
import com.altron.models.Message
import com.altron.models.MessageType
import com.altron.ui.adapters.MessageAdapter
import com.altron.utils.PermissionUtils
import com.altron.viewmodels.ChatViewModel
import com.google.android.material.appbar.MaterialToolbar

class ChatActivity : AppCompatActivity() {
    
    private lateinit var chatViewModel: ChatViewModel
    private lateinit var messageRecyclerView: RecyclerView
    private lateinit var messageAdapter: MessageAdapter
    private lateinit var messageInput: EditText
    private lateinit var sendButton: ImageButton
    private lateinit var toolbar: MaterialToolbar
    private lateinit var receiverNameTextView: TextView
    private lateinit var callButton: ImageButton
    private lateinit var videoCallButton: ImageButton
    
    private var senderId: String = ""
    private var receiverId: String = ""
    private var receiverName: String = ""
    
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_chat)
        
        // Initialize ViewModel
        chatViewModel = ViewModelProvider(this).get(ChatViewModel::class.java)
        
        // Get extras
        senderId = intent.getStringExtra("senderId") ?: ""
        receiverId = intent.getStringExtra("receiverId") ?: ""
        receiverName = intent.getStringExtra("receiverName") ?: ""
        
        // Initialize UI
        messageRecyclerView = findViewById(R.id.messageRecyclerView)
        messageInput = findViewById(R.id.messageInput)
        sendButton = findViewById(R.id.sendButton)
        toolbar = findViewById(R.id.toolbar)
        receiverNameTextView = findViewById(R.id.receiverNameTextView)
        callButton = findViewById(R.id.callButton)
        videoCallButton = findViewById(R.id.videoCallButton)
        
        // Set up toolbar
        setSupportActionBar(toolbar)
        supportActionBar?.apply {
            setDisplayHomeAsUpEnabled(true)
            setDisplayShowTitleEnabled(false)
        }
        
        // Set receiver name
        receiverNameTextView.text = receiverName
        
        // Set up RecyclerView
        messageAdapter = MessageAdapter(senderId) { message ->
            onMessageClicked(message)
        }
        
        messageRecyclerView.apply {
            layoutManager = LinearLayoutManager(this@ChatActivity).apply {
                stackFromEnd = true
            }
            adapter = messageAdapter
        }
        
        // Set up message input
        messageInput.addTextChangedListener(object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {}
            override fun afterTextChanged(s: Editable?) {
                sendButton.isEnabled = !s.toString().trim().isEmpty()
            }
        })
        
        // Set up send button
        sendButton.setOnClickListener {
            sendMessage()
        }
        
        // Set up call buttons
        callButton.setOnClickListener {
            startCall(false)
        }
        
        videoCallButton.setOnClickListener {
            startCall(true)
        }
        
        // Initialize ViewModel
        chatViewModel.initialize(senderId, receiverId)
        
        // Observe messages
        chatViewModel.messages.observe(this) { messages ->
            messageAdapter.submitList(messages)
            scrollToBottom()
        }
        
        // Observe new messages
        chatViewModel.newMessage.observe(this) { message ->
            message?.let {
                messageAdapter.addMessage(it)
                scrollToBottom()
            }
        }
        
        // Observe loading state
        chatViewModel.isLoading.observe(this) { isLoading ->
            // Show/hide loading indicator
        }
        
        // Observe error messages
        chatViewModel.errorMessage.observe(this) { error ->
            error?.let {
                Toast.makeText(this, it, Toast.LENGTH_SHORT).show()
            }
        }
        
        // Fetch messages
        chatViewModel.fetchMessages()
        
        // Mark messages as read
        chatViewModel.markMessagesAsRead()
    }
    
    private fun sendMessage() {
        val content = messageInput.text.toString().trim()
        if (content.isEmpty()) return
        
        chatViewModel.sendMessage(content, MessageType.TEXT)
        messageInput.text.clear()
    }
    
    private fun startCall(isVideo: Boolean) {
        // Check call permissions
        if (!PermissionUtils.hasAllCallPermissions(this)) {
            PermissionUtils.requestCallPermissions(this)
            return
        }
        
        val intent = Intent(this, CallActivity::class.java).apply {
            putExtra("callerId", senderId)
            putExtra("receiverId", receiverId)
            putExtra("receiverName", receiverName)
            putExtra("isVideo", isVideo)
            putExtra("isIncoming", false)
        }
        startActivity(intent)
    }
    
    private fun onMessageClicked(message: Message) {
        // Handle message click (e.g., reply, delete, etc.)
        when (message.type) {
            MessageType.CALL -> {
                // Handle call message click
            }
            else -> {
                // Handle other message types
            }
        }
    }
    
    private fun scrollToBottom() {
        if (messageAdapter.itemCount > 0) {
            messageRecyclerView.smoothScrollToPosition(messageAdapter.itemCount - 1)
        }
    }
    
    override fun onDestroy() {
        super.onDestroy()
        chatViewModel.cleanup()
    }
}
