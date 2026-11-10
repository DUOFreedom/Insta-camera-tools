<p align="center">
  <img src="desktop/assets/app.svg" width="112" alt="影石相机工具">
</p>

<h1 align="center">InstaAce</h1>

<p align="center">
把普通视频转成影石相机相册认得的原生格式：产出 VID + LRV 成对文件、移植相机私有的 <code>inst</code> box、登记 DCIM 索引。
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-GPL--3.0--or--later-blue?style=flat-square" alt="License"></a>
  <a href="desktop/CHANGELOG.md"><img src="https://img.shields.io/badge/version-1.2.0-success?style=flat-square" alt="Version"></a>
  <a href="desktop/requirements.txt"><img src="https://img.shields.io/badge/python-3.10%2B-3776ab?style=flat-square" alt="Python"></a>
  <a href="desktop/tests"><img src="https://img.shields.io/badge/tests-110%20passed-brightgreen?style=flat-square" alt="Tests"></a>
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

`requirements.txt` 里是两套界面的依赖，一次装齐：`PyQt5>=5.15`（经典版）与 `PySide6>=6.5`（QML 版）。要求 Python 3.10+。

**桌面端有两套界面，共用 `desktop/core.py`，但功能不等价。**

| 功能 | 经典版 | QML 版 |
|---|---|---|
| 封面选择 | 有 | 无 |
| 开工前体检 `preflight` | 有 | 无 |
| 断点续跑 `save_job` / `load_job` | 有 | 无 |
| 卡校验 / 修复 `verify_card` | 有 | 无 |
| 自动从存储卡分析样本 | 有 | 无 |
| 内置更新检查 | 无 | 有 |

经典版入口 `desktop/run.bat`（`python gui.py`），打包脚本 `desktop/build.bat` → `desktop/dist/InstaAceImporter.exe`（单文件，约 39 MB）。

QML 版入口 `desktop/run_qml.bat`（`pythonw main.py`），打包脚本 `desktop/build_qml.bat` → `desktop/dist/InstaAceQml.exe`（单文件，约 79 MB）。

<details>
<summary>功能差异的源码依据</summary>

- **封面**：`desktop/qml/OutputOptionView.qml:124` 的按钮文案是「选择封面图片」，但 `desktop/qml/OutputOptionView.qml:127` 是 `onClicked: {}` 空处理；`grep -in cover desktop/bridge.py` 零命中，`desktop/bridge.py:218` 的 `start()` 只有 `output_dir / do_index / auto_seq / encoder_label` 四个参数。经典版的完整实现在 `desktop/gui.py:562-577`（「选择封面图片」/「恢复自动」），底层是 `desktop/core.py:1875` 的 `render_cover()`（896x512 NV12）与 `desktop/core.py:1925` 的 `default_cover_for()`（默认取源视频第 10 秒）。
- **preflight**：`desktop/core.py:1961` 定义，`desktop/gui.py:1093` 调用；`bridge.py` 与 `qml/` 零命中。
- **断点续跑**：`desktop/core.py:2048` / `:2055` / `:2065`（`job_path` / `load_job` / `save_job`），调用点在 `desktop/gui.py:1113`、`:1164`、`:1192`、`:1243`；QML 侧零命中。
- **卡校验**：`desktop/core.py:2594` `verify_card()`、`:2661` `repair_card()`，界面入口 `desktop/gui.py:514`（「校验索引」按钮）；QML 侧零命中。
- **自动分析样本**：经典版 `desktop/gui.py:648` `auto_pick_spec()`（按钮「自动从存储卡分析」）；QML 版退化为 `desktop/qml/main.qml:116` 的 `bridge.setStatusHint("请手动选择卡内的 VID_*.mp4 作为样本")`。
- **更新检查**：只有 QML 版有，`desktop/updater.py:11` `REPO = "duofreedom/Insta-camera-tools"`，经 `desktop/main.py:53` 注入 QML 上下文，`desktop/qml/main.qml:22` 调 `updater.check()`；`desktop/gui.py` 零命中。

</details>

### 安卓端

```bash
cd android
gradle --offline :app:assembleRelease
```

产物：`android/app/build/outputs/apk/release/app-release.apk`（约 75 MB）。需要 JDK 21、Gradle 8.11.1、Android SDK 35、Python 3.11，并让 `JAVA_HOME`、`ANDROID_HOME`、`CHAQUOPY_PYTHON`、`GRADLE_USER_HOME` 指向本机安装位置。完整环境要求见 [`docs/BUILD.md`](docs/BUILD.md)。

> **只 clone 仓库不能直接构建安卓端。** 仓库没有 Gradle wrapper（无 `gradlew`），且 `android/app/src/main/jniLibs/` 下的 4 个 ffmpeg/ffprobe 二进制约 91 MB 被 `.gitignore` 排除（`arm64-v8a` 与 `armeabi-v7a` 双 ABI）。补齐方法见 [`docs/BUILD.md`](docs/BUILD.md)。

### 安装 ffmpeg

桌面端需要带 **libx264 + libx265** 的 ffmpeg。程序按下面的顺序自己找，找到就跳过下载：

| 查找顺序 | 位置 |
|---|---|
| 1 | 环境变量 `FFMPEG_PATH` / `FFPROBE_PATH` |
| 2 | exe 所在目录及其 `bin\` 子目录 |
| 3 | `%LOCALAPPDATA%\InstaAceImporter\bin` |
| 4 | `~\InstaAceImporter\bin` |
| 5 | `C:\ffmpeg\bin`、`C:\Program Files\ffmpeg\bin`、`C:\Program Files (x86)\ffmpeg\bin`、`%ProgramData%\chocolatey\bin` |
| 6 | 系统 `PATH`（`shutil.which`） |

实现见 `desktop/core.py:145` 的 `_tool_dirs()` 与 `desktop/core.py:161` 的 `_find_tool()`。找到后还会实跑一次 `ffmpeg -version` 确认可用（`desktop/core.py:185`）。

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

时间戳优先取容器内嵌的 `creation_time`，其次取文件系统时间，都没有才用当前时间（`desktop/core.py:1320` `_source_stamp()`）。这样导入的视频在相册里按原始拍摄时间排序，而不是全挤在导入当天。

主视频 1920x1080 / 60000/1001 fps / `libx265` + `hvc1`，代理 1280x720 / 30000/1001 fps / `libx264` + `avc1`，GOP 固定 16 帧。参数见 `desktop/core.py:67-72` 与 `desktop/core.py:952-953`。

### 批量转换

第一个参数换成目录即可，程序按扩展名（`.mp4` `.mov` `.mkv` `.avi` `.ts` `.flv` `.wmv` `.m4v`）过滤后逐个转换：

```bash
python desktop/core.py D:/clips D:/card/DCIM/Camera01
```

结束打印 `成功 N 个，失败 M 个。`，失败的逐条列出原因。

### 图形界面

1. 双击 `desktop/dist/InstaAceImporter.exe`，或在 `desktop/` 下运行 `run.bat`。
2. 输出目录选到卡上的 `DCIM\Camera01`。
3. 样本选卡里任意一段相机原生录制的 `VID_*.mp4`（经典版可点「自动从存储卡分析」自动找）。
4. 添加视频，点「开始转换」。
5. 拔卡插回相机，相册里应能看到这段视频。

## 🔧 配置

### 命令行参数

| 参数 | 默认值 | 说明 |
|---|---|---|
| 输入路径 | 无（必填） | 视频文件，或含视频的目录 |
| 输出目录 | 输入文件所在目录 | 建议指向 `DCIM\Camera01` |
| 起始序号 | 自动接续 | 省略时扫描卡里已有文件的最大序号 |

无参数运行会打印用法并以退出码 1 结束。三个参数的位置由 `desktop/core.py:2762` 起的 `__main__` 块解析。

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

程序没找到 ffmpeg（`desktop/core.py:800`）。按上面的查找顺序检查，最快是直接指定：

```bash
set FFMPEG_PATH=D:\tools\ffmpeg\bin\ffmpeg.exe
set FFPROBE_PATH=D:\tools\ffmpeg\bin\ffprobe.exe
```

`ffmpeg -version` 必须能正常输出；装的是精简构建（不带 libx264/libx265）也会在转码阶段失败。

### 报 `目标不是影石相机卡（缺少 DCIM\Camera01 结构）`

索引登记前会校验目标确实是相机卡，避免在普通文件夹里误建 `DCIM` 污染数据（`desktop/core.py:1795`）。把输出目录指到卡上的 `DCIM` 或 `DCIM\Camera01` 再跑。

### 报 `卡里找不到真机原片作模板（DCIM\Camera01\VID_*.mp4 + LRV_*.lrv）`

程序需要一对**相机原生录制**的 VID/LRV 当模板，它要抄模板里的 `inst` box 结构和索引条目格式（`desktop/core.py:2036`）。

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

预期 `110 passed, 2 skipped`。跳过的两条依赖真机索引样本（`desktop/samples/`、`android/app/src/test/resources/samples/`），样本含设备标识，按约定不入库。

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
│   ├── core.py                   # 转码核心（GUI / QML / CLI 共用）
│   ├── gui.py                    # 经典版界面（PyQt5）
│   ├── main.py                   # QML 版入口（PySide6）
│   ├── bridge.py                 # QML 版与 core.py 之间的桥
│   ├── updater.py                # 更新检查（仅 QML 版）
│   ├── qml/                      # 23 个 .qml（含 main.qml）
│   ├── build.bat                 # 经典版构建
│   └── build_qml.bat             # QML 版构建
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
