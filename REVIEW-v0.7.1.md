# InstaAceAndroid v0.7.1 导出包审查报告

审查对象：`G:\InstaAceAndroid-v0.7.1-src-artifacts.zip`
- 大小 80,466,153 B（76.74 MB），mtime 2026-10-30 12:17:56
- SHA256 `CBEECDFCA1C371E41552485BCBE2EEB105702AF8C985635EB60D26A9D61582D9`
- 解压 12 条目 / 88.02 MB → `_android071`
- 审查方式：只读静态审计（源码 + APK 容器解析 + 自写 AXML 解析 + pyc 裸扫），未安装、未执行 APK

---

## 0. 结论摘要

**这个包是 `instaace-fusion` 的前身，不是新版本。它比 fusion 早 7 天，不是升级关系。**

| 判断 | 结论 |
|---|---|
| 能否据此重新构建 APK | **不能**。扁平导出，缺 Kotlin 源码、AndroidManifest、res、jniLibs 源，只有 5 个 .py + 3 个 gradle 配置 + 成品 APK |
| v0.7.1 能不能跑 | **能跑**。`_INST_ORIGIN` 指向不存在的 `cpvc_origin` 只是无害的空操作，模块靠 Chaquopy 的 python 目录导入 —— 这一点与 fusion 相反（fusion 改包名后才断） |
| 已分发 APK 里有没有敏感数据 | **有**。`IBGLA2606J3U7N` 在 `insta_index.pyc` 里，**已签名产物不可撤回** |
| 元数据是否可信 | **不可信**。AMBA 重叠写缺陷在 v0.7.1 就已存在，每次导入都写坏视频帧率分母 |
| 能否上架/长期分发 | **不能**。debug 证书签名 + `debuggable=true` + 三份合规文档版本过期 + 合规声明与代码矛盾 |

**最需要立刻处理的一件事**：`latest.apk` 里带着真实设备序列号，而这个 APK 在 G 盘根目录还有一份同名副本，说明它可能已经分发出去过。源码可以改，已分发的 APK 收不回来。

---

## 1. 时间线定位：这是 fusion 的前身

| | v0.7.1（本包） | fusion（`G:\instaace-fusion.zip`） |
|---|---|---|
| 打包时间 | 2026-10-30 12:17 | 2026-11-06 18:17 |
| `insta_core.__version__` | **1.3.0** | **1.1.0** |
| `versionName` / `versionCode` | 0.7.1 / 13 | 0.7.1 / 13（未变） |
| 形态 | 扁平导出（源码+APK） | 完整四目录工程（shared/desktop/android/docs） |
| Android 模块名 | 顶层 `insta360_tf_import` / `camera_moov_rewrap` | 包 `instbox.inst_transplant` / `instbox.moov_rewrap` |
| 更新检查 | **无** | 有 `_Updater`（带 3 个缺陷） |

**结论：fusion 的 Android 侧是把 v0.7.1 往「统一包结构」方向重构的结果，重构过程中把一个能跑的路径改坏了，同时把版本号从 1.3.0 回退到 1.1.0。**

源码差异量化（`insta_core.py` 632 增 / 281 删，函数 79 → 87，**v0.7.1 的函数无一被删**；`insta_index.py` 只删了 6 行注释，逻辑零改动）。

---

## 2. MANIFEST 声称的三项修复：逐条验证

### ✅ 第 2 项属实：mediacodec 补关键帧参数

`src/insta_core.py:654`（软件分支）与 `:703`（硬件分支）均为：

```python
"-tag:v", tag, "-g", "16", "-keyint_min", "16", "-sc_threshold", "0",
```

`:709-716` 注释也写明了「必须补齐 `-keyint_min` / `-sc_threshold`，否则 MediaCodec 的 i-frame-interval…」以及「`-g 16` 在 mediacodec 下实际会被取整为 1 秒，这是已知取舍」。声明与代码一致。

### ✅ 第 1 项「表驱动 + 越界检查」属实，但**语义描述是错的**

`src/insta360_tf_import.py:241-273` 确实改成了 `_amba_fields` 表 + 逐字段 `_off + 4 > amba_size` 校验。

但 MANIFEST 写「取值语义不变（**84 = 音频采样率 × 4**，91 = 音频帧数）」——**代码里 84 写的是 `audio_frames * 4`（音频帧数 × 4），音频采样率写在 67**（`(67, stats["audio_rate"])`）。同一段代码上方注释又写「0x54 (84) = 音频采样率，0x5B (91) = 音频帧数」。三处说法互相矛盾，说明作者对不同偏移的含义本身没有定论。

### ⚠️ 第 3 项「改偏移 + 修 NameError」：改动属实，**但改的方向是错的**

`src/camera_moov_rewrap.py:141-142`：

```python
audio_rate_offset = amba[0] + 0x20
audio_frames_offset = amba[0] + 0x5B
```

`audio_fps_field` 的 NameError 确实清除了（5 个 .py 全文搜 0 命中）。但把原偏移 `84` 换成 `0x20`（= 32）**不是修复，是把一个字段写坏** —— 见下节 P0-1。

---

## 3. P0 级缺陷

### P0-1 AMBA 字段重叠写：v0.7.1 就已存在，每次导入都触发

**两条代码路径写同一块 AMBA box，写入区间重叠。**

`src/insta360_tf_import.py:262-269`（`camera_udta`，偏移相对 AMBA 数据区）：

```python
_amba_fields = [
    (25, stats["video_timescale"]), (29, 1001), (41, stats["video_duration_ts"]),
    (49, stats["video_frames"]), (53, 16), (67, stats["audio_rate"]), (71, 1024),
    (84, stats["audio_frames"] * 4), (91, stats["audio_frames"]),
]
```

→ 占用字节区间：25-28 / **29-32** / 41-44 / 49-52 / 53-56 / 67-70 / 71-74 / 84-87 / 91-94

`src/camera_moov_rewrap.py:141-142`（`udta_with_audio_frames`，偏移相对整个 udta）：

```python
audio_rate_offset = amba[0] + 0x20    # → AMBA 内 32-35
audio_frames_offset = amba[0] + 0x5B  # → AMBA 内 91-94
```

→ 占用字节区间：**32-35** / 91-94

**冲突点：字节 32。** `audio_frames * 4` 被写到 AMBA 内偏移 32，覆写 `(29, 1001)` 的最后一个字节。

**已在 fusion 上做过字节级实证**（探针 `_fusion_amba_probe.py`：合成 688144 B 的 nail 模板，真跑 `camera_udta`，再用 `udta_with_audio_frames` 二次改写）：

- 变化字节只有 2 个：AMBA 偏移 32 / 33，写为 `0x15F8`（= 5624 = `audio_frames * 4`，小端）
- 字段 `(29, 1001)`：`camera_udta` 之后是 **1001**，`udta_with_audio_frames` 之后变成 **4160750569**

`1001` 是视频帧率分母（`1/1001` 秒制），被写成 `audio_frames * 4` 后 ≈ 41.6 亿。

**v0.7.1 与 fusion 在这里的代码完全同源**（`amba[0] + 0x20` 逐字相同，`_amba_fields` 九项逐值相同），且 `camera_moov_rewrap.py:128-132` 的 docstring 自己写着 `0x20-0x23: 视频帧率 (fps_num / fps_den)`、`0x54 (84): 音频采样率` —— **照 docstring 就该写 0x54，代码写的是 0x20**。

**正确修法**：`audio_rate_offset = amba[0] + 0x54`（与 `_amba_fields` 的 `(84, audio_frames * 4)` 对齐）；或干脆删掉 `udta_with_audio_frames` 的音频写入，因为 `camera_udta` 已经写过 84 和 91。

**影响面**：`insta_core.py:2010` `_inst_attach_one` → `rw.rebuild_media(...)` → `udta_with_audio_frames`，是**每次主视频/代理视频导入的必经路径**，不是边角情况。v0.7.1 的 APK 已经把这个缺陷带进产物。

**必须标注的边界**：本机无真机样本 mp4（工作区与两个 zip 内递归搜 `*.mp4` / `*.lrv` 均 0 命中），**无法实测哪个偏移才是相机固件真值**。以上是「代码级确证的重叠写 + 用合成模板实证的字节损坏」，不是「实测相机行为错误」。

### P0-2 已签名 APK 内嵌真实设备序列号

从 `latest.apk` 提取 `assets/chaquopy/app.imy`（131,289 B，内部是 zip，5 个 .pyc，magic 为 CPython 3.11 的 `a7 0d 0d 0a`）：

```
  9188  android_bridge.pyc
 34091  camera_moov_rewrap.pyc
 81614  insta360_tf_import.pyc
137208  insta_core.pyc
 27361  insta_index.pyc
```

裸扫结果：

- **`insta_index.pyc` 偏移 1457 命中完整 `IBGLA2606J3U7N`**
- 该 pyc 里还整段保留了 protobuf 字段说明 docstring（含 `device_serial = 1;    // "IBGLA2606J3U7N"` 与 4 处 `CPVC`）

源码侧同样命中：`src/insta_index.py:28` `string device_serial = 1;    // "IBGLA2606J3U7N"`（数据类默认值 `device_serial: str = ""` 是干净的，泄在注释里）。

**严重性高于 fusion 的同名问题**：fusion 的序列号只在源码注释里，改了就行；这里已经在**已签名可分发的 APK** 里，同等条件下等于对外发布了设备标识。而且 `G:\latest.apk` 与包内那份 SHA256 完全一致，说明它曾被单独取出使用过。

### P0-3 合规声明与实际代码直接矛盾（法律风险）

`assets/docs/开源合规声明.md:59-66` §1.1「与 CPVC 的关系（重要）」原文声称：

> 本项目是**独立实现**：不包含、不破解、不反编译 CPVC 的付费授权代码…与任何第三方商业软件无授权关系、无代码复用、无品牌关联。

实际：

- `src/insta_core.py` 里 `CPVC` 出现 **22 次**、`cpvc_origin` 3 次；字节码里 `insta_core.pyc` CPVC=9 / cpvc_origin=3、`insta_index.pyc` CPVC=4
- `src/insta_core.py:1139-1140` 硬编码目录名 `cpvc_origin`
- 注释原文包括「真机样本 + CPVC 5.0.4 反汇编交叉验证」「策略与 CPVC 的 set_field/encode_message 一致」「与 CPVC 的 check_card_if_insta / build_indexes 完全一致」
- `src/insta360_tf_import.py:417` 注释「打包成单文件 exe 后，`__file__` 指向 `_MEIxxxx/cpvc_origin/`」

**这份声明不是「写得不严谨」，是写了一件与事实相反的事。** 随 APK 分发的法律文书与源码证据冲突，一旦被主张，比代码 bug 更难处理。要么改声明，要么清代码里的字样 —— **不能两边都留着**。

---

## 4. P1 级问题

### P1-1 release APK 用 debug 证书签名，且 `debuggable=true`

- `META-INF/CERT.RSA` 1,167 B，主体字符串含 **`Android Debug`** → 用的是 `~/.android/debug.keystore`。MANIFEST.txt 自己也写「产物签名：~/.android/debug.keystore（debug.keystore，可覆盖安装）」。
- `build.gradle.kts` 的 `signingConfig` 名为 `sideload`，`storePassword = "android"` / `keyAlias = "androiddebugkey"` / `keyPassword = "android"`（公开默认口令）。
- 二进制 manifest 实测 `<application>` 上 **`debuggable = True`**，对应 `build.gradle.kts` 的 `release { isDebuggable = true }`。
- 后果：① 不能上任何应用商店；② debug keystore 换机器/换用户就不同，**无法做可验证的增量升级**；③ `debuggable=true` 允许 `run-as` 与调试器附加，配合 `allowBackup=true` 可导出私有目录。

### P1-2 三份随包合规文档版本停在 0.6.3

`assets/docs/` 三份都标「版本 0.6.3 / versionCode 8 / 2026-10-22」，而 APK 实际是 0.7.1 / versionCode 13。用户装 0.7.1 看到的却是 0.6.3 的协议与隐私政策 —— **协议版本与实际版本脱钩**，属于合规范畴的实质缺陷（用户同意的是旧版条款）。

### P1-3 版本号三处不一致，且 fusion 相对本包是倒退

- `src/insta_core.py:41` `__version__ = "1.3.0"`
- `build.gradle.kts:24-25` `versionCode = 13` / `versionName = "0.7.1"`
- 文档 0.6.3 / 8
- fusion 的 `insta_core.py:40` 与 `desktop/core.py:63` 都是 `"1.1.0"` → **从 v0.7.1 到 fusion，内核版本号从 1.3.0 退到 1.1.0**

CHANGELOG 里 1.0.0 / 1.1.0 / 1.1.1 / 1.2.0 是一套，`0.7.x` 是另一套，`1.3.0` 又是第三套。没有单一事实来源。

### P1-4 `_INST_ORIGIN` 指向不存在的目录（本包无害，但是 fusion 回归的根因）

`src/insta_core.py:1139-1140`：

```python
_INST_ORIGIN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cpvc_origin")
```

`src/` 下**没有 `cpvc_origin` 子目录**（只有 5 个平铺 .py），`sys.path.insert` 插入一个不存在的路径 —— **无害的空操作**。`:1161-1162` 用顶层模块名 `import insta360_tf_import` / `import camera_moov_rewrap`，靠 Chaquopy 把 `app/src/main/python` 本身放进 `sys.path` 就能成功。

**这正是理解 fusion P0-2 的关键**：v0.7.1 的这套写法是自洽的、能跑的；fusion 把它改成 `"..","..","..","shared"` + `import instbox.inst_transplant`，而 Android 侧磁盘上从来没有 `instbox/` 包 → `init()` 必抛 `RuntimeError("inst 模块加载失败")`。**那是 fusion 引入的回归，不是 v0.7.1 的问题。**

### P1-5 `amba_start` 死变量

`src/camera_moov_rewrap.py:137` `amba_start = amba[0] + 8  # AMBA box 数据区起始（跳过 8 字节 box header）` —— 全文只此一处赋值，**从未被使用**。同一函数还做了 `amba[0] + 92 > len(udta)` 与两个 offset 越界检查，三处校验实际只有两处有意义。

### P1-6 本包无法重建 APK

扁平导出只有：5 个 `.py` + `build.gradle.kts` + `gradle.properties` + `local.properties` + 成品 APK。

缺：Kotlin 源码（12 个 `.kt`）、`settings.gradle.kts`、根 `build.gradle.kts`、`AndroidManifest.xml`、`res/`、`jniLibs/` 源。

→ 这个包只能作为「源码快照 + 产物」，**不能作为可复现构建的输入**。给第三方时会被理解为「源码齐全」，实际不齐全。

---

## 5. P2 级问题

1. **`local.properties` 打进包里**：内容 `sdk.dir=D:\android-build\sdk`，暴露本机构建路径（`.gitignore` 已排除该文件，是导出时直接复制工作目录导致的）。
2. **`latest.apk.sha256` 内是 Linux 风格路径**：`394c0c9c... */d/InstaAceAndroid/latest.apk`，与 Windows 导出包不一致，校验命令照抄会失败。
3. **`allowBackup=true`**：Android 12 以下可通过 `adb backup` 导出应用数据。
4. **`extractNativeLibs=true`**：为让 `libffmpeg.so` / `libffprobe.so`（实为 PIE 可执行文件）落地以便执行，与 `useLegacyPackaging = true` 对应，属必要取舍，但会增大安装体积（APK 92 MB，解压 177 MB）。
5. **`armeabi-v7a` 的 x265 无 NEON**：`BUILD_NOTES.md` 自述 armv7a 仍 `ENABLE_ASSEMBLY=OFF`（32 位自定义命令不接受 `${ASM_FLAGS}`）→ 32 位设备转码明显慢。文档已披露，属已知取舍。
6. **`build.gradle.kts:113` `buildPython("D:/android-build/py311/python.exe")`** 写死本机绝对路径，换机器无法构建。
7. **`lint { abortOnError = false }`**：lint 错误不阻断构建。
8. **`release { isMinifyEnabled = false; isShrinkResources = false }`**：未混淆未裁剪（对 Python 引擎部分意义不大，但 Kotlin 侧未做任何保护）。

---

## 6. 与 `_fusion/REVIEW.md` 的交叉比对：两处归因需要修正

| 项 | fusion 报告原判断 | 本次核查后 |
|---|---|---|
| P0-1 AMBA 重叠写 | 表述为 fusion 的缺陷（CHANGELOG 在 1.0.1 分两次改出来的） | **归因需扩大**：`amba[0]+0x20` 与 `_amba_fields` 九项在 v0.7.1 就已完全相同 → 该缺陷**至少从 2026-10-30 起就存在**，fusion 只是继承了它，并把错误的偏移当成「修复」写进了 MANIFEST 与 CHANGELOG |
| P0-2 Android 缺 `instbox` 包 | 表述为「Android 端完全不可用」 | **结论成立，但要加因果**：v0.7.1 用 `cpvc_origin` + 顶层模块名是自洽可跑的；**是 fusion 改包名时把能跑的路径写坏的**，属回归而非「一直如此」 |
| 序列号泄露 | 判定为源码注释泄露（`android/.../insta_index.py:26`） | **实际更严重**：v0.7.1 的**已构建 APK** 里 `insta_index.pyc` 就带着序列号 → fusion 若沿用同一构建流程，产物同样带 |
| 版本号 1.1.0 | 记为「与 CHANGELOG 1.0.2、gradle 0.7.1 三者不一致」 | **补一维**：v0.7.1 的 `__version__` 是 **1.3.0** → fusion 的 1.1.0 是**倒退**，共四处不一致 |

两包共同的、已确认无问题的项见下节。

---

## 7. 已核实正常项

- **5 个 `.py` 全部 `py_compile` 通过**（本机 Python 3.13，逐文件 doraise 编译，0 失败）。
- **`INTERNET` 权限未申请 —— 实测确认**。自写 AXML 解析二进制 `AndroidManifest.xml`（5,628 B / 66 字符串），`uses-permission` 仅 1 条：`com.duofreedom.instaace.DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION`（AndroidX 自动生成的自定义权限）。配合源码侧 `urllib|requests|http|socket` 全文 **0 命中**，可确认 v0.7.1 **完全无网络能力、无遥测**。这一点与「隐私优先」的定位相符，是**加分项**。
  - 注：fusion 的 Android 侧后加了 `_Updater` 走 `urllib` 查 GitHub releases，但 `AndroidManifest.xml` 仍未申请 `INTERNET` → 即使修掉 `__version__` NameError，更新检查也会因无权限失败。**这是 fusion 更新检查的第 4 个缺陷**。
- **`audio_fps_field` NameError 确已修**：5 个 `.py` 全文 0 命中。
- **无 `instbox` 引用**：5 个 `.py` 全文 0 命中，与本包布局自洽。
- **manifest 关键字段与 MANIFEST.txt 声明一致**：`package=com.duofreedom.instaace`、`versionCode=13`、`versionName=0.7.1`、`compileSdk=34`、`minSdk=26`、`targetSdk=34`、`label=InstaAce 导入器`。
- **APK 完整性**：208 条目，`zipfile` 可全量读取，`assets/chaquopy/app.imy` 可解出 5 个合法 pyc。
- **v0.7.1 无删除任何函数**：`insta_core.py` 79 个函数全部存在于 fusion 的 87 个中，fusion 纯新增 8 个（`set_hwdecode`、`hwdecode`、`available_decoders`、`_probe_hw_decoder_alive`、`probe_hw_decoder`、`_attach_validate_paths`、`_attach_prepare_and_attach`、`_attach_post_process`）。
- **`BUILD_NOTES.md` 的引擎构建说明质量高**：9 条踩坑逐条可复现（x264 `--target=` 走 CC、x265 与 CMake 4.x 不兼容、x265 需 `CMAKE_SYSTEM_NAME=Linux`、NEON 需 `-DASM_FLAGS` 注入等），GPL 许可链（FFmpeg GPL-2.0-or-later / x264 GPL-2.0-or-later / x265 GPL-2.0）与项目 GPL-3.0-or-later 兼容的判断正确。

---

## 8. 无法验证的项（审查局限）

1. **无 aapt / aapt2 / apksigner**：本机 `D:\android-build`、`C:\android-build\sdk\build-tools`、`%LOCALAPPDATA%\Android\Sdk\build-tools` 全部不存在，只有 `java`。→ MANIFEST 声明的 `aapt badging` 结果无法复现；**签名有效性与 V1/V2/V3 完整性未验证**（只确认了 `CERT.RSA` / `CERT.SF` 存在且主体是 Android Debug）。
2. **无 adb、无真机**：导入链路（转码 → inst box 移植 → 索引登记）**一次都没有真机验证**。MANIFEST 自己也写「本机无 adb，需将 latest.apk 覆盖安装到设备并导入视频验证」。
3. **无真机样本 mp4/lrv**：AMBA 正确偏移只能从代码与注释的内部矛盾推断，无法实测确证。
4. **无 Kotlin 源码**：无法审查 `Engine.kt` / `Index.kt` / `SafeCard.kt` 逻辑（这些只在 fusion 里才有）。

---

## 9. 建议的处理顺序

| 优先级 | 动作 | 理由 |
|---|---|---|
| 1 | **停止分发 `latest.apk`**，重新构建并清除 `insta_index.py:28` 注释里的序列号 | 已签名产物带设备标识，不可撤回 |
| 2 | **修 AMBA 偏移**：`audio_rate_offset = amba[0] + 0x54` | 每次导入都写坏视频帧率分母 |
| 3 | **改合规声明或清 CPVC 字样**，二者必须统一 | 随包分发的法律文书与代码证据相反 |
| 4 | 换正式 keystore 签名 + `isDebuggable = false` | 否则无法升级、不可上架 |
| 5 | 更新 `assets/docs/` 三份文档版本号 | 用户同意的是 0.6.3 的条款 |
| 6 | 统一版本号单一事实来源 | 1.3.0 / 1.1.0 / 0.7.1 / 0.6.3 四套并存 |
| 7 | 若要交付「源码包」，补齐 Kotlin / manifest / res / settings.gradle | 当前扁平包无法重建 |
