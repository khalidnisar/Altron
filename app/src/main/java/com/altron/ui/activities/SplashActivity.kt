package com.altron.ui.activities

import android.content.Intent
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.ViewModelProvider
import com.altron.R
import com.altron.viewmodels.AuthViewModel

class SplashActivity : AppCompatActivity() {
    
    private lateinit var authViewModel: AuthViewModel
    
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_splash)
        
        // Initialize ViewModel
        authViewModel = ViewModelProvider(this).get(AuthViewModel::class.java)
        
        // Set up UI
        val appNameTextView = findViewById<TextView>(R.id.appNameTextView)
        appNameTextView.text = "Altron"
        
        // Check authentication state
        authViewModel.checkAuthState()
        
        // Observe auth state
        authViewModel.authState.observe(this) { isAuthenticated ->
            navigateToNextScreen(isAuthenticated)
        }
        
        // Fallback: navigate after 3 seconds if auth state is not determined
        Handler(Looper.getMainLooper()).postDelayed({
            navigateToNextScreen(authViewModel.authState.value ?: false)
        }, 3000)
    }
    
    private fun navigateToNextScreen(isAuthenticated: Boolean) {
        val nextIntent = if (isAuthenticated) {
            Intent(this, MainActivity::class.java)
        } else {
            Intent(this, LoginActivity::class.java)
        }
        
        startActivity(nextIntent)
        finish()
    }
}
