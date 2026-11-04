# InstaAce — 影石 Ace Pro 2 第三方视频导入工具

融合仓库：**同时支持桌面端（Windows PyQt5）和安卓端（Chaquopy / Android Gradle）** 的影石 Ace Pro 2 视频导入工具。

普通视频转码为影石相机相册可识别的原生格式（VID + LRV 双文件、移植 `inst` box、登记相机索引），使手机相册与 App 能识别并播放。

## 仓库结构

```
instaace-fusion/
├── shared/              # 共享核心库（桌面 + 安卓通用）
│   ├── __init__.py
│   ├── insta_index.py   # 相机索引 protobuf 解析/生成（fileinfo_list.list, .editinfo_list.list）
│   └── instbox/         # inst box 移植与 moov 重封装
│       ├── __init__.py
│       ├── inst_transplant.py  # camera_udta / inst box 移植 / ftyp 补丁 / 索引登记
│       └── moov_rewrap.py      # moov 骨架重封装 / 音视频样本重排 / avc1 采样条目精简
├── desktop/             # 桌面端（Windows，PyQt5 + PyInstaller）
│   ├── core.py          # 转码核心（桌面版，含 GUI 调用接口）
│   ├── gui.py           # PyQt5 图形界面
│   ├── build.bat        # PyInstaller 一键打包脚本
│   ├── run.bat          # 开发模式直接运行脚本
│   ├── InstaAceImporter.spec  # PyInstaller 打包规范
│   ├── requirements.txt # 运行时依赖（PyQt5）
│   ├── requirements-dev.txt   # 开发依赖（PyQt5 + pytest）
│   ├── assets/          # 图标、图片等打包资源
│   ├── tests/           # pytest 离线回归
│   ├── tools/           # make_icon.py 等辅助工具
│   ├── CHANGELOG.md     # 桌面端变更日志
│   └── LICENSE          # GPL-3.0
├── android/             # 安卓端（Gradle + Chaquo Python）
│   ├── build.gradle.kts         # Gradle 构建配置（双 ABI arm64-v8a/armeabi-v7a）
│   ├── settings.gradle.kts
│   ├── gradle.properties
│   ├── local.properties         # SDK 路径（需本地配置 sdk.dir）
│   ├── AndroidManifest.xml      # 应用清单
│   ├── LICENSE                  # GPL-3.0
│   └── src/main/python/         # Chaquo Python 源码
│       ├── insta_core.py        # 转码核心（安卓版，含 android_bridge 调用）
│       ├── android_bridge.py    # 安卓桥接层（卡检测、索引写入、前台服务等）
│       ├── camera_moov_rewrap.py# moov 重封装（安卓版）
│       ├── insta360_tf_import.py# inst box 移植（安卓版）
│       └── insta_index.py       # 相机索引（安卓版副本）
├── docs/                # 文档
└── README.md            # 本文件
```

## 核心设计

### 共享库 (`shared/`)
`instbox/inst_transplant.py`、`instbox/moov_rewrap.py`、`insta_index.py` 三个模块在桌面端和安卓端之间**完全同源**（字节级一致），已修复以下问题：

- **AMBA 硬编码偏移**：`camera_udta` 中 9 个硬编码 AMBA 偏移（25/29/41/49/53/67/71/84/91）改为表驱动 `_amba_fields`，逐字段做 `_off + 4 > amba_size` 越界校验，超界抛 `ValueError`，不再静默写错字节。
- **AMBA 音频偏移**：`udta_with_audio_frames` 中 `amba[0]+84`/`amba[0]+91` 改为按实测布局的 `amba[0]+0x20`（音频采样率）/`amba[0]+0x5B`（音频帧数），并加边界检查；修复 `audio_fps_field` 未定义导致的 `NameError`。

### 桌面端 (`desktop/`)
- 语言：Python 3.11+，PyQt5 GUI
- 打包：PyInstaller `--onefile --windowed`，输出单文件 `InstaAceImporter.exe`
- 构建：`desktop/build.bat`
- 直接运行：`desktop/run.bat`

### 安卓端 (`android/`)
- 语言：Python 3.11（Chaquopy）+ Kotlin
- 构建：Gradle，双 ABI `arm64-v8a` + `armeabi-v7a`
- 签名：`~/.android/debug.keystore`（debug.keystore，可覆盖安装）
- APK：`versionCode 13 / versionName 0.7.1`

## 快速开始

### 桌面端构建（Windows）

```cmd
cd desktop
build.bat
```

产物：`desktop/dist/InstaAceImporter.exe`

### 安卓端构建

```bash
cd android
# 需配置 local.properties 中的 sdk.dir 指向 Android SDK
JAVA_HOME=/d/android-build/jdk21 /d/android-build/gradle-8.7/bin/gradle --no-daemon assembleRelease
```

产物：`android/app/build/outputs/apk/release/app-release.apk`

### 环境要求

| 平台 | 关键依赖 | 构建工具 |
|------|---------|---------|
| 桌面端 | Python 3.14，PyQt5>=5.15，PyInstaller 6.22.3 | PyInstaller |
| 安卓端 | JDK 21，Gradle 8.7，Android SDK 34，NDK r27，Chaquopy Python 3.11，ffmpeg 7.1（静态 libx264+libx265） | Gradle |

## 许可证

本项目采用 **GPL-3.0-or-later** 许可。因为链接了 libx264/libx265（GPL-2.0-or-later），FFmpeg 7.1 实际为 GPL-2.0-or-later，与项目 GPL-3.0 兼容。

详见 `desktop/LICENSE` 和 `android/LICENSE`。

## 变更日志

桌面端变更请见 `desktop/CHANGELOG.md`。

## 真机验证

安卓 APK 需在实际 Insta360 Ace Pro 2 设备上验证：覆盖安装 `latest.apk`，导入一段视频，确认相机相册能识别并播放。本机无 adb，验证依赖用户提供 `import.log` 或截图。
