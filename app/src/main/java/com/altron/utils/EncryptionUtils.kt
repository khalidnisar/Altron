package com.altron.utils

import android.util.Base64
import android.util.Log
import com.altron.models.Message
import com.google.crypto.tink.Aead
import com.google.crypto.tink.KeysetHandle
import com.google.crypto.tink.aead.AeadConfig
import com.google.crypto.tink.aead.AeadKeyTemplates
import com.google.crypto.tink.json.JsonFormat
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.io.ObjectOutputStream
import java.nio.charset.StandardCharsets
import javax.crypto.Cipher
import javax.crypto.spec.SecretKeySpec

object EncryptionUtils {
    
    private const val TAG = "EncryptionUtils"
    private const val ALGORITHM = "AES"
    private const val SECRET_KEY = "AltronSecureKey2024!@#"
    
    init {
        try {
            AeadConfig.register()
        } catch (e: Exception) {
            Log.e(TAG, "Failed to register Tink config", e)
        }
    }
    
    fun encrypt(data: String): String {
        try {
            val cipher = Cipher.getInstance(ALGORITHM)
            val secretKey = SecretKeySpec(SECRET_KEY.toByteArray(), ALGORITHM)
            cipher.init(Cipher.ENCRYPT_MODE, secretKey)
            val encryptedBytes = cipher.doFinal(data.toByteArray(StandardCharsets.UTF_8))
            return Base64.encodeToString(encryptedBytes, Base64.DEFAULT)
        } catch (e: Exception) {
            Log.e(TAG, "Encryption failed", e)
            return data // Return original if encryption fails
        }
    }
    
    fun decrypt(encryptedData: String): String {
        try {
            val cipher = Cipher.getInstance(ALGORITHM)
            val secretKey = SecretKeySpec(SECRET_KEY.toByteArray(), ALGORITHM)
            cipher.init(Cipher.DECRYPT_MODE, secretKey)
            val decodedBytes = Base64.decode(encryptedData, Base64.DEFAULT)
            val decryptedBytes = cipher.doFinal(decodedBytes)
            return String(decryptedBytes, StandardCharsets.UTF_8)
        } catch (e: Exception) {
            Log.e(TAG, "Decryption failed", e)
            return encryptedData // Return original if decryption fails
        }
    }
    
    fun generateQRCodeData(userId: String, phoneNumber: String): String {
        // Simple concatenation for QR code
        return "ALTRON:$userId:$phoneNumber:${System.currentTimeMillis()}"
    }
    
    fun serializeMessage(message: Message): ByteArray {
        try {
            val byteArrayOutputStream = ByteArrayOutputStream()
            val objectOutputStream = ObjectOutputStream(byteArrayOutputStream)
            objectOutputStream.writeObject(message)
            objectOutputStream.close()
            return byteArrayOutputStream.toByteArray()
        } catch (e: Exception) {
            Log.e(TAG, "Failed to serialize message", e)
            return ByteArray(0)
        }
    }
    
    fun deserializeMessage(data: ByteArray): Message? {
        try {
            val byteArrayInputStream = java.io.ByteArrayInputStream(data)
            val objectInputStream = java.io.ObjectInputStream(byteArrayInputStream)
            val message = objectInputStream.readObject() as Message
            objectInputStream.close()
            return message
        } catch (e: Exception) {
            Log.e(TAG, "Failed to deserialize message", e)
            return null
        }
    }
    
    fun serializeMap(map: Map<String, Any>): ByteArray {
        try {
            val jsonString = mapToJson(map)
            return jsonString.toByteArray(StandardCharsets.UTF_8)
        } catch (e: Exception) {
            Log.e(TAG, "Failed to serialize map", e)
            return ByteArray(0)
        }
    }
    
    fun deserializeMap(data: ByteArray): Map<String, Any>? {
        try {
            val jsonString = String(data, StandardCharsets.UTF_8)
            return jsonToMap(jsonString)
        } catch (e: Exception) {
            Log.e(TAG, "Failed to deserialize map", e)
            return null
        }
    }
    
    fun mapToJson(map: Map<String, Any>): String {
        return JSONObject(map).toString()
    }
    
    fun jsonToMap(json: String): Map<String, Any> {
        val jsonObject = JSONObject(json)
        val map = mutableMapOf<String, Any>()
        
        val keys = jsonObject.keys()
        while (keys.hasNext()) {
            val key = keys.next()
            val value = jsonObject.get(key)
            map[key] = value
        }
        
        return map
    }
    
    // Tink-based encryption for more secure communication
    fun createSecureEncryption(): Aead? {
        try {
            val keysetHandle: KeysetHandle = KeysetHandle.generateNew(AeadKeyTemplates.AES256_GCM)
            return keysetHandle.getPrimitive(Aead::class.java)
        } catch (e: Exception) {
            Log.e(TAG, "Failed to create secure encryption", e)
            return null
        }
    }
    
    fun generateSecureKey(): String {
        // Generate a random key for session encryption
        val random = java.util.Random()
        val bytes = ByteArray(32)
        random.nextBytes(bytes)
        return Base64.encodeToString(bytes, Base64.DEFAULT)
    }
}
