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
import com.altron.viewmodels.AuthViewModel
import com.google.android.material.textfield.TextInputLayout

class VerifyOTPActivity : AppCompatActivity() {
    
    private lateinit var authViewModel: AuthViewModel
    private lateinit var otpInput: EditText
    private lateinit var otpInputLayout: TextInputLayout
    private lateinit var verifyButton: Button
    private lateinit var phoneNumberTextView: TextView
    private lateinit var resendOtpTextView: TextView
    
    private var phoneNumber: String = ""
    private var verificationId: String = ""
    
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_verify_otp)
        
        // Initialize ViewModel
        authViewModel = ViewModelProvider(this).get(AuthViewModel::class.java)
        
        // Get extras
        phoneNumber = intent.getStringExtra("phoneNumber") ?: ""
        verificationId = intent.getStringExtra("verificationId") ?: ""
        
        // Initialize UI
        otpInput = findViewById(R.id.otpInput)
        otpInputLayout = findViewById(R.id.otpInputLayout)
        verifyButton = findViewById(R.id.verifyButton)
        phoneNumberTextView = findViewById(R.id.phoneNumberTextView)
        resendOtpTextView = findViewById(R.id.resendOtpTextView)
        
        // Set phone number
        phoneNumberTextView.text = "We sent an OTP to $phoneNumber"
        
        // Set up OTP input validation
        otpInput.addTextChangedListener(object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {}
            override fun afterTextChanged(s: Editable?) {
                validateOtpInput()
            }
        })
        
        // Set up verify button
        verifyButton.setOnClickListener {
            verifyOTP()
        }
        
        // Set up resend OTP
        resendOtpTextView.setOnClickListener {
            resendOTP()
        }
        
        // Observe login state
        authViewModel.loginState.observe(this) { (success, user) ->
            if (success && user != null) {
                // Navigate to main activity
                val intent = Intent(this, MainActivity::class.java)
                startActivity(intent)
                finishAffinity()
            } else if (!success) {
                Toast.makeText(this, "Invalid OTP", Toast.LENGTH_SHORT).show()
            }
        }
        
        // Observe loading state
        authViewModel.isLoading.observe(this) { isLoading ->
            verifyButton.isEnabled = !isLoading
            verifyButton.text = if (isLoading) "Verifying..." else "Verify"
        }
        
        // Observe error messages
        authViewModel.errorMessage.observe(this) { error ->
            error?.let {
                Toast.makeText(this, it, Toast.LENGTH_SHORT).show()
            }
        }
    }
    
    private fun validateOtpInput() {
        val otp = otpInput.text.toString().trim()
        val isValid = otp.length == 6
        
        otpInputLayout.error = if (isValid) null else "Please enter 6-digit OTP"
        verifyButton.isEnabled = isValid
    }
    
    private fun verifyOTP() {
        val otp = otpInput.text.toString().trim()
        authViewModel.verifyOTP(verificationId, otp)
    }
    
    private fun resendOTP() {
        authViewModel.sendOTP(phoneNumber)
        Toast.makeText(this, "OTP resent", Toast.LENGTH_SHORT).show()
    }
}
