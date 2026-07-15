package com.altron.viewmodels

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.LiveData
import androidx.lifecycle.MutableLiveData
import com.altron.contacts.ContactsManager
import com.altron.models.User

class ContactsViewModel(application: Application) : AndroidViewModel(application) {
    
    private val contactsManager: ContactsManager = ContactsManager.getInstance()
    
    // LiveData for contacts list
    private val _contacts = MutableLiveData<List<User>>()
    val contacts: LiveData<List<User>> = _contacts
    
    // LiveData for loading state
    private val _isLoading = MutableLiveData<Boolean>()
    val isLoading: LiveData<Boolean> = _isLoading
    
    // LiveData for error messages
    private val _errorMessage = MutableLiveData<String?>()
    val errorMessage: LiveData<String?> = _errorMessage
    
    // LiveData for search results
    private val _searchResults = MutableLiveData<List<User>>()
    val searchResults: LiveData<List<User>> = _searchResults
    
    // LiveData for contact added
    private val _contactAdded = MutableLiveData<Boolean>()
    val contactAdded: LiveData<Boolean> = _contactAdded
    
    init {
        // Add contact listener
        contactsManager.addContactListener { contacts ->
            _contacts.postValue(contacts)
        }
    }
    
    fun fetchContacts(userId: String) {
        _isLoading.postValue(true)
        _errorMessage.postValue(null)
        
        contactsManager.fetchContacts(userId) { contacts ->
            _isLoading.postValue(false)
            _contacts.postValue(contacts)
        }
    }
    
    fun searchUsers(query: String) {
        if (query.isBlank()) {
            _searchResults.postValue(emptyList())
            return
        }
        
        _isLoading.postValue(true)
        
        contactsManager.searchUsers(query) { users ->
            _isLoading.postValue(false)
            _searchResults.postValue(users)
        }
    }
    
    fun addContact(userId: String, contactUserId: String) {
        _isLoading.postValue(true)
        _errorMessage.postValue(null)
        
        contactsManager.addContact(userId, contactUserId) { success ->
            _isLoading.postValue(false)
            _contactAdded.postValue(success)
            if (!success) {
                _errorMessage.postValue("Failed to add contact")
            }
        }
    }
    
    fun removeContact(userId: String, contactUserId: String) {
        _isLoading.postValue(true)
        
        contactsManager.removeContact(userId, contactUserId) { success ->
            _isLoading.postValue(false)
            if (!success) {
                _errorMessage.postValue("Failed to remove contact")
            }
        }
    }
    
    fun isContact(userId: String, contactUserId: String, callback: (Boolean) -> Unit) {
        contactsManager.isContact(userId, contactUserId, callback)
    }
    
    fun getUserById(userId: String, callback: (User?) -> Unit) {
        contactsManager.getUserById(userId, callback)
    }
    
    fun getUserByQRCode(qrCode: String, callback: (User?) -> Unit) {
        contactsManager.getUserByQRCode(qrCode, callback)
    }
    
    override fun onCleared() {
        super.onCleared()
        contactsManager.removeContactListener { }
    }
}
