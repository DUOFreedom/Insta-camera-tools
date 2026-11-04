# 构建指南（桌面端 + 安卓端）

本文档说明如何在同一仓库中分别构建桌面端和安卓端产物。

## 一、桌面端构建（Windows）

### 环境要求
- Python 3.14（`C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe`）
- PyInstaller 6.22.3
- PyQt5>=5.15

### 构建命令

```cmd
cd desktop
build.bat
```

`build.bat` 内容：

```bat
@echo off
set PY=C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe
cd /d "%~dp0"
"%PY%" -m PyInstaller --noconfirm --windowed --onefile --name InstaAceImporter --icon assets\app.ico --add-data "assets;assets" --hiddenimport inst_transplant --hiddenimport moov_rewrap gui.py
echo EXITCODE=%ERRORLEVEL%
```

### 产物

| 文件 | 说明 |
|------|------|
| `desktop/dist/InstaAceImporter.exe` | 单文件 GUI 可执行文件（约 39 MB） |

### 开发模式运行

```cmd
cd desktop
run.bat
```

### 打包说明

- `--onefile --windowed`：单文件、无控制台窗口
- `--hiddenimport inst_transplant --hiddenimport moov_rewrap`：确保 shared/instbox 模块被打入 PYZ
- `--add-data "assets;assets"`：将图标资源打入 exe
- 打包后 `shared/` 目录中的 `insta_index.py` 和 `instbox/` 模块通过 `sys.path` 运行时加载（开发时）；PyInstaller 打包后通过 `_MEIPASS` 定位资源

## 二、安卓端构建

### 环境要求

| 组件 | 版本 | 路径 |
|------|------|------|
| JDK | 21 LTS | `D:\android-build\jdk21\jdk-21.0.12.1+1` |
| Gradle | 8.7 | `D:\android-build\gradle-8.7\bin\gradle` |
| Android SDK | 34 | `D:\android-build\sdk` |
| NDK | r27 | `D:\android-build\ndk\android-ndk-r27` |
| Python | 3.11（Chaquopy） | `D:\android-build\py311\python.exe` |

> ⚠️ **不要使用 JDK 27**：Gradle 8.7 不支持 Java 27，构建会直接失败（`What went wrong: 27.0.1`），必须使用 JDK 21。

### 构建命令

```bash
cd android
export JAVA_HOME=/d/android-build/jdk21/jdk-21.0.12.1+1
export ANDROID_HOME=/d/android-build/sdk
export ANDROID_SDK_ROOT=/d/android-build/sdk
export GRADLE_USER_HOME=/d/android-build/.gradle
JAVA_HOME=/d/android-build/jdk21/jdk-21.0.12.1+1 /d/android-build/gradle-8.7/bin/gradle --no-daemon assembleRelease
```

### 产物

| 文件 | 说明 |
|------|------|
| `android/app/build/outputs/apk/release/app-release.apk` | 签名 APK，versionCode 13 / versionName 0.7.1 |

### 签名

使用 `~/.android/debug.keystore`（debug 签名），可覆盖已安装的旧版本（0.1.0 ~ 0.6.x ~ 0.7.0）。

### local.properties 配置

`android/local.properties` 内容：

```
sdk.dir=D:\\android-build\\sdk
```

### 双 ABI 支持

`android/build.gradle.kts` 已配置：

```kotlin
ndk {
    abiFilters += listOf("arm64-v8a", "armeabi-v7a")
}
```

## 三、共享库说明

`shared/` 下的模块与桌面端和安卓端同源：

| 模块 | 桌面端引用路径 | 安卓端引用路径 |
|------|--------------|--------------|
| `shared/insta_index.py` | `sys.path` 指向 `shared/`，`import insta_index as ix` | 同上 |
| `shared/instbox/inst_transplant.py` | `import instbox.inst_transplant as _tf` | 同上 |
| `shared/instbox/moov_rewrap.py` | `import instbox.moov_rewrap as _rw` | 同上 |

桌面端 `desktop/core.py` 和安卓端 `android/src/main/python/insta_core.py` 均已将 `_INST_ORIGIN` 指向仓库根目录的 `shared/`。

## 四、GitHub 发布清单

推送前请确认：

- [ ] `.gitignore` 已排除 `build/`、`dist/`、`*.exe`、`*.apk`、`__pycache__/`、`local.properties`、`android/app/build/` 等构建产物
- [ ] `desktop/LICENSE` 和 `android/LICENSE` 均为 GPL-3.0
- [ ] `desktop/CHANGELOG.md` 已记录 AMBA 修复（1.0.1 补丁）
- [ ] 顶层 `README.md` 已说明仓库结构与构建步骤
- [ ] 本目录 `BUILD.md` 已说明双端构建命令
