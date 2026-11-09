# 构建指南（桌面端 + 安卓端）

本文档说明如何在同一仓库中分别构建桌面端和安卓端产物。

## 一、桌面端构建（Windows）

### 环境要求

- Python **3.10+**（3.11 / 3.12 / 3.13 均可；仓库不再指定某个具体小版本）
- PyInstaller 6.x
- PyQt5 >= 5.15（经典版）与/或 PySide6 >= 6.5（QML 版）

两套界面的依赖都写在 `desktop/requirements.txt` 里，一次装齐即可：

```cmd
cd desktop
pip install -r requirements.txt
```

### 构建命令

```cmd
cd desktop

rem 经典版：PyQt5 单文件 exe -> dist\InstaAceImporter.exe
build.bat

rem QML 版：PySide6 单文件 exe -> dist\InstaAceQml.exe
build_qml.bat
```

两个脚本都只是 `python -m PyInstaller --noconfirm <spec>` 的薄封装，
真正的打包参数在 spec 文件里（避免命令行漏掉 `--add-data`）。

`desktop/build.bat` 内容：

```bat
@echo off
chcp 936 >nul
setlocal
cd /d "%~dp0"
python -c "import PyInstaller" 2>nul
if errorlevel 1 (
  echo [错误] 未安装 PyInstaller，请先执行: pip install pyinstaller
  exit /b 1
)
python -m PyInstaller --noconfirm InstaAceImporter.spec
echo EXITCODE=%ERRORLEVEL%
endlocal
```

`build_qml.bat` 额外检查 `PySide6` 是否可导入，再调用 `InstaAceQml.spec`。

### 产物

| 文件 | 说明 |
|------|------|
| `desktop/dist/InstaAceImporter.exe` | 经典版，PyQt5，单文件，约 39 MB |
| `desktop/dist/InstaAceQml.exe` | QML 版，PySide6，单文件（约 79 MB） |

> QML 版为 onefile 单文件：首次启动需把约 79 MB 内容解压到 `%TEMP%`，
> 冷启动约 2-5 秒，之后由系统缓存加速。若更在意启动速度，可把 spec 末尾改回
> `COLLECT`（onedir）并分发整个文件夹。spec 里已排除 WebEngine / Quick3D 等
> 用不到的 Qt6 模块以控制体积。

### 开发模式运行

```cmd
cd desktop
run.bat        rem 经典版，python gui.py
run_qml.bat    rem QML 版，pythonw main.py
```

QML 版支持自检模式，用于 CI 或快速验证 QML 是否可加载：

```cmd
python main.py --self-test
```

成功时打印 `QML_OK roots=N` 并以 0 退出；QML 有语法/导入错误时退出码非 0。

### 打包说明

- `--onefile --windowed`（经典版）：单文件、无控制台窗口
- `hiddenimports=['inst_transplant','moov_rewrap']`：确保 shared/instbox 模块被打入 PYZ
- `hiddenimports=['insta_index','instbox','instbox.inst_transplant','instbox.moov_rewrap']`（QML 版）：同上，另含 `insta_index`
- `datas=[('assets','assets')]`：图标资源；QML 版另有 `('qml','qml')`
- `pathex`：经典版为 `['../shared/instbox']`，QML 版为 `['../shared','../shared/instbox']`，
  让 PyInstaller 能找到 `desktop/` 之外的两个共享模块

## 二、安卓端构建

### 环境要求

| 组件 | 版本 | 说明 |
|------|------|------|
| JDK | **21** | AGP 8.7 要求 17+；实测 JDK 21 可用（Temurin 21.0.12.1+1） |
| Gradle | **8.11.1** | 仓库**没有** gradle wrapper，必须自备 `gradle` 可执行文件 |
| AGP | 8.7.3 | 见根 `build.gradle.kts` |
| Android SDK | **35** | `compileSdk = 35`、`targetSdk = 35`、`minSdk = 26` |
| NDK | r27 | 仅在重建 `jniLibs/` 里的 ffmpeg 时需要 |
| Python | **3.11** | Chaquopy 用；3.12/3.13 没有 armeabi-v7a 构件，无法出 32 位包 |

具体安装路径由本机决定，**不要写死进仓库**。需要告诉 Gradle 的两处位置：

`android/local.properties`（已被 `.gitignore` 排除，不入库）：

```
sdk.dir=<你的 Android SDK 路径>
chaquopy.python=<你的 Python 3.11 解释器路径>
```

也可以改用环境变量 `CHAQUOPY_PYTHON` 指定 Python 3.11；
两者都不配时由 Chaquopy 自行探测。SDK 路径也支持 `ANDROID_HOME` / `ANDROID_SDK_ROOT`。

### 构建命令

仓库里没有 wrapper（`gradlew` / `gradle/wrapper/` 均不存在），直接调用本机 `gradle`：

```bash
cd android
export JAVA_HOME=<你的 JDK 21 路径>
export ANDROID_HOME=<你的 Android SDK 路径>
export CHAQUOPY_PYTHON=<你的 Python 3.11 路径>
export GRADLE_USER_HOME=<Gradle 依赖缓存目录>
gradle assembleRelease
```

> 首次构建会从 Maven 拉 Chaquopy 与 Compose 依赖，耗时数分钟。

**`GRADLE_USER_HOME` 是最容易踩的坑**：AGP 8.7.3 必须在该缓存目录里已有构件，
否则 `--offline` 会报 `Plugin [id: 'com.android.application', version: '8.7.3'] was not found`，
联网又被墙时完全无法构建。缓存里只有 AGP 8.5.2 的目录不能直接用，换一个放对了缓存的目录。

离线构建（依赖已缓存时）：

```bash
gradle --offline assembleRelease
```

`debug` 变体额外需要 `ui-tooling` 和 `junit:4.13.2`，缓存里通常没有；
只发版的话用 `release` 变体即可，不受影响。

### 单元测试

```bash
gradle --offline :app:testReleaseUnitTest
```

预期 **5 passed / 7 skipped / 0 failed**。
`IndexTest` 的 7 条依赖 `android/app/src/test/resources/samples/` 下的真机 `.list` 样本；
样本含设备标识，按约定不入库，缺失时用 JUnit `Assume` **跳过**而不是判失败。

### 产物

| 文件 | 说明 |
|------|------|
| `android/app/build/outputs/apk/release/app-release.apk` | 签名 APK，versionCode 14 / versionName 1.2.0，约 75.3 MB |

实测产物：75,257,546 B，sha256 `f0dbef7779be36c0a6b9942a61f79d6d801d0b0b37215bcadd27c351e8d569d0`。

### 签名

默认使用 `~/.android/debug.keystore`（debug 签名），可覆盖已安装的旧版本。
**debug 签名不适合对外分发**——如需发布，请在 `android/app/build.gradle.kts`
的 `signingConfigs` 里换成自己的 keystore，并把密码放在 `local.properties` 或
环境变量里，不要提交进仓库。

### 双 ABI 支持

`android/app/build.gradle.kts` 已配置：

```kotlin
ndk {
    abiFilters += listOf("arm64-v8a", "armeabi-v7a")
}
```

只带 `arm64-v8a` 时，32 位设备会 `INSTALL_FAILED_NO_MATCHING_ABIS`，
系统界面显示成「应用未安装」。

### jniLibs 里的 ffmpeg

`android/app/src/main/jniLibs/<abi>/` 下的 `libffmpeg.so` / `libffprobe.so`
**不是真正的动态库**，而是静态链接了 ffmpeg 7.1 + libx264 + libx265 的
**PIE 可执行文件**，只是沿用 `lib*.so` 命名以便被打进 `nativeLibraryDir`
（Android 10+ 只允许从该目录执行自带二进制）。

- 必须保持 `jniLibs { useLegacyPackaging = true }`，否则文件会被压缩，无法执行。
- 该目录被 `.gitignore` 排除（约 92 MB）。重建方式见
  `InstaAceAndroid` 导出包里的 `BUILD_NOTES.md`（含 9 条交叉编译踩坑记录）。
- 若只改 Python 逻辑、不动编码参数，不需要重建这两个二进制。

## 三、共享库说明

`shared/` 是**桌面端唯一的引用源**：`desktop/` 下没有 `insta_index.py`，
也没有 `instbox/` 目录，靠 spec 的 `pathex` 指向 `../shared` 与 `../shared/instbox`。

安卓端因为 Chaquopy 只打包 `android/app/src/main/python/` 这一个目录，
在该目录下保留了同名副本：

| 模块 | 桌面端 | 安卓端 |
|------|--------|--------|
| 索引读写 | `shared/insta_index.py`，`import insta_index as ix` | `android/app/src/main/python/insta_index.py` |
| inst 移植 | `shared/instbox/inst_transplant.py`，`import instbox.inst_transplant as _tf` | `android/app/src/main/python/insta360_tf_import.py`，`import insta360_tf_import as _tf` |
| moov 重封装 | `shared/instbox/moov_rewrap.py`，`import instbox.moov_rewrap as _rw` | `android/app/src/main/python/camera_moov_rewrap.py`，`import camera_moov_rewrap as _rw` |

**这两套副本逻辑等价，但不是字节级一致**：安卓副本去掉了 GPL 头、部分中文注释，
模块名也不同。修改共享逻辑时必须两处同时改——`desktop/tests/` 只覆盖桌面端，
安卓侧没有自动化测试。

安卓端 `insta_core.py` 的 `_INST_ORIGIN` 指向自身所在目录，配合上面的顶层模块名
`import` 使用；不要改回 `import instbox.*`（Android 侧不存在该包）。

## 四、GitHub 发布清单

推送前请确认：

- [ ] `.gitignore` 已排除 `build/`、`dist/`、`*.exe`、`*.apk`、`__pycache__/`、`local.properties`、`android/app/build/` 等构建产物
- [ ] `desktop/LICENSE` 和 `android/LICENSE` 均为 GPL-3.0
- [ ] `desktop/CHANGELOG.md` 已记录本次版本的全部修复（当前为 1.2.0）
- [ ] 顶层 `README.md` 已说明仓库结构与构建步骤
- [ ] 本目录 `BUILD.md` 已说明双端构建命令
- [ ] 仓库内无真实设备序列号（`grep -r IBGLA` 应为 0 命中）
- [ ] 仓库内无商业字体、无写死的本机绝对路径
