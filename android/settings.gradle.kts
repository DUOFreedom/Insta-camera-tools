pluginManagement {
    repositories {
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

rootProject.name = "instatools-android"
include(":app")
