# Altron - Download & Setup Guide

## 📥 Download the App

### **Option 1: Clone the Repository (Recommended)**

```bash
# Clone the repository
git clone https://github.com/khalidnisar/Altron.git

# Navigate to project directory
cd Altron

# Check all files are present
ls -la
```

**Repository URL**: https://github.com/khalidnisar/Altron

---

### **Option 2: Download ZIP**

1. Go to: https://github.com/khalidnisar/Altron
2. Click **"Code"** button (green button)
3. Click **"Download ZIP"**
4. Extract the ZIP file
5. Open the extracted folder in Android Studio

---

### **Option 3: Direct File Access**

You can browse and download individual files from:
- **Main Repository**: https://github.com/khalidnisar/Altron
- **Raw Files**: https://raw.githubusercontent.com/khalidnisar/Altron/main/

---

## 🚀 Quick Setup (5 Minutes)

### **Step 1: Open in Android Studio**
1. Launch Android Studio
2. Click **"Open an Existing Project"**
3. Navigate to the **Altron** folder
4. Click **"OK"**

### **Step 2: Add Firebase Configuration**

1. **Create Firebase Project**:
   - Go to [Firebase Console](https://console.firebase.google.com/)
   - Click **"Add Project"**
   - Name it **"Altron"**
   - Click **"Continue"** and complete setup

2. **Add Android App**:
   - In Firebase Console, click **"Add App"** > **Android**
   - Package name: `com.altron`
   - SHA-1: (Get from Android Studio: Gradle > Signing Report)
   - Click **"Register App"**

3. **Download google-services.json**:
   - Click **"Download google-services.json"**
   - Save to: `Altron/app/google-services.json`

4. **Enable Phone Authentication**:
   - In Firebase Console, go to **Authentication**
   - Click **"Sign-in method"**
   - Enable **Phone** provider
   - Click **"Save"**

### **Step 3: Sync Gradle**
1. In Android Studio, click **"Sync Project with Gradle Files"**
2. Wait for sync to complete (may take 1-2 minutes)
3. Android Studio will download all dependencies

### **Step 4: Build APK**
1. Click **Build > Build Bundle(s) / APK(s) > Build APK**
2. Wait for build to complete (2-5 minutes)
3. Android Studio will show a notification: **"APK(s) generated"**
4. Click **"locate"** or **"show in explorer"**

### **Step 5: Install on Device**

**Option A: Direct Install**
1. Connect your Android device via USB
2. Enable **USB Debugging** on your device
3. In Android Studio, click **Run > Run 'app'**
4. Select your device and click **OK**

**Option B: Manual APK Install**
1. Navigate to: `Altron/app/build/outputs/apk/debug/`
2. Find: `app-debug.apk`
3. Copy to your Android device
4. Open the APK file on your device
5. Allow installation from unknown sources if prompted

---

## 📋 File Structure Verification

After cloning, verify all files are present:

```bash
# Count total files
find . -type f -not -path './.git/*' | wc -l
# Should show: 90 files (including this guide)

# Count Kotlin files
find . -name "*.kt" | wc -l
# Should show: 35 files

# Count XML files
find . -name "*.xml" | wc -l
# Should show: 50+ files
```

---

## 🔧 Troubleshooting

### **Issue: Gradle Sync Failed**
**Solution**:
1. Click **File > Invalidate Caches / Restart**
2. Select **"Invalidate and Restart"**
3. Try syncing again

### **Issue: Missing google-services.json**
**Solution**:
1. Create the file manually in `app/` directory
2. Add your Firebase configuration (see Step 2 above)

### **Issue: Tailscale SDK Not Found**
**Solution**:
1. Add JitPack repository to `app/build.gradle`:
```gradle
repositories {
    google()
    mavenCentral()
    maven { url 'https://jitpack.io' }
}
```
2. Sync Gradle again

### **Issue: WebRTC Native Libraries Missing**
**Solution**:
1. Add to `app/build.gradle`:
```gradle
android {
    defaultConfig {
        ndk {
            abiFilters 'armeabi-v7a', 'arm64-v8a', 'x86', 'x86_64'
        }
    }
    packagingOptions {
        pickFirst 'lib/arm64-v8a/libc++_shared.so'
        pickFirst 'lib/x86_64/libc++_shared.so'
    }
}
```
2. Sync Gradle again

### **Issue: Build Failed - Missing Dependencies**
**Solution**:
1. Check internet connection
2. Click **File > Sync Project with Gradle Files**
3. Wait for all dependencies to download
4. Try building again

---

## 📊 Repository Information

| Info | Details |
|------|---------|
| **Repository** | https://github.com/khalidnisar/Altron |
| **Branch** | main |
| **Total Files** | 90 |
| **Kotlin Files** | 35 |
| **XML Files** | 50+ |
| **Lines of Code** | ~7,300+ |
| **Last Updated** | July 15, 2024 |
| **License** | MIT |

---

## 🎯 Next Steps After Setup

### **1. Test Authentication**
- [ ] Enter phone number
- [ ] Receive OTP
- [ ] Verify OTP
- [ ] Login successful

### **2. Test QR Code**
- [ ] Go to My QR Code
- [ ] Share with friend
- [ ] Friend scans QR code
- [ ] Both users added as contacts

### **3. Test Chat**
- [ ] Select contact
- [ ] Send message
- [ ] Message delivered
- [ ] Message received

### **4. Test Calls**
- [ ] Select contact
- [ ] Start voice call
- [ ] Call connects
- [ ] Test mute/speakerphone
- [ ] End call

---

## 💡 Pro Tips

### **Speed Up Builds**
1. Enable **Gradle Offline Mode** (File > Settings > Build > Gradle)
2. Use **Build Cache** (File > Settings > Build > Build cache)
3. Increase **Heap Size** (File > Settings > Build > Gradle > VM Options: `-Xmx2048m`)

### **Reduce APK Size**
1. Enable **ProGuard** (minifyEnabled true in build.gradle)
2. Use **WebP** for images instead of PNG/JPG
3. Remove unused resources (`shrinkResources true`)

### **Improve Performance**
1. Enable **Instant Run** (File > Settings > Build > Instant Run)
2. Use **Android Profiler** to monitor app performance
3. Optimize images and resources

---

## 📞 Support

### **Need Help?**
1. **Check this guide** - Most common issues are covered above
2. **Check README.md** - Detailed project documentation
3. **Check REPOSITORY_STRUCTURE.md** - Complete file structure
4. **Create GitHub Issue** - For bugs or feature requests

### **GitHub Issues**
- Report bugs: https://github.com/khalidnisar/Altron/issues
- Request features: https://github.com/khalidnisar/Altron/issues
- Ask questions: https://github.com/khalidnisar/Altron/discussions

---

## ✅ Success Checklist

- [ ] Repository cloned successfully
- [ ] All files present (90 files)
- [ ] Firebase project created
- [ ] google-services.json added
- [ ] Phone authentication enabled
- [ ] Gradle sync successful
- [ ] APK built successfully
- [ ] App installed on device
- [ ] Login tested
- [ ] QR code tested
- [ ] Chat tested
- [ ] Calls tested

---

## 🎉 Congratulations!

You now have a complete, production-ready **Altron** app with:
- ✅ Secure authentication
- ✅ Tailscale integration
- ✅ QR code sharing
- ✅ Free voice/video calls
- ✅ Unlimited encrypted chat

**Ready to build the future of secure communication!** 🚀

---

**Last Updated**: July 15, 2024  
**Version**: 1.0.0  
**Status**: ✅ All files available and ready to use
