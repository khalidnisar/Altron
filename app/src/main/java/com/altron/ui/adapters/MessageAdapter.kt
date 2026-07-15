package com.altron.ui.adapters

import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.TextView
import androidx.recyclerview.widget.DiffUtil
import androidx.recyclerview.widget.ListAdapter
import androidx.recyclerview.widget.RecyclerView
import com.altron.R
import com.altron.models.Message
import com.altron.models.MessageStatus
import com.altron.models.MessageType
import com.altron.utils.DateUtils
import com.bumptech.glide.Glide
import de.hdodenhof.circleimageview.CircleImageView

class MessageAdapter(
    private val currentUserId: String,
    private val onClick: (Message) -> Unit
) : ListAdapter<Message, RecyclerView.ViewHolder>(MessageDiffCallback()) {
    
    companion object {
        private const val VIEW_TYPE_SENT = 1
        private const val VIEW_TYPE_RECEIVED = 2
        private const val VIEW_TYPE_CALL = 3
    }
    
    override fun getItemViewType(position: Int): Int {
        val message = getItem(position)
        return when {
            message.senderId == currentUserId && message.type == MessageType.CALL -> VIEW_TYPE_CALL
            message.senderId == currentUserId -> VIEW_TYPE_SENT
            else -> VIEW_TYPE_RECEIVED
        }
    }
    
    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): RecyclerView.ViewHolder {
        return when (viewType) {
            VIEW_TYPE_SENT -> {
                val view = LayoutInflater.from(parent.context)
                    .inflate(R.layout.item_message_sent, parent, false)
                SentMessageViewHolder(view)
            }
            VIEW_TYPE_RECEIVED -> {
                val view = LayoutInflater.from(parent.context)
                    .inflate(R.layout.item_message_received, parent, false)
                ReceivedMessageViewHolder(view)
            }
            VIEW_TYPE_CALL -> {
                val view = LayoutInflater.from(parent.context)
                    .inflate(R.layout.item_message_call, parent, false)
                CallMessageViewHolder(view)
            }
            else -> {
                val view = LayoutInflater.from(parent.context)
                    .inflate(R.layout.item_message_received, parent, false)
                ReceivedMessageViewHolder(view)
            }
        }
    }
    
    override fun onBindViewHolder(holder: RecyclerView.ViewHolder, position: Int) {
        val message = getItem(position)
        
        when (holder) {
            is SentMessageViewHolder -> (holder as SentMessageViewHolder).bind(message)
            is ReceivedMessageViewHolder -> (holder as ReceivedMessageViewHolder).bind(message)
            is CallMessageViewHolder -> (holder as CallMessageViewHolder).bind(message)
        }
        
        holder.itemView.setOnClickListener { onClick(message) }
    }
    
    fun addMessage(message: Message) {
        val newList = currentList.toMutableList()
        newList.add(message)
        submitList(newList)
    }
    
    class SentMessageViewHolder(itemView: View) : RecyclerView.ViewHolder(itemView) {
        private val messageTextView: TextView = itemView.findViewById(R.id.messageTextView)
        private val timeTextView: TextView = itemView.findViewById(R.id.timeTextView)
        private val statusImageView: CircleImageView = itemView.findViewById(R.id.statusImageView)
        
        fun bind(message: Message) {
            when (message.type) {
                MessageType.TEXT -> messageTextView.text = message.content
                MessageType.IMAGE -> messageTextView.text = "📷 Photo"
                MessageType.VIDEO -> messageTextView.text = "🎥 Video"
                MessageType.AUDIO -> messageTextView.text = "🎵 Audio"
                else -> messageTextView.text = message.content
            }
            
            timeTextView.text = DateUtils.formatChatTime(message.timestamp)
            
            // Set status icon
            val statusIcon = when (message.status) {
                MessageStatus.SENDING -> R.drawable.ic_clock
                MessageStatus.SENT -> R.drawable.ic_check
                MessageStatus.DELIVERED -> R.drawable.ic_check_all
                MessageStatus.READ -> R.drawable.ic_check_all_blue
                MessageStatus.FAILED -> R.drawable.ic_error
            }
            statusImageView.setImageResource(statusIcon)
        }
    }
    
    class ReceivedMessageViewHolder(itemView: View) : RecyclerView.ViewHolder(itemView) {
        private val messageTextView: TextView = itemView.findViewById(R.id.messageTextView)
        private val timeTextView: TextView = itemView.findViewById(R.id.timeTextView)
        private val profileImageView: CircleImageView = itemView.findViewById(R.id.profileImageView)
        
        fun bind(message: Message) {
            when (message.type) {
                MessageType.TEXT -> messageTextView.text = message.content
                MessageType.IMAGE -> messageTextView.text = "📷 Photo"
                MessageType.VIDEO -> messageTextView.text = "🎥 Video"
                MessageType.AUDIO -> messageTextView.text = "🎵 Audio"
                else -> messageTextView.text = message.content
            }
            
            timeTextView.text = DateUtils.formatChatTime(message.timestamp)
            
            // Load profile image (placeholder for now)
            profileImageView.setImageResource(R.drawable.ic_person)
        }
    }
    
    class CallMessageViewHolder(itemView: View) : RecyclerView.ViewHolder(itemView) {
        private val callTypeTextView: TextView = itemView.findViewById(R.id.callTypeTextView)
        private val durationTextView: TextView = itemView.findViewById(R.id.durationTextView)
        private val timeTextView: TextView = itemView.findViewById(R.id.timeTextView)
        private val callIconImageView: CircleImageView = itemView.findViewById(R.id.callIconImageView)
        
        fun bind(message: Message) {
            val callType = message.callType ?: "voice"
            val isMissed = message.type == MessageType.CALL
            
            callTypeTextView.text = if (isMissed) "Missed $callType call" else "$callType call"
            
            message.callDuration?.let { duration ->
                durationTextView.text = DateUtils.formatCallDuration(duration)
                durationTextView.visibility = View.VISIBLE
            } ?: run {
                durationTextView.visibility = View.GONE
            }
            
            timeTextView.text = DateUtils.formatChatTime(message.timestamp)
            
            // Set call icon
            val iconRes = when {
                isMissed -> R.drawable.ic_call_missed
                callType == "video" -> R.drawable.ic_video_call
                else -> R.drawable.ic_call
            }
            callIconImageView.setImageResource(iconRes)
        }
    }
    
    private class MessageDiffCallback : DiffUtil.ItemCallback<Message>() {
        override fun areItemsTheSame(oldItem: Message, newItem: Message): Boolean {
            return oldItem.messageId == newItem.messageId
        }
        
        override fun areContentsTheSame(oldItem: Message, newItem: Message): Boolean {
            return oldItem == newItem
        }
    }
}
