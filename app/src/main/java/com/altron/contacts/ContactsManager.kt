package com.altron.contacts

import android.util.Log
import com.altron.models.User
import com.google.firebase.firestore.FirebaseFirestore
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.tasks.await

class ContactsManager {
    
    companion object {
        private const val TAG = "ContactsManager"
        private var instance: ContactsManager? = null
        
        fun getInstance(): ContactsManager {
            if (instance == null) {
                instance = ContactsManager()
            }
            return instance!!
        }
    }
    
    private val firestore: FirebaseFirestore = FirebaseFirestore.getInstance()
    private val usersCollection = firestore.collection("users")
    private val contactsCollection = firestore.collection("contacts")
    
    // Contact listeners
    private var contactListeners: MutableList<(List<User>) -> Unit> = mutableListOf()
    
    fun addContactListener(listener: (List<User>) -> Unit) {
        contactListeners.add(listener)
    }
    
    fun removeContactListener(listener: (List<User>) -> Unit) {
        contactListeners.remove(listener)
    }
    
    private fun notifyContactsUpdated(contacts: List<User>) {
        contactListeners.forEach { it(contacts) }
    }
    
    fun addContact(userId: String, contactUserId: String, callback: (Boolean) -> Unit) {
        CoroutineScope(Dispatchers.IO).launch {
            try {
                // Add contact to user's contact list
                val userRef = usersCollection.document(userId)
                userRef.update("contacts", com.google.firebase.firestore.FieldValue.arrayUnion(contactUserId)).await()
                
                // Also add reverse contact (bidirectional)
                val contactRef = usersCollection.document(contactUserId)
                contactRef.update("contacts", com.google.firebase.firestore.FieldValue.arrayUnion(userId)).await()
                
                // Create contact relationship
                val contactData = mapOf(
                    "userId1" to minOf(userId, contactUserId),
                    "userId2" to maxOf(userId, contactUserId),
                    "addedAt" to System.currentTimeMillis(),
                    "lastInteraction" to System.currentTimeMillis()
                )
                
                val contactId = "${minOf(userId, contactUserId)}_${maxOf(userId, contactUserId)}"
                contactsCollection.document(contactId).set(contactData).await()
                
                callback(true)
                
                // Refresh contacts
                fetchContacts(userId)
            } catch (e: Exception) {
                Log.e(TAG, "Failed to add contact", e)
                callback(false)
            }
        }
    }
    
    fun removeContact(userId: String, contactUserId: String, callback: (Boolean) -> Unit) {
        CoroutineScope(Dispatchers.IO).launch {
            try {
                // Remove contact from user's contact list
                val userRef = usersCollection.document(userId)
                userRef.update("contacts", com.google.firebase.firestore.FieldValue.arrayRemove(contactUserId)).await()
                
                // Remove reverse contact
                val contactRef = usersCollection.document(contactUserId)
                contactRef.update("contacts", com.google.firebase.firestore.FieldValue.arrayRemove(userId)).await()
                
                // Remove contact relationship
                val contactId = "${minOf(userId, contactUserId)}_${maxOf(userId, contactUserId)}"
                contactsCollection.document(contactId).delete().await()
                
                callback(true)
                
                // Refresh contacts
                fetchContacts(userId)
            } catch (e: Exception) {
                Log.e(TAG, "Failed to remove contact", e)
                callback(false)
            }
        }
    }
    
    fun fetchContacts(userId: String, callback: ((List<User>) -> Unit)? = null) {
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val userSnapshot = usersCollection.document(userId).get().await()
                if (userSnapshot.exists()) {
                    val contactIds = userSnapshot.get("contacts") as? List<String> ?: emptyList()
                    
                    if (contactIds.isNotEmpty()) {
                        val contacts = mutableListOf<User>()
                        
                        for (contactId in contactIds) {
                            val contactSnapshot = usersCollection.document(contactId).get().await()
                            if (contactSnapshot.exists()) {
                                val user = User.fromMap(contactSnapshot.data!!)
                                contacts.add(user)
                            }
                        }
                        
                        // Sort by last seen or name
                        val sortedContacts = contacts.sortedByDescending { it.lastSeen }
                        
                        notifyContactsUpdated(sortedContacts)
                        callback?.invoke(sortedContacts)
                    } else {
                        notifyContactsUpdated(emptyList())
                        callback?.invoke(emptyList())
                    }
                } else {
                    notifyContactsUpdated(emptyList())
                    callback?.invoke(emptyList())
                }
            } catch (e: Exception) {
                Log.e(TAG, "Failed to fetch contacts", e)
                notifyContactsUpdated(emptyList())
                callback?.invoke(emptyList())
            }
        }
    }
    
    fun searchUsers(query: String, callback: (List<User>) -> Unit) {
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val results = usersCollection
                    .whereGreaterThanOrEqualTo("phoneNumber", query)
                    .whereLessThanOrEqualTo("phoneNumber", query + "\uf8ff")
                    .limit(10)
                    .get()
                    .await()
                
                val users = results.documents.mapNotNull { doc ->
                    User.fromMap(doc.data!!)
                }
                
                callback(users)
            } catch (e: Exception) {
                Log.e(TAG, "Failed to search users", e)
                callback(emptyList())
            }
        }
    }
    
    fun getUserById(userId: String, callback: (User?) -> Unit) {
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val userSnapshot = usersCollection.document(userId).get().await()
                if (userSnapshot.exists()) {
                    val user = User.fromMap(userSnapshot.data!!)
                    callback(user)
                } else {
                    callback(null)
                }
            } catch (e: Exception) {
                Log.e(TAG, "Failed to get user by ID", e)
                callback(null)
            }
        }
    }
    
    fun getUserByQRCode(qrCode: String, callback: (User?) -> Unit) {
        CoroutineScope(Dispatchers.IO).launch {
            try {
                // Search for user with matching QR code
                val results = usersCollection
                    .whereEqualTo("qrCode", qrCode)
                    .limit(1)
                    .get()
                    .await()
                
                if (results.documents.isNotEmpty()) {
                    val user = User.fromMap(results.documents[0].data!!)
                    callback(user)
                } else {
                    callback(null)
                }
            } catch (e: Exception) {
                Log.e(TAG, "Failed to get user by QR code", e)
                callback(null)
            }
        }
    }
    
    fun isContact(userId: String, contactUserId: String, callback: (Boolean) -> Unit) {
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val userSnapshot = usersCollection.document(userId).get().await()
                if (userSnapshot.exists()) {
                    val contacts = userSnapshot.get("contacts") as? List<String> ?: emptyList()
                    callback(contacts.contains(contactUserId))
                } else {
                    callback(false)
                }
            } catch (e: Exception) {
                Log.e(TAG, "Failed to check if user is contact", e)
                callback(false)
            }
        }
    }
}
