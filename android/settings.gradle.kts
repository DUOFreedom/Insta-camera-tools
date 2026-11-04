pluginManagement {
    repositories {
        // ★ 必须把 Maven Central 放在最前面：chaquo.com/maven 不提供 target 的
        //   stdlib-pyc 构件，只搜它会报 Could not find target-3.x.0-0-stdlib-pyc.zip
        maven("https://repo1.maven.org/maven2")
        maven("https://chaquo.com/maven")
        maven("https://maven.aliyun.com/repository/gradle-plugin")
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositories {
        maven("https://repo1.maven.org/maven2")
        maven("https://chaquo.com/maven")
        maven("https://maven.aliyun.com/repository/google")
        maven("https://maven.aliyun.com/repository/public")
        google()
        mavenCentral()
    }
}

rootProject.name = "InstaAceAndroid"
include(":app")
