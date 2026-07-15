package com.altron.ui.activities

import android.content.Intent
import android.os.Bundle
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.ViewModelProvider
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import com.altron.R
import com.altron.models.User
import com.altron.ui.adapters.ContactsAdapter
import com.altron.viewmodels.ContactsViewModel
import com.google.android.material.floatingactionbutton.FloatingActionButton

class ContactsActivity : AppCompatActivity() {
    
    private lateinit var contactsViewModel: ContactsViewModel
    private lateinit var contactsRecyclerView: RecyclerView
    private lateinit var contactsAdapter: ContactsAdapter
    private lateinit var addContactFab: FloatingActionButton
    
    private var currentUserId: String = ""
    
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_contacts)
        
        // Initialize ViewModel
        contactsViewModel = ViewModelProvider(this).get(ContactsViewModel::class.java)
        
        // Get current user ID
        currentUserId = intent.getStringExtra("userId") ?: ""
        
        // Initialize UI
        contactsRecyclerView = findViewById(R.id.contactsRecyclerView)
        addContactFab = findViewById(R.id.addContactFab)
        
        // Set up RecyclerView
        contactsAdapter = ContactsAdapter { user ->
            onContactClicked(user)
        }
        
        contactsRecyclerView.apply {
            layoutManager = LinearLayoutManager(this@ContactsActivity)
            adapter = contactsAdapter
        }
        
        // Set up FAB
        addContactFab.setOnClickListener {
            startActivity(Intent(this, QRScannerActivity::class.java))
        }
        
        // Observe contacts
        contactsViewModel.contacts.observe(this) { contacts ->
            contactsAdapter.submitList(contacts)
        }
        
        // Observe loading state
        contactsViewModel.isLoading.observe(this) { isLoading ->
            // Show/hide loading indicator
        }
        
        // Observe error messages
        contactsViewModel.errorMessage.observe(this) { error ->
            error?.let {
                Toast.makeText(this, it, Toast.LENGTH_SHORT).show()
            }
        }
        
        // Fetch contacts
        contactsViewModel.fetchContacts(currentUserId)
    }
    
    private fun onContactClicked(user: User) {
        // Navigate to chat with this contact
        val intent = Intent(this, ChatActivity::class.java).apply {
            putExtra("receiverId", user.userId)
            putExtra("receiverName", user.displayName)
            putExtra("receiverPhone", user.phoneNumber)
        }
        startActivity(intent)
    }
    
    override fun onResume() {
        super.onResume()
        // Refresh contacts
        contactsViewModel.fetchContacts(currentUserId)
    }
}
