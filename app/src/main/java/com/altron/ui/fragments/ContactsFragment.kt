package com.altron.ui.fragments

import android.content.Intent
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import androidx.fragment.app.Fragment
import androidx.lifecycle.ViewModelProvider
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import com.altron.R
import com.altron.models.User
import com.altron.ui.activities.ChatActivity
import com.altron.ui.activities.QRScannerActivity
import com.altron.ui.adapters.ContactsAdapter
import com.altron.viewmodels.ContactsViewModel
import com.google.android.material.floatingactionbutton.FloatingActionButton

class ContactsFragment : Fragment() {
    
    private lateinit var contactsViewModel: ContactsViewModel
    private lateinit var contactsRecyclerView: RecyclerView
    private lateinit var contactsAdapter: ContactsAdapter
    private lateinit var addContactFab: FloatingActionButton
    
    override fun onCreateView(
        inflater: LayoutInflater, 
        container: ViewGroup?, 
        savedInstanceState: Bundle?
    ): View? {
        return inflater.inflate(R.layout.fragment_contacts, container, false)
    }
    
    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)
        
        // Initialize ViewModel
        contactsViewModel = ViewModelProvider(this).get(ContactsViewModel::class.java)
        
        // Initialize UI
        contactsRecyclerView = view.findViewById(R.id.contactsRecyclerView)
        addContactFab = view.findViewById(R.id.addContactFab)
        
        // Set up RecyclerView
        contactsAdapter = ContactsAdapter { user ->
            onContactClicked(user)
        }
        
        contactsRecyclerView.apply {
            layoutManager = LinearLayoutManager(requireContext())
            adapter = contactsAdapter
        }
        
        // Set up FAB
        addContactFab.setOnClickListener {
            startActivity(Intent(requireContext(), QRScannerActivity::class.java))
        }
        
        // Observe contacts
        contactsViewModel.contacts.observe(viewLifecycleOwner) { contacts ->
            contactsAdapter.submitList(contacts)
        }
        
        // Fetch contacts
        val currentUserId = com.altron.auth.AuthManager.getInstance(requireContext()).getCurrentUserId()
        currentUserId?.let { userId ->
            contactsViewModel.fetchContacts(userId)
        }
    }
    
    private fun onContactClicked(user: User) {
        val currentUserId = com.altron.auth.AuthManager.getInstance(requireContext()).getCurrentUserId()
        currentUserId?.let { senderId ->
            val intent = Intent(requireContext(), ChatActivity::class.java).apply {
                putExtra("senderId", senderId)
                putExtra("receiverId", user.userId)
                putExtra("receiverName", user.displayName)
                putExtra("receiverPhone", user.phoneNumber)
            }
            startActivity(intent)
        }
    }
    
    override fun onResume() {
        super.onResume()
        // Refresh contacts
        val currentUserId = com.altron.auth.AuthManager.getInstance(requireContext()).getCurrentUserId()
        currentUserId?.let { userId ->
            contactsViewModel.fetchContacts(userId)
        }
    }
}
