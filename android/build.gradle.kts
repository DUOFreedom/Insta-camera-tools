plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("com.chaquo.python")
}

repositories {
    maven("https://repo1.maven.org/maven2")
    maven("https://chaquo.com/maven")
    maven("https://maven.aliyun.com/repository/google")
    maven("https://maven.aliyun.com/repository/public")
    google()
    mavenCentral()
}

android {
    namespace = "com.duofreedom.instaace"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.duofreedom.instaace"
        minSdk = 26
        targetSdk = 34
        versionCode = 1
        versionName = "0.1.0beta"
        resourceConfigurations += listOf("zh", "en")
        manifestPlaceholders["appLabel"] = "InstaAce 导入器"

        // ★ 双 ABI：同时支持 64 位与 32 位 ARM。
        //   只带 arm64-v8a 时，32 位设备会 INSTALL_FAILED_NO_MATCHING_ABIS，
        //   系统界面显示成「应用未安装」——这正是早期版本装不上的最可能原因。
        ndk {
            abiFilters += listOf("arm64-v8a", "armeabi-v7a")
        }
    }

    buildFeatures {
        compose = true
    }

    composeOptions {
        kotlinCompilerExtensionVersion = "1.5.14"
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }

    packaging {
        resources.excludes += setOf("/META-INF/{AL2.0,LGPL2.1}")
        // ★ ffmpeg/ffprobe 以 lib*.so 形式随包，必须解压到 nativeLibraryDir 才能 exec
        jniLibs {
            useLegacyPackaging = true
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            isShrinkResources = false
            signingConfig = null
            isDebuggable = false
        }
    }

    lint {
        abortOnError = false
    }
}

dependencies {
    val composeBom = platform("androidx.compose:compose-bom:2024.06.00")
    implementation(composeBom)

    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.activity:activity-compose:1.9.0")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.8.2")
    implementation("androidx.documentfile:documentfile:1.0.1")

    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.compose.foundation:foundation")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material:material-icons-extended")

    debugImplementation("androidx.compose.ui:ui-tooling")

    testImplementation("junit:junit:4.13.2")
}

extensions.configure<com.chaquo.python.ChaquopyExtension> {
    defaultConfig {
        // ★ Python 3.11：3.12/3.13 没有 armeabi-v7a 构件，无法出 32 位包
        version = "3.11"
        buildPython("D:/android-build/py311/python.exe")
    }
}
