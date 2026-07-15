package com.altron.viewmodels

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.LiveData
import androidx.lifecycle.MutableLiveData
import com.altron.calls.CallManager
import com.altron.models.Call
import com.altron.models.CallStatus
import com.altron.models.CallType

class CallViewModel(application: Application) : AndroidViewModel(application) {
    
    private val callManager: CallManager = CallManager.getInstance(application)
    
    // LiveData for current call
    private val _currentCall = MutableLiveData<Call?>()
    val currentCall: LiveData<Call?> = _currentCall
    
    // LiveData for call state
    private val _callState = MutableLiveData<CallStatus?>()
    val callState: LiveData<CallStatus?> = _callState
    
    // LiveData for call events
    private val _callEvent = MutableLiveData<CallManager.CallEvent?>()
    val callEvent: LiveData<CallManager.CallEvent?> = _callEvent
    
    // LiveData for loading state
    private val _isLoading = MutableLiveData<Boolean>()
    val isLoading: LiveData<Boolean> = _isLoading
    
    // LiveData for error messages
    private val _errorMessage = MutableLiveData<String?>()
    val errorMessage: LiveData<String?> = _errorMessage
    
    // LiveData for call duration
    private val _callDuration = MutableLiveData<String>()
    val callDuration: LiveData<String> = _callDuration
    
    // LiveData for mute state
    private val _isMuted = MutableLiveData<Boolean>()
    val isMuted: LiveData<Boolean> = _isMuted
    
    // LiveData for speakerphone state
    private val _isSpeakerphone = MutableLiveData<Boolean>()
    val isSpeakerphone: LiveData<Boolean> = _isSpeakerphone
    
    // LiveData for video state
    private val _isVideoEnabled = MutableLiveData<Boolean>()
    val isVideoEnabled: LiveData<Boolean> = _isVideoEnabled
    
    private var callStartTime: Long = 0
    private var durationTimer: java.util.Timer? = null
    
    init {
        // Set up call state listener
        callManager.addCallStateCallback { call ->
            _currentCall.postValue(call)
            _callState.postValue(call.status)
        }
        
        // Set up call event listener
        callManager.addCallEventCallback { event ->
            _callEvent.postValue(event)
            
            when (event) {
                CallManager.CallEvent.AUDIO_MUTED -> _isMuted.postValue(true)
                CallManager.CallEvent.AUDIO_UNMUTED -> _isMuted.postValue(false)
                CallManager.CallEvent.SPEAKERPHONE_ON -> _isSpeakerphone.postValue(true)
                CallManager.CallEvent.SPEAKERPHONE_OFF -> _isSpeakerphone.postValue(false)
                CallManager.CallEvent.VIDEO_ENABLED -> _isVideoEnabled.postValue(true)
                CallManager.CallEvent.VIDEO_DISABLED -> _isVideoEnabled.postValue(false)
                else -> {}
            }
        }
    }
    
    fun startCall(callerId: String, receiverId: String, callType: CallType) {
        _isLoading.postValue(true)
        _errorMessage.postValue(null)
        
        callManager.startCall(callerId, receiverId, callType) { success, call ->
            _isLoading.postValue(false)
            if (success && call != null) {
                _currentCall.postValue(call)
                _callState.postValue(call.status)
                startDurationTimer()
            } else {
                _errorMessage.postValue("Failed to start call")
            }
        }
    }
    
    fun endCall() {
        _currentCall.value?.let { call ->
            _isLoading.postValue(true)
            
            callManager.endCall(call.callId) { success ->
                _isLoading.postValue(false)
                if (success) {
                    stopDurationTimer()
                } else {
                    _errorMessage.postValue("Failed to end call")
                }
            }
        }
    }
    
    fun acceptCall(callId: String) {
        _isLoading.postValue(true)
        
        callManager.acceptCall(callId) { success ->
            _isLoading.postValue(false)
            if (success) {
                startDurationTimer()
            } else {
                _errorMessage.postValue("Failed to accept call")
            }
        }
    }
    
    fun rejectCall(callId: String) {
        _isLoading.postValue(true)
        
        callManager.rejectCall(callId) { success ->
            _isLoading.postValue(false)
            if (!success) {
                _errorMessage.postValue("Failed to reject call")
            }
        }
    }
    
    fun toggleMute() {
        callManager.toggleMute()
    }
    
    fun toggleSpeakerphone() {
        callManager.toggleSpeakerphone()
    }
    
    fun toggleVideo() {
        callManager.toggleVideo()
    }
    
    private fun startDurationTimer() {
        callStartTime = System.currentTimeMillis()
        
        durationTimer = java.util.Timer().apply {
            scheduleAtFixedRate(object : java.util.TimerTask() {
                override fun run() {
                    val duration = System.currentTimeMillis() - callStartTime
                    val formattedDuration = formatDuration(duration)
                    _callDuration.postValue(formattedDuration)
                }
            }, 0, 1000) // Update every second
        }
    }
    
    private fun stopDurationTimer() {
        durationTimer?.cancel()
        durationTimer = null
        _callDuration.postValue("00:00")
    }
    
    private fun formatDuration(milliseconds: Long): String {
        val seconds = milliseconds / 1000
        val minutes = seconds / 60
        val hours = minutes / 60
        
        return when {
            hours > 0 -> String.format("%02d:%02d:%02d", hours, minutes % 60, seconds % 60)
            minutes > 0 -> String.format("%02d:%02d", minutes, seconds % 60)
            else -> String.format("00:%02d", seconds)
        }
    }
    
    fun handleIncomingCall(callId: String, callerId: String, callType: CallType) {
        callManager.handleIncomingCall(callId, callerId, callType)
    }
    
    fun isInCall(): Boolean = callManager.isInCall()
    
    fun cleanup() {
        stopDurationTimer()
        callManager.cleanup()
    }
    
    override fun onCleared() {
        super.onCleared()
        cleanup()
        callManager.removeCallStateCallback { }
        callManager.removeCallEventCallback { }
    }
}
