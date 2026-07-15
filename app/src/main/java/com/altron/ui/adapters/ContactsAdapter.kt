package com.altron.ui.adapters

import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.TextView
import androidx.recyclerview.widget.DiffUtil
import androidx.recyclerview.widget.ListAdapter
import androidx.recyclerview.widget.RecyclerView
import com.altron.R
import com.altron.models.User
import com.bumptech.glide.Glide
import de.hdodenhof.circleimageview.CircleImageView

class ContactsAdapter(private val onClick: (User) -> Unit) : 
    ListAdapter<User, ContactsAdapter.ContactViewHolder>(ContactDiffCallback()) {
    
    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): ContactViewHolder {
        val view = LayoutInflater.from(parent.context)
            .inflate(R.layout.item_contact, parent, false)
        return ContactViewHolder(view)
    }
    
    override fun onBindViewHolder(holder: ContactViewHolder, position: Int) {
        val user = getItem(position)
        holder.bind(user)
        holder.itemView.setOnClickListener { onClick(user) }
    }
    
    class ContactViewHolder(itemView: View) : RecyclerView.ViewHolder(itemView) {
        private val profileImageView: CircleImageView = itemView.findViewById(R.id.profileImageView)
        private val nameTextView: TextView = itemView.findViewById(R.id.nameTextView)
        private val phoneTextView: TextView = itemView.findViewById(R.id.phoneTextView)
        private val statusTextView: TextView = itemView.findViewById(R.id.statusTextView)
        
        fun bind(user: User) {
            nameTextView.text = user.displayName
            phoneTextView.text = user.phoneNumber
            statusTextView.text = user.status
            
            // Load profile image
            if (user.profileImageUrl.isNotEmpty()) {
                Glide.with(itemView.context)
                    .load(user.profileImageUrl)
                    .placeholder(R.drawable.ic_person)
                    .error(R.drawable.ic_person)
                    .into(profileImageView)
            } else {
                profileImageView.setImageResource(R.drawable.ic_person)
            }
            
            // Show online status
            val onlineIndicator = itemView.findViewById<View>(R.id.onlineIndicator)
            onlineIndicator.visibility = if (user.isOnline) View.VISIBLE else View.GONE
        }
    }
    
    private class ContactDiffCallback : DiffUtil.ItemCallback<User>() {
        override fun areItemsTheSame(oldItem: User, newItem: User): Boolean {
            return oldItem.userId == newItem.userId
        }
        
        override fun areContentsTheSame(oldItem: User, newItem: User): Boolean {
            return oldItem == newItem
        }
    }
}
