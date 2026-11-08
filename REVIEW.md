# instaace-fusion 源码审查报告

审查对象：`G:\instaace-fusion.zip`（SHA256 `C15CD8FDDB6A2F4825924D5E0D572E0EA4756516B9BBCD6D241AEDD76C3CA398`，698.87 MB，2026-11-06 18:17）
解压副本：`_fusion\instaace-fusion`（93 个源文件，排除 build/dist/.git/.gradle/__pycache__）
审查方式：**只读静态审计 + 可复现探针**。无真机 MP4 样本，未做端到端真机验证。
审查时间：2026-11-08

---

## 一、结论摘要

**当前状态不可发布，也不可交付使用。** 存在 4 个 P0 级缺陷，其中 2 个会导致核心功能失效：

| 级别 | 缺陷 | 后果 |
|---|---|---|
| P0-1 | AMBA 字段重叠写 | **每一个**导入产物的帧率字段被写坏 |
| P0-2 | Android 缺 `instbox` 包 + 路径错误 | Android 端 `init()` 必抛异常，导入链路完全不可用 |
| P0-3 | `__version__` 未定义 | Android 更新检查永久静默失败 |
| P0-4 | GitHub 仓库名拼错 | 桌面 + Android 更新检查双双 404 |

桌面端（PyQt5 版）在**不修 P0-1** 的前提下可以跑通流程，但产物元数据不可信。Android 端**完全跑不起来**。

另有 11 项 P1、9 项 P2，以及 2 类隐私/合规问题（真实设备序列号、商业字体随 GPL 分发）。

---

## 二、P0 缺陷

### P0-1　AMBA 字段重叠写 —— 每次导入都破坏视频帧率字段

**位置**
- `shared/instbox/moov_rewrap.py:193`　`audio_rate_offset = amba[0] + 0x20`
- `shared/instbox/inst_transplant.py:287-297`　`_amba_fields` 中 `(29, 1001)`

**现象**：两条代码路径写同一块 AMBA box，字段区间重叠。

`camera_udta()` 的字段布局（偏移相对 amba 子字节串）：

| 偏移 | 内容 | 占用字节 |
|---|---|---|
| 25 | video_timescale | 25–28 |
| **29** | **1001**（帧率分母） | **29–32** |
| 41 | video_duration_ts | 41–44 |
| 49 | video_frames | 49–52 |
| 53 | 16（GOP） | 53–56 |
| 67 | audio_rate | 67–70 |
| 71 | 1024 | 71–74 |
| 84 | audio_frames * 4 | 84–87 |
| 91 | audio_frames | 91–94 |

`udta_with_audio_frames()` 写两个字段（偏移相对整个 udta，`amba[0]` 是 AMBA box 在 udta 内的绝对偏移）：

```python
audio_rate_offset = amba[0] + 0x20      # amba 内偏移 32
audio_frames_offset = amba[0] + 0x5B    # amba 内偏移 91
struct.pack_into("<I", udta, audio_rate_offset, audio_frames * 4)
```

**`amba[0] + 0x20` 占 amba 内字节 32–35，与 `(29, 1001)` 的 29–32 在字节 32 处重叠。**

**已实证**：探针脚本 `_fusion_amba_probe.py` 用合成模板（AMBA size=128、nail size=688144）真跑两条函数，输出：

```
字段 (29, 1001) 期望 1001：camera_udta 后 = 1001 → udta_with_audio_frames 后 = 4160750569  <-- 被破坏
变化字节：udta 偏移 40 (amba 内 32): 0x00 -> 0xF8 ;  udta 偏移 41 (amba 内 33): 0x00 -> 0x15
          （0x15F8 = 5624 = audio_frames * 4，小端）
```

**正确值应为 `0x54`（=84）**，依据是同一仓库内 `android/app/src/main/python/camera_moov_rewrap.py:135` 的 docstring：

```
0x20-0x23: 视频帧率 (fps_num / fps_den)
0x54 (84): 音频采样率
0x5B (91): 音频帧数
```

即 0x20 是**视频帧率**字段，不是音频采样率。

**影响面**：`desktop/core.py:2492` 调 `rw.rebuild_media(...)`，其内部 `moov_rewrap.py:411` 必然调 `udta_with_audio_frames`。这是 `import_with_inst` 的必经路径 —— **每一个 VID 和每一个 LRV 产物的 AMBA 帧率字段都被写坏**。非边角情况。

**自证**：`desktop/CHANGELOG.md:32` 记录 1.0.1 把硬编码 `amba[0]+84` 改成 `amba[0]+0x20`，同批 `:31` 把 `camera_udta` 改成表驱动。两处改动分别做，没人核对过写入区间是否互斥。

**修复**
```python
audio_rate_offset = amba[0] + 0x54      # 与 camera_udta 的 (84, audio_frames*4) 对齐
```
同时修正 `moov_rewrap.py:181-182` 的 docstring（当前写 `0x54 (84): 音频采样率`，与 `:193` 代码的 `0x20` 自相矛盾）。

**遗留不确定性**：工作区与 zip 内均无 `*.mp4` / `*.lrv` 真机样本，无法用真机产物反证哪个偏移是相机真值。本结论是「代码级确证的重叠写 + 仓库内注释互相矛盾」，不是「已实测的相机行为错误」。修复后必须用真机原片做一次 `verify_card` 闭环。

---

### P0-2　Android 端不存在 `instbox` 包 —— 导入链路完全不可用

**位置**
- `android/app/src/main/python/insta_core.py:1460-1461`
- `android/app/src/main/python/insta_core.py:1479-1482`

**现象**

```python
_INST_ORIGIN = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "..", "..", "..", "shared")
```

从 `android/app/src/main/python/` 往上三级 = `android/`，拼 `shared` 得到 `android/shared` —— **该目录不存在**。（桌面版 `desktop/core.py:1435-1436` 用 `"..", "shared"`，从 `desktop/` 上一级到仓库根，是正确的。）

而 `_load_inst_modules()` 无条件执行：

```python
import instbox.inst_transplant as _tf
import instbox.moov_rewrap as _rw
```

Android 侧磁盘上只有顶层模块 `insta360_tf_import.py` / `camera_moov_rewrap.py`，**没有 `instbox/` 包**（全目录递归搜 `instbox` = 0 命中）。

**调用点**
- `insta_core.py:1494`（`extract_inst_meta` 内）—— `try/except: return None`，静默吞掉
- `insta_core.py:2164`（`import_with_inst` 内）—— **裸调用，不捕获**
- `android_bridge.py` 的 `init()` 也调用并 `raise RuntimeError("inst 模块加载失败: ...")`

**后果**：Android 端 `init()` 必抛异常 → PythonEngine 初始化失败 → **整条导入链路不可用**。这不是运行时偶发，是必然失败。

**根因**：仓库把 shared 代码当作单一真源，但 Android 侧靠 Chaquopy 打包 `app/src/main/python/`，没有任何构建步骤把仓库根的 `shared/` 挂进去。`android/app/build.gradle.kts` 全文搜 `sourceSets|srcDirs|srcDir` = **0 命中**，`_INST_ORIGIN` 指向的 `android/shared` 也不会被任何步骤创建。**这是死配置。**

**修复**（三选一）
1. 在 `android/app/build.gradle.kts` 加 `sourceSets` / Chaquopy `srcDirs`，把 `../shared` 纳入 Python 源集
2. 构建前用脚本把 `shared/instbox/` 复制到 `android/app/src/main/python/instbox/`（并改 `_INST_ORIGIN` 为 `os.path.dirname(__file__)`）
3. 让 Android 侧改回顶层模块名（`insta360_tf_import` / `camera_moov_rewrap`），`_INST_ORIGIN` 指向自身目录

无论哪种，都必须同时消除「三份副本哈希不一致」的问题（见 P1-5）。

---

### P0-3　`android_bridge.py` 使用未定义的 `__version__` —— 更新检查永久静默失败

**位置**
- `android/app/src/main/python/android_bridge.py:202`　`"User-Agent": "InstaAceAndroid/%s" % __version__`
- `android/app/src/main/python/android_bridge.py:209`　`current = _parse_version(__version__)`

**现象**：`__version__` 只定义在 `android/app/src/main/python/insta_core.py:40`（`__version__ = "1.1.0"`），`android_bridge.py` 自身**没有定义也没有导入**。

`_Updater._run()` 外层是 `try/except Exception: pass`（`:219-220`），`NameError` 被静默吞掉。

**后果**：Android 端更新检查**永远返回空、永远不提示新版本**，且无任何日志。用户无法感知，排查也无从下手。

**修复**
```python
from insta_core import __version__     # 或在 android_bridge.py 内单独定义
```
并把 `except Exception: pass` 改为记录到 `_log_file`。

---

### P0-4　GitHub 仓库名拼写错误 —— 两平台更新检查必然 404

**位置**
- `desktop/updater.py:11`　`REPO = "duofreedom/Insta-camera-tools"`
- `android/app/src/main/python/android_bridge.py:153`　`_REPO = "duofreedom/Insta-camera-tools"`

**现象**：实际交付文件夹/仓库名是 `Insta-camara-tools`（camera 被拼成 camara）。

两处都请求 `GET https://api.github.com/repos/duofreedom/Insta-camera-tools/releases/latest` → **必然 404**。叠加 P0-3 的静默吞异常，Android 端连失败都不留痕迹。

**修复**：确认最终仓库名后，同步修正两处常量。若决定沿用 `Insta-camara-tools` 这个拼错的仓库名，建议在 README 说明，避免后续再改。

---

## 三、P1 缺陷

### P1-1　QML 版「自动接续序号」开关是死开关

`desktop/qml/OutputOptionView.qml:8` 定义 `property bool autoSequence: true`，`:79-81` 绑定到界面开关，`main.qml:150` 把它传给 `bridge.start(..., outputView.autoSequence, ...)`。

但 `desktop/bridge.py:265` 的 `_run(self, files, out, do_index, auto_seq, encoder)` **接收后从未使用** `auto_seq`。`_run` 里调 `core.import_with_inst(...)` 和 `core.convert(...)` 时都没传 `start_number`，于是 `core.py:1055` / `:1258` 一律走 `next_seq(output_dir)` 自动接续。

**后果**：用户关闭「自动接续序号」后行为不变，序号仍然自动递增。PyQt5 版 `gui.py:361` 的 `self.auto_seq = True` 同样是死变量（全文仅此一处出现）。

**修复**：`_run` 里按 `auto_seq` 传参，例如
```python
start = None if auto_seq else 1
core.convert(..., start_number=start)
```
`import_with_inst` 目前签名没有 `start_number`（`core.py:2083`），需要先补上该参数。

---

### P1-2　`requirements.txt` 缺 PySide6 —— QML 版按文档装不起来

`desktop/requirements.txt` 只有 `PyQt5>=5.15`；`desktop/requirements-dev.txt` 是 `PyQt5>=5.15` + `pytest>=8.0`。

但 `desktop/main.py` / `bridge.py` / `updater.py` 全部 `from PySide6...`，QML 版依赖 PySide6。

**后果**：照 README 装依赖的用户，跑 `python main.py` 直接 `ModuleNotFoundError`。

**修复**：拆成 `requirements-pyqt.txt` / `requirements-qml.txt`，或合并并注明两个 GUI 各自所需。

---

### P1-3　构建/启动脚本只覆盖 PyQt5 版，QML 版无入口

- `desktop/build.bat`（14 行）：`python -m PyInstaller --noconfirm InstaAceImporter.spec` —— 只构建 PyQt5 onefile
- `desktop/run.bat`（7 行）：`start "" python gui.py` —— 只跑 PyQt5 版

`InstaAceQml.spec` 存在但没有对应批处理。**用户无法从仓库直接构建 QML 版。**

---

### P1-4　两套 GUI 并存，README 完全未提及 QML 版

仓库里实际有两套完整桌面 GUI：
- `gui.py`（PyQt5，1495 行）
- `main.py` + `bridge.py` + `qml/`（PySide6 + QML，24 个 qml 文件）

根 `README.md:3` 只写「桌面端（Windows PyQt5）」，`:18` 的 `desktop/` 结构清单里**完全没有** `main.py`/`bridge.py`/`updater.py`/`qml/`/`InstaAceQml.spec`。全文也未说明两套 GUI 的关系、如何选择、哪套是主线。

**后果**：新用户/贡献者看到的仓库结构与实际不符，无从判断该用哪套。

**修复**：README 补齐两套 GUI 的说明，明确「推荐/维护中」的是哪一套；另一套要么标注为实验性，要么删除。

---

### P1-5　README 声称三模块「字节级一致」，实际哈希全不同

`README.md:51` 写「`instbox/inst_transplant.py`、`instbox/moov_rewrap.py`、`insta_index.py` 三个模块在桌面端和安卓端之间完全同源（字节级一致）」。

实测三对副本哈希全不同：

| shared 版 | 大小 | android 版 | 大小 |
|---|---|---|---|
| `insta_index.py` `25A98FC2…39E026` | 15829 B | `insta_index.py` `A4DA1B08…BD589` | 15124 B |
| `instbox/inst_transplant.py` `CADB5B01…47F4FB` | 56283 B | `insta360_tf_import.py` `3DC4DC9E…FEE9C2E` | 54575 B |
| `instbox/moov_rewrap.py` `DB4AF224…C4C770` | 22127 B | `camera_moov_rewrap.py` `AF93C8D9…791FE0` | 19804 B |

差异内容：shared 版有 GPL 头（16 行）+ 中文 docstring + 新模块名 import；android 版是英文 docstring + 旧模块名 + 缺 AMBA 越界校验 + 多行 format 版报错串。

**Android 侧是旧版代码，未跟随 shared 更新。** 这正是 P0-2 的另一面。

---

### P1-6　版本号三处不一致

| 位置 | 值 |
|---|---|
| `desktop/CHANGELOG.md:3` | `1.0.0 — 2026-10-25`（后续 1.0.1 / 1.0.2） |
| `desktop/core.py:63` | `__version__ = "1.1.0"` |
| `android/app/src/main/python/insta_core.py:40` | `__version__ = "1.1.0"` |
| `android/app/build.gradle.kts:24-25` | `versionCode = 13` / `versionName = "0.7.1"` |

CHANGELOG 停在 1.0.2，代码里是 1.1.0，Android 包版本是 0.7.1。三者无对应关系。

**修复**：确立单一版本真源（建议 `core.py:63` 的 `__version__`），CHANGELOG 与 gradle 同步。

---

### P1-7　商业字体随 GPL 项目分发

`desktop/assets/fonts/Lenovo-XiaoxinChaokuGB.ttf`（1,284,276 B）为联想小新系列字体，随 GPL-3.0 项目公开分发存在版权风险。`main.py` 的 `load_fonts()` 会在启动时加载 `assets/fonts/*.ttf`。

**建议**：确认授权，或替换为可自由分发的字体（如思源黑体/Noto Sans SC）。

---

### P1-8　现有测试对核心数据路径零覆盖

`desktop/tests/test_insta.py` 共 25 个测试函数，覆盖索引读写、时间戳解析、stage 回调、封面推断、preflight、断点账本、`set_awake`。

**对 `AMBA` / `amba` / `udta` / `audio_frames` / `camera_udta` / `rebuild_media` 零覆盖。** 上述 P0-1 因此完全无法被现有测试捕获。

**修复**：至少补三个测试 ——
1. `camera_udta()` 写完后逐字段回读校验
2. `udta_with_audio_frames()` 不覆盖 `camera_udta` 已写字段
3. 两者串行执行后所有 9 + 2 个字段区间互不重叠

---

### P1-9　`InstaAceQml.spec` 无图标

`desktop/InstaAceQml.spec`（71 行）里没有 `icon=` 参数，而 `InstaAceImporter.spec` 有 `icon=['assets/app.ico']`。QML 版打包产物会是默认 PyInstaller 图标。

---

### P1-10　`is_camera_card` 判断失败即静默降级

`desktop/bridge.py:270`：`use_inst = do_index and core.is_camera_card(out)`。若用户勾选了「登记索引」但目标目录不被识别为相机卡，`:277-279` 只是 `use_inst = False` 并显示「未找到相机原片，改为纯转换」—— 不阻断、不报错。

**风险**：用户以为已经完成相机卡登记，实际只是拿到一个普通转码文件，插卡后相机不认。属于静默功能降级。

**修复**：勾选登记索引但目标非相机卡时，应显式确认或直接报错。

---

### P1-11　`updater.py` 全链路静默吞异常

`desktop/updater.py` 的 `_run()` 用 `except Exception: pass` 收尾，`TIMEOUT = 6.0`，`User-Agent: InstaAceQml/<version>`。网络失败、JSON 解析失败、字段缺失全部无痕。叠加 P0-4 的 404，桌面端更新检查也不会有任何可见反馈。

---

## 四、P2 / 文档与实现不符

### P2-1　写死本机绝对路径（7 处）

| 位置 | 内容 |
|---|---|
| `android/app/build.gradle.kts:113` | `buildPython("D:/android-build/py311/python.exe")` |
| `docs/BUILD.md:8` | `C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe` |
| `docs/BUILD.md:23` | `set PY=C:\Users\Administrator\...\Python314\python.exe` |
| `docs/BUILD.md:55` | `D:\android-build\jdk21\jdk-21.0.12.1+1` |
| `docs/BUILD.md:56` | `D:\android-build\gradle-8.7\bin\gradle` |
| `docs/BUILD.md:57` | `D:\android-build\sdk` |
| `docs/BUILD.md:58` | `D:\android-build\ndk\android-ndk-r27` |
| `docs/BUILD.md:59` | `D:\android-build\py311\python.exe` |
| `README.md:84` | `JAVA_HOME=/d/android-build/jdk21 /d/android-build/gradle-8.7/bin/gradle --no-daemon assembleRelease` |

`build.gradle.kts:113` 是**硬编码在构建脚本里**的，别人克隆后必须改这行才能构建 Android。建议改为读 `local.properties` 或环境变量。

### P2-2　`.gitignore` 缺 `*.pyc`

140 行里含 `__pycache__/`，但**没有 `*.pyc` 规则**。若某个 `.pyc` 被放到非 `__pycache__` 目录（Chaquopy 的 `build/python/sources/release/*.pyc` 就是这种布局），不会被忽略。不过 `build/` 已在忽略列表内，实际风险低。

### P2-3　文档内 Python 版本自相矛盾

`README.md:57` 写「Python 3.11+」，`:93` 的环境要求表写「桌面端 Python 3.14」。`docs/BUILD.md:8` 也是 3.14。Chaquopy 侧是 3.11。桌面端 `build.bat` 不锁版本。

### P2-4　README 的 android 目录层级写错

`README.md:31-43` 写成 `android/src/main/python/`，实际是 `android/app/src/main/python/`（少一层 `app/`）。且列的是 Android 旧模块名 `camera_moov_rewrap.py` / `insta360_tf_import.py`，未提 shared 的 `instbox/` 包。

### P2-5　AMBA 布局注释三处互相矛盾

| 位置 | 说法 |
|---|---|
| `shared/instbox/moov_rewrap.py:181-182` | `0x54 (84): 音频采样率` |
| `shared/instbox/moov_rewrap.py:193`（代码） | `amba[0] + 0x20` |
| `android/.../camera_moov_rewrap.py:135-138` | `0x20-0x23: 视频帧率`、`0x54 (84): 音频采样率` |
| `android/.../camera_moov_rewrap.py:149` | 「实测：AMBA box 内，偏移 0x20 是音频采样率」 |
| `android/.../insta360_tf_import.py:276-277` | 「0x54 (84) = 音频采样率，0x5B (91) = 音频帧数」（但 `:278-288` 代码用 84/91） |

`camera_moov_rewrap.py` 同一函数内 docstring 与行内注释直接冲突。这是 P0-1 得以长期存在的原因之一。

### P2-6　README 称 `camera_udta` 偏移「改为表驱动不再硬编码」

`README.md:53`。实际仍是硬编码十进制值，只是搬进了 `_amba_fields` 列表。表述与实现不符。

### P2-7　裸 `except` / `except Exception: pass` 共 19 处

| 文件 | 处数 |
|---|---|
| `android/.../insta_core.py` | 5 |
| `desktop/core.py` | 5 |
| `desktop/bridge.py` | 3 |
| `shared/instbox/inst_transplant.py` | 2 |
| `android/.../insta360_tf_import.py` | 2 |
| `desktop/updater.py` | 1 |
| `android_bridge.py` | 1 |

其中 `android_bridge.py:219-220`（吞 P0-3 的 `NameError`）与 `desktop/updater.py`（吞 P0-4 的 404）直接导致缺陷不可见。建议至少在这些位置记录日志。

### P2-8　Android 从未真机验证

`README.md:108` 自述「本机无 adb，验证依赖用户提供 `import.log` 或截图」。结合 P0-2 的必抛异常，可推断 Android 端**从未成功运行过**。

### P2-9　`android/local.properties` 含本机路径

`sdk.dir=D:\\android-build\\sdk`。`.gitignore` 已含 `local.properties`，未提交，但存在于 zip 内。分发前确认未打包。

---

## 五、隐私与合规

### 5-1　真实设备序列号泄露（Android 侧）

**唯一命中**：`android/app/src/main/python/insta_index.py:26`

```
string device_serial = 1;    // "IBGLA2606J3U7N"
```

桌面端 `shared/insta_index.py:41` 已清理为 `// 设备序列号`，**Android 侧未同步**。

同一目录下 `__pycache__/insta_index.cpython-313.pyc` 也含该串（编译产物，随源码目录一起存在于 zip 内）。

**处置**：删除注释中的序列号字面量，并清理 `__pycache__` 目录。

### 5-2　CPVC 字样残留（16 处，全部 Android 侧）

| 文件 | 处数 | 行号 |
|---|---|---|
| `android/.../insta_core.py` | 14 | 750、752、830、883、924、1010、1272、1454、1655、1719、1818、2401 |
| `android/.../insta_index.py` | 4 | 13、58、60、200 |

桌面端 0 处。示例：「（与 CPVC 的 check_card_if_insta / build_indexes 完全一致。）」「真机样本 + CPVC 5.0.4 反汇编交叉验证」。

**处置**：与桌面端一致，改为中性表述（「真机样本 + 反汇编交叉验证」）。

### 5-3　`local.properties` 本机路径

见 P2-9。

### 5-4　商业字体

见 P1-7。

### 5-5　zip 内含构建产物

zip 原始 6060 条目 / 解压 1,397.74 MB，含大量 `build/`、`dist/`、`.gradle/`、`__pycache__`。`.gitignore` 已覆盖这些路径，但**打包分发时应排除**，避免体积膨胀与残留泄露。

---

## 六、已验证为正常的项

- **17 个 `.py` 文件全部通过 `py_compile`，0 失败**
- **无 TODO / FIXME / XXX 标记**（扫描命中均为 `todo` 变量名，非待办标记）
- `_shrink_avc1_entry`（`desktop/core.py:2305-2359`）：`avc1` VisualSampleEntry 头长 86 字节计算正确，`out` 长度与 `c[0]` 对齐，拼接无误
- QML 24 个文件，`qmldir` 声明的 22 个组件与磁盘文件一一对应，无缺失
- `desktop/InstaAceImporter.spec` 的 `datas` **已不含 `samples`** —— 前序 EXE 内嵌序列号的根因已消除
- 根 `.gitignore` 已覆盖 `jniLibs/`、`local.properties`、`*.keystore`、`*.apk`、`*.exe`、`*.spec`、`build/`
- Android 无 `<uses-permission>` 声明，走 SAF 目录授权，权限设计合理

---

## 七、修复优先级建议

**必须修（阻断发布）**
1. P0-1 AMBA 偏移 → `0x54`，并用真机原片做 `verify_card` 闭环
2. P0-2 Android `instbox` 路径/打包配置
3. P0-3 `__version__` 导入
4. P0-4 仓库名统一

**发布前应修**
5. P1-2 补 PySide6 依赖
6. P1-3 补 QML 构建脚本
7. P1-4 README 补齐两套 GUI 说明
8. P1-5 / P1-6 副本同步与版本号归一
9. P1-8 补 AMBA/udta 测试（防止 P0-1 复发）
10. 5-1 / 5-2 清理序列号与 CPVC 字样

**可后续处理**
11. P1-1 自动序号开关、P1-7 字体、P1-9 图标、P1-10 静默降级、P1-11 更新日志
12. P2 全部

---

## 八、审查局限（必须如实说明）

1. **无真机样本**：工作区与 zip 内均无 `*.mp4` / `*.lrv`，P0-1 的「哪个偏移是相机真值」无法用真实产物反证。修复后必须真机验证。
2. **未运行测试套件**：`desktop/tests/test_insta.py` 未执行（缺 pytest 环境下的完整依赖）。只做了 `py_compile` 语法检查。
3. **Android 未构建**：无 Gradle / Android SDK / Chaquopy 环境，P0-2 的结论来自静态路径推导与目录存在性核查，未实跑 `assembleRelease`。
4. **子代理未产出**：本轮三个子代理任务全部失败，本报告全部结论由主审查人独立核出。
5. **前序交付物已不存在**：`F:\Insta-camara-tools` 目录在本机已删除，无法与本次审查对象做差异比对。

---

*报告生成：2026-11-08　审查对象 SHA256：`C15CD8FDDB6A2F4825924D5E0D572E0EA4756516B9BBCD6D241AEDD76C3CA398`*

---

## 九、与 v0.7.1 导出包交叉比对后的归因修正（2026-11-08 补）

审查完 `G:\InstaAceAndroid-v0.7.1-src-artifacts.zip`（2026-10-30 打包，比本包早 7 天）后，上文中有两条归因需要修正。详见 `_android071/REVIEW.md`。

### 修正 1：P0-1 AMBA 重叠写不是 fusion 引入的

v0.7.1 的 `src/camera_moov_rewrap.py:141-142` 同样是 `audio_rate_offset = amba[0] + 0x20`、`audio_frames_offset = amba[0] + 0x5B`；`src/insta360_tf_import.py:262-269` 的 `_amba_fields` 九项（25/29/41/49/53/67/71/84/91）与本包逐值相同。

→ 该缺陷**至少从 2026-10-30 起就存在**。fusion 只是继承，并把 `amba[0]+84` 改成 `amba[0]+0x20` 当成「修复」写进了 CHANGELOG 与 MANIFEST（v0.7.1 的 MANIFEST 第 3 条）。真正的错是从 84 改成了 32，应改回 `amba[0] + 0x54`。

### 修正 2：Android 缺 `instbox` 包是 fusion 引入的回归

v0.7.1 的 `src/insta_core.py:1139-1140` 是 `_INST_ORIGIN = .../"cpvc_origin"`，`:1161-1162` 用**顶层模块名** `import insta360_tf_import` / `import camera_moov_rewrap`。`cpvc_origin` 目录实际不存在，`sys.path.insert` 是无害空操作；模块靠 Chaquopy 把 `app/src/main/python` 放进 `sys.path` 就能导入 —— **v0.7.1 这套写法是自洽可跑的**。

fusion 把这两行改成 `"..","..","..","shared"` + `import instbox.inst_transplant` / `instbox.moov_rewrap`，而 Android 侧磁盘上从来没有 `instbox/` 包 → `init()` 必抛 `RuntimeError("inst 模块加载失败")`。

→ **这不是「Android 端一直不可用」，而是重构统一包结构时把原本可用的路径写坏了。**

### 修正 3：序列号泄露的实际形态更严重

v0.7.1 的**已构建 APK** 里，`assets/chaquopy/app.imy` 内的 `insta_index.pyc` 偏移 1457 命中完整 `IBGLA2606J3U7N`。源码注释泄露可以改，已签名产物的泄露不可撤回。若 fusion 沿用同一构建流程，产物同样带。

### 修正 4：版本号共四处不一致，且 1.1.0 是倒退

v0.7.1 的 `src/insta_core.py:41` 是 `__version__ = "1.3.0"`。本包是 `1.1.0`（`desktop/core.py:63` 与 `android/.../insta_core.py:40`）→ **内核版本号从 1.3.0 退到 1.1.0**。加上 CHANGELOG 的 1.0.2 与 gradle 的 0.7.1，共四处不一致。

### 修正 5：Android 更新检查实际有 4 重失效（原记 3 重）

v0.7.1 的二进制 `AndroidManifest.xml` 经自写 AXML 解析确认：`uses-permission` 仅 1 条（AndroidX 的 `DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION`），**`INTERNET` 未申请**，且源码侧 `urllib|requests|http|socket` 0 命中 → v0.7.1 完全无网络能力（这是加分项）。

fusion 新增 `_Updater` 走 `urllib.request` 查 `api.github.com`，但 `android/app/src/main/AndroidManifest.xml` 仍未申请 `INTERNET`。→ 即使修掉 `__version__` NameError，网络请求也会因缺权限失败。**四重失效**：① `__version__` NameError；② 仓库名 `Insta-camera-tools` vs 实际 `Insta-camara-tools` → 404；③ manifest 无 `INTERNET` 权限；④ `except Exception: pass` 静默吞掉全部失败无日志。
