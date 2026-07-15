package com.altron.ui.activities

import android.content.Intent
import android.os.Bundle
import android.view.Menu
import android.view.MenuItem
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.appcompat.widget.Toolbar
import androidx.drawerlayout.widget.DrawerLayout
import androidx.lifecycle.ViewModelProvider
import androidx.navigation.findNavController
import androidx.navigation.ui.AppBarConfiguration
import androidx.navigation.ui.setupActionBarWithNavController
import androidx.navigation.ui.setupWithNavController
import com.altron.R
import com.altron.viewmodels.AuthViewModel
import com.google.android.material.bottomnavigation.BottomNavigationView
import com.google.android.material.navigation.NavigationView

class MainActivity : AppCompatActivity() {
    
    private lateinit var authViewModel: AuthViewModel
    private lateinit var appBarConfiguration: AppBarConfiguration
    
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        
        // Initialize ViewModel
        authViewModel = ViewModelProvider(this).get(AuthViewModel::class.java)
        
        // Set up toolbar
        val toolbar = findViewById<Toolbar>(R.id.toolbar)
        setSupportActionBar(toolbar)
        
        // Set up navigation
        val navController = findNavController(R.id.nav_host_fragment)
        val bottomNavView = findViewById<BottomNavigationView>(R.id.bottom_nav_view)
        val drawerLayout = findViewById<DrawerLayout>(R.id.drawer_layout)
        val navView = findViewById<NavigationView>(R.id.navigation_view)
        
        // Configure app bar
        appBarConfiguration = AppBarConfiguration(
            setOf(
                R.id.navigation_contacts,
                R.id.navigation_calls,
                R.id.navigation_settings
            ),
            drawerLayout
        )
        
        setupActionBarWithNavController(navController, appBarConfiguration)
        bottomNavView.setupWithNavController(navController)
        navView.setupWithNavController(navController)
        
        // Set up navigation header
        val navHeader = navView.getHeaderView(0)
        val userNameTextView = navHeader.findViewById<TextView>(R.id.userNameTextView)
        val userPhoneTextView = navHeader.findViewById<TextView>(R.id.userPhoneTextView)
        
        // Observe current user
        authViewModel.currentUser.observe(this) { user ->
            user?.let {
                userNameTextView.text = it.displayName
                userPhoneTextView.text = it.phoneNumber
            }
        }
        
        // Handle navigation item selection
        navView.setNavigationItemSelectedListener { menuItem ->
            when (menuItem.itemId) {
                R.id.nav_profile -> {
                    // Navigate to profile
                    true
                }
                R.id.nav_my_qr -> {
                    // Navigate to my QR code
                    startActivity(Intent(this, MyQRCodeActivity::class.java))
                    true
                }
                R.id.nav_scan_qr -> {
                    // Navigate to QR scanner
                    startActivity(Intent(this, QRScannerActivity::class.java))
                    true
                }
                R.id.nav_logout -> {
                    logout()
                    true
                }
                else -> false
            }
        }
        
        // Check for incoming call
        checkForIncomingCall()
    }
    
    private fun checkForIncomingCall() {
        if (intent.hasExtra("callId") && intent.getBooleanExtra("isIncoming", false)) {
            val callId = intent.getStringExtra("callId") ?: ""
            val callerId = intent.getStringExtra("callerId") ?: ""
            val callType = intent.getStringExtra("callType") ?: "VOICE"
            
            // Handle incoming call
            // This would typically show a call notification or start CallActivity
        }
    }
    
    private fun logout() {
        authViewModel.logout()
        val intent = Intent(this, LoginActivity::class.java)
        startActivity(intent)
        finishAffinity()
    }
    
    override fun onCreateOptionsMenu(menu: Menu): Boolean {
        menuInflater.inflate(R.menu.main_menu, menu)
        return true
    }
    
    override fun onOptionsItemSelected(item: MenuItem): Boolean {
        when (item.itemId) {
            R.id.action_search -> {
                // Handle search
                return true
            }
            R.id.action_scan_qr -> {
                startActivity(Intent(this, QRScannerActivity::class.java))
                return true
            }
            else -> return super.onOptionsItemSelected(item)
        }
    }
    
    override fun onSupportNavigateUp(): Boolean {
        val navController = findNavController(R.id.nav_host_fragment)
        return navController.navigateUp(appBarConfiguration) || super.onSupportNavigateUp()
    }
}
