package com.altron.utils

import java.text.SimpleDateFormat
import java.util.*

object DateUtils {
    
    private const val DATE_FORMAT = "yyyy-MM-dd HH:mm:ss"
    private const val TIME_FORMAT = "HH:mm"
    private const val CHAT_DATE_FORMAT = "MMM dd, yyyy"
    private const val CHAT_TIME_FORMAT = "hh:mm a"
    
    fun formatDate(timestamp: Long): String {
        val date = Date(timestamp)
        val format = SimpleDateFormat(DATE_FORMAT, Locale.getDefault())
        return format.format(date)
    }
    
    fun formatTime(timestamp: Long): String {
        val date = Date(timestamp)
        val format = SimpleDateFormat(TIME_FORMAT, Locale.getDefault())
        return format.format(date)
    }
    
    fun formatChatDate(timestamp: Long): String {
        val date = Date(timestamp)
        val format = SimpleDateFormat(CHAT_DATE_FORMAT, Locale.getDefault())
        return format.format(date)
    }
    
    fun formatChatTime(timestamp: Long): String {
        val date = Date(timestamp)
        val format = SimpleDateFormat(CHAT_TIME_FORMAT, Locale.getDefault())
        return format.format(date)
    }
    
    fun formatRelativeTime(timestamp: Long): String {
        val now = System.currentTimeMillis()
        val diff = now - timestamp
        
        val seconds = diff / 1000
        val minutes = seconds / 60
        val hours = minutes / 60
        val days = hours / 24
        
        return when {
            seconds < 60 -> "Just now"
            minutes < 60 -> "${minutes}m ago"
            hours < 24 -> "${hours}h ago"
            days == 1L -> "Yesterday"
            days < 7 -> "${days}d ago"
            else -> formatChatDate(timestamp)
        }
    }
    
    fun formatCallDuration(seconds: Long): String {
        val hours = seconds / 3600
        val minutes = (seconds % 3600) / 60
        val secs = seconds % 60
        
        return when {
            hours > 0 -> String.format("%02d:%02d:%02d", hours, minutes, secs)
            minutes > 0 -> String.format("%02d:%02d", minutes, secs)
            else -> String.format("00:%02d", secs)
        }
    }
    
    fun isToday(timestamp: Long): Boolean {
        val date = Date(timestamp)
        val today = Date()
        return date.year == today.year && date.month == today.month && date.date == today.date
    }
    
    fun isYesterday(timestamp: Long): Boolean {
        val date = Date(timestamp)
        val yesterday = Date(System.currentTimeMillis() - 86400000) // 24 hours in milliseconds
        return date.year == yesterday.year && date.month == yesterday.month && date.date == yesterday.date
    }
    
    fun getDayOfWeek(timestamp: Long): String {
        val date = Date(timestamp)
        val calendar = Calendar.getInstance()
        calendar.time = date
        return when (calendar.get(Calendar.DAY_OF_WEEK)) {
            Calendar.SUNDAY -> "Sunday"
            Calendar.MONDAY -> "Monday"
            Calendar.TUESDAY -> "Tuesday"
            Calendar.WEDNESDAY -> "Wednesday"
            Calendar.THURSDAY -> "Thursday"
            Calendar.FRIDAY -> "Friday"
            Calendar.SATURDAY -> "Saturday"
            else -> ""
        }
    }
}
