package com.altron.calls

import android.content.Context
import android.media.AudioManager
import android.util.Log
import com.altron.models.Call
import com.altron.models.CallStatus
import com.altron.models.CallType
import com.altron.network.TailscaleManager
import com.google.firebase.firestore.FirebaseFirestore
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.tasks.await
import org.webrtc.*
import java.util.*

class CallManager(private val context: Context) {
    
    companion object {
        private const val TAG = "CallManager"
        private var instance: CallManager? = null
        
        fun getInstance(context: Context): CallManager {
            if (instance == null) {
                instance = CallManager(context)
            }
            return instance!!
        }
    }
    
    private val firestore: FirebaseFirestore = FirebaseFirestore.getInstance()
    private val callsCollection = firestore.collection("calls")
    
    // WebRTC components
    private val peerConnectionFactory: PeerConnectionFactory
    private val rootEglBase: EglBase
    private val peerConnections: MutableMap<String, PeerConnection> = mutableMapOf()
    private val dataChannels: MutableMap<String, DataChannel> = mutableMapOf()
    
    // Call state
    private var currentCall: Call? = null
    private var isMuted = false
    private var isSpeakerphone = false
    private var isVideoEnabled = true
    
    // Callbacks
    private var callStateCallbacks: MutableList<(Call) -> Unit> = mutableListOf()
    private var callEventCallbacks: MutableList<(CallEvent) -> Unit> = mutableListOf()
    
    // ICE servers configuration
    private val iceServers: List<PeerConnection.IceServer> = listOf(
        PeerConnection.IceServer.builder("stun:stun.l.google.com:19302").createIceServer(),
        PeerConnection.IceServer.builder("stun:stun1.l.google.com:19302").createIceServer(),
        PeerConnection.IceServer.builder("stun:stun2.l.google.com:19302").createIceServer()
    )
    
    // Media constraints
    private val sdpConstraints: MediaConstraints = MediaConstraints().apply {
        mandatory.add(MediaConstraints.KeyValuePair("offerToReceiveAudio", "true"))
        mandatory.add(MediaConstraints.KeyValuePair("offerToReceiveVideo", "true"))
    }
    
    init {
        // Initialize WebRTC
        PeerConnectionFactory.initialize(PeerConnectionFactory.InitializationOptions.builder(context).createInitializationOptions())
        
        val options = PeerConnectionFactory.Options()
        rootEglBase = EglBase.create()
        
        peerConnectionFactory = PeerConnectionFactory.builder()
            .setOptions(options)
            .createPeerConnectionFactory()
        
        // Set up audio manager
        val audioManager = context.getSystemService(Context.AUDIO_SERVICE) as AudioManager
        audioManager.mode = AudioManager.MODE_IN_COMMUNICATION
    }
    
    enum class CallEvent {
        CALL_STARTED, CALL_ENDED, CALL_MISSED, CALL_REJECTED, 
        AUDIO_MUTED, AUDIO_UNMUTED, SPEAKERPHONE_ON, SPEAKERPHONE_OFF,
        VIDEO_ENABLED, VIDEO_DISABLED, CONNECTION_ESTABLISHED, CONNECTION_FAILED
    }
    
    fun addCallStateCallback(callback: (Call) -> Unit) {
        callStateCallbacks.add(callback)
    }
    
    fun removeCallStateCallback(callback: (Call) -> Unit) {
        callStateCallbacks.remove(callback)
    }
    
    fun addCallEventCallback(callback: (CallEvent) -> Unit) {
        callEventCallbacks.add(callback)
    }
    
    fun removeCallEventCallback(callback: (CallEvent) -> Unit) {
        callEventCallbacks.remove(callback)
    }
    
    private fun notifyCallState(call: Call) {
        callStateCallbacks.forEach { it(call) }
    }
    
    private fun notifyCallEvent(event: CallEvent) {
        callEventCallbacks.forEach { it(event) }
    }
    
    fun startCall(
        callerId: String,
        receiverId: String,
        callType: CallType,
        callback: (Boolean, Call?) -> Unit
    ) {
        CoroutineScope(Dispatchers.IO).launch {
            try {
                // Check if receiver is online and has Tailscale
                val receiverSnapshot = firestore.collection("users").document(receiverId).get().await()
                
                if (!receiverSnapshot.exists()) {
                    callback(false, null)
                    return@launch
                }
                
                val receiverNodeId = receiverSnapshot.getString("tailscaleNodeId") ?: ""
                val receiverIp = receiverSnapshot.getString("tailscaleIp") ?: ""
                
                if (receiverNodeId.isEmpty() || receiverIp.isEmpty()) {
                    callback(false, null)
                    return@launch
                }
                
                // Check if Tailscale is connected
                if (!TailscaleManager.isTailscaleConnected()) {
                    callback(false, null)
                    return@launch
                }
                
                // Create call record
                val callId = generateCallId()
                val call = Call(
                    callId = callId,
                    callerId = callerId,
                    receiverId = receiverId,
                    callType = callType,
                    status = CallStatus.RINGING,
                    startTime = System.currentTimeMillis(),
                    isIncoming = false,
                    tailscaleIp = receiverIp,
                    peerConnectionId = ""
                )
                
                currentCall = call
                
                // Save call to Firestore
                callsCollection.document(callId).set(call.toMap()).await()
                
                // Create peer connection
                createPeerConnection(callId, callerId, receiverId, callType, false)
                
                // Send call invitation via Tailscale
                sendCallInvitation(callId, callerId, receiverId, callType)
                
                callback(true, call)
                notifyCallState(call)
                notifyCallEvent(CallEvent.CALL_STARTED)
                
            } catch (e: Exception) {
                Log.e(TAG, "Failed to start call", e)
                callback(false, null)
            }
        }
    }
    
    fun endCall(callId: String, callback: (Boolean) -> Unit) {
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val call = currentCall ?: return@launch
                
                // Update call status
                val endTime = System.currentTimeMillis()
                val duration = endTime - call.startTime
                
                val updatedCall = call.copy(
                    status = CallStatus.DISCONNECTED,
                    endTime = endTime,
                    duration = duration
                )
                
                callsCollection.document(callId).update(
                    "status", CallStatus.DISCONNECTED.name,
                    "endTime", endTime,
                    "duration", duration
                ).await()
                
                // Close peer connection
                closePeerConnection(callId)
                
                currentCall = null
                
                callback(true)
                notifyCallState(updatedCall)
                notifyCallEvent(CallEvent.CALL_ENDED)
                
            } catch (e: Exception) {
                Log.e(TAG, "Failed to end call", e)
                callback(false)
            }
        }
    }
    
    fun rejectCall(callId: String, callback: (Boolean) -> Unit) {
        CoroutineScope(Dispatchers.IO).launch {
            try {
                callsCollection.document(callId).update(
                    "status", CallStatus.REJECTED.name,
                    "endTime", System.currentTimeMillis()
                ).await()
                
                closePeerConnection(callId)
                currentCall = null
                
                callback(true)
                notifyCallEvent(CallEvent.CALL_REJECTED)
                
            } catch (e: Exception) {
                Log.e(TAG, "Failed to reject call", e)
                callback(false)
            }
        }
    }
    
    fun acceptCall(callId: String, callback: (Boolean) -> Unit) {
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val callSnapshot = callsCollection.document(callId).get().await()
                
                if (!callSnapshot.exists()) {
                    callback(false)
                    return@launch
                }
                
                val call = Call.fromMap(callSnapshot.data!!)
                
                // Update call status
                callsCollection.document(callId).update(
                    "status", CallStatus.CONNECTED.name
                ).await()
                
                // Create peer connection
                createPeerConnection(
                    callId, 
                    call.receiverId, 
                    call.callerId, 
                    call.callType, 
                    true
                )
                
                currentCall = call.copy(status = CallStatus.CONNECTED)
                
                callback(true)
                notifyCallState(currentCall!!)
                notifyCallEvent(CallEvent.CONNECTION_ESTABLISHED)
                
            } catch (e: Exception) {
                Log.e(TAG, "Failed to accept call", e)
                callback(false)
            }
        }
    }
    
    private fun createPeerConnection(
        callId: String,
        localUserId: String,
        remoteUserId: String,
        callType: CallType,
        isIncoming: Boolean
    ) {
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val peerConnection = peerConnectionFactory.createPeerConnection(
                    iceServers,
                    sdpConstraints,
                    object : PeerConnection.Observer {
                        override fun onSignalingChange(signalingState: PeerConnection.SignalingState?) {
                            Log.d(TAG, "Signaling state changed: $signalingState")
                        }
                        
                        override fun onIceConnectionChange(iceConnectionState: PeerConnection.IceConnectionState?) {
                            Log.d(TAG, "ICE connection state changed: $iceConnectionState")
                            if (iceConnectionState == PeerConnection.IceConnectionState.CONNECTED) {
                                notifyCallEvent(CallEvent.CONNECTION_ESTABLISHED)
                            } else if (iceConnectionState == PeerConnection.IceConnectionState.FAILED) {
                                notifyCallEvent(CallEvent.CONNECTION_FAILED)
                            }
                        }
                        
                        override fun onIceConnectionReceivingChange(receiving: Boolean) {
                            Log.d(TAG, "ICE connection receiving changed: $receiving")
                        }
                        
                        override fun onIceCandidate(candidate: IceCandidate?) {
                            candidate?.let { 
                                // Send ICE candidate to remote peer via Tailscale
                                sendIceCandidate(callId, localUserId, remoteUserId, candidate)
                            }
                        }
                        
                        override fun onIceCandidatesRemoved(candidates: Array<out IceCandidate>?) {
                            Log.d(TAG, "ICE candidates removed")
                        }
                        
                        override fun onAddStream(mediaStream: MediaStream?) {
                            Log.d(TAG, "Stream added")
                            mediaStream?.let { 
                                // Handle remote stream
                                handleRemoteStream(callId, it)
                            }
                        }
                        
                        override fun onRemoveStream(mediaStream: MediaStream?) {
                            Log.d(TAG, "Stream removed")
                        }
                        
                        override fun onDataChannel(dataChannel: DataChannel?) {
                            dataChannel?.let { 
                                dataChannels[callId] = it
                                setupDataChannel(callId, it)
                            }
                        }
                        
                        override fun onRenegotiationNeeded() {
                            Log.d(TAG, "Renegotiation needed")
                        }
                        
                        override fun onAddTrack(rtpTransceiver: RtpTransceiver?) {
                            Log.d(TAG, "Track added")
                        }
                    }
                )
                
                peerConnections[callId] = peerConnection
                
                // Create data channel for signaling
                val dataChannel = peerConnection.createDataChannel("signaling", DataChannel.Init().apply {
                    ordered = true
                    maxRetransmits = 0
                    maxRetransmitTimeMs = -1
                    protocol = ""
                    negotiated = false
                })
                
                dataChannels[callId] = dataChannel
                setupDataChannel(callId, dataChannel)
                
                // Add local media stream
                addLocalMediaStream(callId, callType)
                
                // Create offer
                peerConnection.createOffer(object : SdpObserver {
                    override fun onCreateSuccess(sdp: SessionDescription?) {
                        sdp?.let { 
                            peerConnection.setLocalDescription(object : SdpObserver {
                                override fun onSetSuccess() {
                                    // Send offer to remote peer
                                    sendSdpOffer(callId, localUserId, remoteUserId, sdp)
                                }
                                override fun onSetFailure(error: String?) {
                                    Log.e(TAG, "Failed to set local description: $error")
                                }
                            }, sdp)
                        }
                    }
                    
                    override fun onSetSuccess() {
                        Log.d(TAG, "Offer set successfully")
                    }
                    
                    override fun onCreateFailure(error: String?) {
                        Log.e(TAG, "Failed to create offer: $error")
                    }
                    
                    override fun onSetFailure(error: String?) {
                        Log.e(TAG, "Failed to set offer: $error")
                    }
                }, sdpConstraints)
                
            } catch (e: Exception) {
                Log.e(TAG, "Failed to create peer connection", e)
            }
        }
    }
    
    private fun addLocalMediaStream(callId: String, callType: CallType) {
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val peerConnection = peerConnections[callId] ?: return@launch
                
                // Create audio source
                val audioSource = peerConnectionFactory.createAudioSource(MediaConstraints())
                val audioTrack = peerConnectionFactory.createAudioTrack("audio", audioSource)
                
                // Create video source if video call
                var videoTrack: VideoTrack? = null
                if (callType == CallType.VIDEO) {
                    val videoSource = peerConnectionFactory.createVideoSource(false)
                    videoTrack = peerConnectionFactory.createVideoTrack("video", videoSource)
                }
                
                // Create local stream
                val localStream = peerConnectionFactory.createLocalMediaStream("local")
                localStream.addTrack(audioTrack)
                videoTrack?.let { localStream.addTrack(it) }
                
                // Add stream to peer connection
                peerConnection.addStream(localStream)
                
            } catch (e: Exception) {
                Log.e(TAG, "Failed to add local media stream", e)
            }
        }
    }
    
    private fun handleRemoteStream(callId: String, mediaStream: MediaStream) {
        // Handle remote audio/video stream
        // This would be passed to the UI for rendering
        Log.d(TAG, "Remote stream received for call $callId")
    }
    
    private fun setupDataChannel(callId: String, dataChannel: DataChannel) {
        dataChannel.registerObserver(object : DataChannel.Observer {
            override fun onBufferedAmountChange(amount: Long) {
                Log.d(TAG, "Data channel buffered amount changed: $amount")
            }
            
            override fun onStateChange() {
                Log.d(TAG, "Data channel state changed: ${dataChannel.state()}")
                if (dataChannel.state() == DataChannel.State.OPEN) {
                    // Data channel is ready
                }
            }
            
            override fun onMessage(buffer: DataChannel.Buffer) {
                // Handle incoming messages (ICE candidates, SDP answers, etc.)
                val data = ByteArray(buffer.data.remaining())
                buffer.data.get(data)
                handleDataChannelMessage(callId, data)
            }
        })
    }
    
    private fun handleDataChannelMessage(callId: String, data: ByteArray) {
        // Parse message and handle accordingly
        // This would handle SDP answers, ICE candidates, etc.
        Log.d(TAG, "Received data channel message for call $callId")
    }
    
    private fun sendCallInvitation(callId: String, callerId: String, receiverId: String, callType: CallType) {
        CoroutineScope(Dispatchers.IO).launch {
            try {
                // Get receiver's Tailscale node ID
                val receiverSnapshot = firestore.collection("users").document(receiverId).get().await()
                val receiverNodeId = receiverSnapshot.getString("tailscaleNodeId") ?: ""
                
                if (receiverNodeId.isNotEmpty()) {
                    // Create invitation data
                    val invitationData = mapOf(
                        "type" to "call_invitation",
                        "callId" to callId,
                        "callerId" to callerId,
                        "receiverId" to receiverId,
                        "callType" to callType.name,
                        "timestamp" to System.currentTimeMillis()
                    )
                    
                    // Convert to bytes and send via Tailscale
                    val data = com.altron.utils.EncryptionUtils.serializeMap(invitationData)
                    TailscaleManager.sendDataToPeer(receiverNodeId, data) { success ->
                        if (!success) {
                            Log.e(TAG, "Failed to send call invitation via Tailscale")
                        }
                    }
                }
            } catch (e: Exception) {
                Log.e(TAG, "Failed to send call invitation", e)
            }
        }
    }
    
    private fun sendSdpOffer(callId: String, localUserId: String, remoteUserId: String, sdp: SessionDescription) {
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val receiverSnapshot = firestore.collection("users").document(remoteUserId).get().await()
                val receiverNodeId = receiverSnapshot.getString("tailscaleNodeId") ?: ""
                
                if (receiverNodeId.isNotEmpty()) {
                    val offerData = mapOf(
                        "type" to "sdp_offer",
                        "callId" to callId,
                        "senderId" to localUserId,
                        "receiverId" to remoteUserId,
                        "sdp" to sdp.description,
                        "sdpType" to sdp.type.name
                    )
                    
                    val data = com.altron.utils.EncryptionUtils.serializeMap(offerData)
                    TailscaleManager.sendDataToPeer(receiverNodeId, data) { success ->
                        if (!success) {
                            Log.e(TAG, "Failed to send SDP offer via Tailscale")
                        }
                    }
                }
            } catch (e: Exception) {
                Log.e(TAG, "Failed to send SDP offer", e)
            }
        }
    }
    
    private fun sendIceCandidate(callId: String, localUserId: String, remoteUserId: String, candidate: IceCandidate) {
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val receiverSnapshot = firestore.collection("users").document(remoteUserId).get().await()
                val receiverNodeId = receiverSnapshot.getString("tailscaleNodeId") ?: ""
                
                if (receiverNodeId.isNotEmpty()) {
                    val candidateData = mapOf(
                        "type" to "ice_candidate",
                        "callId" to callId,
                        "senderId" to localUserId,
                        "receiverId" to remoteUserId,
                        "sdpMid" to candidate.sdpMid,
                        "sdpMLineIndex" to candidate.sdpMLineIndex,
                        "sdp" to candidate.sdp
                    )
                    
                    val data = com.altron.utils.EncryptionUtils.serializeMap(candidateData)
                    TailscaleManager.sendDataToPeer(receiverNodeId, data) { success ->
                        if (!success) {
                            Log.e(TAG, "Failed to send ICE candidate via Tailscale")
                        }
                    }
                }
            } catch (e: Exception) {
                Log.e(TAG, "Failed to send ICE candidate", e)
            }
        }
    }
    
    fun handleIncomingCall(callId: String, callerId: String, callType: CallType) {
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val call = Call(
                    callId = callId,
                    callerId = callerId,
                    receiverId = getCurrentUserId() ?: return@launch,
                    callType = callType,
                    status = CallStatus.RINGING,
                    startTime = System.currentTimeMillis(),
                    isIncoming = true,
                    tailscaleIp = "",
                    peerConnectionId = ""
                )
                
                currentCall = call
                callsCollection.document(callId).set(call.toMap()).await()
                
                notifyCallState(call)
                notifyCallEvent(CallEvent.CALL_STARTED)
                
            } catch (e: Exception) {
                Log.e(TAG, "Failed to handle incoming call", e)
            }
        }
    }
    
    fun handleSdpAnswer(callId: String, sdp: SessionDescription) {
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val peerConnection = peerConnections[callId] ?: return@launch
                
                peerConnection.setRemoteDescription(object : SdpObserver {
                    override fun onSetSuccess() {
                        Log.d(TAG, "Remote description set successfully")
                    }
                    
                    override fun onSetFailure(error: String?) {
                        Log.e(TAG, "Failed to set remote description: $error")
                    }
                }, sdp)
                
            } catch (e: Exception) {
                Log.e(TAG, "Failed to handle SDP answer", e)
            }
        }
    }
    
    fun handleIceCandidate(callId: String, candidate: IceCandidate) {
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val peerConnection = peerConnections[callId] ?: return@launch
                peerConnection.addIceCandidate(candidate)
            } catch (e: Exception) {
                Log.e(TAG, "Failed to handle ICE candidate", e)
            }
        }
    }
    
    private fun closePeerConnection(callId: String) {
        CoroutineScope(Dispatchers.IO).launch {
            try {
                peerConnections[callId]?.let { peerConnection ->
                    peerConnection.close()
                    peerConnection.dispose()
                    peerConnections.remove(callId)
                }
                
                dataChannels[callId]?.let { dataChannel ->
                    dataChannel.close()
                    dataChannels.remove(callId)
                }
                
            } catch (e: Exception) {
                Log.e(TAG, "Failed to close peer connection", e)
            }
        }
    }
    
    fun toggleMute() {
        isMuted = !isMuted
        // Implement mute logic
        notifyCallEvent(if (isMuted) CallEvent.AUDIO_MUTED else CallEvent.AUDIO_UNMUTED)
    }
    
    fun toggleSpeakerphone() {
        isSpeakerphone = !isSpeakerphone
        val audioManager = context.getSystemService(Context.AUDIO_SERVICE) as AudioManager
        audioManager.isSpeakerphoneOn = isSpeakerphone
        notifyCallEvent(if (isSpeakerphone) CallEvent.SPEAKERPHONE_ON else CallEvent.SPEAKERPHONE_OFF)
    }
    
    fun toggleVideo() {
        isVideoEnabled = !isVideoEnabled
        // Implement video toggle logic
        notifyCallEvent(if (isVideoEnabled) CallEvent.VIDEO_ENABLED else CallEvent.VIDEO_DISABLED)
    }
    
    fun getCurrentCall(): Call? = currentCall
    
    fun isInCall(): Boolean = currentCall != null
    
    private fun generateCallId(): String {
        return "call_${System.currentTimeMillis()}_${(Math.random() * 1000).toInt()}"
    }
    
    private fun getCurrentUserId(): String? {
        return com.altron.auth.AuthManager.getInstance(context).getCurrentUserId()
    }
    
    fun cleanup() {
        // Close all peer connections
        peerConnections.values.forEach { peerConnection ->
            peerConnection.close()
            peerConnection.dispose()
        }
        peerConnections.clear()
        
        dataChannels.values.forEach { dataChannel ->
            dataChannel.close()
        }
        dataChannels.clear()
        
        currentCall = null
    }
}
