package com.altron.auth

import android.content.Context
import android.util.Log
import com.altron.models.User
import com.altron.network.TailscaleManager
import com.altron.utils.EncryptionUtils
import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.auth.PhoneAuthCredential
import com.google.firebase.auth.PhoneAuthOptions
import com.google.firebase.auth.PhoneAuthProvider
import com.google.firebase.firestore.FirebaseFirestore
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.tasks.await
import java.util.concurrent.TimeUnit

class AuthManager(private val context: Context) {
    
    companion object {
        private const val TAG = "AuthManager"
        private var instance: AuthManager? = null
        
        fun getInstance(context: Context): AuthManager {
            if (instance == null) {
                instance = AuthManager(context)
            }
            return instance!!
        }
    }
    
    private val auth: FirebaseAuth = FirebaseAuth.getInstance()
    private val firestore: FirebaseFirestore = FirebaseFirestore.getInstance()
    private val usersCollection = firestore.collection("users")
    
    // Authentication state listeners
    private var authStateListeners: MutableList<(Boolean, User?) -> Unit> = mutableListOf()
    
    init {
        // Add auth state listener
        auth.addAuthStateListener {
            val user = auth.currentUser
            if (user != null) {
                fetchUserData(user.uid)
            } else {
                notifyAuthState(false, null)
            }
        }
    }
    
    fun addAuthStateListener(listener: (Boolean, User?) -> Unit) {
        authStateListeners.add(listener)
    }
    
    fun removeAuthStateListener(listener: (Boolean, User?) -> Unit) {
        authStateListeners.remove(listener)
    }
    
    private fun notifyAuthState(isAuthenticated: Boolean, user: User?) {
        authStateListeners.forEach { it(isAuthenticated, user) }
    }
    
    fun isUserAuthenticated(): Boolean = auth.currentUser != null
    
    fun getCurrentUserId(): String? = auth.currentUser?.uid
    
    fun sendOTP(phoneNumber: String, callback: (Boolean, String?) -> Unit) {
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val options = PhoneAuthOptions.newBuilder(auth)
                    .setPhoneNumber(phoneNumber)
                    .setTimeout(60L, TimeUnit.SECONDS)
                    .setActivity(context as android.app.Activity)
                    .setCallbacks(object : PhoneAuthProvider.OnVerificationStateChangedCallbacks() {
                        override fun onVerificationCompleted(credential: PhoneAuthCredential) {
                            // Auto-verification on some devices
                            signInWithCredential(credential, callback)
                        }
                        
                        override fun onVerificationFailed(e: Exception) {
                            Log.e(TAG, "Verification failed", e)
                            callback(false, e.message)
                        }
                        
                        override fun onCodeSent(
                            verificationId: String,
                            token: PhoneAuthProvider.ForceResendingToken
                        ) {
                            // Code sent successfully
                            callback(true, verificationId)
                        }
                    })
                    .build()
                
                PhoneAuthProvider.verifyPhoneNumber(options)
            } catch (e: Exception) {
                Log.e(TAG, "Failed to send OTP", e)
                callback(false, e.message)
            }
        }
    }
    
    fun verifyOTP(verificationId: String, otp: String, callback: (Boolean, User?) -> Unit) {
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val credential = PhoneAuthProvider.getCredential(verificationId, otp)
                signInWithCredential(credential, callback)
            } catch (e: Exception) {
                Log.e(TAG, "Failed to verify OTP", e)
                callback(false, null)
            }
        }
    }
    
    private fun signInWithCredential(credential: PhoneAuthCredential, callback: (Boolean, User?) -> Unit) {
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val authResult = auth.signInWithCredential(credential).await()
                val firebaseUser = authResult.user
                
                if (firebaseUser != null) {
                    // Check if user exists in Firestore
                    val userSnapshot = usersCollection.document(firebaseUser.uid).get().await()
                    
                    if (userSnapshot.exists()) {
                        // User exists, fetch data
                        val user = User.fromMap(userSnapshot.data!!)
                        notifyAuthState(true, user)
                        callback(true, user)
                    } else {
                        // New user, create profile
                        val newUser = createNewUser(firebaseUser)
                        val userMap = newUser.toMap()
                        usersCollection.document(firebaseUser.uid).set(userMap).await()
                        
                        notifyAuthState(true, newUser)
                        callback(true, newUser)
                    }
                } else {
                    callback(false, null)
                }
            } catch (e: Exception) {
                Log.e(TAG, "Failed to sign in with credential", e)
                callback(false, null)
            }
        }
    }
    
    private suspend fun createNewUser(firebaseUser: com.google.firebase.auth.FirebaseUser): User {
        val phoneNumber = firebaseUser.phoneNumber ?: ""
        val userId = firebaseUser.uid
        
        // Generate QR code data
        val qrCodeData = EncryptionUtils.generateQRCodeData(userId, phoneNumber)
        
        // Get Tailscale info
        val tailscaleNodeId = TailscaleManager.getNodeId()
        val tailscaleIp = TailscaleManager.getTailscaleIp()
        
        return User(
            userId = userId,
            phoneNumber = phoneNumber,
            displayName = "User ${phoneNumber.takeLast(4)}",
            profileImageUrl = "",
            tailscaleNodeId = tailscaleNodeId,
            tailscaleIp = tailscaleIp,
            qrCode = qrCodeData,
            contacts = emptyList(),
            createdAt = System.currentTimeMillis(),
            lastSeen = System.currentTimeMillis(),
            isOnline = true,
            status = "Hey there! I'm using Altron"
        )
    }
    
    private fun fetchUserData(userId: String) {
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val userSnapshot = usersCollection.document(userId).get().await()
                if (userSnapshot.exists()) {
                    val user = User.fromMap(userSnapshot.data!!)
                    notifyAuthState(true, user)
                } else {
                    notifyAuthState(false, null)
                }
            } catch (e: Exception) {
                Log.e(TAG, "Failed to fetch user data", e)
                notifyAuthState(false, null)
            }
        }
    }
    
    fun updateUserProfile(user: User, callback: (Boolean) -> Unit) {
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val userMap = user.toMap()
                usersCollection.document(user.userId).update(userMap).await()
                callback(true)
            } catch (e: Exception) {
                Log.e(TAG, "Failed to update user profile", e)
                callback(false)
            }
        }
    }
    
    fun logout(callback: (Boolean) -> Unit) {
        CoroutineScope(Dispatchers.IO).launch {
            try {
                // Update user status to offline
                val currentUserId = getCurrentUserId()
                if (currentUserId != null) {
                    usersCollection.document(currentUserId)
                        .update("isOnline", false, "lastSeen", System.currentTimeMillis())
                        .await()
                }
                
                auth.signOut()
                notifyAuthState(false, null)
                callback(true)
            } catch (e: Exception) {
                Log.e(TAG, "Failed to logout", e)
                callback(false)
            }
        }
    }
    
    fun getCurrentUser(callback: (User?) -> Unit) {
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val currentUserId = getCurrentUserId()
                if (currentUserId != null) {
                    val userSnapshot = usersCollection.document(currentUserId).get().await()
                    if (userSnapshot.exists()) {
                        val user = User.fromMap(userSnapshot.data!!)
                        callback(user)
                    } else {
                        callback(null)
                    }
                } else {
                    callback(null)
                }
            } catch (e: Exception) {
                Log.e(TAG, "Failed to get current user", e)
                callback(null)
            }
        }
    }
}
