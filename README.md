# Altron - Secure Communication App

## Overview

Altron is a secure mobile communication app that combines the ease of use of WhatsApp with the security of Tailscale's peer-to-peer networking. It provides free voice/video calls, unlimited chat, and secure friend connections via QR codes.

## Features

### 🔐 Security
- **Tailscale Integration**: Uses Tailscale for secure peer-to-peer connectivity
- **End-to-End Encryption**: All messages are encrypted
- **Secure Authentication**: Phone number verification with OTP
- **QR Code Connections**: Add friends securely by scanning QR codes

### 📞 Communication
- **Free Voice Calls**: High-quality voice calls between app users
- **Free Video Calls**: Face-to-face video communication
- **Unlimited Chat**: Send text messages, images, videos, and audio
- **Call History**: Track all your calls
- **Message Status**: See when messages are sent, delivered, and read

### 👥 Social
- **Contact Management**: Add, remove, and manage your contacts
- **QR Code Sharing**: Share your QR code to connect with friends
- **Online Status**: See when your contacts are online
- **User Profiles**: Customize your profile with display name and status

## Architecture

### Tech Stack
- **Language**: Kotlin
- **Platform**: Android (Native)
- **Networking**: Tailscale, Firebase, WebRTC
- **Database**: Firebase Firestore
- **Authentication**: Firebase Phone Authentication
- **UI**: Material Design Components

### Project Structure

```
app/
├── src/main/java/com/altron/
│   ├── AltronApp.kt                 # Application class
│   ├── auth/                        # Authentication module
│   │   └── AuthManager.kt           # Handles phone auth and user management
│   ├── contacts/                    # Contacts management
│   │   └── ContactsManager.kt       # Manages user contacts
│   ├── calls/                      # Call functionality
│   │   └── CallManager.kt           # Handles voice/video calls via WebRTC
│   ├── chat/                        # Chat functionality
│   │   └── ChatManager.kt           # Manages messages and conversations
│   ├── network/                     # Network connectivity
│   │   └── TailscaleManager.kt      # Tailscale integration
│   ├── qr/                          # QR code functionality
│   │   └── QRCodeManager.kt         # QR code generation and scanning
│   ├── models/                      # Data models
│   │   ├── User.kt                  # User data model
│   │   ├── Message.kt               # Message data model
│   │   └── Call.kt                  # Call data model
│   ├── services/                    # Background services
│   │   ├── TailscaleService.kt      # Tailscale service
│   │   ├── CallService.kt           # Call service
│   │   ├── CallReceiver.kt          # Phone call receiver
│   │   └── NotificationService.kt   # Notification management
│   ├── utils/                       # Utility classes
│   │   ├── EncryptionUtils.kt      # Encryption utilities
│   │   ├── PermissionUtils.kt       # Permission handling
│   │   └── DateUtils.kt             # Date formatting
│   ├── viewmodels/                  # ViewModels
│   │   ├── AuthViewModel.kt         # Authentication ViewModel
│   │   ├── ContactsViewModel.kt     # Contacts ViewModel
│   │   ├── ChatViewModel.kt         # Chat ViewModel
│   │   └── CallViewModel.kt         # Call ViewModel
│   └── ui/                          # UI components
│       ├── activities/              # Activities
│       │   ├── SplashActivity.kt    # Splash screen
│       │   ├── LoginActivity.kt     # Phone login
│       │   ├── VerifyOTPActivity.kt  # OTP verification
│       │   ├── MainActivity.kt      # Main app screen
│       │   ├── ContactsActivity.kt  # Contacts list
│       │   ├── ChatActivity.kt      # Chat interface
│       │   ├── CallActivity.kt      # Call interface
│       │   ├── QRScannerActivity.kt # QR code scanner
│       │   └── MyQRCodeActivity.kt  # My QR code display
│       ├── fragments/               # Fragments
│       │   ├── ContactsFragment.kt  # Contacts fragment
│       │   ├── CallsFragment.kt     # Calls fragment
│       │   └── SettingsFragment.kt  # Settings fragment
│       └── adapters/                # RecyclerView adapters
│           ├── ContactsAdapter.kt   # Contacts list adapter
│           └── MessageAdapter.kt     # Messages list adapter
└── res/                            # Resources
    ├── layout/                      # Layout files
    ├── drawable/                   # Drawable resources
    ├── values/                     # String, color, style resources
    ├── menu/                       # Menu resources
    └── navigation/                 # Navigation graph
```

## Setup

### Prerequisites
- Android Studio (latest version)
- Android SDK (API 24+)
- Java JDK 17+
- Kotlin plugin

### Dependencies
Add these to your `build.gradle`:

```gradle
// Firebase
implementation platform('com.google.firebase:firebase-bom:32.2.0')
implementation 'com.google.firebase:firebase-auth-ktx'
implementation 'com.google.firebase:firebase-firestore-ktx'

// Tailscale
implementation 'com.github.tailscale:tailscale-android:0.1.0'

// WebRTC
implementation 'org.webrtc:google-webrtc:1.0.32006'

// QR Code
implementation 'com.journeyapps:zxing-android-embedded:4.3.0'

// Material Components
implementation 'com.google.android.material:material:1.9.0'

// Coroutines
implementation 'org.jetbrains.kotlinx:kotlinx-coroutines-android:1.6.4'

// Encryption
implementation 'com.google.crypto.tink:tink-android:1.7.0'

// Image Loading
implementation 'com.github.bumptech.glide:glide:4.15.1'
```

### Firebase Setup
1. Create a Firebase project at [Firebase Console](https://console.firebase.google.com/)
2. Add your Android app to the project
3. Download the `google-services.json` file and place it in your app module
4. Enable Phone Authentication in Firebase Console

### Tailscale Setup
1. Sign up for a Tailscale account at [Tailscale](https://tailscale.com/)
2. Create a Tailnet for your app
3. Configure the Tailscale Android SDK with your Tailnet credentials

## Usage

### Authentication
1. User enters phone number
2. App sends OTP via Firebase
3. User enters OTP to verify
4. User is authenticated and Tailscale connection is established

### Adding Contacts
1. User A shares their QR code with User B
2. User B scans User A's QR code
3. Both users are added to each other's contacts
4. Tailscale establishes direct connection between devices

### Making Calls
1. User selects a contact
2. User taps voice or video call button
3. App establishes WebRTC connection via Tailscale
4. Call is connected peer-to-peer

### Sending Messages
1. User selects a contact
2. User types a message
3. Message is encrypted and sent via Firebase
4. If Tailscale connection is available, message is also sent directly
5. Message is delivered to recipient

## Security Features

### End-to-End Encryption
- All messages are encrypted using AES-256
- Encryption keys are generated per session
- Messages can only be decrypted by the intended recipient

### Tailscale Integration
- Creates a secure mesh network between devices
- All traffic is encrypted using WireGuard
- No central server for call routing
- Direct peer-to-peer connections

### QR Code Authentication
- QR codes contain user ID and public key
- QR codes are signed to prevent tampering
- QR codes expire after a certain time

### Phone Number Verification
- Uses Firebase Phone Authentication
- OTP is sent via SMS
- Phone number is verified before account creation

## Customization

### Themes
Edit `res/values/colors.xml` to change the app's color scheme:

```xml
<color name="colorPrimary">#6200EE</color>
<color name="colorPrimaryDark">#3700B3</color>
<color name="colorAccent">#03DAC6</color>
```

### Styles
Edit `res/values/styles.xml` to change the app's styling:

```xml
<style name="Theme.Altron" parent="Theme.MaterialComponents.DayNight.NoActionBar">
    <item name="colorPrimary">@color/colorPrimary</item>
    <item name="colorPrimaryDark">@color/colorPrimaryDark</item>
    <item name="colorAccent">@color/colorAccent</item>
</style>
```

## Troubleshooting

### Tailscale Connection Issues
- Ensure Tailscale service is running
- Check internet connectivity
- Verify Tailnet credentials
- Restart the app

### Call Quality Issues
- Check network connectivity
- Ensure both devices have Tailscale connected
- Verify microphone and camera permissions
- Restart the call

### Message Delivery Issues
- Check internet connectivity
- Verify Firebase configuration
- Check Firestore permissions
- Restart the app

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Contact

For questions or support, please contact the development team.

---

**Altron - Secure Communication for Everyone**
