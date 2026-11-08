# InstaAce — 影石 Ace Pro 2 第三方视频导入工具

融合仓库：**桌面端（Windows，双界面）+ 安卓端（Chaquopy / Gradle）** 的影石 Ace Pro 2 视频导入工具。

普通视频转码为影石相机相册可识别的原生格式（VID + LRV 双文件、移植 `inst` box、登记相机索引），使相机相册与 App 能识别并播放。

## 仓库结构

```
instaace-fusion/
├── shared/                        # 共享核心库（桌面端唯一引用源）
│   ├── __init__.py
│   ├── insta_index.py             # 相机索引 protobuf 解析/生成
│   └── instbox/                   # inst box 移植与 moov 重封装
│       ├── __init__.py
│       ├── inst_transplant.py     # camera_udta / inst box 移植 / ftyp 补丁 / 索引登记
│       └── moov_rewrap.py         # moov 骨架重封装 / 样本重排 / avc1 条目精简
├── desktop/                       # 桌面端（Windows）
│   ├── core.py                    # 转码核心（含 QML/CLI 调用接口）
│   ├── gui.py                     # 经典版界面（PyQt5）
│   ├── main.py                    # QML 版入口（PySide6）
│   ├── bridge.py                  # QML 版与 core.py 的槽/信号桥
│   ├── updater.py                 # QML 版更新检查
│   ├── qml/                       # 24 个 QML 组件与视图
│   ├── build.bat / run.bat        # 经典版一键构建 / 一键运行
│   ├── build_qml.bat / run_qml.bat# QML 版一键构建 / 一键运行
│   ├── InstaAceImporter.spec      # 经典版 PyInstaller 配置（onefile）
│   ├── InstaAceQml.spec           # QML 版 PyInstaller 配置（onefile）
│   ├── requirements.txt           # 运行时依赖（PyQt5 + PySide6）
│   ├── requirements-dev.txt       # 开发依赖（+ pytest）
│   ├── assets/                    # 图标、图片等打包资源
│   ├── tests/                     # pytest 离线回归
│   ├── tools/                     # make_icon.py 等辅助工具
│   ├── CHANGELOG.md               # 桌面端变更日志
│   └── LICENSE                    # GPL-3.0
├── android/                       # 安卓端（Gradle + Chaquopy）
│   ├── app/build.gradle.kts       # 应用构建配置（双 ABI）
│   ├── app/src/main/AndroidManifest.xml
│   ├── app/src/main/python/       # Chaquopy Python 源码
│   │   ├── insta_core.py          # 转码核心（安卓版）
│   │   ├── android_bridge.py      # 桥接层（初始化、导入、日志、更新检查）
│   │   ├── camera_moov_rewrap.py  # moov 重封装（安卓副本）
│   │   ├── insta360_tf_import.py  # inst box 移植（安卓副本）
│   │   └── insta_index.py         # 相机索引（安卓副本）
│   ├── app/src/main/java/         # Kotlin（Compose UI + Python 引擎封装）
│   ├── build.gradle.kts
│   ├── settings.gradle.kts
│   ├── gradle.properties
│   ├── local.properties           # SDK 路径，本机配置，不入库
│   └── LICENSE                    # GPL-3.0
├── docs/
│   └── BUILD.md                   # 双端构建指南
└── README.md                      # 本文件
```

## 桌面端两套界面

两套界面功能等价，共用同一份 `core.py` 与 `shared/`：

| 界面 | 技术栈 | 入口 | 构建脚本 | 产物 |
|---|---|---|---|---|
| 经典版 | PyQt5 5.15 | `gui.py` | `build.bat` | 单文件 `InstaAceImporter.exe` |
| QML 版 | PySide6 6.5+ | `main.py` + `bridge.py` + `qml/` | `build_qml.bat` | 单文件 `InstaAceQml.exe`（约 79 MB） |

## 核心设计

### 共享库（`shared/`）

`shared/` 是**桌面端唯一的引用源**：`desktop/` 下没有 `insta_index.py`，也没有 `instbox/` 目录，
靠 spec 的 `pathex` 指向 `../shared` 与 `../shared/instbox`。

安卓端因为 Chaquopy 只打包 `android/app/src/main/python/` 一个目录，保留了同名副本
（`insta360_tf_import.py` / `camera_moov_rewrap.py` / `insta_index.py`）。
**两套副本逻辑等价但不是字节级一致**：安卓副本去掉了 GPL 头与部分中文注释，模块名也不同。
修改共享逻辑时必须两处同时改，`desktop/tests/` 只覆盖桌面端。

已修复的关键缺陷：

- **AMBA 字段重叠写**：`udta_with_audio_frames` 曾把「音频采样率」写到 `amba[0]+0x20`，
  而 `0x20-0x23` 实际是视频帧率（fps_num/fps_den），与 `camera_udta` 写入的
  `(29, 1001)` 在 AMBA 内字节 **32** 处重叠，导致每次导入都把帧率分母写成垃圾值。
  现改为 `amba[0]+0x54`（与 `camera_udta` 的 `(84, frames*4)` 对齐）。
- **AMBA 越界校验**：`camera_udta` 的 9 个偏移改为表驱动 `_amba_fields`，
  逐字段做 `_off + 4 > amba_size` 校验，超界抛 `ValueError`。
- **安卓端模块加载**：`insta_core.py` 的 `_INST_ORIGIN` 指向自身所在目录，
  并用顶层模块名 `import insta360_tf_import` / `import camera_moov_rewrap`
  （Android 侧没有 `instbox` 包，旧写法会让 `init()` 直接抛异常）。

### 桌面端（`desktop/`）

- 语言：Python 3.10+，PyQt5 / PySide6 双界面
- 打包：PyInstaller（两版均为 onefile 单文件）
- 构建与运行命令见 `docs/BUILD.md`

### 安卓端（`android/`）

- 语言：Python 3.11（Chaquopy）+ Kotlin（Compose）
- 构建：Gradle，双 ABI `arm64-v8a` + `armeabi-v7a`
- 签名：默认 `~/.android/debug.keystore`，**对外分发前须换成正式签名**
- APK：`versionCode 14 / versionName 0.7.2`

## 快速开始

### 桌面端构建（Windows）

```cmd
cd desktop
pip install -r requirements.txt
build.bat          rem 经典版 -> dist\InstaAceImporter.exe
build_qml.bat      rem QML 版 -> dist\InstaAceQml\
```

### 安卓端构建

```bash
cd android
# 先在 local.properties 配置 sdk.dir 与 chaquopy.python（或用环境变量）
export JAVA_HOME=<JDK 21 路径>
gradle --no-daemon assembleRelease
```

产物：`android/app/build/outputs/apk/release/app-release.apk`

### 环境要求

| 平台 | 关键依赖 | 构建工具 |
|------|---------|---------|
| 桌面端 | Python 3.10+，PyQt5>=5.15，PySide6>=6.5，PyInstaller 6.x | PyInstaller |
| 安卓端 | JDK 21，Gradle 8.7，Android SDK 34，NDK r27，Chaquopy Python 3.11，ffmpeg 7.1（静态 libx264+libx265） | Gradle |

> 桌面端不锁定具体 Python 小版本；安卓端必须 Python 3.11（Chaquopy 的 armeabi-v7a 构件只到 3.11）。

## 已知限制

### 安卓端 `jniLibs/` 不随仓库分发

`android/app/src/main/jniLibs/<abi>/libffmpeg.so` 与 `libffprobe.so` 共 4 个文件、
约 92 MB，被 `.gitignore` 排除。**只克隆本仓库无法直接 `assembleRelease`**，
需要先补齐这两个二进制：

- 它们本质是 **PIE 可执行文件**（静态链接的 ffmpeg 7.1，含 libx264 + libx265），
  只是沿用 `lib*.so` 命名，以便随 APK 打进 `nativeLibraryDir`（Android 10+ 只允许
  从该目录执行自带二进制）。
- 必须保持 `jniLibs { useLegacyPackaging = true }`，否则不会解压到磁盘、无法执行。
- 重建方式见 [`docs/BUILD.md`](docs/BUILD.md) 的「jniLibs 里的 ffmpeg」一节。

### 真机链路未端到端验证

- AMBA 字段修复只做了合成模板的偏移级验证，未在相机上实拍确认。
- MediaCodec 硬件解码 / 硬件编码路径带自动回退，但未经真机验证。
- 首次真机导入后，建议用 `ffprobe` 比对产物与真机原片的 `avg_frame_rate` / `nb_frames`，
  并检查 `import.log` 中的 `[硬件解码]` / `[回退]` 行。

### 签名

默认回退到 `~/.android/debug.keystore`，仅为能覆盖手机上的旧版。
**正式分发必须配置自有证书**（环境变量 `INSTA_KEYSTORE` / `INSTA_KEYSTORE_PASSWORD` /
`INSTA_KEY_ALIAS` / `INSTA_KEY_PASSWORD`，或 `local.properties` 的 `insta.keystore*`），
否则任何持有 debug.keystore 的人都能伪造升级包。

## 许可证

本项目采用 **GPL-3.0-or-later** 许可。因为链接了 libx264/libx265（GPL-2.0-or-later），
FFmpeg 7.1 实际为 GPL-2.0-or-later，与项目 GPL-3.0 兼容。

详见根目录 `LICENSE`（以及 `desktop/LICENSE`、`android/LICENSE` 副本）。

## 变更日志

桌面端变更请见 `desktop/CHANGELOG.md`。

## 真机验证

安卓 APK 需在实际 Insta360 Ace Pro 2 设备上验证：覆盖安装 APK，导入一段视频，
确认相机相册能识别并播放。构建机上无 adb，验证依赖真机侧导出的 `import.log` 或截图。
