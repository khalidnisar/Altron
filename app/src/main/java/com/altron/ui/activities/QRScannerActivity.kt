package com.altron.ui.activities

import android.content.Intent
import android.os.Bundle
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import com.altron.R
import com.altron.viewmodels.ContactsViewModel
import com.google.zxing.integration.android.IntentIntegrator
import com.google.zxing.integration.android.IntentResult
import com.journeyapps.barcodescanner.CaptureActivity

class QRScannerActivity : AppCompatActivity() {
    
    private lateinit var contactsViewModel: ContactsViewModel
    
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_qr_scanner)
        
        // Initialize ViewModel
        contactsViewModel = ContactsViewModel(this.application)
        
        // Start QR scanner
        startQRScanner()
    }
    
    private fun startQRScanner() {
        val integrator = IntentIntegrator(this)
        integrator.setCaptureActivity(CaptureActivity::class.java)
        integrator.setOrientationLocked(true)
        integrator.setDesiredBarcodeFormats(IntentIntegrator.QR_CODE)
        integrator.setPrompt("Scan QR code to add contact")
        integrator.initiateScan()
    }
    
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        
        val result: IntentResult = IntentIntegrator.parseActivityResult(requestCode, resultCode, data)
        
        if (result != null) {
            if (result.contents == null) {
                Toast.makeText(this, "Scan cancelled", Toast.LENGTH_SHORT).show()
                finish()
            } else {
                handleQRCodeResult(result.contents)
            }
        } else {
            super.onActivityResult(requestCode, resultCode, data)
        }
    }
    
    private fun handleQRCodeResult(qrCode: String) {
        // Parse QR code and get user info
        contactsViewModel.getUserByQRCode(qrCode) { user ->
            if (user != null) {
                // User found, add as contact
                val currentUserId = intent.getStringExtra("currentUserId") ?: ""
                if (currentUserId.isNotEmpty()) {
                    contactsViewModel.addContact(currentUserId, user.userId)
                }
                
                // Show user info and option to chat
                val intent = Intent(this, ChatActivity::class.java).apply {
                    putExtra("receiverId", user.userId)
                    putExtra("receiverName", user.displayName)
                    putExtra("receiverPhone", user.phoneNumber)
                }
                startActivity(intent)
                finish()
            } else {
                Toast.makeText(this, "Invalid QR code or user not found", Toast.LENGTH_SHORT).show()
                finish()
            }
        }
    }
}
