import java.util.Properties

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
        versionCode = 14
        versionName = "1.2.0"
        resourceConfigurations += listOf("zh", "en")
        manifestPlaceholders["appLabel"] = "InstaAce 导入器"

        // 双 ABI：同时支持 64 位与 32 位 ARM。
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
        // ffmpeg/ffprobe 以 lib*.so 形式随包，必须解压到 nativeLibraryDir 才能 exec
        jniLibs {
            useLegacyPackaging = true
        }
    }

    // 签名证书从 local.properties / 环境变量读取，不把口令写进仓库。
    //   本地自用（覆盖手机上的旧版）时回退到 debug.keystore，保证可升级；
    //   正式分发必须配 INSTA_KEYSTORE* 四项换成自有证书。
    //   查找顺序：环境变量 -> local.properties -> debug.keystore 兜底。
    fun signingValue(envName: String, propName: String): String? {
        val fromEnv = System.getenv(envName)
        if (!fromEnv.isNullOrBlank()) return fromEnv
        val props = rootProject.file("local.properties")
        if (!props.exists()) return null
        return Properties().apply { props.inputStream().use { load(it) } }
            .getProperty(propName)?.takeIf { it.isNotBlank() }
    }

    val customStore = signingValue("INSTA_KEYSTORE", "insta.keystore")?.let { file(it) }
    val useCustomKey = customStore != null && customStore.exists()

    signingConfigs {
        create("sideload") {
            if (useCustomKey) {
                storeFile = customStore
                storePassword = signingValue("INSTA_KEYSTORE_PASSWORD", "insta.keystore.password")
                keyAlias = signingValue("INSTA_KEY_ALIAS", "insta.key.alias")
                keyPassword = signingValue("INSTA_KEY_PASSWORD", "insta.key.password")
            } else {
                storeFile = file(System.getProperty("user.home") + "/.android/debug.keystore")
                storePassword = "android"
                keyAlias = "androiddebugkey"
                keyPassword = "android"
            }
            enableV1Signing = true
            enableV2Signing = true
            enableV3Signing = true
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            isShrinkResources = false
            signingConfig = signingConfigs.getByName("sideload")
            // release 必须不可调试：debuggable=true 会允许 attach 调试器、
            // 导出堆栈与任意 run-as，正式包不能带。
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

// Chaquopy 需要一个真实的 Python 3.11 解释器来打包 .pyc。
//   路径不要写死在仓库里（早期版本写死 D:/android-build/py311/python.exe，
//   换台机器必失败）。查找顺序：
//     1. 环境变量 CHAQUOPY_PYTHON
//     2. local.properties 的 chaquopy.python（该文件已被 .gitignore 排除）
//     3. 都不配时交给 Chaquopy 自行探测
fun chaquopyPython(): String? {
    val fromEnv = System.getenv("CHAQUOPY_PYTHON")
    if (!fromEnv.isNullOrBlank()) return fromEnv
    val props = rootProject.file("local.properties")
    if (!props.exists()) return null
    return Properties().apply { props.inputStream().use { load(it) } }
        .getProperty("chaquopy.python")?.takeIf { it.isNotBlank() }
}

extensions.configure<com.chaquo.python.ChaquopyExtension> {
    defaultConfig {
        // Python 3.11：3.12/3.13 没有 armeabi-v7a 构件，无法出 32 位包
        version = "3.11"
        chaquopyPython()?.let { buildPython(it) }
    }
}
