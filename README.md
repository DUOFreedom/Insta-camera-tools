<div align="center">

<img src="assets/app.svg" width="120" alt="影石相机工具">

# 影石相机工具

**把普通视频变成影石 Ace Pro 2 的「原生」素材**

转码成相机原生结构（VID + LRV）· 移植 `inst` box · 登记相机索引
插回相机，相册里能识别、能播放、封面正确

[![Version](https://img.shields.io/badge/version-1.0.0-blue?style=flat-square)](CHANGELOG.md)
[![License](https://img.shields.io/badge/license-GPL--3.0-green?style=flat-square)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Windows%2010%20%7C%2011-lightgrey?style=flat-square)]()
[![Python](https://img.shields.io/badge/python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white)]()
[![ffmpeg](https://img.shields.io/badge/ffmpeg-required-007808?style=flat-square&logo=ffmpeg&logoColor=white)]()

[下载](#下载) · [快速开始](#快速开始) · [功能](#功能) · [常见问题](#常见问题) · [从源码构建](#从源码构建) · [技术原理](#技术原理) · [开源声明](#开源声明)

</div>

---

## 这是什么

影石（Insta360）Ace Pro 2 只认自己录出来的文件。把手机或相机拍的视频拷进卡里，相册里要么看不见，要么能列出来但点了打不开，要么没有封面。

影石相机工具解决这个问题：它把任意普通视频重新封装成相机认可的结构，写进相机索引，插回相机后就和原生录制的素材表现一致。

**它做三件事，缺一不可：**

| 步骤 | 做什么 | 不做会怎样 |
|---|---|---|
| ① 转码 | 视频流转成 HEVC `hvc1` 1080p、关掉 B 帧、关键帧间隔对齐；同时生成 H.264 的 `.lrv` 代理文件 | 相机拒绝播放 |
| ② 移植 | 把相机私有 `inst` box 从模板片移植进新文件，写入缩略图与元数据 | 相机视为外来文件，不显示 |
| ③ 登记 | 在 `fileinfo_list.list` 与 `.editinfo_list.list` 中写入条目 | 相册里不出现 |

## 下载

从 [**Releases**](../../releases/latest) 下载 `InstaAceImporter.exe`，双击运行，无需安装。

```text
InstaAceImporter.exe   38.93 MB (40,820,647 字节)
SHA256  E0A2BB89DD45AAC634073D88F238B5EA835E6C0C684C2642CD634F3B47A3D27F
```

> 校验方法：`Get-FileHash .\InstaAceImporter.exe -Algorithm SHA256`
>
> 从源码自行打包得到的 exe 哈希会与此不同——PyInstaller 会把构建时间写进产物，同样的代码每次构建结果都不一致。请以本页面公布的哈希为准核对 Release 下载的文件。

> **ffmpeg 需要自备。** 下载 ffmpeg 后把 `ffmpeg.exe` 与 `ffprobe.exe` 放进 exe 同目录的 `bin\` 文件夹。
> 程序按「exe 目录 → exe\bin → 系统 PATH」顺序查找，都找不到会明确报错并指出缺哪个。

## 快速开始

1. 把相机卡插到电脑，或者先指定一个输出文件夹
2. 拖入要导入的视频（支持多选、也支持直接拖整个文件夹）
3. 点「开始」，等进度条走完
4. 把卡插回相机，打开相册

首次使用建议先拿一个短视频试一遍，确认相册里能看到、能播放、封面正常，再批量处理。

## 功能

<table>
<tr><td width="50%" valign="top">

**导入与转码**

- 🔍 **开工前体检** — 开跑前 1 秒内检查 ffmpeg、源文件、输出目录、剩余空间、卡是否可写、模板片是否存在，有问题当场拦下
- ⏸️ **随时取消** — 转码中途点取消，ffmpeg 进程干净退出，不留孤儿进程
- 🔁 **断点续跑** — 中断后重新打开，会问「只跑未完成的 N 条」还是「全部重跑」
- 🖼️ **同名封面** — `a.mp4` 旁边有 `a.jpg` / `a.png` 就自动用它当封面
- 📦 **批量排队** — 一次拖几百个文件进来也没问题

</td><td width="50%" valign="top">

**运行体验**

- 📊 **三阶段进度** — 转码 / 移植 / 登记分开显示，不糊成一条进度条
- 💤 **防休眠** — 处理长片时系统不会中途睡过去
- ⚡ **硬件加速** — 自动探测并优先使用 QSV / NVENC / AMF，不可用时回落到软件编码
- 🧪 **离线回归** — 31 项测试，不需要真机也能跑
- 🪵 **运行日志** — 写入 `%LOCALAPPDATA%\InstaAceImporter\`，出问题可回溯

</td></tr>
</table>

## 常见问题

<details>
<summary><b>点开始没反应，或者报错找不到 ffmpeg</b></summary>

把 `ffmpeg.exe` 和 `ffprobe.exe` 放进 exe 同目录的 `bin\` 文件夹，或者装进系统 PATH。

注意两个文件都要，只放 `ffmpeg.exe` 不够——程序需要用 `ffprobe.exe` 读取源文件信息。
</details>

<details>
<summary><b>视频导进去了，但相机相册里看不到</b></summary>

按顺序检查三件事：

1. **编码结构是否达标** —— 主视频必须是 HEVC `hvc1`、1080p、无 B 帧、关键帧间隔 16
2. **`inst` box 是否移植成功** —— 用卡内真机原片当模板，模板片不能是别的机型录的
3. **索引是否登记** —— 见下方「技术原理」

三者任一缺失都会导致相册里没有这个文件。
</details>

<details>
<summary><b>相册里能看到条目，但点了打不开</b></summary>

通常是索引字段写错，最常见两种：

- `f7` 时间戳不是 14 位纯数字 `YYYYMMDDHHMMSS`（写成 9 位带序号就会这样）
- `f9` 偏移不是 `inst` box 在文件内的真实字节偏移（写成了文件大小也会这样）
</details>

<details>
<summary><b>相册里出现了 0KB 打不开的条目</b></summary>

索引里多登记了 `.lrv` 文件。规则是**只登记主视频，不登记 LRV**。

重新导入时程序会覆盖修正，不需要手动删。
</details>

<details>
<summary><b>超过 4GB 的长视频会失败吗</b></summary>

不会。重封装对 32 位 `size` 与 64 位 `largesize` box 头、以及 `stco` / `co64` 两种分块偏移表都做了完整支持。
</details>

<details>
<summary><b>Windows 提示「未知发布者」或杀毒软件报毒</b></summary>

PyInstaller 打包的未签名程序会触发 SmartScreen，这是预期行为。

点「更多信息 → 仍要运行」即可。杀软误报通常是启发式规则对 PyInstaller 启动器敏感，加白名单即可，不需要关闭实时防护。
</details>

<details>
<summary><b>能导入到相机的哪个位置？会不会覆盖原有素材</b></summary>

写入 `DCIM` 目录，文件名按相机规则生成（`VID_YYYYMMDD_HHMMSS_000.mp4`），文件名冲突时自动递增序号。

不会覆盖已有素材。索引写入前会重读现有内容，只追加/替换自己的条目。
</details>

## 从源码构建

```powershell
git clone https://github.com/duofreedom/Insta-camara-tools.git
cd Insta-camara-tools

pip install -r requirements.txt
python gui.py                                              # 直接运行
python -m PyInstaller --noconfirm InstaAceImporter.spec    # 打包
```

打包产物在 `dist\InstaAceImporter.exe`。

**环境要求：** Windows 10 / 11，Python 3.10 及以上，ffmpeg 与 ffprobe 在 PATH 中或放在 `bin\`。

## 目录结构

```text
Insta-camara-tools\
├─ core.py                    核心：转码、inst 移植、索引登记、开工体检
├─ gui.py                     PyQt5 界面：拖拽、三阶段进度、任务队列
├─ insta_index.py             相机索引 protobuf 读写
├─ instbox\                   inst box 移植与 moov 重封装
│  ├─ inst_transplant.py      索引构建、元数据裁剪、box 移植主流程
│  └─ moov_rewrap.py          moov 骨架重建与样本表生成
├─ tests\test_insta.py        离线回归测试套件
├─ assets\                    图标资源（SVG / ICO / PNG）
├─ tools\make_icon.py         SVG 转多尺寸 ICO 生成器
├─ build.bat / run.bat        一键构建 / 一键运行
├─ InstaAceImporter.spec      PyInstaller 打包配置
├─ requirements.txt           运行时依赖
├─ requirements-dev.txt       开发与测试依赖
├─ CHANGELOG.md               版本变更记录
├─ README.md                  本文件
└─ LICENSE                    GPL-3.0
```

## 回归测试

```powershell
cd Insta-camara-tools
pip install -r requirements-dev.txt
python -m pytest -q
```

结果 `31 passed, 2 skipped`。跳过项是需要真机索引样本的用例，仓库不含样本文件，属预期行为。

覆盖范围：14 位时间戳生成、隐藏+只读文件原地改写与属性恢复、`inst` box 探测、进度分段映射、编码等级换算、同名封面查找、输出体积估算、开工体检各项阻断、断点续跑状态账本。

## 技术原理

相机判断「这是不是我自己录的」，靠的不是文件名，而是三重校验。

### 第一层：编码结构

| 文件 | 编码 | 参数 |
|---|---|---|
| 主视频 `VID_*.mp4` | HEVC / `hvc1` | 1920×1080，30fps，`-g 16`，`-bf 0` |
| 代理 `LRV_*.lrv` | H.264 / `avc1` | 1280×720，`-g 16`，`-bf 0` |

`hvc1` 与 `hev1` 不同：`hvc1` 把参数集放在 `hvcC` box 里，`hev1` 内联在码流中。相机只认前者。

`-bf 0` 关掉 B 帧是硬性要求。相机解码器按「无 B 帧、关键帧固定间隔」设计，带 B 帧的文件能写进去但播放会花屏或卡死。

### 第二层：`inst` box

这是影石的私有 box，装在 MP4 的 `moov` 里，存着缩略图、创建时间、机型标识等元数据。没有它，相机把文件当外部拷入的普通视频，不进相册。

`inst` 的结构在不同机型、不同固件间有差异，所以不能凭空构造——必须用**同一台相机、同一版本固件录出的真实原片**当模板，把它的 `inst` 整体移植过来，再改写里面的时间戳和缩略图。

模板片应包含 3 条 `trak`（视频、音频、`tmcd` 时间码）。缺 `tmcd` 轨会导致部分固件版本不识别。

### 第三层：索引登记

相机开机时扫描 `DCIM` 目录，但相册显示的是索引文件里的内容。两个文件都必须改：

- `DCIM\fileinfo_list.list` — 文件列表
- `DCIM\.editinfo_list.list` — 编辑信息，隐藏文件

索引是 protobuf 格式。关键字段：

| 字段 | 含义 | 易错点 |
|---|---|---|
| `f7` | 创建时间 | 必须 14 位 `YYYYMMDDHHMMSS`，不带序号；写成 9 位会「能列出但打不开」 |
| `f9` | `inst` box 在文件中的**字节偏移** | 不是文件大小，不是 `inst` 的长度 |
| meta | 与文件内 `inst` 的 meta 逐字节一致 | 有任何字节不同都可能被判为非法 |

`.editinfo_list.list` 带隐藏与只读属性，必须用 `r+b` 原地改写；用 `wb` 会 `PermissionError`，用「先删再建」会丢文件属性导致相机不认。

缩略图（896×512 NV12）必须在 `rebuild_media` 之前写入 `inst`，顺序错了文件能识别但播放黑屏。

---

## 开源声明

本项目以 **GPL-3.0** 发布。以下为运行与构建所依赖的第三方组件及其许可。

### 运行时依赖

| 组件 | 版本要求 | 许可证 | 用途 |
|---|---|---|---|
| [Python](https://www.python.org/) | 3.10+ | [PSF License](https://docs.python.org/3/license.html) | 运行环境 |
| [PyQt5](https://riverbankcomputing.com/software/pyqt/) | ≥ 5.15 | [GPL-3.0](https://www.gnu.org/licenses/gpl-3.0.html) | 图形界面（Qt5 绑定） |
| [Qt 5](https://www.qt.io/) | 5.15 | [LGPL-3.0](https://www.gnu.org/licenses/lgpl-3.0.html) / GPL-3.0 | PyQt5 底层框架 |
| [FFmpeg](https://ffmpeg.org/) | 任意近期版本 | [LGPL-2.1+](https://ffmpeg.org/legal.html) / GPL-2.0+ | 转码与封装 |

**关于 FFmpeg：** 本项目通过 `subprocess` 调用外部 `ffmpeg.exe` / `ffprobe.exe`，属于进程间调用，不链接其代码，因此不构成衍生作品。FFmpeg **不随本仓库分发**，需用户自行下载安装。请从[官方站点](https://ffmpeg.org/download.html)或 [gyan.dev](https://www.gyan.dev/ffmpeg/builds/) 获取，并遵守其许可证——若使用带 `--enable-gpl` 的构建，该构建本身受 GPL 约束。

### 构建与开发依赖

| 组件 | 用途 | 许可证 |
|---|---|---|
| [PyInstaller](https://pyinstaller.org/) | 打包为单文件 exe | GPL-2.0+ with bootloader exception |
| [pytest](https://pytest.org/) | 回归测试 | MIT |

### 仅使用标准库

除上述组件外，本项目仅使用 Python 标准库（`struct`、`zlib`、`subprocess`、`urllib`、`threading`、`ctypes`、`pathlib`、`dataclasses` 等），无其他第三方代码依赖。索引的 protobuf 编解码为自行实现，未引入 `protobuf` 库。

### 协议兼容性说明

PyQt5 采用 GPL-3.0 授权，本项目同样以 GPL-3.0 发布，二者兼容。若需在闭源项目中使用 PyQt5，应改用 [PySide6](https://doc.qt.io/qtforpython/)（LGPL）。

## 致谢

本项目的 `inst` box 结构与相机索引格式分析，参考了以下公开工作：

- **[YCTS-otree](https://github.com/YCTS-otree)** —— 感谢其在影石相机文件格式逆向分析上的公开工作，为理解 `inst` box 布局与索引 protobuf 结构提供了重要参考
- [FFmpeg](https://ffmpeg.org/) —— 转码与封装
- [PyQt5](https://riverbankcomputing.com/software/pyqt/) —— 界面框架
- [Insta360 官方社区](https://www.insta360.com/) —— 设备使用与格式相关的公开讨论

## 免责声明

本项目为个人开发的第三方工具，与影石创新科技股份有限公司无任何关联，未获其授权或认可。Insta360、Ace Pro 是影石的商标。

工具通过改写文件结构与相机索引实现导入，属于对未公开格式的逆向分析。使用前请自行备份相机卡内素材。因使用本工具导致的素材损坏、相机异常或保修问题，作者不承担责任。

## 许可

[GPL-3.0](LICENSE)

你可以自由使用、修改、分发，但分发修改后的版本必须以同样的 GPL-3.0 协议开源。
