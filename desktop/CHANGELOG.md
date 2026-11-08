# CHANGELOG

## 1.3.0 — 2026-11-08

### 修复（全量审查后的整改）

#### P0（会导致产物损坏或功能完全不可用）

- **`udta_with_audio_frames` 写坏视频帧率分母**：`amba[0]+0x20` 改为 `amba[0]+0x54`。0x20 是视频帧率字段（fps_num/fps_den），与 `camera_udta` 写入的 `(29, 1001)` 在 AMBA 内字节 32 重叠；每次 VID/LRV 导入都会经 `rebuild_media` 走到这里，导致每个产物文件的 AMBA 帧率分母被覆写成 `audio_frames * 4`。`shared/instbox/moov_rewrap.py:177` 与 `android/app/src/main/python/camera_moov_rewrap.py:131` 同步修正，删除未使用的 `amba_start` 死变量，并把越界判定从 `len(udta)` 改为 `AMBA box 自身结束位置`（否则字段会写进紧随其后的 nail box）。
- **Android `_load_inst_modules` 无法加载**：`_INST_ORIGIN` 原为 `"..","..","..","shared"`，从 `android/app/src/main/python/` 上溯三级只到 `android/`，拼出的 `android/shared` 不存在；且按 `instbox.*` 包名导入，而 Android 侧没有该包。改为指向自身目录、按顶层模块名 `insta360_tf_import` / `camera_moov_rewrap` 导入（与 v0.7.1 的可跑路径一致）。
- **真实设备序列号**：`android/app/src/main/python/insta_index.py:26` 注释里的真实序列号字面量已删除。
- **Android 更新检查 `NameError`**：`android_bridge.py` 从未定义 `__version__`（它只在 `insta_core.py` 里），`_Updater._run` 直接引用裸名会抛 `NameError` 并被 `except Exception: pass` 吞掉，表现为更新检查永远无声失效。新增 `_core_version()`（`android_bridge.py:29`）取值，并把异常写入 `import.log`。

#### P1

- **「自动接续序号」开关从死变量接通**：`bridge._run` 收到 `auto_seq` 后从未使用。现由 `core.import_with_inst` 新增 `start_number` 参数承接（含类型/负数校验），`bridge.py:271` 与 `gui.py:1177` 按开关传 `None`（自动接续）或 `0`（从头编号，每成功一个 +1）。
- **依赖补全**：`requirements.txt` / `requirements-dev.txt` 补 `PySide6>=6.5` —— `main.py` + `bridge.py` + `qml/` 这套 QML 界面依赖它，原先只列了 PyQt5。
- **QML 版构建/运行脚本**：新增 `build_qml.bat`、`run_qml.bat`（原先 `build.bat`/`run.bat` 只覆盖 PyQt5 版）。
- **AndroidManifest 补 `INTERNET`**：更新检查需要该权限，此前完全缺失（`AndroidManifest.xml:10`）。
- **版本号统一**：`desktop/core.py:63` 与 `android/.../insta_core.py:40` 的 `__version__` 由 1.1.0 改回 1.3.0（1.1.0 相对 v0.7.1 包内的 1.3.0 是倒退）；gradle `versionCode` 13→14、`versionName` 0.7.1→0.7.2。
- **移除联想商业字体**：删除 `assets/fonts/Lenovo-XiaoxinChaokuGB.ttf`（商业授权不允许随 GPL 项目分发）；`qml/Theme.qml` 改为探测 `loadedFonts`，没有则回退系统「Microsoft YaHei UI」。
- **补 AMBA 回归测试**：`desktop/tests/test_insta.py` 新增 3 条（帧率分母不被覆写、AMBA 过短抛错、九个字段偏移逐一核对），此前对 AMBA 零覆盖，正是 P0 能被带进发布的原因。
- **QML spec 补图标**：`InstaAceQml.spec:57` 补 `icon=['assets/app.ico']`。
- **相机卡判断降级留痕**：勾了「登记索引」但输出目录不是相机卡结构时，原先静默降级为纯转码；现在写日志并提示「改为仅转码」（`bridge.py:274-281`）。
- **更新检查不再吞异常**：`updater.py:105` 从裸 `pass` 改为写 `import.log`。

#### P2（文档与可移植性）

- **去掉写死的本机路径**：`android/app/build.gradle.kts` 的 `buildPython("D:/android-build/py311/python.exe")` 改为 `chaquopyPython()`，依次读环境变量 `CHAQUOPY_PYTHON`、`local.properties` 的 `chaquopy.python`，都没有则交给 Chaquopy 自探测。
- **文档重写**：根 `README.md`、`desktop/README.md`、`docs/BUILD.md` 按真实仓库层级重写（补 `main.py`/`bridge.py`/`updater.py`/`qml/` 两套界面说明、纠正「三个模块字节级一致」的错误表述、仓库名 `Insta-camara-tools` → `Insta-camera-tools`、Python 版本统一为 3.10+、产物哈希不再写死）。

### 第二轮补充（同日，具备完整构建环境后）

- **APK 已重打**：`versionCode 14 / versionName 0.7.2`，双 ABI，72,830,835 B。产物内 `IBGLA`、`CPVC` 均 0 命中（含 `assets/chaquopy` 下 5 个 `.pyc`）。
- **QML 版已实际打包**：`InstaAceQml.exe --self-test` 输出 `QML_OK roots=1`、退出码 0，产物 205 MB。
- **`CPVC` 字样清零**：原 16 处（`insta_core.py` 12、`insta_index.py` 4）全部改为「真机原片」等中性表述；技术内容（偏移、参数、字节布局）未动，只去掉第三方产品名。
- **`release` 关掉 `isDebuggable`**：原为 `true`，正式包不允许（会放行调试器 attach、堆栈导出与 `run-as`）。
- **签名证书可配置**：改为环境变量 `INSTA_KEYSTORE*` → `local.properties` → debug.keystore 三级查找，不再把口令写死在仓库里。回退 debug.keystore 只为覆盖旧版，正式分发必须配自有证书。
- **修正 `build.gradle.kts` 的 `Properties` 导入**：Kotlin DSL 需显式 `import java.util.Properties`，且必须放在 `plugins {}` 之前。
- **商业字体已从仓库与产物移除**：`Lenovo-XiaoxinChaokuGB.ttf` 删除后，`Theme.qml` 探测 `loadedFonts` 为空即回退「Microsoft YaHei UI」。

### 仍未修

- **真机未验证**：本机无 adb、无相机卡，AMBA 修复只做了合成模板的偏移级验证，未在相机上实拍确认；硬解/硬编路径同样未经真机验证。
- **已发布的旧 APK 内嵌真实序列号**：v0.7.1 的 `latest.apk` 中 `insta_index.pyc` 含序列号，已分发部分不可撤回，只能下架 + 换签名重发。

## 1.0.0 — 2026-10-25

### 首个公开版本

影石相机工具（原名 InstaAce Importer）正式发布。把普通视频转成影石
Ace Pro 2 可识别的原生素材：转码为 VID + LRV 双文件、移植 `inst` box、
登记相机索引。

### 变更

- **软件名称改为「影石相机工具」**：窗口标题与界面主标题同步更新。
- **版本号归一为 1.0.0**：此前的 1.1.x / 1.2.x 为内部迭代版本，未公开发布。

### 包含的功能

- 转码：HEVC `hvc1` 1080p 主视频 + H.264 代理文件，无 B 帧、关键帧间隔 16
- `inst` box 移植：以真机原片为模板，写入缩略图与元数据
- 索引登记：`fileinfo_list.list` 与 `.editinfo_list.list` 双表写入
- 开工前体检：ffmpeg、源文件、输出目录、剩余空间、卡可写性、模板片一次性检查
- 断点续跑：中断后重开只跑未完成的条目
- 随时取消：转码中途取消，ffmpeg 进程干净退出
- 同名封面：自动匹配 `a.mp4` → `a.jpg` / `a.png`
- 硬件加速：自动探测 QSV / NVENC / AMF，不可用回落软件编码
- 防休眠：长片处理期间阻止系统休眠
- 三阶段进度：转码 / 移植 / 登记分开显示

### 修复（1.0.1 补丁，2026-11-01）

- **`instbox/inst_transplant.py camera_udta`**：9 个硬编码 AMBA 字段偏移（25/29/41/49/53/67/71/84/91）改为表驱动 `_amba_fields`，逐字段做 `_off + 4 > amba_size` 越界校验，超界抛 `ValueError`，不再静默写错字节导致相机无法识别。
- **`instbox/moov_rewrap.py udta_with_audio_frames`**：AMBA 音频采样率/帧数偏移改为 `amba[0]+0x54`（音频采样率，写 `frames * 4`）/`amba[0]+0x5B`（音频帧数），并加边界检查抛 `ValueError`；同时修复 `audio_fps_field` 未定义导致的运行时 `NameError`。
  - ⚠️ 该条目最初误写成 `amba[0]+0x20`：0x20 是**视频帧率**（fps_num/fps_den），并非音频采样率。0x20 与 `camera_udta` 的 `(29, 1001)`（视频帧率分母）在 AMBA 内字节 32 处重叠，会把帧率分母写成 `frames*4`。已在 1.3.0 修正为 0x54。

### 修复（1.0.2，2026-11-05）

基于 `instaace-fusion-modified.zip` 重建融合仓库，清理桌面/安卓/共享全部 Python 文件中 AI 痕迹注释，并按【边界政策】补全 4 处边界漏洞：

- **`render_cover` 输入校验与超时**：校验图片路径是否存在、输出路径非空、ffmpeg 可执行；新增 `cancel: threading.Event | None` 与 `timeout: float = 120.0`，超时抛 `FFmpegError(retryable=False)`，`CalledProcessError` 转为 `FFmpegError` 并携带 stderr。
- **`_run_ffmpeg` stderr 完整性**：`err_thread` join 超时后若仍存活，继续等待至退出，保证 `FFmpegError.stderr` 不截断不丢失。
- **`convert` 并发模式杀孤儿 ffmpeg**：新增 `procs` 列表与 `procs_lock` 注册所有 ffmpeg 子进程；任一任务失败时置位 `cancel` 并 kill 掉其余注册进程，避免孤儿 ffmpeg 继续写卡；所有并发任务结束后若有第一条错误，向上抛出。
- **`save_job` 不再静默吞 `OSError`**：进度文件写入失败向上抛出；gui.py 三处调用处捕获并通过状态栏提示“断点续跑进度保存失败”，用户可感知并介入。

## 历史版本（内部迭代，未公开发布）

## 1.2.0 — 2026-10-20

### 新增

- **开工前体检**（`core.preflight`）：开跑前 1 秒内检查 ffmpeg、源文件、
  输出目录、剩余空间（按 7MB/分钟 估算）、是否相机卡、索引文件可写（含只读属性提示）、
  真机原片模板。阻断项弹窗直接拦下，不再“转完 20 分钟才失败”。
- **断点续跑**：每条视频的状态/产物落盘到
  `%LOCALAPPDATA%\InstaAceImporter\jobs\<dest>.json`；同一输出目录再次开跑时
  会问“只跑未完成的 N 条 / 全部重跑”。
- **防休眠**：转码期间调用 `SetThreadExecutionState(ES_SYSTEM_REQUIRED)`，
  跑长片时不会因为系统休眠前功尽弃；结束后自动恢复。
- **同名封面图**：导入文件夹时自动找 `a.mp4 → a.jpg / a.png`（也支持
  .jpeg/.webp/.bmp，大小写不敏感），逐条单独生效；表格新增「封面」列，
  显示 自动 / 同名图 / 自选。
- 所有封面图（含同名图）都统一裁切填充为 **896×512 NV12** 后写入 `inst`。

### 变更

- **自选封面仅限单个视频**（多条时弹窗提示改用同名图），不再整批共用一个封面。
- 输出表格从 2 列扩展为 3 列（新增「封面」）。
- **重绘图标**：仍为深海军蓝底 + 亮蓝描边，中心改为「镜头环 + 播放三角」；
  矢量源 `assets/app.svg`，≤ 32px 自动换 `app-small.svg` 简化版，
  `tools/make_icon.py` 生成 7 帧 `.ico`。
- README 全面重写（流程图、性能实测表、FAQ、目录结构）。

### 修复

- 无。

## 1.1.1 — 2026-10-20

### 修复（硬件编码器实际上一直用不上）

- **`detect_hw_encoder` 误判**：探测时给 QSV 加了
  `-init_hw_device qsv=hw -filter_hw_device hw`，部分 Iris Xe 机器会报
  `Could not create the texture (80070057)`，于是永远显示“未检测到硬件”。
  改为用**与正式转码相同的命令形状**探测，现在能正确认出 `hevc_qsv`。
- **`_level_text` 编码族判断错**：只认 `libx265`，`hevc_qsv` / `hevc_nvenc` /
  `hevc_amf` 落到 H.264 公式，给 QSV 传 `-level:v 12.3` → 编码器拒开。
  改为按 `265`/`hevc` 判断。
- **QSV 命令形状**：去掉 `hwupload=extra_hw_frames=64`（部分机器
  `Function not implemented`）；QSV 不再传 `-level:v`，由它按分辨率自选
  （实测 1080p30 → level=120，与真机原片一致）。
- **日志误导**：LRV 走 CPU 时不再误报“[硬件加速]”。

### 性能

- **VID / LRV 并行转码**：两个任务同时跑，进度按像素面积加权聚合。
- **LRV 始终用 CPU 的 x264**（~400fps）：核显只有一个编码引擎，
  VID/LRV 同时上 QSV 会互抢，实测无收益。
- 实测（60s 1080p 片段，含 inst 移植与索引）：软件 21.3s → Intel QSV 约 15～18s。
- **分段并发实测无效**（供后人参考）：单个 x265 已吃满 8 线程，
  1 路 88fps vs 4 路 79fps；QSV 单引擎 1 路 149fps vs 2 路 156fps。
  电影类长片的真实上限是编码器本身，不是并发度。

### 变更

- 编码器「自动」= **软件编码**（相机端已验证的路径，不再随机器静默切换）；
  想提速需手动选 Intel / NVIDIA / AMD。

## 1.1.0 — 2026-10-20

### 新增

- **拖拽导入**：把视频或文件夹直接拖进窗口即可加入列表；文件夹自动展开一层。
  表头改为「输入文件 · 可拖入视频或文件夹」，拖拽悬停时出现虚线高亮。
- **进度细分**：进度条按三阶段显示——`转码 0–70%` → `移植 inst box 70–94%`
  → `登记索引 94–100%`，状态栏显示当前阶段名（如 `移植 inst box · VID`）。
- 窗口副标题显示版本号。
- `tests/`：pytest 离线回归（真机索引样本字节级往返、f7 位数、隐藏属性写入、
  `inst` box 探测）。

### 变更

- 许可证由 MIT 改为 **GPL-3.0**。
- 抽出 `core.stamp_from_name()`：f7 的「14 位 YYYYMMDDHHMMSS，不带序号」规则
  从 `_inst_attach_one()` 内联代码变成可测试的独立函数，行为不变。

### 修复

- 无功能回归。

## 1.0.0 — 2026-10-19

首个可发布版本。

- 三层识别链路全通：结构复刻 → `inst` box 移植 → 索引登记。
- `inst` 缩略图在 `rebuild_media` **之前**写入（顺序错了会导致不能播放 + 帧标记）。
- 自选封面：图片裁切填充为 896×512 NV12，同时写入 `inst` 与 `udta.nail`。
- 模板规格实测化：分辨率/帧率/level 全部取自卡内真机原片，不用硬编码。
- 索引写入保留 Windows 隐藏/只读属性（`r+b` 原地改写）。
- 界面署名：作者 B站@铎DUOFreedom。
