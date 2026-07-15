package com.altron

import android.app.Application
import android.content.Context
import com.altron.network.TailscaleManager
import com.altron.services.CallService
import com.google.firebase.FirebaseApp
import com.google.firebase.firestore.FirebaseFirestore
import com.google.firebase.firestore.FirebaseFirestoreSettings

class AltronApp : Application() {
    
    companion object {
        private lateinit var instance: AltronApp
        fun getContext(): Context = instance.applicationContext
    }
    
    override fun onCreate() {
        super.onCreate()
        instance = this
        
        // Initialize Firebase
        FirebaseApp.initializeApp(this)
        
        // Configure Firestore
        val firestore = FirebaseFirestore.getInstance()
        val settings = FirebaseFirestoreSettings.Builder()
            .setPersistenceEnabled(true)
            .build()
        firestore.firestoreSettings = settings
        
        // Initialize Tailscale
        TailscaleManager.init(this)
        
        // Start Call Service
        CallService.start(this)
    }
}
