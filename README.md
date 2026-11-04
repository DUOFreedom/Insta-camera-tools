# InstaAce — 影石 Ace Pro 2 第三方视频导入工具

把普通视频转码为影石 Ace Pro 2 相机相册可识别的原生格式（VID 主视频 + LRV 预览双文件、移植 `inst` box、登记相机索引），使手机相册与 App 能识别并播放。

同时支持桌面端（Windows PyQt5）与安卓端（Android Gradle + Chaquo Python），共享一套核心算法库。

## 仓库结构

```
.
├── desktop/          # Windows 桌面端（PyQt5 + PyInstaller 单文件 exe）
├── android/          # Android 端（Gradle + Chaquo Python，未签名 APK）
├── shared/           # 共享核心库（inst box 移植、moov 重封装、索引 protobuf）
└── docs/             # 构建文档
```

## 功能特点

- 转码：HEVC `hvc1` 1080p 主视频 + H.264 代理文件，无 B 帧、关键帧间隔 16
- `inst` box 移植：以真机原片为模板，写入缩略图与元数据
- 索引登记：`fileinfo_list.list` 与 `.editinfo_list.list` 双表写入
- 开工前体检：ffmpeg、源文件、输出目录、剩余空间、卡可写性、模板片一次性检查
- 断点续跑：中断后重开只跑未完成的条目
- 随时取消：转码中途取消，ffmpeg 进程干净退出
- 同名封面：自动匹配 `a.mp4 → a.jpg / a.png`
- 硬件加速：自动探测 QSV / NVENC / AMF，不可用回落软件编码
- 防休眠：长片处理期间阻止系统休眠
- 三阶段进度：转码 / 移植 / 登记分开显示

## 快速开始

### 桌面端（Windows）

环境：Python 3.11+，PyQt5>=5.15，PyInstaller

```cmd
cd desktop
build.bat
```

产物：`desktop/dist/InstaAceImporter.exe`

### 安卓端

环境：JDK 21，Gradle，Android SDK，Chaquopy Python 3.11

```bash
cd android
./gradlew assembleRelease
```

产物：`android/app/build/outputs/apk/release/app-release.apk`

APK 为**未签名版本**，请使用你自己的证书签名后安装。从源码构建默认使用测试签名。

## 许可证

本项目采用 GPL-3.0-or-later 许可。因链接 libx264/libx265（GPL-2.0-or-later），FFmpeg 7.1 实际为 GPL-2.0-or-later，与项目 GPL-3.0 兼容。

详见 `desktop/LICENSE` 和 `android/LICENSE`。

## 变更日志

桌面端：`desktop/CHANGELOG.md`
