
plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.moortyvoice.android"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.moortyvoice.android"
        minSdk = 26
        targetSdk = 35
        versionCode = 1
        versionName = "1.0-android-preview"
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }
}
