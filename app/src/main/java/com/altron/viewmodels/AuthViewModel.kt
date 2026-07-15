package com.altron.viewmodels

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.LiveData
import androidx.lifecycle.MutableLiveData
import com.altron.auth.AuthManager
import com.altron.models.User

class AuthViewModel(application: Application) : AndroidViewModel(application) {
    
    private val authManager: AuthManager = AuthManager.getInstance(application)
    
    // LiveData for authentication state
    private val _authState = MutableLiveData<Boolean>()
    val authState: LiveData<Boolean> = _authState
    
    // LiveData for current user
    private val _currentUser = MutableLiveData<User?>()
    val currentUser: LiveData<User?> = _currentUser
    
    // LiveData for OTP verification
    private val _otpVerification = MutableLiveData<Pair<Boolean, String?>>()
    val otpVerification: LiveData<Pair<Boolean, String?>> = _otpVerification
    
    // LiveData for login state
    private val _loginState = MutableLiveData<Pair<Boolean, User?>>()
    val loginState: LiveData<Pair<Boolean, User?>> = _loginState
    
    // LiveData for loading state
    private val _isLoading = MutableLiveData<Boolean>()
    val isLoading: LiveData<Boolean> = _isLoading
    
    // LiveData for error messages
    private val _errorMessage = MutableLiveData<String?>()
    val errorMessage: LiveData<String?> = _errorMessage
    
    init {
        // Check current authentication state
        checkAuthState()
        
        // Add auth state listener
        authManager.addAuthStateListener { isAuthenticated, user ->
            _authState.postValue(isAuthenticated)
            _currentUser.postValue(user)
        }
    }
    
    fun checkAuthState() {
        _authState.postValue(authManager.isUserAuthenticated())
        if (authManager.isUserAuthenticated()) {
            authManager.getCurrentUser { user ->
                _currentUser.postValue(user)
            }
        }
    }
    
    fun sendOTP(phoneNumber: String) {
        _isLoading.postValue(true)
        _errorMessage.postValue(null)
        
        authManager.sendOTP(phoneNumber) { success, verificationId ->
            _isLoading.postValue(false)
            if (success) {
                _otpVerification.postValue(Pair(true, verificationId))
            } else {
                _otpVerification.postValue(Pair(false, verificationId))
                _errorMessage.postValue(verificationId ?: "Failed to send OTP")
            }
        }
    }
    
    fun verifyOTP(verificationId: String, otp: String) {
        _isLoading.postValue(true)
        _errorMessage.postValue(null)
        
        authManager.verifyOTP(verificationId, otp) { success, user ->
            _isLoading.postValue(false)
            if (success) {
                _loginState.postValue(Pair(true, user))
                _authState.postValue(true)
                _currentUser.postValue(user)
            } else {
                _loginState.postValue(Pair(false, null))
                _errorMessage.postValue("Invalid OTP")
            }
        }
    }
    
    fun logout() {
        _isLoading.postValue(true)
        
        authManager.logout { success ->
            _isLoading.postValue(false)
            if (success) {
                _authState.postValue(false)
                _currentUser.postValue(null)
            } else {
                _errorMessage.postValue("Failed to logout")
            }
        }
    }
    
    fun updateProfile(displayName: String, status: String, callback: (Boolean) -> Unit) {
        _currentUser.value?.let { user ->
            val updatedUser = user.copy(
                displayName = displayName,
                status = status
            )
            
            authManager.updateUserProfile(updatedUser) { success ->
                if (success) {
                    _currentUser.postValue(updatedUser)
                }
                callback(success)
            }
        } ?: callback(false)
    }
    
    override fun onCleared() {
        super.onCleared()
        authManager.removeAuthStateListener { _, _ -> }
    }
}
