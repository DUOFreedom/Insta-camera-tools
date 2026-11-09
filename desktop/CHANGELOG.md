# CHANGELOG

## 未发布

### 修复（安卓端 `batch_convert` 截断 / `cancel=None` / 失败被静默吞掉）

三个都是「不报错、只是结果错了」的缺陷，因此全部通过了此前所有测试。

- **安卓端 `batch_convert` 的函数体整段丢失**：只剩 docstring 与参数校验，写到 `base_seq = next_seq(...)` 就断在下一个顶层 `def` 之前，函数永远返回 `None`；唯一调用方 `ok, bad = batch_convert(...)`（CLI 目录批量导入）必然 `TypeError: cannot unpack non-iterable NoneType object`。用 `git log` 回溯 7 个版本直到安卓工程并入仓库的 `234b756`，`body_loop=0` 恒定成立 —— **缺陷从安卓工程进仓库的第一天起就在**，不是本轮改动引入。已按桌面端实现补齐函数体，并补上它依赖、但安卓副本里同样缺失的 `_source_stamp()`（容器 `creation_time` → 文件系统时间 → 当前时间三级回退）。
- **`cancel` 参数默认 `None`，下游却直接调 `cancel.is_set()`**：`convert()` / `batch_convert()` / `_run_ffmpeg()` / `import_with_inst()` 四个入口全部中招，`convert(src, out)` 这种最常见的调用（CLI、早期 GUI、第三方脚本）会立刻抛 `AttributeError: 'NoneType' object has no attribute 'is_set'`。改为在入口处统一归一化成 `threading.Event()`，下游不再逐处判 `None`。桌面端 5 处、安卓端 4 处。
- **桌面端并发路径把失败当成功**：`except BaseException: pass` 吞掉所有异常后靠 `first_error` 汇总，但 `first_error` 只在 `_run_ffmpeg` 外层记录；构建命令行、探测时长这些更早的步骤失败时无人记录，`convert()` 于是正常返回 `(None, None)`，调用方拿两个 `None` 当成功路径继续往下走。已在该 `except` 里兜底记录 `first_error`，并单独跟踪 `canceled` 标志（取消不是「某一路失败」）。
- **`_build_transcode_cmd` / `_build_hw_transcode_cmd` 在缺 ffmpeg 时把 `None` 塞进 argv**：报出来的是「命令列表为空」，真正原因被掩盖。改为显式抛 `ValidationError("未找到 ffmpeg，无法构建转码命令")`。

### 测试（截断守卫 / 取消归一化 / 失败不可静默）

新增 4 条，每条都做过回滚验证（还原成缺陷版本确认变红，再恢复确认变绿）：

- `test_android_core_functions_are_not_truncated` —— 结构性守卫：声明了非 `None` 返回类型却没有 `return` 的函数一律判失败。只按返回注解判断，避免 `save_job` 这类本来就返回 `None` 的函数误报。
- `test_batch_convert_returns_success_and_failed_lists` —— 直接调用 `batch_convert([], tmp)` 断言返回两个空列表；截断版本会立刻返回 `None`，不必等到用户点批量导入。
- `test_convert_without_cancel_does_not_raise_attribute_error`
- `test_convert_failure_is_not_reported_as_success` —— 断言失败必须抛异常且带可读信息，不能返回 `(None, None)`。

全套 **55 passed, 2 skipped**（此前 49 passed）。

### 修复（`batch_convert` 的取消语义）

同一类「取消不生效 / 取消被当成失败」的问题，桌面端与安卓端各一份：

- **桌面端 `batch_convert` 无法中途取消**：循环体既不检查 `cancel`，也不把 `cancel` 传给 `convert`，用户点了取消，剩下的文件还是会一个个转完。已在循环开头检查，并把 `cancel` 透传下去。
- **取消被当成「这个文件失败」**：`except Exception: failed.append(...)` 会把 `CanceledError` 也收进 `failed`，上层看到的是"这一条有问题"，接着转下一条。已改为先 `except CanceledError: raise`。

### 测试（批量取消）

- `test_batch_convert_stops_on_cancel` —— 取消点设**在第一条转完之后**。踩过的坑：`batch_convert` 开头本来就有一道 `if cancel.is_set(): raise`，在入口就置位只能测到那道守卫，测不到循环；第一版测试因此连缺陷版本都能通过。
- `test_batch_convert_propagates_cancel_from_convert` —— `convert` 内部抛 `CanceledError` 时必须原样上抛，不能被塞进 `failed`。

两条都做了回滚验证：还原缺陷版本后双双变红。

### 产物重建与核对

- 安卓 release APK：75,260,052 B，sha256 `62e4294bf6746e05e180c5228f89be955b7a96129ef2f67be0b7039935af6d35`。
  解包 `assets/chaquopy/app.imy` 核对字节码：`_source_stamp` 已存在，`batch_convert` 有 `success`/`failed` 局部变量，
  `_build_transcode_cmd` 有 `ff` 局部变量。`:app:testReleaseUnitTest` → IndexTest 7 skipped / ConsentLogicTest 5 passed。
- 桌面两个可执行文件此前都打包着旧 `core.py`（11-08 构建），已重建：
  `InstaAceQml.exe` 78,829,648 B / sha256 `3cf26977885f0ec4ac785669dc982b451d4d91e703f8d7a79038bd9ba226bcde`；
  `InstaAceImporter.exe` 39,072,863 B / sha256 `4ffe7a64e057b019393793ce45b203556beae8bf124b65e046ecfc5c7766e9f6`。
  从两者内嵌的 `PYZ.pyz` 取出 `core` 模块核对：`convert` 有 `canceled`、`batch_convert` 有 `success`/`failed`、`_source_stamp` 存在。
  `InstaAceQml.exe --self-test` → `QML_OK roots=1`，exit 0。
- `docs/BUILD.md` 的实测产物哈希同步更新，并注明该值随源码变化、不可当作固定校验和。

### 修复（`shared/instbox` 与安卓端的模块导入）

同一类缺陷的三份副本：把「同目录兄弟模块」当成顶层模块平铺导入，能跑通纯靠调用方预先改过 `sys.path`。三种加载方式（包导入 / PyInstaller 平铺冻结 / 直接跑脚本）里只要有一种不满足就 `ModuleNotFoundError`，而失败又常常被宽 `except` 吞掉，表现为功能静默退化。

- **`shared/instbox/moov_rewrap.py` 包导入必然失败**：原代码把 `shared/` 放进 `sys.path` 后 `import inst_transplant`，但该模块实际在 `shared/instbox/` 下，于是 `import instbox.moov_rewrap` 必然 `ModuleNotFoundError` —— 而这正是桌面端 `core._load_inst_modules()` 的加载方式，即**桌面端从源码运行时整条 inst 移植路径不可用**，`desktop/tests/test_insta.py` 也在收集阶段直接失败（此前只有 4 条回退测试真正跑起来）。改为优先包内相对导入，`ImportError` 再回退平铺导入。
- **`desktop/core.py:_meta_equivalent()` 静默退化成逐字节比较**：裸 `import inst_transplant` 失败后被 `except Exception: return a == b` 吞掉，退化成逐字节全量比较；而 f9（inst 偏移）是可变长字段，全量比较会把合法条目误判成不匹配。改为走 `_load_inst_modules()`。`android/.../insta_core.py` 的同名函数同步修正。
- **`shared/instbox/inst_transplant.py` 主移植路径的平铺导入**：v18–v21 成功路径里 `from moov_rewrap import rebuild_media` 位于函数体内，包导入时 `shared/instbox` 不在 `sys.path` 上，真机/真片导入时才炸。改为相对导入优先 + 平铺回退，并保留原有的 `globals()["filter_avc1_children"]` 注入点。
- **`android/.../camera_moov_rewrap.py` 的 `sys.path` 指错目录**：`parents[1]` 解析到 `android/app/src/main`，而 `insta360_tf_import.py` 与它同在 `main/python/` 下；此前没炸只因 `insta_core` 已把该目录放进 `sys.path`。改为 `parent`。

### 修复（安卓端硬解/硬编回退与取消分类）

三个缺陷都在 `android/app/src/main/python/insta_core.py` 的 `convert()` 内，共同点是**都不会抛异常，只是结果错了**，所以原有的 4 条回退测试全绿。

- **硬解失败日志永远是 `UnboundLocalError`**：`_run_transcode()` 的 `defer_fail` 分支读写 `first_error`，但该函数没有 `nonlocal` 声明（只有 `_run_one` 和 `_fail` 有）。于是每次硬解失败，`[回退] hevc_mediacodec 硬件解码失败（cannot access local variable 'first_error' ...）` 顶掉了真实 ffmpeg 报错，用户永远查不出硬解为什么失败。
- **补 `nonlocal` 并不能修好，反而会彻底断掉回退**：调用方用 `if first_error is not None: raise` 区分「本任务失败，可以回退」与「兄弟任务已失败，整批要停」。defer 分支一旦先记一笔，自己的失败就冒充成兄弟失败，回退分支永远进不去 —— 硬解失败直接变成整批中止。正确做法是**根本不在 defer 分支记 `first_error`**，只把异常抛给调用方。随之删除已成死代码的 `my_error` 恢复块（它原本用来撤销自己记下的失败）。
- **用户取消被当成编码器故障**：`CanceledError` 是 `Exception` 的子类，会落进 `except BaseException` 的「MediaCodec 硬编失败」分支，每取消一次就多跑一条注定被取消的软编 ffmpeg。硬解回退的软编阶段同样如此，且 `_fail()` 还会把取消记成 `first_error`、顶掉兄弟任务真实的 ffmpeg 报错。两处均改为优先 `except CanceledError: raise`。
- **取消被报成转码成功**（上述修复引入的回归，本轮已一并解决）：并行驱动用 `except BaseException: pass` 吞掉所有异常、再靠 `first_error` 汇总。取消一旦不再写进 `first_error`，`convert()` 就会在用户已取消的情况下正常返回两个输出路径。改为在汇总循环里单独记 `canceled` 标志，`first_error` 之后再抛 `CanceledError`。

### 测试

- 新增 5 条回退回归用例（`desktop/tests/test_android_fallback.py`，共 9 条）：硬解回退日志必须含真实错因、每个任务都要各自回退而不是整批中止、硬解回退途中取消必须抛 `CanceledError`、取消不得触发软编重试、软编回退阶段取消不得顶掉兄弟任务的失败原因。
- **每条用例都做过「回滚验证」**：把对应修复逐一还原成缺陷版本，确认对应用例变红、其余保持绿，再恢复。避免写出「看着像测试、其实永远绿」的空壳。
- 写测试时踩到一个坑并记录在注释里：`cmd` 是参数列表，`"mediacodec" in cmd` 只做整元素相等匹配，永远匹配不到 `"hevc_mediacodec"`，必须逐元素 `any("mediacodec" in a for a in cmd)`。
- 全套 **49 passed, 2 skipped**（此前 43 passed）。

### 产物验证

- 重新离线构建 release APK 通过：75,257,520 B，sha256 `bd45835bc208aaa8cb115cf9824cd9a97cb6434edadfe96ada0daa087c1f1515`。
- 解开 `assets/chaquopy/app.imy` 反序列化 `insta_core.pyc` 核对名字表：`_run_transcode` 的 `freevars`/`varnames` 里都已没有 `first_error`（缺陷的病根就是它），`convert` 有 `canceled`、无 `my_error`，两处都引用了 `CanceledError`。
- `:app:testReleaseUnitTest` → IndexTest 7 skipped / ConsentLogicTest 5 passed / 0 failures。
- `desktop/dist/InstaAceQml.exe --self-test` → `QML_OK roots=1`，exit 0。

### 测试（模块导入与 IndexTest）

- 新增 4 条回归护栏：`instbox` 包导入、`instbox` 平铺导入（子进程验证）、`inst_transplant` 相对导入分支的 ast 静态检查、`_meta_equivalent` 在 f9 漂移时仍判等价而 f7 时间戳变化时判不等价。当时全套 **42 passed, 2 skipped**（此前因收集失败只跑到 4 条）。
- **`IndexTest` 在干净检出上 6/7 红**：样本取自真机、含设备标识，按既有约定不入库，但测试用 `assertTrue` 做前置判断，于是每条都抛 `FileNotFoundException`。改为 JUnit `Assume.assumeTrue`：有样本时照常做字节级幂等校验，无样本时整类跳过。实测 `:app:testReleaseUnitTest` → **5 passed / 7 skipped / 0 failed**。

### 构建验证（本轮实际跑通）

- **Android 构建此前被误判为「本机做不了」**：仓库确实没有 gradle wrapper，`gradle` 也不在 PATH 上，但工具链其实齐备 —— `D:\android-build\gradle-8.11.1`、JDK 21（`D:\android-build\jdk21`）、SDK（`D:\android-build\sdk`）、Python 3.11.9（`D:\android-build\py311`），且真正的依赖缓存位于 `D:\android-build\.gradle`（`~/.gradle` 里只有 AGP 8.5.2，联网又拿不到 8.7.3）。
- 构建命令：`GRADLE_USER_HOME=D:/android-build/.gradle JAVA_HOME=... ANDROID_HOME=... CHAQUOPY_PYTHON=... gradle --offline assembleRelease`。
- `:app:compileReleaseKotlin`、`:app:assembleRelease` 均通过；产物 `app-release.apk` 75,257,546 B，versionCode 14 / versionName 1.2.0，sha256 `f0dbef7779be36c0a6b9942a61f79d6d801d0b0b37215bcadd27c351e8d569d0`。
- **验证修复确实进了产物**：解开 `assets/chaquopy/app.imy` 反序列化模块字节码 —— `camera_moov_rewrap` 的 `co_names` 里是 `parent`（不再是 `parents`），`insta_core._meta_equivalent` 的 `co_names` 里是 `_load_inst_modules`（不再是裸 `insta360_tf_import`）。
- `debug` 变体离线编译不可行：`ui-tooling` 与 `junit` 只在联网时可解析（`--offline` 下 `checkDebugAarMetadata` 失败），release 变体不受影响。

## 1.2.0 — 2026-11-08

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
- **版本号统一**：桌面端与安卓端统一为 `1.2.0`（`desktop/core.py`、`android/.../insta_core.py` 的 `__version__`，gradle 的 `versionName`，以及安卓关于页文案）；`versionCode` 13→14。
- **移除联想商业字体**：删除 `assets/fonts/Lenovo-XiaoxinChaokuGB.ttf`（商业授权不允许随 GPL 项目分发）；`qml/Theme.qml` 改为探测 `loadedFonts`，没有则回退系统「Microsoft YaHei UI」。
- **补 AMBA 回归测试**：`desktop/tests/test_insta.py` 新增 3 条（帧率分母不被覆写、AMBA 过短抛错、九个字段偏移逐一核对），此前对 AMBA 零覆盖，正是 P0 能被带进发布的原因。
- **QML spec 补图标**：`InstaAceQml.spec:57` 补 `icon=['assets/app.ico']`。
- **相机卡判断降级留痕**：勾了「登记索引」但输出目录不是相机卡结构时，原先静默降级为纯转码；现在写日志并提示「改为仅转码」（`bridge.py:274-281`）。
- **更新检查不再吞异常**：`updater.py:105` 从裸 `pass` 改为写 `import.log`。

#### P2（文档与可移植性）

- **去掉写死的本机路径**：`android/app/build.gradle.kts` 的 `buildPython("D:/android-build/py311/python.exe")` 改为 `chaquopyPython()`，依次读环境变量 `CHAQUOPY_PYTHON`、`local.properties` 的 `chaquopy.python`，都没有则交给 Chaquopy 自探测。
- **文档重写**：根 `README.md`、`desktop/README.md`、`docs/BUILD.md` 按真实仓库层级重写（补 `main.py`/`bridge.py`/`updater.py`/`qml/` 两套界面说明、纠正「三个模块字节级一致」的错误表述、仓库名 `Insta-camara-tools` → `Insta-camera-tools`、Python 版本统一为 3.10+、产物哈希不再写死）。

### 第二轮补充（同日，具备完整构建环境后）

- **APK 已重打**：`versionCode 14 / versionName 1.2.0`，双 ABI，72,830,835 B。产物内设备序列号与第三方产品名均 0 命中（含 `assets/chaquopy` 下 5 个 `.pyc`）。
- **QML 版已实际打包**：`InstaAceQml.exe --self-test` 输出 `QML_OK roots=1`、退出码 0，产物 205 MB。
- **第三方产品名引用清零**：原 16 处注释（`insta_core.py` 12、`insta_index.py` 4）全部改为「真机原片」等中性表述；技术内容（偏移、参数、字节布局）未动，只去掉产品名与溯源表述。
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
  - ⚠️ 该条目最初误写成 `amba[0]+0x20`：0x20 是**视频帧率**（fps_num/fps_den），并非音频采样率。0x20 与 `camera_udta` 的 `(29, 1001)`（视频帧率分母）在 AMBA 内字节 32 处重叠，会把帧率分母写成 `frames*4`。已在 1.2.0 修正为 0x54。

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
