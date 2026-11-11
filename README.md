<p align="center">
  <img src="desktop/assets/app.svg" width="112" alt="影石相机工具">
</p>

<h1 align="center">instatools</h1>

<p align="center">
把普通视频转成影石相机相册认得的原生格式：产出 VID + LRV 成对文件、移植相机私有的 <code>inst</code> box、登记 DCIM 索引。
</p>

<p align="center">
  <a href="README.en.md">English</a> · <a href="README.md">中文</a>
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-GPL--3.0--or--later-blue?style=flat-square" alt="License"></a>
  <a href="desktop/CHANGELOG.md"><img src="https://img.shields.io/badge/version-1.2.0-success?style=flat-square" alt="Version"></a>
  <a href="desktop/requirements.txt"><img src="https://img.shields.io/badge/python-3.10%2B-3776ab?style=flat-square" alt="Python"></a>
  <a href="desktop/tests"><img src="https://img.shields.io/badge/tests-178%20passed-brightgreen?style=flat-square" alt="Tests"></a>
  <img src="https://img.shields.io/badge/platform-Windows%20%7C%20Android-6f42c1?style=flat-square" alt="Platform">
</p>

---

## 📦 安装

桌面端和安卓端跑的是同一套转换逻辑（两份手工同步的副本），装哪一端取决于你要在哪台机器上转换。

### 桌面端（Windows）

```bash
git clone https://github.com/duofreedom/Insta-camera-tools.git
cd Insta-camera-tools/desktop
pip install -r requirements.txt
```

`requirements.txt` 只装 `PySide6>=6.5`。要求 Python 3.10+。

桌面端入口 `desktop/run_qml.bat`（`pythonw main.py`），打包脚本 `desktop/build_qml.bat` → `desktop/dist/instatools.exe`（单文件，约 79 MB）。

<details>
<summary>桌面端功能对照</summary>

早期有两套并列界面（PyQt5 经典版 + QML 版）。经典版已删除，只保留 QML 版 —— 两套界面维护同一份逻辑，缺陷总是「修一遍、第二遍忘」，合并后这类漂移不可能再发生。

删除时 QML 版缺的九项已全部补齐，都有测试守着（`desktop/tests/test_qml_bridge.py`）：

| 能力 | 入口 |
| --- | --- |
| 开工前体检 | `Bridge.start()` 调 `core.preflight` |
| 自动找样本 | `Bridge.autoDetectSample` |
| 封面选择 | `Bridge.pickCover` / `clearCovers` |
| 断点续跑 | `Bridge.checkResume` + `_run` 里逐步存 `core.save_job` |
| 卡校验与清理 | `Bridge.verifyCard` / `repairCard` |
| 定位 SD 卡 | `Bridge.locateCard` |
| 单条移除 | `Bridge.removeFile` |
| 硬件编码器探测 | `Bridge.detectHardware` |
| 拖拽添加 | `DropArea` → `Bridge.addPaths` |

转换中关窗给两个出路：停止并退出（`cancel()` + `waitWorker(20000)` 确认线程结束后才退出）、最小化到托盘（转换继续，跑完弹通知）。直接退出会让 ffmpeg 变孤儿继续往相机卡写，留下半截 VID/LRV 且索引没登记。

</details>

### 安卓端

```bash
cd android
gradle --offline :app:assembleRelease
```

产物：`android/app/build/outputs/apk/release/app-release.apk`（约 75 MB）。需要 JDK 21、Gradle 8.11.1、Android SDK 35、Python 3.11，并让 `JAVA_HOME`、`ANDROID_HOME`、`CHAQUOPY_PYTHON`、`GRADLE_USER_HOME` 指向本机安装位置。完整环境要求见 [`docs/BUILD.md`](docs/BUILD.md)。

> **只 clone 仓库不能直接构建安卓端。** 仓库没有 Gradle wrapper（无 `gradlew`），且 `android/app/src/main/jniLibs/` 下的 4 个 ffmpeg/ffprobe 二进制约 91 MB 被 `.gitignore` 排除（`arm64-v8a` 与 `armeabi-v7a` 双 ABI）。补齐方法见 [`docs/BUILD.md`](docs/BUILD.md)。

### 安装 ffmpeg

桌面端需要带 **libx264 + libx265** 的 ffmpeg。程序按下面的顺序自己找，**先看系统里装没装，再退到程序自己的目录**：

| 查找顺序 | 位置 |
|---|---|
| 1 | 环境变量 `FFMPEG_PATH` / `FFPROBE_PATH` |
| 2 | 注册表 `App Paths\ffmpeg.exe`（安装器登记的位置，HKLM 优先于 HKCU） |
| 3 | `C:\Program Files\instatools\bin`（本程序「装到系统目录」的目标） |
| 4 | `C:\Program Files\ffmpeg\bin`、`C:\Program Files (x86)\ffmpeg\bin`、`C:\ffmpeg\bin`、`%ProgramData%\chocolatey\bin`、`~\scoop\shims`、`%LOCALAPPDATA%\Microsoft\WinGet\Links` |
| 5 | 系统 `PATH`（`shutil.which`） |
| 6 | exe 所在目录及其 `bin\` 子目录 |
| 7 | `%LOCALAPPDATA%\instatoolsImporter\bin`、`~\instatoolsImporter\bin` |

实现见 `desktop/core.py:161` 的 `_system_tool_dirs()`、`desktop/core.py:146` 的 `_portable_tool_dirs()` 与 `desktop/core.py:179` 的 `_registry_ffmpeg()`。找到后还会实跑一次 `ffmpeg -version` 确认可用。

都找不到时，界面上会出现一个橙色横幅，给两个按钮：

| 按钮 | 装到哪 | 需要什么 |
|---|---|---|
| 装到系统目录 | `C:\Program Files\instatools\bin`，所有程序都能用，并登记到注册表 `App Paths` | 管理员权限（弹 UAC） |
| 装到程序目录 | exe 同目录下的 `bin\`，程序目录不可写时退回 `%LOCALAPPDATA%\instatoolsImporter\bin` | 不需要任何权限 |

两个按钮都是**先下载到临时目录、再落盘**：用户拒绝 UAC 时只损失几秒，不用重下 200 MB。装完会自动重探硬件编码器，否则横幅消失了「未检测到硬件编码器」也不会更新。

<details>
<summary>手动指定 ffmpeg 路径</summary>

```bash
set FFMPEG_PATH=D:\tools\ffmpeg\bin\ffmpeg.exe
set FFPROBE_PATH=D:\tools\ffmpeg\bin\ffprobe.exe
```

必须是带 libx264 + libx265 的构建，精简构建会在转码阶段报编码器不存在。
</details>

## 🚀 快速开始

### 命令行

```bash
python desktop/core.py D:/clips/holiday.mp4 D:/card/DCIM/Camera01
```

输出两个文件（`stamp` 取源视频自己的拍摄时间，`NNN` 是序号）：

```
VID_20261109_183000_000.mp4
LRV_20261109_183000_000.lrv
```

时间戳优先取容器内嵌的 `creation_time`，其次取文件系统时间，都没有才用当前时间（`desktop/core.py:1594` `_source_stamp()`）。这样导入的视频在相册里按原始拍摄时间排序，而不是全挤在导入当天。

主视频与代理的编码格式、分辨率、帧率、GOP **全部跟随卡里的真机模板**：Ace Pro 2 是 `libx265`+`hvc1` / `libx264`+`avc1`、GOP 16，GO Ultra 两轨都是 `hvc1`、GOP 分别是 120 与 10。模板的 GOP 从 `stss` 量出来（`shared/instbox/inst_transplant.py:233` 的 `video_gop()`），写进 AMBA box 偏移 53 并同时约束 ffmpeg 的 `-g`。参数见 `desktop/core.py:67-72` 与 `desktop/core.py:1194-1200`。

### 批量转换

第一个参数换成目录即可，程序按扩展名（`.mp4` `.mov` `.mkv` `.avi` `.ts` `.flv` `.wmv` `.m4v`）过滤后逐个转换：

```bash
python desktop/core.py D:/clips D:/card/DCIM/Camera01
```

结束打印 `成功 N 个，失败 M 个。`，失败的逐条列出原因。

### 图形界面

1. 双击 `desktop/dist/instatools.exe`，或在 `desktop/` 下运行 `run_qml.bat`。
2. 输出目录选到卡上的 `DCIM\Camera01`。
3. 样本选卡里任意一段相机原生录制的 `VID_*.mp4`，或点「自动从存储卡分析」让它自己找。
4. 添加视频，点「开始转换」。
5. 拔卡插回相机，相册里应能看到这段视频。

## 🔧 配置

### 命令行参数

| 参数 | 默认值 | 说明 |
|---|---|---|
| 输入路径 | 无（必填） | 视频文件，或含视频的目录 |
| 输出目录 | 输入文件所在目录 | 建议指向 `DCIM\Camera01` |
| 起始序号 | 自动接续 | 省略时扫描卡里已有文件的最大序号 |

无参数运行会打印用法并以退出码 1 结束。三个参数的位置由 `desktop/core.py:3104` 起的 `__main__` 块解析。

### 环境变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| `FFMPEG_PATH` | 自动查找 | ffmpeg 可执行文件绝对路径 |
| `FFPROBE_PATH` | 自动查找 | ffprobe 可执行文件绝对路径 |

两者都必须是存在的文件才会被采用，否则回落到查找顺序。

### 安卓端设置

| 选项 | 默认值 | 说明 |
|---|---|---|
| 编码器 | `自动` | `自动` = 软件编码 libx265 + libx264 |
| 登记相机索引 | 开 | 写入 DCIM 下的 fileinfo / editinfo，相册才会出现 |

<details>
<summary>「硬件」编码可能让相机不认</summary>

MediaCodec 的关键帧间隔受系统 `MediaFormat` 限制，只能按整数秒设置。相机要求密集 GOP（Ace Pro 2 是 16 帧、GO Ultra 的 VID 是 120 帧），30fps 下 16 帧约 0.53 秒，硬编只能给到 1 秒。

结果是文件能生成、也能播，但相机可能不显示缩略图或干脆不识别。导入后若相册看不到，切回「自动」重导一次。这条限制在安卓端设置页的说明文案里也写着。
</details>

<details>
<summary>支持的机型</summary>

规格不写死，从卡里那对**真机原片**量出来，所以机型差异不需要改代码：

| 项目 | Ace Pro 2 | GO Ultra | 来源 |
|---|---|---|---|
| VID | HEVC 1080p | HEVC 1080p @59.94 | ffprobe |
| VID 关键帧间隔 | 16 | 120 | `stss` |
| LRV 编码 | H.264 `avc1` | HEVC `hvc1` | `stsd` |
| LRV 关键帧间隔 | 16 | 10 | `stss` |
| `AMBA[53]` | 16 | 120 / 10 | 上面两项 |

转换时按模板选编码器与 `-g`，移植 `inst` box 时把真实间隔写进 `AMBA[53]`（相机按它算缩略图抽帧位置）。换机型只需要卡里留一段该机型自己录的原片，无需改代码或加配置。

GO Ultra 的适配来自用户提供的真机素材，两代机型的差异见 [CHANGELOG](desktop/CHANGELOG.md) 的「Go Ultra 机型适配」一节。
</details>

## ❓ 常见问题

### 报 `ValidationError: 未找到 ffmpeg，无法构建转码命令`

程序没找到 ffmpeg（`desktop/core.py:1027`）。按上面的查找顺序检查，最快是直接指定：

```bash
set FFMPEG_PATH=D:\tools\ffmpeg\bin\ffmpeg.exe
set FFPROBE_PATH=D:\tools\ffmpeg\bin\ffprobe.exe
```

`ffmpeg -version` 必须能正常输出；装的是精简构建（不带 libx264/libx265）也会在转码阶段失败。

### 报 `目标不是影石相机卡（缺少 DCIM\Camera01 结构）`

索引登记前会校验目标确实是相机卡，避免在普通文件夹里误建 `DCIM` 污染数据（`desktop/core.py:2111`）。把输出目录指到卡上的 `DCIM` 或 `DCIM\Camera01` 再跑。

### 报 `卡里找不到真机原片作模板（DCIM\Camera01\VID_*.mp4 + LRV_*.lrv）`

程序需要一对**相机原生录制**的 VID/LRV 当模板，它要抄模板里的 `inst` box 结构和索引条目格式（`desktop/core.py:2279`）。

解决：先用相机随手录几秒，让它留在卡里，再跑转换。

### 报 `缓存空间不足：源 2.1 GB，可用 800 MB`

安卓端导入会先把源文件复制到应用私有目录，并按源大小的 3 倍预留（转码中间产物 + 输出，判据见 `AppState.kt:373`）。清理手机存储，或先删掉队列里的大文件。

### 安卓构建报 `Plugin [id: 'com.android.application', version: '8.7.3'] was not found`

<details>
<summary>展开处理办法</summary>

Gradle 在错误的目录找依赖缓存。项目需要 AGP 8.7.3，而默认的 `~/.gradle` 里通常只有旧版本：

```bash
export GRADLE_USER_HOME=D:/android-build/.gradle
```

若报 `Minimum supported Gradle version is 8.9. Current version is 8.7`，那是 Gradle 本身版本太低，必须用 8.11.1。两者都缓存在同一目录时，只有 8.11.1 能构建。详见 [`docs/BUILD.md`](docs/BUILD.md)。
</details>

## 🤝 贡献

```bash
cd desktop
pip install -r requirements-dev.txt
python -m pytest tests/ -q
```

预期 `178 passed, 2 skipped`。跳过的两条依赖真机索引样本（`desktop/samples/`、`android/app/src/test/resources/samples/`），样本含设备标识，按约定不入库。

改代码前请先读 [`docs/BUILD.md`](docs/BUILD.md)。两处容易踩：

- **共享逻辑有多份副本，改一处必须同时改另一处**。`shared/insta_index.py` 与 `android/app/src/main/python/insta_index.py` 是两份副本，`desktop/tests/test_insta.py:491` 的 `test_insta_index_copies_do_not_drift` 用剥掉 docstring 的 AST 比对，逻辑漂移会直接失败。`shared/instbox/` 下的两个模块在安卓侧**文件名不同**：

| 桌面端 | 安卓端 |
|---|---|
| `shared/instbox/inst_transplant.py` | `android/app/src/main/python/insta360_tf_import.py` |
| `shared/instbox/moov_rewrap.py` | `android/app/src/main/python/camera_moov_rewrap.py` |
| `shared/insta_index.py` | `android/app/src/main/python/insta_index.py` |

- **改完要更新产物记录**：`desktop/CHANGELOG.md` 记了每次重建的实测尺寸与核对方法，提交前跑一遍双端构建。

## 📄 许可证

[GPL-3.0-or-later](LICENSE)。

项目链接了 libx264 / libx265（GPL-2.0-or-later），实际使用的 FFmpeg 7.1 因此也是 GPL-2.0-or-later，与 GPL-3.0 兼容。第三方声明见 [`android/app/src/main/assets/docs/open-source-notices.md`](android/app/src/main/assets/docs/open-source-notices.md)。

## 🗂 架构

<details>
<summary>仓库结构与模块职责</summary>

```
instaace-fusion/
├── shared/                       # 桌面端唯一引用源
│   ├── insta_index.py            # 相机索引 protobuf 解析 / 生成
│   └── instbox/
│       ├── inst_transplant.py    # inst box 移植、ftyp 补丁
│       └── moov_rewrap.py        # moov 重封装、样本重排、avc1 精简
├── desktop/                      # Windows 桌面端
│   ├── core.py                   # 转码核心（界面 / CLI 共用）
│   ├── main.py                   # 入口（PySide6 + QApplication）
│   ├── bridge.py                 # 界面与 core.py 之间的桥
│   ├── tray.py                   # 系统托盘（转换中最小化继续跑）
│   ├── updater.py                # 更新检查
│   ├── qml/                      # 23 个 .qml（含 main.qml）
│   └── build_qml.bat             # 打包脚本
├── android/                      # Gradle + Chaquopy
│   ├── app/src/main/python/      # insta_core.py / android_bridge.py 等
│   └── app/src/main/java/        # Kotlin（Compose UI + Python 引擎封装）
└── docs/BUILD.md                 # 双端构建指南
```

`desktop/qml/` 共 23 个 `.qml`（含 `main.qml`）。其中 `Card.qml`、`Divider.qml`、`Sidebar.qml`、`TextArea.qml`、`Toast.qml`、`Tooltip.qml` 这 6 个没有任何 QML 文件引用（`qmldir` 里仍有登记）。

</details>

<details>
<summary>为什么需要「转码 + 移植」两步</summary>

相机不只看文件扩展名，它同时校验三件事：

1. **文件名与索引**：`VID_YYYYMMDD_HHMMSS_NNN.mp4` 格式，且 `DCIM` 下的 `fileinfo_list.list` 里有对应条目。
2. **`inst` box**：moov 里一段影石私有的元数据，记着时间戳、帧率、缩略图等。缺了它文件能播但相册不认。
3. **AMBA 字段**：`udta` 里一段相机专属字段表，帧率、音频参数按固定偏移写入，越界或错位都会让相机拒收。

所以流程是：先用 ffmpeg 转出符合相机参数的 VID/LRV 双文件（16 帧密集 GOP、hvc1/avc1 标签、指定色彩范围），再从真机模板里抄 `inst` box 结构移植过去，最后把新条目追加进索引。索引是追加而非重建，卡里原有的视频不受影响。

索引文件在卡根下的 `DCIM\fileinfo_list.list` 与 `DCIM\.editinfo_list.list`（注意后者带前导点），字段定义见 `shared/insta_index.py` 顶部 docstring。

</details>

<details>
<summary>已知限制</summary>

- **真机链路未端到端验证**：AMBA 字段修复只做了合成模板的偏移级验证，MediaCodec 硬件编解码路径带自动回退但未经真机确认。首次真机导入后建议用 `ffprobe` 比对产物与真机原片的 `avg_frame_rate` / `nb_frames`。
- **安卓端未随 Release 分发 APK**：真机导入链路与部分机型兼容性尚未验证完毕。
- **签名**：默认回退到 `~/.android/debug.keystore`，仅为能覆盖安装旧版。正式分发必须配置自有证书（`INSTA_KEYSTORE` / `INSTA_KEYSTORE_PASSWORD` / `INSTA_KEY_ALIAS` / `INSTA_KEY_PASSWORD`），否则任何持有 debug.keystore 的人都能伪造升级包。

</details>
