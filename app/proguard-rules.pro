# Android ProGuard rules

# Keep R classes
-keep class **.R {
    *;
}

# Keep native methods
-keep class * extends java.lang.Object {
    native <methods>;
}

# Keep classes that implement Parcelable
-keep class * implements android.os.Parcelable {
    public static final android.os.Parcelable$Creator *;
}

# Keep classes that implement Serializable
-keepclassmembers class * implements java.io.Serializable {
    static final long serialVersionUID;
    private <fields>;
    private <methods>;
}

# Keep Firebase classes
-keep class com.google.firebase.** { *; }
-keep class com.google.android.gms.** { *; }

# Keep Tailscale classes
-keep class com.tailscale.** { *; }

# Keep WebRTC classes
-keep class org.webrtc.** { *; }

# Keep Glide classes
-keep class com.bumptech.glide.** { *; }

# Keep Tink classes
-keep class com.google.crypto.tink.** { *; }

# Keep ZXing classes
-keep class com.google.zxing.** { *; }
-keep class com.journeyapps.barcodescanner.** { *; }

# Keep Kotlin classes
-keep class kotlin.** { *; }
-keep class kotlinx.** { *; }

# Keep ViewModel classes
-keep class androidx.lifecycle.** { *; }

# Keep Room database classes
-keep class androidx.room.** { *; }

# Keep Navigation classes
-keep class androidx.navigation.** { *; }

# Keep Material Components classes
-keep class com.google.android.material.** { *; }

# Keep Retrofit classes
-keep class retrofit2.** { *; }
-keep class okhttp3.** { *; }
-keep class okio.** { *; }

# Keep GSON classes
-keep class com.google.gson.** { *; }

# Keep classes with @Keep annotation
-keep @com.google.android.gms.common.annotation.Keep class *
-keepclassmembers class * {
    @com.google.android.gms.common.annotation.Keep <methods>;
}

# Keep classes with @KeepName annotation
-keep @androidx.annotation.Keep class *
-keepclassmembers class * {
    @androidx.annotation.Keep <methods>;
}

# Keep classes with @Keep annotation (Kotlin)
-keep @kotlinx.android.parcel.Parcelize class *

# Keep R classes for all packages
-keep class *.** {
    public *;
}

# Keep all activities, services, and receivers
-keep public class * extends android.app.Activity
-keep public class * extends android.app.Service
-keep public class * extends android.content.BroadcastReceiver

# Keep all fragments
-keep public class * extends android.app.Fragment
-keep public class * extends androidx.fragment.app.Fragment

# Keep all ViewModels
-keep public class * extends androidx.lifecycle.ViewModel

# Keep all data binding classes
-keep class * extends android.databinding.ViewDataBinding

# Keep all classes that might be used in layouts
-keep class * implements android.view.View.OnClickListener

# Keep all enum classes
-keepclassmembers enum * {
    public static **[] values();
    public static ** valueOf(java.lang.String);
}

# Keep all classes that implement Comparable
-keep class * implements java.lang.Comparable {
    public int compareTo(java.lang.Object);
}

# Keep all classes that implement AutoCloseable
-keep class * implements java.lang.AutoCloseable {
    public void close();
}

# Keep all classes that implement Closeable
-keep class * implements java.io.Closeable {
    public void close();
}

# Keep all classes that implement Flushable
-keep class * implements java.io.Flushable {
    public void flush();
}

# Keep all classes that implement Runnable
-keep class * implements java.lang.Runnable {
    public void run();
}

# Keep all classes that implement Callable
-keep class * implements java.util.concurrent.Callable {
    public java.lang.Object call();
}

# Keep all classes that implement Future
-keep class * implements java.util.concurrent.Future {
    public boolean cancel(boolean);
    public boolean isCancelled();
    public boolean isDone();
    public java.lang.Object get();
    public java.lang.Object get(long, java.util.concurrent.TimeUnit);
}

# Keep all classes that implement Executor
-keep class * implements java.util.concurrent.Executor {
    public void execute(java.lang.Runnable);
}

# Keep all classes that implement ExecutorService
-keep class * implements java.util.concurrent.ExecutorService {
    public void shutdown();
    public java.util.List shutdownNow();
    public boolean isShutdown();
    public boolean isTerminated();
    public boolean awaitTermination(long, java.util.concurrent.TimeUnit);
    public java.util.concurrent.Future submit(java.util.concurrent.Callable);
    public java.util.concurrent.Future submit(java.lang.Runnable, java.lang.Object);
    public java.util.concurrent.Future submit(java.lang.Runnable);
    public java.util.List invokeAll(java.util.Collection);
    public java.util.List invokeAll(java.util.Collection, long, java.util.concurrent.TimeUnit);
    public java.lang.Object invokeAny(java.util.Collection);
    public java.lang.Object invokeAny(java.util.Collection, long, java.util.concurrent.TimeUnit);
}

# Keep all classes that implement ScheduledExecutorService
-keep class * implements java.util.concurrent.ScheduledExecutorService {
    public java.util.concurrent.ScheduledFuture schedule(java.util.concurrent.Callable, long, java.util.concurrent.TimeUnit);
    public java.util.concurrent.ScheduledFuture schedule(java.lang.Runnable, long, java.util.concurrent.TimeUnit);
    public java.util.concurrent.ScheduledFuture scheduleAtFixedRate(java.lang.Runnable, long, long, java.util.concurrent.TimeUnit);
    public java.util.concurrent.ScheduledFuture scheduleWithFixedDelay(java.lang.Runnable, long, long, java.util.concurrent.TimeUnit);
}
