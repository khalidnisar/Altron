package com.altron.utils

import android.Manifest
import android.app.Activity
import android.content.Context
import android.content.pm.PackageManager
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat

object PermissionUtils {
    
    private const val REQUEST_CODE_CAMERA = 1001
    private const val REQUEST_CODE_RECORD_AUDIO = 1002
    private const val REQUEST_CODE_READ_CONTACTS = 1003
    private const val REQUEST_CODE_READ_PHONE_STATE = 1004
    private const val REQUEST_CODE_LOCATION = 1005
    private const val REQUEST_CODE_STORAGE = 1006
    
    fun checkCameraPermission(context: Context): Boolean {
        return ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA) == 
               PackageManager.PERMISSION_GRANTED
    }
    
    fun checkRecordAudioPermission(context: Context): Boolean {
        return ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO) == 
               PackageManager.PERMISSION_GRANTED
    }
    
    fun checkReadContactsPermission(context: Context): Boolean {
        return ContextCompat.checkSelfPermission(context, Manifest.permission.READ_CONTACTS) == 
               PackageManager.PERMISSION_GRANTED
    }
    
    fun checkReadPhoneStatePermission(context: Context): Boolean {
        return ContextCompat.checkSelfPermission(context, Manifest.permission.READ_PHONE_STATE) == 
               PackageManager.PERMISSION_GRANTED
    }
    
    fun checkLocationPermission(context: Context): Boolean {
        return ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_FINE_LOCATION) == 
               PackageManager.PERMISSION_GRANTED
    }
    
    fun checkStoragePermission(context: Context): Boolean {
        return ContextCompat.checkSelfPermission(context, Manifest.permission.READ_EXTERNAL_STORAGE) == 
               PackageManager.PERMISSION_GRANTED
    }
    
    fun requestCameraPermission(activity: Activity) {
        ActivityCompat.requestPermissions(
            activity,
            arrayOf(Manifest.permission.CAMERA),
            REQUEST_CODE_CAMERA
        )
    }
    
    fun requestRecordAudioPermission(activity: Activity) {
        ActivityCompat.requestPermissions(
            activity,
            arrayOf(Manifest.permission.RECORD_AUDIO),
            REQUEST_CODE_RECORD_AUDIO
        )
    }
    
    fun requestReadContactsPermission(activity: Activity) {
        ActivityCompat.requestPermissions(
            activity,
            arrayOf(Manifest.permission.READ_CONTACTS),
            REQUEST_CODE_READ_CONTACTS
        )
    }
    
    fun requestReadPhoneStatePermission(activity: Activity) {
        ActivityCompat.requestPermissions(
            activity,
            arrayOf(Manifest.permission.READ_PHONE_STATE),
            REQUEST_CODE_READ_PHONE_STATE
        )
    }
    
    fun requestLocationPermission(activity: Activity) {
        ActivityCompat.requestPermissions(
            activity,
            arrayOf(
                Manifest.permission.ACCESS_FINE_LOCATION,
                Manifest.permission.ACCESS_COARSE_LOCATION
            ),
            REQUEST_CODE_LOCATION
        )
    }
    
    fun requestStoragePermission(activity: Activity) {
        ActivityCompat.requestPermissions(
            activity,
            arrayOf(Manifest.permission.READ_EXTERNAL_STORAGE),
            REQUEST_CODE_STORAGE
        )
    }
    
    fun requestCallPermissions(activity: Activity) {
        ActivityCompat.requestPermissions(
            activity,
            arrayOf(
                Manifest.permission.CAMERA,
                Manifest.permission.RECORD_AUDIO,
                Manifest.permission.MODIFY_AUDIO_SETTINGS
            ),
            REQUEST_CODE_RECORD_AUDIO
        )
    }
    
    fun hasAllCallPermissions(context: Context): Boolean {
        return checkCameraPermission(context) && 
               checkRecordAudioPermission(context) &&
               checkReadPhoneStatePermission(context)
    }
    
    fun hasAllAppPermissions(context: Context): Boolean {
        return checkCameraPermission(context) &&
               checkRecordAudioPermission(context) &&
               checkReadContactsPermission(context) &&
               checkReadPhoneStatePermission(context) &&
               checkLocationPermission(context)
    }
}
