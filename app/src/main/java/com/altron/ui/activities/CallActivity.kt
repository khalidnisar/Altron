package com.altron.ui.activities

import android.content.Intent
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.View
import android.view.WindowManager
import android.widget.Chronometer
import android.widget.ImageButton
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.ViewModelProvider
import com.altron.R
import com.altron.models.CallStatus
import com.altron.models.CallType
import com.altron.utils.PermissionUtils
import com.altron.viewmodels.CallViewModel
import org.webrtc.SurfaceViewRenderer

class CallActivity : AppCompatActivity() {
    
    private lateinit var callViewModel: CallViewModel
    private lateinit var remoteVideoView: SurfaceViewRenderer
    private lateinit var localVideoView: SurfaceViewRenderer
    private lateinit var callerNameTextView: TextView
    private lateinit var callStatusTextView: TextView
    private lateinit var callDurationTextView: TextView
    private lateinit var muteButton: ImageButton
    private lateinit var speakerButton: ImageButton
    private lateinit var videoButton: ImageButton
    private lateinit var endCallButton: ImageButton
    
    private var isIncoming: Boolean = false
    private var isVideo: Boolean = false
    private var callId: String = ""
    private var callerId: String = ""
    private var receiverId: String = ""
    private var receiverName: String = ""
    
    private var isMuted: Boolean = false
    private var isSpeakerphone: Boolean = false
    private var isVideoEnabled: Boolean = true
    
    private var callStartTime: Long = 0
    private var chronometer: Chronometer? = null
    
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_call)
        
        // Keep screen on
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        
        // Initialize ViewModel
        callViewModel = ViewModelProvider(this).get(CallViewModel::class.java)
        
        // Get extras
        callId = intent.getStringExtra("callId") ?: ""
        callerId = intent.getStringExtra("callerId") ?: ""
        receiverId = intent.getStringExtra("receiverId") ?: ""
        receiverName = intent.getStringExtra("receiverName") ?: ""
        isIncoming = intent.getBooleanExtra("isIncoming", false)
        isVideo = intent.getBooleanExtra("isVideo", false)
        
        // Initialize UI
        remoteVideoView = findViewById(R.id.remoteVideoView)
        localVideoView = findViewById(R.id.localVideoView)
        callerNameTextView = findViewById(R.id.callerNameTextView)
        callStatusTextView = findViewById(R.id.callStatusTextView)
        callDurationTextView = findViewById(R.id.callDurationTextView)
        muteButton = findViewById(R.id.muteButton)
        speakerButton = findViewById(R.id.speakerButton)
        videoButton = findViewById(R.id.videoButton)
        endCallButton = findViewById(R.id.endCallButton)
        chronometer = findViewById(R.id.chronometer)
        
        // Set up UI based on call type
        if (isIncoming) {
            callerNameTextView.text = receiverName
            callStatusTextView.text = "Incoming call..."
        } else {
            callerNameTextView.text = receiverName
            callStatusTextView.text = "Calling..."
        }
        
        // Hide local video if not video call
        localVideoView.visibility = if (isVideo) View.VISIBLE else View.GONE
        videoButton.visibility = if (isVideo) View.VISIBLE else View.GONE
        
        // Set up button click listeners
        muteButton.setOnClickListener {
            toggleMute()
        }
        
        speakerButton.setOnClickListener {
            toggleSpeakerphone()
        }
        
        videoButton.setOnClickListener {
            toggleVideo()
        }
        
        endCallButton.setOnClickListener {
            endCall()
        }
        
        // Initialize call
        if (isIncoming) {
            // Handle incoming call
            callViewModel.handleIncomingCall(callId, callerId, if (isVideo) CallType.VIDEO else CallType.VOICE)
        } else {
            // Start outgoing call
            callViewModel.startCall(
                callerId, 
                receiverId, 
                if (isVideo) CallType.VIDEO else CallType.VOICE
            )
        }
        
        // Observe call state
        callViewModel.callState.observe(this) { callStatus ->
            callStatus?.let { handleCallState(it) }
        }
        
        // Observe call events
        callViewModel.callEvent.observe(this) { callEvent ->
            callEvent?.let { handleCallEvent(it) }
        }
        
        // Observe call duration
        callViewModel.callDuration.observe(this) { duration ->
            callDurationTextView.text = duration
        }
        
        // Observe mute state
        callViewModel.isMuted.observe(this) { isMuted ->
            this.isMuted = isMuted
            updateButtonStates()
        }
        
        // Observe speakerphone state
        callViewModel.isSpeakerphone.observe(this) { isSpeakerphone ->
            this.isSpeakerphone = isSpeakerphone
            updateButtonStates()
        }
        
        // Observe video state
        callViewModel.isVideoEnabled.observe(this) { isVideoEnabled ->
            this.isVideoEnabled = isVideoEnabled
            updateButtonStates()
        }
        
        // Observe error messages
        callViewModel.errorMessage.observe(this) { error ->
            error?.let {
                Toast.makeText(this, it, Toast.LENGTH_SHORT).show()
            }
        }
        
        // Start chronometer
        startChronometer()
    }
    
    private fun handleCallState(callStatus: CallStatus) {
        when (callStatus) {
            CallStatus.RINGING -> {
                if (isIncoming) {
                    callStatusTextView.text = "Incoming call..."
                } else {
                    callStatusTextView.text = "Calling..."
                }
            }
            CallStatus.CONNECTED -> {
                callStatusTextView.text = "Connected"
                callStartTime = System.currentTimeMillis()
            }
            CallStatus.DISCONNECTED -> {
                callStatusTextView.text = "Call ended"
                endCall()
            }
            CallStatus.MISSED -> {
                callStatusTextView.text = "Missed call"
                endCall()
            }
            CallStatus.REJECTED -> {
                callStatusTextView.text = "Call rejected"
                endCall()
            }
        }
    }
    
    private fun handleCallEvent(event: CallViewModel.CallEvent) {
        when (event) {
            CallViewModel.CallEvent.CALL_STARTED -> {
                // Call started
            }
            CallViewModel.CallEvent.CALL_ENDED -> {
                endCall()
            }
            CallViewModel.CallEvent.CONNECTION_ESTABLISHED -> {
                callStatusTextView.text = "Connected"
            }
            CallViewModel.CallEvent.CONNECTION_FAILED -> {
                callStatusTextView.text = "Connection failed"
            }
            else -> {
                // Handle other events
            }
        }
    }
    
    private fun toggleMute() {
        isMuted = !isMuted
        callViewModel.toggleMute()
        updateButtonStates()
    }
    
    private fun toggleSpeakerphone() {
        isSpeakerphone = !isSpeakerphone
        callViewModel.toggleSpeakerphone()
        updateButtonStates()
    }
    
    private fun toggleVideo() {
        isVideoEnabled = !isVideoEnabled
        callViewModel.toggleVideo()
        updateButtonStates()
        localVideoView.visibility = if (isVideoEnabled) View.VISIBLE else View.GONE
    }
    
    private fun endCall() {
        callViewModel.endCall()
        finishCall()
    }
    
    private fun finishCall() {
        // Stop chronometer
        chronometer?.stop()
        
        // Clear flags
        window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        
        // Return to chat or main activity
        val intent = Intent(this, ChatActivity::class.java).apply {
            putExtra("senderId", callerId)
            putExtra("receiverId", receiverId)
            putExtra("receiverName", receiverName)
        }
        startActivity(intent)
        finish()
    }
    
    private fun updateButtonStates() {
        muteButton.setImageResource(
            if (isMuted) R.drawable.ic_mic_off else R.drawable.ic_mic
        )
        
        speakerButton.setImageResource(
            if (isSpeakerphone) R.drawable.ic_speaker_on else R.drawable.ic_speaker_off
        )
        
        videoButton.setImageResource(
            if (isVideoEnabled) R.drawable.ic_videocam else R.drawable.ic_videocam_off
        )
    }
    
    private fun startChronometer() {
        chronometer?.apply {
            base = SystemClock.elapsedRealtime()
            start()
        }
    }
    
    override fun onBackPressed() {
        // Prevent going back during call
        if (callViewModel.isInCall()) {
            Toast.makeText(this, "End the call first", Toast.LENGTH_SHORT).show()
        } else {
            super.onBackPressed()
        }
    }
    
    override fun onDestroy() {
        super.onDestroy()
        callViewModel.cleanup()
    }
}
