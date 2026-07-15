package com.altron.qr

import android.graphics.Bitmap
import android.graphics.Color
import com.google.zxing.BarcodeFormat
import com.google.zxing.MultiFormatWriter
import com.google.zxing.common.BitMatrix
import com.journeyapps.barcodescanner.BarcodeEncoder
import java.util.*

object QRCodeManager {
    
    private const val QR_CODE_SIZE = 512
    private const val QR_CODE_COLOR = Color.BLACK
    private const val QR_CODE_BACKGROUND = Color.WHITE
    
    fun generateQRCode(content: String): Bitmap {
        try {
            val bitMatrix: BitMatrix = MultiFormatWriter().encode(
                content,
                BarcodeFormat.QR_CODE,
                QR_CODE_SIZE,
                QR_CODE_SIZE,
                null
            )
            
            val barcodeEncoder = BarcodeEncoder()
            return barcodeEncoder.createBitmap(bitMatrix)
        } catch (e: Exception) {
            e.printStackTrace()
            // Return a blank bitmap as fallback
            return Bitmap.createBitmap(QR_CODE_SIZE, QR_CODE_SIZE, Bitmap.Config.ARGB_8888)
        }
    }
    
    fun generateQRCodeData(userId: String, phoneNumber: String): String {
        // Create a structured QR code data
        val qrData = mapOf(
            "type" to "altron_user",
            "userId" to userId,
            "phoneNumber" to phoneNumber,
            "timestamp" to System.currentTimeMillis(),
            "version" to "1.0"
        )
        
        // Convert to JSON string
        return com.altron.utils.EncryptionUtils.mapToJson(qrData)
    }
    
    fun parseQRCodeData(qrCode: String): Map<String, String>? {
        try {
            val data = com.altron.utils.EncryptionUtils.jsonToMap(qrCode)
            
            // Validate the QR code structure
            if (data["type"] == "altron_user") {
                return mapOf(
                    "userId" to data["userId"] as? String ?: "",
                    "phoneNumber" to data["phoneNumber"] as? String ?: ""
                )
            }
            return null
        } catch (e: Exception) {
            e.printStackTrace()
            return null
        }
    }
    
    fun isValidQRCode(qrCode: String): Boolean {
        try {
            val data = com.altron.utils.EncryptionUtils.jsonToMap(qrCode)
            return data["type"] == "altron_user" && 
                   data.containsKey("userId") && 
                   data.containsKey("phoneNumber")
        } catch (e: Exception) {
            return false
        }
    }
    
    fun generateShareableQRCode(userId: String, phoneNumber: String, displayName: String): Bitmap {
        // Create a more detailed QR code for sharing
        val qrData = mapOf(
            "type" to "altron_contact",
            "userId" to userId,
            "phoneNumber" to phoneNumber,
            "displayName" to displayName,
            "timestamp" to System.currentTimeMillis(),
            "version" to "1.0"
        )
        
        val content = com.altron.utils.EncryptionUtils.mapToJson(qrData)
        return generateQRCode(content)
    }
}
