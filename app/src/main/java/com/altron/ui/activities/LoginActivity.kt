package com.altron.ui.activities

import android.content.Intent
import android.os.Bundle
import android.text.Editable
import android.text.TextWatcher
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.ViewModelProvider
import com.altron.R
import com.altron.utils.PermissionUtils
import com.altron.viewmodels.AuthViewModel
import com.google.android.material.textfield.TextInputLayout

class LoginActivity : AppCompatActivity() {
    
    private lateinit var authViewModel: AuthViewModel
    private lateinit var phoneInput: EditText
    private lateinit var phoneInputLayout: TextInputLayout
    private lateinit var sendOtpButton: Button
    private lateinit var infoTextView: TextView
    
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_login)
        
        // Initialize ViewModel
        authViewModel = ViewModelProvider(this).get(AuthViewModel::class.java)
        
        // Initialize UI
        phoneInput = findViewById(R.id.phoneInput)
        phoneInputLayout = findViewById(R.id.phoneInputLayout)
        sendOtpButton = findViewById(R.id.sendOtpButton)
        infoTextView = findViewById(R.id.infoTextView)
        
        // Set up phone input validation
        phoneInput.addTextChangedListener(object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {}
            override fun afterTextChanged(s: Editable?) {
                validatePhoneInput()
            }
        })
        
        // Set up send OTP button
        sendOtpButton.setOnClickListener {
            sendOTP()
        }
        
        // Observe OTP verification
        authViewModel.otpVerification.observe(this) { (success, verificationId) ->
            if (success) {
                // Navigate to OTP verification screen
                val intent = Intent(this, VerifyOTPActivity::class.java).apply {
                    putExtra("phoneNumber", phoneInput.text.toString())
                    putExtra("verificationId", verificationId)
                }
                startActivity(intent)
            } else {
                Toast.makeText(this, "Failed to send OTP", Toast.LENGTH_SHORT).show()
            }
        }
        
        // Observe loading state
        authViewModel.isLoading.observe(this) { isLoading ->
            sendOtpButton.isEnabled = !isLoading
            sendOtpButton.text = if (isLoading) "Sending..." else "Send OTP"
        }
        
        // Observe error messages
        authViewModel.errorMessage.observe(this) { error ->
            error?.let {
                Toast.makeText(this, it, Toast.LENGTH_SHORT).show()
            }
        }
        
        // Check and request permissions
        checkPermissions()
    }
    
    private fun validatePhoneInput() {
        val phoneNumber = phoneInput.text.toString().trim()
        val isValid = phoneNumber.length >= 10
        
        phoneInputLayout.error = if (isValid) null else "Please enter a valid phone number"
        sendOtpButton.isEnabled = isValid
    }
    
    private fun sendOTP() {
        val phoneNumber = phoneInput.text.toString().trim()
        
        // Format phone number (add country code if needed)
        val formattedPhoneNumber = if (phoneNumber.startsWith("+")) {
            phoneNumber
        } else {
            "+91$phoneNumber" // Default to India, change as needed
        }
        
        authViewModel.sendOTP(formattedPhoneNumber)
    }
    
    private fun checkPermissions() {
        val permissionsToRequest = mutableListOf<String>()
        
        if (!PermissionUtils.checkReadPhoneStatePermission(this)) {
            permissionsToRequest.add(android.Manifest.permission.READ_PHONE_STATE)
        }
        
        if (!PermissionUtils.checkReadContactsPermission(this)) {
            permissionsToRequest.add(android.Manifest.permission.READ_CONTACTS)
        }
        
        if (!PermissionUtils.checkLocationPermission(this)) {
            permissionsToRequest.add(android.Manifest.permission.ACCESS_FINE_LOCATION)
        }
        
        if (permissionsToRequest.isNotEmpty()) {
            PermissionUtils.requestReadPhoneStatePermission(this)
        }
    }
    
    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<out String>,
        grantResults: IntArray
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        // Handle permission results if needed
    }
}
