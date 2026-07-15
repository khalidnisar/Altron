package com.altron.network

import android.content.Context
import android.util.Log
import com.altron.AltronApp
import com.tailscale.ipn.DeviceState
import com.tailscale.ipn.Tailscale
import com.tailscale.ipn.TailscaleCallback
import com.tailscale.ipn.TailscaleService
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

object TailscaleManager : TailscaleCallback {
    
    private const val TAG = "TailscaleManager"
    private var tailscale: Tailscale? = null
    private var context: Context? = null
    private var isConnected = false
    private var nodeId: String = ""
    private var tailscaleIp: String = ""
    
    // Callbacks
    private var connectionCallbacks: MutableList<(Boolean, String, String) -> Unit> = mutableListOf()
    private var stateCallbacks: MutableList<(DeviceState) -> Unit> = mutableListOf()
    
    fun init(context: Context) {
        this.context = context
        tailscale = Tailscale.getInstance(context)
        tailscale?.setCallback(this)
        
        // Start Tailscale service
        CoroutineScope(Dispatchers.IO).launch {
            startTailscale()
        }
    }
    
    private fun startTailscale() {
        try {
            tailscale?.startService()
            Log.d(TAG, "Tailscale service started")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to start Tailscale service", e)
        }
    }
    
    fun stopTailscale() {
        try {
            tailscale?.stopService()
            Log.d(TAG, "Tailscale service stopped")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to stop Tailscale service", e)
        }
    }
    
    fun getTailscale(): Tailscale? = tailscale
    
    fun isTailscaleConnected(): Boolean = isConnected
    
    fun getNodeId(): String = nodeId
    
    fun getTailscaleIp(): String = tailscaleIp
    
    fun getPeerIp(nodeId: String): String? {
        return try {
            tailscale?.getPeerIp(nodeId)
        } catch (e: Exception) {
            Log.e(TAG, "Failed to get peer IP for $nodeId", e)
            null
        }
    }
    
    fun addConnectionCallback(callback: (Boolean, String, String) -> Unit) {
        connectionCallbacks.add(callback)
    }
    
    fun removeConnectionCallback(callback: (Boolean, String, String) -> Unit) {
        connectionCallbacks.remove(callback)
    }
    
    fun addStateCallback(callback: (DeviceState) -> Unit) {
        stateCallbacks.add(callback)
    }
    
    fun removeStateCallback(callback: (DeviceState) -> Unit) {
        stateCallbacks.remove(callback)
    }
    
    // TailscaleCallback methods
    override fun onServiceConnected(service: TailscaleService) {
        Log.d(TAG, "Tailscale service connected")
        tailscale = service
    }
    
    override fun onServiceDisconnected() {
        Log.d(TAG, "Tailscale service disconnected")
        isConnected = false
        connectionCallbacks.forEach { it(false, "", "") }
    }
    
    override fun onStateChanged(state: DeviceState) {
        Log.d(TAG, "Tailscale state changed: ${state.state}")
        
        when (state.state) {
            DeviceState.State.RUNNING -> {
                isConnected = true
                nodeId = state.nodeId ?: ""
                tailscaleIp = state.tailscaleIp ?: ""
                
                Log.d(TAG, "Tailscale connected - Node ID: $nodeId, IP: $tailscaleIp")
                connectionCallbacks.forEach { it(true, nodeId, tailscaleIp) }
            }
            DeviceState.State.STOPPED -> {
                isConnected = false
                nodeId = ""
                tailscaleIp = ""
                connectionCallbacks.forEach { it(false, "", "") }
            }
            else -> {
                // Other states: STARTING, STOPPING, etc.
            }
        }
        
        stateCallbacks.forEach { it(state) }
    }
    
    override fun onLoginChanged(loggedIn: Boolean) {
        Log.d(TAG, "Tailscale login changed: $loggedIn")
    }
    
    override fun onPeerChanged(peerId: String, online: Boolean) {
        Log.d(TAG, "Peer $peerId changed online status: $online")
    }
    
    // Utility methods for direct peer-to-peer communication
    fun sendDataToPeer(nodeId: String, data: ByteArray, callback: (Boolean) -> Unit) {
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val peerIp = getPeerIp(nodeId)
                if (peerIp != null) {
                    // Use Tailscale's direct connection
                    val success = tailscale?.sendData(peerIp, data) ?: false
                    callback(success)
                } else {
                    callback(false)
                }
            } catch (e: Exception) {
                Log.e(TAG, "Failed to send data to peer $nodeId", e)
                callback(false)
            }
        }
    }
    
    fun createDirectConnection(nodeId: String, callback: (Boolean, String?) -> Unit) {
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val peerIp = getPeerIp(nodeId)
                if (peerIp != null) {
                    // Create a direct connection channel
                    val connectionId = tailscale?.createConnection(peerIp)
                    callback(connectionId != null, connectionId)
                } else {
                    callback(false, null)
                }
            } catch (e: Exception) {
                Log.e(TAG, "Failed to create direct connection to $nodeId", e)
                callback(false, null)
            }
        }
    }
}
