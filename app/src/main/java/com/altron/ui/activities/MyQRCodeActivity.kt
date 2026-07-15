package com.altron.ui.activities

import android.graphics.Bitmap
import android.os.Bundle
import android.widget.ImageView
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.ViewModelProvider
import com.altron.R
import com.altron.qr.QRCodeManager
import com.altron.viewmodels.AuthViewModel

class MyQRCodeActivity : AppCompatActivity() {
    
    private lateinit var authViewModel: AuthViewModel
    private lateinit var qrCodeImageView: ImageView
    private lateinit var userNameTextView: TextView
    private lateinit var userPhoneTextView: TextView
    
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_my_qr_code)
        
        // Initialize ViewModel
        authViewModel = ViewModelProvider(this).get(AuthViewModel::class.java)
        
        // Initialize UI
        qrCodeImageView = findViewById(R.id.qrCodeImageView)
        userNameTextView = findViewById(R.id.userNameTextView)
        userPhoneTextView = findViewById(R.id.userPhoneTextView)
        
        // Observe current user
        authViewModel.currentUser.observe(this) { user ->
            user?.let { updateQRCode(it) }
        }
        
        // Check current user
        authViewModel.checkAuthState()
    }
    
    private fun updateQRCode(user: com.altron.models.User) {
        userNameTextView.text = user.displayName
        userPhoneTextView.text = user.phoneNumber
        
        // Generate QR code
        val qrCodeBitmap = QRCodeManager.generateShareableQRCode(
            user.userId, 
            user.phoneNumber, 
            user.displayName
        )
        
        qrCodeImageView.setImageBitmap(qrCodeBitmap)
    }
}
