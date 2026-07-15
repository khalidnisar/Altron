#!/bin/bash

# Altron Setup Script
# This script helps set up the development environment

echo "🚀 Altron Setup Script"
echo "===================="
echo ""

# Check if running on Android project
if [ ! -f "build.gradle" ]; then
    echo "❌ Error: Please run this script from the project root directory"
    exit 1
fi

# Check for Android Studio
if [ ! -d "$ANDROID_HOME" ]; then
    echo "⚠️  Warning: ANDROID_HOME is not set. Android SDK may not be available."
fi

# Check for Java
if ! command -v java &> /dev/null; then
    echo "❌ Error: Java is not installed. Please install Java JDK 17+."
    exit 1
fi

# Check Java version
JAVA_VERSION=$(java -version 2>&1 | head -1 | cut -d'"' -f2)
if [[ "$JAVA_VERSION" < "17" ]]; then
    echo "⚠️  Warning: Java version $JAVA_VERSION detected. Recommended: Java 17+"
fi

# Check for Kotlin
if ! command -v kotlin &> /dev/null; then
    echo "⚠️  Warning: Kotlin compiler not found in PATH. It should be included with Android Studio."
fi

echo "✅ Environment checks completed"
echo ""

echo "📋 Project Structure:"
echo "-------------------"
tree -L 2 -I 'build|.git|.idea|*.iml' .
echo ""

echo "🔧 Next Steps:"
echo "-------------"
echo "1. Open the project in Android Studio"
echo "2. Add google-services.json to app/ directory"
echo "3. Configure Firebase project"
echo "4. Set up Tailscale Tailnet"
echo "5. Build and run the app"
echo ""

echo "📚 Documentation:"
echo "---------------"
echo "See README.md for detailed setup instructions"
echo ""

echo "✨ Setup complete!"
