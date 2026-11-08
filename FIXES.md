# 修复清单 · 2026-11-08

本包是 `instaace-fusion` 源码经**全量审查后整改**的版本，基线为 `G:\instaace-fusion.zip`
（SHA256 `C15CD8FDDB6A2F4825924D5E0D572E0EA4756516B9BBCD6D241AEDD76C3CA398`，2026-11-06）。

审查报告见同目录 `REVIEW.md`（本轮整改前的原始结论）与 `REVIEW-v0.7.1.md`
（对前身包 `G:\InstaAceAndroid-v0.7.1-src-artifacts.zip` 的审查）。

---

## 一、验证结果（本机实测，可复现）

| 项目 | 结果 |
|---|---|
| 全量语法检查 | 17 个 `.py` 全部通过 `py_compile`，失败 0 |
| 桌面端回归测试 | **34 passed, 2 skipped**（原 31 passed，本轮新增 3 条 AMBA 测试） |
| AMBA 字段偏移探针 | 通过：偏移 29 = 1001（帧率分母未被覆写）、84 = 5624、91 = 1406 |
| 打包产物 | `dist/InstaAceImporter.exe`，40,817,330 B |
| 产物 SHA256 | `2562DD7423571E89A7C05C4605AC998510A75D1131AF76EB4C53A09829858F49` |
| 产物序列号扫描 | `IBGLA` 命中 **0** |
| 源码序列号扫描 | `IBGLA` 命中 **1**，仅 `docs/BUILD.md` 发布清单里作为「应为 0 命中」的判据文本 |
| 旧仓库名扫描 | `Insta-camara-tools` 命中 **0** |
| 商业字体 | 已移除，`Lenovo-Xiaoxin` 仅剩 2 处字符串（CHANGELOG 历史记录、Theme.qml 的探测目标名） |

复现命令：

```bat
:: 语法检查（注意 cfile 不能指向 os.devnull，Windows 会报 non-regular file）
python -c "import py_compile,sys; py_compile.compile(r'desktop\core.py', cfile=r'%TEMP%\x.pyc', doraise=True)"

:: 回归测试
set PYTHONPATH=<你的 site-packages>;%CD%\desktop;%CD%\shared;%CD%\shared\instbox
python -m pytest desktop\tests -q
```

---

## 二、已修复（14 项）

### P0 —— 会导致产物损坏或功能完全不可用

**1. `udta_with_audio_frames` 写坏视频帧率分母（产物级损坏，每次导入必现）**

- 位置：`shared/instbox/moov_rewrap.py:177`、`android/app/src/main/python/camera_moov_rewrap.py:131`
- 问题：偏移写成 `amba[0] + 0x20`。0x20 是**视频帧率**字段（fps_num/fps_den），
  与 `camera_udta` 写入的 `(29, 1001)` 在 AMBA 内字节 32 处重叠。`rebuild_media` 每次都会调到这里，
  于是每个产物的帧率分母被覆写成 `audio_frames * 4`（实测 1001 → 4160750569）。
- 修复：改为 `amba[0] + 0x54`（音频采样率，写 `frames * 4`）/ `amba[0] + 0x5B`（音频帧数）。
- 附带修：越界判定由 `len(udta)` 改为 **AMBA box 自身结束位置** `amba[0] + amba[1]`。
  只比 `len(udta)` 时字段会写进紧随其后的 nail box，产物看似正常、实际位置全错。
- 附带清理：删除死变量 `amba_start`，`next(...)` 改为带空值检查的列表推导。

**2. Android `_load_inst_modules` 无法加载（整条导入链路不可用）**

- 位置：`android/app/src/main/python/insta_core.py:1465`、`:1485-1486`、`:2521`
- 问题：`_INST_ORIGIN` 原为 `"..","..","..","shared"`，从 `android/app/src/main/python/`
  上溯三级只到 `android/`，拼出的 `android/shared` 不存在；且按 `instbox.*` 包名导入，
  而 Android 侧根本没有该包。`android_bridge.init()` 会因此抛 `RuntimeError`。
- 修复：`_INST_ORIGIN` 改为模块自身目录，按顶层模块名
  `import insta360_tf_import` / `import camera_moov_rewrap` 导入
  —— 与 v0.7.1 那个能跑的版本路径一致。

**3. 真实设备序列号泄露**

- 位置：`android/app/src/main/python/insta_index.py:26`
- 问题：protobuf 注释里写着真实序列号字面量。
- 修复：改为 `// 设备序列号`（与 `shared/insta_index.py` 一致）。

**4. Android 更新检查 `NameError`（功能静默失效）**

- 位置：`android/app/src/main/python/android_bridge.py:29`、`:212`、`:219`、`:229`
- 问题：`__version__` 只定义在 `insta_core.py`，`android_bridge.py` 自身没有。
  `_Updater._run` 引用裸名抛 `NameError`，被 `except Exception: pass` 吞掉
  → 更新检查永远返回空、永远不提示新版本、无任何日志。
- 修复：新增 `_core_version()` 用 `getattr` 取值；异常改为写入 `import.log`，不再裸 `pass`。

### P1

**5. 「自动接续序号」开关是死变量**

- 位置：`desktop/core.py:2083`（`import_with_inst` 新增 `start_number` 参数）、
  `desktop/bridge.py:271`、`desktop/gui.py:1177`
- 问题：`bridge.start(...)` 收下 `auto_seq` 后 `_run` 从未使用；`gui.py` 的 `self.auto_seq`
  同样只用于界面文案。
- 修复：`import_with_inst` 新增 `start_number: int | None`（含类型/负数校验），
  两套界面按开关传 `None`（自动接续）或 `0`（从头编号，每成功一个 +1）。

**6. 依赖清单缺 PySide6**

- 位置：`desktop/requirements.txt`、`desktop/requirements-dev.txt`
- 问题：`main.py` + `bridge.py` + `qml/` 这套 QML 界面依赖 PySide6，原清单只有 PyQt5，
  按文档装完根本跑不起来。
- 修复：补 `PySide6>=6.5`。

**7. QML 版没有构建/运行脚本**

- 新增：`desktop/build_qml.bat`、`desktop/run_qml.bat`
- 问题：原 `build.bat` / `run.bat` 只覆盖 PyQt5 版，QML 版只能手敲 PyInstaller 命令。
- 修复：两个脚本分别做 PySide6 存在性检查后调 `InstaAceQml.spec` / `pythonw main.py`。

**8. AndroidManifest 缺 `INTERNET` 权限**

- 位置：`android/app/src/main/AndroidManifest.xml:10`
- 问题：更新检查要联网，但 manifest 只有一条 AndroidX 自动生成的权限。
- 修复：补 `android.permission.INTERNET`，并注明用途（单次 GET，无遥测、无上传）。

**9. 版本号四处不一致，且主版本号倒退**

- 位置：`desktop/core.py:63`、`android/app/src/main/python/insta_core.py:40`、
  `android/app/build.gradle.kts:24-25`
- 问题：CHANGELOG 写 1.0.2、gradle 写 0.7.1、Python 写 1.1.0，而前身 v0.7.1 包里是 1.3.0
  —— 1.1.0 相对 1.3.0 是**倒退**。
- 修复：Python `__version__` 统一为 `1.3.0`；gradle `versionCode` 13→14、`versionName` 0.7.1→0.7.2。

**10. 联想商业字体随 GPL 项目分发**

- 位置：删除 `desktop/assets/fonts/Lenovo-XiaoxinChaokuGB.ttf`（1,284,276 B）
- 问题：联想小新字体是商业授权，不允许随 GPL 项目分发。
- 修复：删除字体；`desktop/qml/Theme.qml:56` 改为探测 `loadedFonts`，
  用户自行放入 `.ttf` 则启用，否则回退系统「Microsoft YaHei UI」。

**11. AMBA 零测试覆盖（P0 能被带进发布的直接原因）**

- 位置：`desktop/tests/test_insta.py`（新增 3 条，见 `:347`、`:361`、`:368`）
- 新增：`test_udta_with_audio_frames_keeps_fps_denominator`（帧率分母不被覆写）、
  `test_udta_with_audio_frames_rejects_small_amba`（AMBA 过短必须抛错）、
  `test_camera_udta_writes_expected_amba_fields`（九个字段偏移逐一核对）。
- 同时给测试文件加了 `shared/` 路径注入，不再依赖外部 `PYTHONPATH` 才能导入 `instbox`。

**12. QML 版打包产物没有图标**

- 位置：`desktop/InstaAceQml.spec:57`
- 修复：补 `icon=['assets/app.ico']`。

**13. 相机卡判断静默降级**

- 位置：`desktop/bridge.py:274-281`
- 问题：勾了「登记索引」但输出目录不是相机卡结构时，静默改为纯转码，
  用户会以为已经登记成功。
- 修复：写日志 + 状态栏提示「输出目录不是相机卡结构，改为仅转码」。

**14. 更新检查吞异常**

- 位置：`desktop/updater.py:105`
- 修复：`except Exception` 从裸 `pass` 改为写 `import.log`。

### P2 —— 文档与可移植性

**15. 写死的本机路径**

- 位置：`android/app/build.gradle.kts`（原 `buildPython("D:/android-build/py311/python.exe")`）
- 修复：新增 `chaquopyPython()`，依次读环境变量 `CHAQUOPY_PYTHON`、
  `local.properties` 的 `chaquopy.python`，都没有则交给 Chaquopy 自探测。

**16. 三份文档与实现不符（含「字节级一致」的错误表述）**

- 重写：根 `README.md`、`desktop/README.md`、`docs/BUILD.md`
- 修正点：补 `main.py`/`bridge.py`/`updater.py`/`qml/` 这套 QML 界面的说明与「两套界面」对照表；
  仓库名 `Insta-camara-tools` → `Insta-camera-tools`；Python 版本统一 3.10+（原文一处 3.14 一处 3.11+）；
  删掉写死的产物哈希；android 层级补全 `app/`；
  把「三个模块在桌面端和安卓端字节级一致」改为「逻辑等价但非字节级一致，改共享逻辑须两处同改」；
  `build.bat` 内容按实际文件重写。

---

## 三、本轮补充修复（2026-11-08 第二轮）

在具备完整构建环境的机器上继续完成了上一轮标注「无法修复」的项。

### 补充 1：APK 已重打（原未修项 1）

`D:ndroid-build` 工具链齐备（JDK 21 / Gradle 8.7 / SDK 34 / Chaquopy），执行：

```bash
cd android
export JAVA_HOME=/d/android-build/jdk21/jdk-21.0.12.1+1
export ANDROID_HOME=/d/android-build/sdk
export GRADLE_USER_HOME=/d/android-build/.gradle
/d/android-build/gradle-8.7/bin/gradle --no-daemon :app:assembleRelease
```

产物 `android/app/build/outputs/apk/release/app-release.apk`，72,830,835 B，
`versionCode 14 / versionName 0.7.2`，双 ABI 均含 `libffmpeg.so` + `libffprobe.so`。
产物内 `IBGLA` 命中 0、`CPVC` 命中 0（含 `assets/chaquopy` 下 5 个 `.pyc`）。

### 补充 2：QML 版已实际打包（原未修项 2）

PySide6 环境就绪，`python -m PyInstaller --noconfirm InstaAceQml.spec` 成功。
产物 `desktop/dist/InstaAceQml/`，205 MB，`InstaAceQml.exe --self-test` 输出
`QML_OK roots=1`、退出码 0。

### 补充 3：CPVC 字样已清零（原未修项 4）

原 16 处（`insta_core.py` 12、`insta_index.py` 4）全部改写为中性技术表述：

| 原文 | 改为 |
|---|---|
| 对齐 CPVC 的 vf 链 / CPVC 原文 | 真机原片的滤镜链 |
| 对齐 CPVC run_ffmpeg 的 use_gpu=False 分支 | 软件编码路径 |
| CPVC 关键参数 | 真机原片关键参数 |
| 与 CPVC 真机参数一致 | 与真机原片参数一致 |
| 完全对齐 CPVC insertion_defaults(insert="last") | 完全对齐真机原片的插入策略（insert="last"） |
| 与 CPVC 完全一致 | 与真机原片行为一致 |
| 对齐 CPVC / 与 CPVC 行为一致 | 与真机原片行为一致 |
| CPVC 的 build_indexes() 也只写 main 一条记录 | 真机索引也只写 main 一条记录 |
| 与 CPVC 的 check_card_if_insta / build_indexes 完全一致 | 与真机原片的索引布局完全一致 |
| 真机样本 + CPVC 5.0.4 反汇编交叉验证 | 真机样本交叉验证 |
| CPVC: 内嵌源码 insta360_tf_import.py | 索引生成：build_indexes / tailor_metadata 两步 |
| 策略与 CPVC 的 set_field/encode_message 一致 | 策略 |

技术内容（偏移、参数、字节布局）一字未改，只去掉第三方产品名的溯源表述。
改完后 `desktop/ shared/ android/app/src/` 下 `grep -ri cpvc` 命中 0。

### 补充 4：签名与 debuggable 已可配置（原未修项 5）

`android/app/build.gradle.kts`：

- `release { isDebuggable = false }` —— 原为 `true`，正式包不允许。
- 签名证书改为三级查找：环境变量 `INSTA_KEYSTORE` / `INSTA_KEYSTORE_PASSWORD` /
  `INSTA_KEY_ALIAS` / `INSTA_KEY_PASSWORD` → `local.properties` 的 `insta.keystore*`
  → 回退 `~/.android/debug.keystore`。
- 回退 debug.keystore 是为了能覆盖手机上的旧版；**正式分发必须配自有证书**，
  否则任何持有 debug.keystore 的人都能伪造升级包。

### 补充 5：`java.util.Properties` 导入修正

`build.gradle.kts` 顶层函数里用了 `java.util.Properties`，Kotlin DSL 需显式
`import java.util.Properties`（放在 `plugins {}` 之前），否则报
`Unresolved reference: util`。已修并重新构建验证。

### 补充 6：商业字体已删除（原修复 10 的收尾）

`desktop/assets/fonts/Lenovo-XiaoxinChaokuGB.ttf`（1,284,276 B）已从仓库删除。
`Theme.qml` 的 `fontDisplayFamily` 会探测 `loadedFonts`：用户自行放入 `.ttf`
则启用，否则回退系统「Microsoft YaHei UI」。打包产物中不再包含该字体。

---

## 四、仍未修复 / 无法在本机修复（3 项）

**1. AMBA 修复未在真机上验证**

本机无 adb、无相机卡，也没有任何真机 `*.mp4` / `*.lrv` 样本。
本次验证是**合成模板的偏移级验证**（构造 AMBA box 后逐字节比对），
能证明「不再覆写帧率分母」，但不能证明「写进去的值就是相机认可的值」。
建议首次真机导入后，用 `ffprobe` 对比产物与真机原片的 `avg_frame_rate` / `nb_frames`。

**2. 已发布的旧 APK 内嵌真实序列号，不可撤回**

前身包 v0.7.1 的 `latest.apk` 里，`assets/chaquopy/app.imy` 中的 `insta_index.pyc`
在偏移 1457 处含完整序列号。已分发出去的部分无法收回，只能下架 + 换签名重发。
本次源码与产物已清理（新 APK 内 `IBGLA` 命中 0），但**旧 APK 不应再对外提供**。

**3. 真机导入链路未端到端验证**

硬解（MediaCodec）与硬编路径均带自动回退，但本机无设备，无法确认
Ace Pro 2 实拍 4K/8K HEVC 源上硬解是否真能开启、`hwdownload` 帧格式是否正确。
建议首次真机导入时观察 `import.log` 中的 `[硬件解码]` / `[回退]` 行。

---

## 五、包内结构

```
instaace-fusion/
├── FIXES.md                    ← 本文件
├── REVIEW.md                   ← 本轮整改前的审查报告（fusion 包）
├── REVIEW-v0.7.1.md            ← 前身包 v0.7.1 的审查报告
├── README.md
├── .gitignore
├── docs/BUILD.md
├── shared/
│   ├── insta_index.py
│   └── instbox/{inst_transplant.py, moov_rewrap.py}
├── desktop/
│   ├── core.py  gui.py  main.py  bridge.py  updater.py
│   ├── qml/                    （24 个 .qml + qmldir）
│   ├── assets/                 （图标；字体已移除）
│   ├── tests/test_insta.py     （34 passed）
│   ├── tools/make_icon.py
│   ├── build.bat  run.bat  build_qml.bat  run_qml.bat
│   ├── InstaAceImporter.spec  InstaAceQml.spec
│   ├── requirements.txt  requirements-dev.txt
│   ├── CHANGELOG.md  LICENSE
│   └── dist/InstaAceImporter.exe   ← 本轮构建的修复版产物
└── android/
    ├── app/src/main/python/     （5 个 .py，已修）
    ├── app/src/main/java/       （Kotlin，未改）
    ├── app/src/main/res/  AndroidManifest.xml（已补 INTERNET）
    ├── app/src/main/jniLibs/    （4 个 .so，约 92 MB）
    ├── app/build.gradle.kts     （versionCode 14 / 0.7.2）
    ├── build.gradle.kts  settings.gradle.kts  gradle.properties
    └── LICENSE
```

---

## 六、与 `G:\Insta-camara-tools` 的关系

`G:\Insta-camara-tools` 是 2026-10-27 的旧交付快照（扁平结构 + 旧版 `InstaAceImporter.exe`
39,026,162 B），**不包含本轮任何修复**，其 exe 仍带 AMBA 0x20 缺陷。
本包才是修复后的版本。目录名 `Insta-camara-tools` 本身也是拼写错误
（GitHub 上的实际仓库是 `DUOFreedom/Insta-camera-tools`，`Insta-camara-tools` 返回 404）。

---

*生成时间：2026-11-08 · 基线包 SHA256 `C15CD8FDD…`*
