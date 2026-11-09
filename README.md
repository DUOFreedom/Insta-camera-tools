# InstaAce

**把普通视频转成影石 Ace Pro 2 相册认得的原生格式** —— 生成 VID + LRV 双文件、移植 `inst` box、登记相机索引，让相机和官方 App 能识别并播放。

[![License](https://img.shields.io/badge/license-GPL--3.0--or--later-blue?style=flat-square)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-3776ab?style=flat-square)](desktop/requirements.txt)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Android-6f42c1?style=flat-square)](#安装)
[![Version](https://img.shields.io/badge/version-1.2.0-success?style=flat-square)](desktop/CHANGELOG.md)
[![Tests](https://img.shields.io/badge/tests-61%20passed-brightgreen?style=flat-square)](desktop/tests)

```bash
python desktop/core.py D:/clips/holiday.mp4 D:/card/DCIM/Camera01
# 输入：任意 mp4/mov/mkv，输出目录指向相机卡
# 输出：VID_20261109_183000_000.mp4 + LRV_20261109_183000_000.lrv
```

> 演示图 / GIF：TODO（仓库内暂无演示素材，需补一段真机相册识别录屏）

## 安装

桌面端分两套界面，功能等价、共用同一份 `desktop/core.py`。任选其一，或两个都装。

### 桌面端（Windows）

```bash
git clone https://github.com/DUOFreedom/Insta-camera-tools.git
cd Insta-camera-tools/desktop
pip install -r requirements.txt
```

装完还需要 **ffmpeg**。程序按下面的顺序自己找，找到就跳过下载：

| 查找位置 | 说明 |
|---|---|
| `FFMPEG_PATH` / `FFPROBE_PATH` | 环境变量，优先级最高 |
| exe 所在目录及其 `bin/` | 打包版解压后自带 |
| `%LOCALAPPDATA%\InstaAceImporter\bin` | 程序自己的下载目录 |
| `C:\ffmpeg\bin` 等常见路径 | 含 Chocolatey 的 `bin` |
| 系统 `PATH` | 最后兜底 |

<details>
<summary>不想让它自己下载，手动指定 ffmpeg</summary>

```bash
set FFMPEG_PATH=D:\tools\ffmpeg\bin\ffmpeg.exe
set FFPROBE_PATH=D:\tools\ffmpeg\bin\ffprobe.exe
```

必须是带 **libx264 + libx265** 的构建，否则转码会报编码器不存在。
</details>

### 安卓端

```bash
cd android
# 先在 local.properties 写 sdk.dir 与 chaquopy.python，或改用环境变量
export JAVA_HOME=D:/android-build/jdk21/jdk-21.0.12.1+1
export ANDROID_HOME=D:/android-build/sdk
export CHAQUOPY_PYTHON=D:/android-build/py311/python.exe
export GRADLE_USER_HOME=D:/android-build/.gradle
gradle --offline :app:assembleRelease
```

产物：`android/app/build/outputs/apk/release/app-release.apk`

> **只 clone 仓库不能直接构建安卓端**：`jniLibs/` 里的 4 个 ffmpeg 二进制约 92 MB，被 `.gitignore` 排除；仓库也**没有** Gradle wrapper（无 `gradlew`）。补齐方法见 [`docs/BUILD.md`](docs/BUILD.md)。

## 快速开始

```bash
cd desktop
python core.py D:/clips/holiday.mp4 D:/card/DCIM/Camera01
# 输入：一个视频文件，输出目录 = 相机卡里的 DCIM/Camera01
# 输出：打印 "生成完成:" 以及 VID 与 LRV 两个文件路径
# 拔卡插回相机，相册里应该能看到这段视频
```

批量转换：把第一个参数换成一个目录即可，程序会自动接续卡里已有的序号。

```bash
python core.py D:/clips D:/card/DCIM/Camera01
# 输出：成功 N 个，失败 M 个。（失败的逐条列出原因）
```

## 配置

命令行只有三个位置参数，全部可省略后两个：

| 参数 | 默认值 | 说明 |
|---|---|---|
| 输入路径 | 无（必填） | 视频文件，或含视频的目录 |
| 输出目录 | 输入文件所在目录 | 建议指向 `DCIM/Camera01` |
| 起始序号 | 自动接续 | 省略时会扫描卡里已有文件的最大序号 |

环境变量：

| 变量 | 默认值 | 说明 |
|---|---|---|
| `FFMPEG_PATH` | 自动查找 | ffmpeg 可执行文件绝对路径 |
| `FFPROBE_PATH` | 自动查找 | ffprobe 可执行文件绝对路径 |

安卓端在「设置」页有两个开关：

| 选项 | 默认值 | 说明 |
|---|---|---|
| 编码器 | `自动` | `自动` = 软件编码 libx265 + libx264，相机识别最稳 |
| 登记相机索引 | 开 | 写入 DCIM 下的 fileinfo / editinfo，相册才出现 |

<details>
<summary>为什么「硬件」编码可能让相机不认</summary>

MediaCodec 的关键帧间隔受系统 `MediaFormat` 限制，只能按**整数秒**设置。相机要求 16 帧的密集 GOP，30fps 下约 0.53 秒，硬编只能给到 1 秒（约 30 帧）。

结果是文件能生成、也能播，但相机可能不显示缩略图或干脆不识别。导入后若相册看不到，切回「自动」重导一次。
</details>

## 常见问题

### 报 `ValidationError: 未找到 ffmpeg，无法构建转码命令`

程序没找到 ffmpeg。按上面的查找顺序检查，最快是直接指定：

```bash
set FFMPEG_PATH=D:\tools\ffmpeg\bin\ffmpeg.exe
set FFPROBE_PATH=D:\tools\ffmpeg\bin\ffprobe.exe
```

注意 `ffmpeg -version` 必须能正常输出。装的是精简构建（不带 libx264/libx265）也会在转码阶段失败。

### 报 `目标不是影石相机卡（缺少 DCIM/Camera01 结构）`

索引登记前会校验目标确实是相机卡，防止在普通文件夹里误建 `DCIM` 污染数据。把输出目录指到卡上的 `DCIM` 或 `DCIM/Camera01` 再跑。

### 报 `卡里找不到真机原片作模板（DCIM/Camera01/VID_*.mp4 + LRV_*.lrv）`

程序需要一对**相机原生录制**的 VID/LRV 当模板 —— 它要抄模板里的 `inst` box 结构和索引条目格式，这些没法凭空构造。

解决：先用相机随手录一小段（几秒即可），让它留在卡里，再跑转换。

### 报 `缓存空间不足：源 2.1 GB，可用 800 MB`

安卓端导入会先把源文件复制到应用私有目录，并按源大小的 3 倍预留（转码中间产物 + 输出）。清理手机存储，或先删掉队列里的大文件。

### 报 `Plugin [id: 'com.android.application', version: '8.7.3'] was not found`

Gradle 在错误的目录找依赖缓存。项目需要 AGP 8.7.3，而 `~/.gradle` 里通常只有旧版本：

```bash
export GRADLE_USER_HOME=D:/android-build/.gradle
```

如果报 `Minimum supported Gradle version is 8.9. Current version is 8.7`，那是 Gradle 版本太低 —— 必须用 8.11.1，`D:\android-build` 下同时存在 8.7 和 8.11.1，只有后者能构建。

## 贡献

```bash
cd desktop
pip install -r requirements-dev.txt
python -m pytest tests/ -q
```

预期 `61 passed, 2 skipped`。跳过的两条依赖真机索引样本（`desktop/samples/`、`android/app/src/test/resources/samples/`），样本含设备标识，按约定不入库。

改代码前请先读 [`docs/BUILD.md`](docs/BUILD.md)。两处容易踩：

- **共享逻辑有两份**：`shared/instbox/` 是桌面端唯一引用源，安卓端因为 Chaquopy 只打包一个目录而保留了同名副本。改 `insta_index.py` / inst 移植逻辑必须两边同时改。
- **改完要更新产物**：`desktop/CHANGELOG.md` 记录了每次重建的尺寸与核对方法，提交前跑一遍双端构建。

## 许可证

[GPL-3.0-or-later](LICENSE)。

项目链接了 libx264 / libx265（GPL-2.0-or-later），实际使用的 FFmpeg 7.1 因此也是 GPL-2.0-or-later，与 GPL-3.0 兼容。

## 架构

<details>
<summary>仓库结构与模块职责</summary>

```
instaace-fusion/
├── shared/                    # 桌面端唯一引用源
│   ├── insta_index.py         # 相机索引 protobuf 解析 / 生成
│   └── instbox/
│       ├── inst_transplant.py # inst box 移植、ftyp 补丁、索引登记
│       └── moov_rewrap.py     # moov 重封装、样本重排、avc1 精简
├── desktop/                   # Windows 桌面端
│   ├── core.py                # 转码核心（GUI / QML / CLI 共用）
│   ├── gui.py                 # 经典版界面（PyQt5）
│   ├── main.py + bridge.py    # QML 版入口（PySide6）
│   ├── qml/                   # 22 个 QML 组件 + main.qml 主视图
│   ├── build.bat              # 经典版构建 -> InstaAceImporter.exe
│   └── build_qml.bat          # QML 版构建 -> InstaAceQml.exe
├── android/                   # Gradle + Chaquopy
│   ├── app/src/main/python/   # insta_core.py / android_bridge.py 等
│   └── app/src/main/java/     # Kotlin（Compose UI + Python 引擎封装）
└── docs/BUILD.md              # 双端构建指南
```

</details>

<details>
<summary>为什么需要「转码 + 移植」两步</summary>

相机不只看文件扩展名，它同时校验三件事：

1. **文件名与索引**：`VID_YYYYMMDD_HHMMSS_NNN.mp4` 格式，且 DCIM 下的 `fileinfo_list.list` 里有对应条目。
2. **`inst` box**：moov 里一段影石私有的元数据，记着时间戳、帧率、缩略图等。缺了它文件能播但相册不认。
3. **AMBA 字段**：`udta` 里一段相机专属字段表，帧率、音频参数等按固定偏移写入，越界或错位都会让相机拒收。

所以流程是：先用 ffmpeg 转出符合相机参数的 VID/LRV 双文件（16 帧密集 GOP、hvc1/avc1 标签、指定色彩范围），再从真机模板里抄 `inst` box 结构移植过去，最后把新条目追加进索引 —— 追加而非重建，所以卡里原有的视频不受影响。

</details>

<details>
<summary>已知限制</summary>

- **真机链路未端到端验证**：AMBA 字段修复只做了合成模板的偏移级验证，MediaCodec 硬件解码/编码路径带自动回退但未经真机确认。首次真机导入后建议用 `ffprobe` 比对产物与真机原片的 `avg_frame_rate` / `nb_frames`。
- **安卓端未随 Release 分发 APK**：真机导入链路与部分机型兼容性尚未验证完毕。
- **签名**：默认回退到 `~/.android/debug.keystore`，仅为能覆盖安装旧版。正式分发必须配置自有证书（`INSTA_KEYSTORE` / `INSTA_KEYSTORE_PASSWORD` / `INSTA_KEY_ALIAS` / `INSTA_KEY_PASSWORD`），否则任何持有 debug.keystore 的人都能伪造升级包。

</details>
