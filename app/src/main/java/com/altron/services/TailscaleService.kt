package com.altron.services

import android.app.Service
import android.content.Intent
import android.os.IBinder
import android.util.Log
import com.altron.network.TailscaleManager

class TailscaleService : Service() {
    
    companion object {
        private const val TAG = "TailscaleService"
    }
    
    override fun onCreate() {
        super.onCreate()
        Log.d(TAG, "TailscaleService created")
        
        // Initialize Tailscale manager
        TailscaleManager.init(this)
    }
    
    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        Log.d(TAG, "TailscaleService started")
        
        // Start Tailscale connection
        TailscaleManager.getTailscale()?.startService()
        
        return START_STICKY
    }
    
    override fun onDestroy() {
        super.onDestroy()
        Log.d(TAG, "TailscaleService destroyed")
        
        // Stop Tailscale connection
        TailscaleManager.stopTailscale()
    }
    
    override fun onBind(intent: Intent?): IBinder? {
        return null
    }
}
