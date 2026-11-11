# CHANGELOG

## 未发布

### 修复（机型预设：选了就崩，且选了不生效）

「机型预设」这个功能从 `cb6099a` 加进来那天起就是坏的，两处：

**一、桌面端 `CAMERA_PRESETS` 从来没定义过。** `cb6099a` 的提交说明写着「desktop/core.py: 新增 CAMERA_PRESETS 常量表」，但 `git show cb6099a -- desktop/core.py | grep CAMERA_PRESETS` 只命中一行 `+        preset = CAMERA_PRESETS.get(model_override)` —— 函数体里的引用贴上了，表本体没贴。后果是只要用户在界面选「Ace Pro 2」或「GO Ultra」、而卡里又没有真机原片可量（`spec` 为 None 或没有 `video` 段），`_build_spec_tasks()` 就 `NameError: name 'CAMERA_PRESETS' is not defined`，整个转换直接抛异常。把安卓侧那份完整的表抄过来即可 —— 两份必须逐字一致，由新增的 `test_camera_presets_match_android` 守着。

**二、桌面端机型下拉框根本没接线。** `OutputOptionView.qml` 声明了 `signal modelOverrideSelected(string value)`，delegate 里也 `root.modelOverrideSelected(modelData)` 发了信号，但 `main.qml` 里 `OutputOptionView { id: outputView }` 的实例化只接了 `onBrowseOutput` / `onLocateCard` / `onPickCover` / `onClearCovers` / `onVerifyCard` 五个，`onModelOverrideSelected` 从来没接；`git log -S "onModelOverrideSelected" -- desktop/qml/main.qml` 是空的。`bridge.setModelOverride()` 全仓库零调用者。所以选机型只改了 QML 本地 property 和那行标签文字，`bridge._model_override` 永远是 `"auto"`，`convert(..., model_override=...)` 永远收到 auto。

对照组 `encoder` 是通的：它由 delegate 直接写 `root.encoder`，最后 `main.qml` 把 `outputView.encoder` 作为 `bridge.start()` 的第 4 个实参传下去 —— 走的是属性而不是信号。机型也按这个思路补：既绑 `modelOverride: bridge.modelOverride`（重开界面要显示上次的选择），也接 `onModelOverrideSelected`（选中即生效）。

两处都是「没有测试碰过这条路径」的后果：`grep -rn "model_override\|modelOverride\|CAMERA_PRESETS" desktop/tests/` 在修复前零命中，而 `cb6099a` 当时声称「全套 177 passed」。

### 测试（机型预设 7 条，含三处回滚验证）

`desktop/tests/test_insta.py` 四条：两端 `CAMERA_PRESETS` 逐字相等且键集恰好是 `{"auto","ace_pro_2","go_ultra"}`；`go_ultra` 无模板时出 `libx265/hvc1/gop120` 主视频 + `libx265/hvc1/gop10` 预览 + 单音轨，`ace_pro_2` 出 `gop16` + `libx264/avc1/gop16` 预览 + 双音轨；**卡里有真机原片时原片实测值优先于预设**（反过来的话，插着 GO Ultra 的卡选「Ace Pro 2」就会被静默按 Ace Pro 2 编，而卡里的 AMBA 与 nail 是按 GO Ultra 写的）；`auto` 档保持老行为（`VID_WIDTH`/`VID_HEIGHT`、gop 0）。

`desktop/tests/test_qml_bridge.py` 三条：`setModelOverride` 只认三个值，非法值报错且不改当前选择；`bridge._run()` 必须把 `model_override` 传到 `core.convert`（monkeypatch 记录实参）；`main.qml` 的 `OutputOptionView` 那段必须同时含 `modelOverride: bridge.modelOverride`、`onModelOverrideSelected:`、`bridge.setModelOverride(`，`OutputOptionView.qml` 必须含 `root.modelOverrideSelected(modelData)`。

回滚验证三处，都实测变红后还原：删掉整份 `CAMERA_PRESETS`（2799 字符）→ 两条测试红，报 `NameError` 于 `desktop/core.py:1154`；删掉 `main.qml` 里那 7 行接线（339 字符）→ 接线测试红；删掉 `bridge.py` 的 `convert` 分支里 `model_override=self._model_override,` → 转发测试红（`At index 0 diff: None != 'go_ultra'`）。**只删 `import_with_inst` 分支那处不会变红** —— 该测试走的是 `convert` 分支（`use_inst=False`），两处得分别验。

端到端复核（`.e2e/src.mp4`，`model_override="go_ultra"`，本机 ffmpeg 9.0.1 + QSV）：产物 `VID gop=120` / `LRV gop=10`，与真机 GO Ultra 模板一致。

### 新增（桌面端中英双语，跟随系统界面语言）

新增 `desktop/i18n.py`：键是中文原文、值是英文译文的文案表，共 210 条。查不到的键**原样返回中文** —— 漏译时界面显示中文，既不崩也不会露出内部键名，可以增量补齐。

语言判定顺序（`i18n.detect()`）：环境变量 `INSTA_LANG` > Windows 用户界面语言 > Qt 的 `QLocale` > 英文。Windows 这一级用 `GetUserDefaultUILanguage()` 而不是 `locale.getdefaultlocale()`：后者读的是进程的 C locale，中文系统上照样可能返回 `en_US`，判断不了用户实际看到的界面语言。`langid & 0x3FF == 0x04` 判中文（低 10 位是主语言 ID，0x04 是 `LANG_CHINESE`，因此简体、繁体、香港、新加坡全部落到中文）。进程内只判定一次 —— 系统界面语言不会在运行期间变化。

**产品名**按用户要求区分大小写：英文界面 `instatools`（全小写，写成 `InstaTools` 就算错），中文界面「影石相机工具」。此前界面里出现的「导入器」措辞全部去掉。

接线的三处：

- `desktop/bridge.py` 新增 `appName` / `lang` 两个 constant Property 和 `tr(text)` 槽。`_set_status()` / `_set_error()` 在**出口**统一过一遍文案表，而不是逐个调用点去包 —— 核心层把 `log` 直接接到 `_set_status` 上，逐个改必然漏。属性与槽直接返回给 QML 的字符串（封面状态、样本摘要、序号提示、卡校验结果、硬件编码器名）逐个单独包。
- **模板反查**是这一轮必须解决的问题：核心层先把参数套进模板再把字符串送到界面（`转换失败：源文件不存在`），到 `_set_status` 时 `%s` 早被替换，按原键必然查不到。`i18n._templates()` 把带占位符的键按 `re.split(r"%[sd]", key)` 拆成几段、用 `(.+?)` 连接、`re.DOTALL` 编译，`t()` 用 `fullmatch` 命中后按捕获组顺序替换。递归深度限制 3 层 —— 参数本身常常又是一条中文（`权限被拒`），要再查一次。
- 23 个 QML 文件里 96 处中文字面量包成 `bridge.tr("…")`；窗口标题、页面大标题、托盘提示与通知标题改为 `bridge.appName`，`desktop/main.py` 的 `setApplicationName()` 与新增的 `setApplicationDisplayName()` 都走 `i18n.app_name()`（任务栏与 Alt+Tab 显示的是 displayName）。跨行拼接的文案合并成单键，带标点的整句（`当前版本 %1，最新版本 %2。`）也合并 —— 中文句号「。」拼在英文后面很刺眼。编码器下拉框改成「值/显示」分离（`encoderValues` + `encoderLabels`），否则翻译后的标签会被当成编码器名传给核心。

### 测试（双语文案层 25 条 + 4 条守卫）

`desktop/tests/test_i18n.py`：语言判定 5 条（环境变量覆盖、大小写、非法值回落系统、Windows 优先于 Qt、全链回落英文）、产品名 3 条（英文全小写、中文正确、不得出现「导入器」）、翻译 9 条（中文原样、已知译出、未知原样、空串安全、模板反查、参数逐字节保留、嵌套递归、多行整段译出、重复参数不炸）、守卫 8 条。

守卫里三条是**用 AST 而不是 grep** 的：这些字符串常常是多行隐式拼接（解析时已合成一个常量），包住它们的调用也可能跨行，正则数不准。做法是先标出「在 `t()` / `_tf()` / `_set_status()` / `_set_error()` 实参位置上的」字符串常量，剩下的中文常量就是漏网的；同时反过来要求「每个进界面的字面量都必须有译文」。第四条是 QML 侧的「任何中文都必须包在 `bridge.tr()` 里」—— 一块中文一块英文比整屏中文更像半成品。

回滚验证四处：删掉文案表里 `文件夹不存在` 的译文 → `test_status_and_error_message_templates_are_translated` 红；把 `self._hw = i18n.t("未检测到")` 还原成裸字符串 → `test_no_untranslated_chinese_left_in_bridge` 红；去掉 `Sidebar.qml` 里一处 `bridge.tr()` → `test_no_untranslated_chinese_left_in_qml` 红。三条都实测变红后还原。

顺带修掉一个测试环境的坑：`desktop/i18n.py` 与 `android/app/src/main/python/i18n.py` 同名，而 `test_android_fallback.py` 把安卓的 python 目录插到了 `sys.path[0]`，于是同一次 pytest 会话里 `import i18n` 可能拿到安卓那份（只有几十条标签文案），桌面端的翻译断言整片报错、单独跑 test_i18n.py 又全绿。新增 `desktop/tests/conftest.py` 把桌面目录钉在 `sys.path` 最前面并清掉误加载的 `i18n`，`test_android_fallback.py` 改为 `sys.path.append()`。

### 新增（安卓端中英双语资源）

`android/app/src/main/res/values/strings.xml` 13 键 → 124 键（英文），新建 `values-zh/strings.xml` 124 键（中文）。选 `values-zh` 而非 `values-zh-rCN`：一份文件覆盖 zh-CN / zh-HK / zh-TW / zh-SG，繁体用户拿到简体中文仍比回落到英文可用，也免维护第二套。Manifest 两处 `android:label` 由 `${appLabel}` 改 `@string/app_name`，`build.gradle.kts` 删掉 `manifestPlaceholders["appLabel"]`。

aapt2 实测：`application-label:'instatools'`、`application-label-zh:'影石相机工具'`。

145 行中文字面量换成 130 处 `stringResource` / `getString`。有三处不是纯替换，因为原来的逻辑拿**中文文案前缀**做判断，一翻译必然失效：

- 新增 `enum class StageKind { Idle, Running, Canceling, Canceled, Done, Partial, Failed }` 与 `AppState.stageKind` / `setStage(kind, text, error?)` / `stageError`。`stage` 只负责显示；Snackbar 分支与 `cardStateFor()` 改按 `StageKind` 走；失败卡不再从文案里 `removePrefix("失败：")` 猜错误内容。旧的 `cardStateFor(..., stage: String)` 重载保留给既有单测。
- 编码器由 `"自动"/"硬件"` 改为稳定 code `"auto"/"hardware"`（`AppState.ENCODER_AUTO/HW`），显示走资源。
- `PythonEngine.status()` 改返回 `CoreStatus(ok, text)`，`AppState.pythonStatus` 不再对本地化文案做 `startsWith("Python 核心就绪")`。

Java 包目录 `com/duofreedom/instaace` 一并搬到 `com/duofreedom/instatools`（上一轮重命名只改了 `package` 声明，漏了 12 处 `import com.duofreedom.instaace.*`，HEAD 上其实**编不过**）。`instaace_consent.json` → `instatools_consent.json` —— 副作用是已装过的用户会重新看到一次同意页，这是改名后该有的结果。

### 修复（英文界面下「输出与选项」区的排版）

英文文案普遍比中文长，而这一区原本按中文宽度写死：标签列固定 64 像素（只够「机型」两个字），下拉按钮固定 160，说明文字的可用宽度靠 `parent.width - 64 - 8 - 160 - 8` 手算。换成英文后实测：`Camera model` 压在 `Automatic (measured from the card)` 上，`Output folder` 被截成 `Output fold`，`Locate the SD card` 挤出卡片右边界，`Verify index` 的说明跑出窗口。

改成 `RowLayout`（`desktop/qml/OutputOptionView.qml`，新增 `import QtQuick.Layouts`）：标签列宽度由 `FontMetrics` 实测四个标签取最大值（`labelWidth` 属性），按钮按 `implicitWidth` 撑开（`Layout.preferredWidth: Math.max(160, implicitWidth)`），说明文字 `Layout.fillWidth` 并在过长时省略。手算宽度全部删掉。

两种语言都真窗口核对过（`INSTA_LANG=en` / `zh`，截图确认标签列对齐、按钮不出界、省略号正常）。这类问题单元测试看不出来 —— QML 里既没有布局断言也没法在无窗口环境下量文字宽度，只能真渲染一遍。

### 产物（本轮）

- `desktop/dist/instatools.exe` 80,519,132 B，`INSTA_LANG=en` 与 `zh` 下 `--self-test` 均为 `QML_OK roots=1`、exit 0。
- 安卓 release APK 75,311,427 B，`aapt2 dump badging` → `application-label:'instatools'`、`application-label-zh:'影石相机工具'`，包名 `com.duofreedom.instatools`，versionCode 14 / versionName 1.2.0。
- 单测：`IndexTest` 7 skipped（缺真机样本）、`PythonI18nTest` 4、`ConsentLogicTest` 5、`ImportCardStateTest` 6，0 失败；桌面 `pytest` **202 passed, 3 skipped**。

### 变更（删除 PyQt5 经典界面，桌面端只剩 QML 版）

`desktop/gui.py`（PyQt5 经典界面）、`desktop/instatoolsImporter.spec`、`desktop/build.bat`、`desktop/run.bat` 一并删除，`requirements.txt` 与 `requirements-dev.txt` 里的 `PyQt5>=5.15` 去掉。理由是维护两套界面的成本全落在「同一处缺陷修两遍、第二遍总忘」上 —— 本轮删掉的 `_resolve_encoder` 形参覆盖、`batch_convert` 静默推翻软件编码，都是先在经典版发现、再手工同步到 QML 侧的同类问题。合并成一套之后这类漂移不可能再发生。

被删掉的能力在 QML 侧补齐或明确记录：

- **开工前体检 `preflight`**：`core.preflight()` 新增 `template_names` 参数（先按用户选的样本对取模板，取不到再回落 `find_native_template`）；`desktop/bridge.py` 的 `start()` 在动手前调用它，`blocking` 非空就中止并显示「开始前检查未通过：…」，`warnings` 写进 import.log。
- **自动分析样本**：新增 `Bridge.autoDetectSample(output_dir)`。先看输出目录及其父目录，再扫 D 到 I 盘的 `DCIM` / `DCIM\Camera01` / `DCIM\100MEDIA`，找到就用 `setSample()` 走正常分析。**VID 优先于 LRV** —— 按字母序 `LRV_` 排在 `VID_` 前面，直接取第一个会把代理轨当样本，而代理轨的分辨率/帧率/GOP 都与主轨不同。扩展名用新增的 `SAMPLE_EXTS`（在 `VIDEO_EXTS` 基础上加 `.lrv`/`.insv`/`.ins`）：`VIDEO_EXTS` 不含 `.lrv`，用它会让 LRV 分支永远匹配不到、VID 优先的逻辑形同虚设。
- **转换中关窗**：新增 `desktop/tray.py`（`QSystemTrayIcon` 封装 + `showRequested`/`quitRequested`/`notify`）。`main.py` 改用 `QApplication`（`QMenu` 是 QWidget，`QGuiApplication` 下报 `QWidget: Cannot create a QWidget without QApplication`）并 `setQuitOnLastWindowClosed(False)`；`main.qml` 的 `onClosing` 在转换中弹窗给两个出路 —— 「停止并退出」（`bridge.cancel()` + `waitWorker(20000)` 成功才退出）与「最小化到托盘」（窗口隐藏、转换继续、跑完弹提示）。此前 QML 版只拦截、不给选择，直接退出会让 ffmpeg 变孤儿继续往相机卡写。
- 删除时仍缺的封面选择、断点续跑、卡校验，已在下一节补齐（不再有缺口）。

### 变更（ffmpeg 改为「先系统后本地」，安装分全局/程序目录两种）

原来的顺序是「exe 目录 → 本地目录 → 几个常见安装路径 → PATH」，等于**先找自己带的那份**。后果是用户机器上明明装了 ffmpeg（chocolatey / scoop / winget 装的），程序仍然视而不见，还额外下一份 200 MB 塞在程序目录旁边；换台机器又得重下一遍。

新顺序按用户提的要求改成**先看系统装没装**（`desktop/core.py:198` 的 `_find_tool()`）：

| 顺序 | 位置 |
|---|---|
| 1 | 环境变量 `FFMPEG_PATH` / `FFPROBE_PATH` |
| 2 | 注册表 `App Paths\ffmpeg.exe`（安装器登记的权威位置，HKLM 优先 HKCU） |
| 3 | `C:\Program Files\instatools\bin`（本程序装全局的目标） |
| 4 | `Program Files\ffmpeg\bin`、`Program Files (x86)\ffmpeg\bin`、`C:\ffmpeg\bin`、chocolatey、scoop shims、WinGet Links |
| 5 | 系统 `PATH` |
| 6 | exe 所在目录及其 `bin\` |
| 7 | `%LOCALAPPDATA%\instatoolsImporter\bin`、`~\instatoolsImporter\bin` |

配套拆成三个函数：`_system_tool_dirs()`（全局）、`_portable_tool_dirs()`（程序目录）、`_registry_ffmpeg()`（注册表）。新增 `ffmpeg_source(path)` 返回 `missing` / `env` / `system` / `portable`，界面据此告诉用户「这份 ffmpeg 是你系统里那个」，否则用户会以为自己没装。

下载与安装分离成两步（`desktop/core.py:548` 的 `install_ffmpeg(scope)`）：

- **先下到 `%TEMP%\instatoolsFfmpeg`，再按 scope 落盘**。选「装到系统」时 UAC 弹窗只覆盖最后那次复制 —— 用户点了「否」也不会白下 200 MB 再重来。
- `scope="global"` 走 `install_ffmpeg_global()`：已是管理员就直接复制；否则写一个 `.bat`（`mkdir` + 两条 `copy /y` + `reg add` 登记 `App Paths`）用 `ShellExecuteExW(lpVerb="runas")` 提权执行。`SEE_MASK_NOCLOSEPROCESS` 是必须的 —— 不加这一位 `ShellExecuteEx` 立刻返回，复制还在跑就去做存在性校验了，会误报失败。用户拒绝时 `ShellExecuteExW` 返回 0 且 `GetLastError() == 1223`（`ERROR_CANCELLED`），据此回「已取消（未获得管理员权限）」而不是笼统的失败。
- 不改系统 `PATH`：改 `PATH` 有把 `%SystemRoot%` 这类展开值写坏的风险（`setx` 截断、注册表里混入未展开变量），而登记 `App Paths` 已经足够让「运行」对话框和本程序的探测找到它。
- `scope="portable"` 走 `ffmpeg_install_dir()`（exe 同目录 `bin\`，不可写则退回 `%LOCALAPPDATA%\instatoolsImporter\bin`），全程不需要任何权限，绝不弹 UAC。
- `download_and_install_ffmpeg()` 保留为兼容壳，等价 `install_ffmpeg("portable")`。

界面（`desktop/qml/main.qml` 的橙色横幅）从单个「下载 ffmpeg」按钮改成两个：「装到系统目录」与「装到程序目录」，并补一行说明两者区别（全局所有程序能用但要管理员，程序目录只给本程序用但不需要权限）。`Bridge` 新增 `installFfmpeg(scope)` Slot 与 `ffmpegSource` / `ffmpegScope` 两个 Property；`downloadFfmpeg()` 保留，默认 `portable`。

顺带删掉 `_tool_dirs()` —— 新逻辑里 `_find_tool()` 分两段走系统/本地目录，这个合并列表没有调用方了。

测试：新增 `desktop/tests/test_ffmpeg_locate.py` 14 条（系统优先于本地、注册表优先于目录扫描、环境变量优先于一切、`ffmpeg_source` 四种取值、非管理员装全局要走提权且脚本里真有 `copy /y` 与 `App Paths`、已是管理员不重复弹 UAC、UAC 取消如实上报、portable 绝不提权、先下载后提权的顺序、装完仍不可用要报失败、下载失败要报失败、旧入口仍可用），`desktop/tests/test_qml_bridge.py` 新增 4 条（scope 透传、默认 portable、`ffmpegSource` 暴露给界面、`ffmpegScope` 跟随请求）。回滚验证：`_find_tool` 两段顺序对调 → `test_system_install_wins_over_portable` 红；`install_ffmpeg` 改成「global 先提权后下载」→ `test_install_downloads_before_elevating` 红；`installFfmpeg` 忽略 scope 恒用 portable → 两条红。全套 160 → 178 passed。

### 新增（QML 版补齐经典版全部功能）

删掉经典版时 QML 侧缺九项，本节一并补齐，每项都有测试（`desktop/tests/test_qml_bridge.py`，全套 126 → 160 passed）。

- **封面选择**：`Bridge.covers`（键是 `normpath`，不用原字符串，否则正反斜杠两种写法取不到）+ `pickCover` / `clearCovers`。加文件时按 `core.default_cover_for` 自动配对同名图（`a.mp4` + `a.jpg`），`clearCovers` 不是简单清空而是**重新按同名图配一遍**。多视频时 `pickCover` 直接拒绝 —— 猜「这张图配哪个视频」猜错会让 A 用上 B 的封面，而且极难发现。`_run` 里按 `os.path.normpath(src)` 取 `cover=` 传给 `import_with_inst`。
- **断点续跑**：`Bridge.checkResume` 读 `core.load_job`，只统计「这次列表里也有」的已完成条目；`start()` 在 `_resume_only` 时把 `files` 换成未完成的那几条。`_run` 开头**先继承旧 job 再合并本次列表** —— 续跑时 `files` 只是未完成几条，直接重建会把已完成记录抹掉，再取消一次就全白跑。新增 `_job_item(job, src)` 按 `normpath` 查条目，因为合并后索引与 `files` 不再一一对应。每步 `running` → 保存 → `done`/`failed` → 再保存；`CanceledError` 时**保持 running**（下次还要跑它）。
- **卡校验与清理**：`Bridge.verifyCard`（后台线程，卡里几百条要跑几秒）/ `repairCard`。结果拼成「共 N 条索引：正常 X，异常 Y」+ 前 15 条明细，同时写 import.log。
- **定位 SD 卡**：`Bridge.locateCard` 扫 D 到 I 盘的 `DCIM\Camera01` / `DCIM\100MEDIA` / `DCIM`，找到后由 `locatedChanged` 反填输出目录。
- **单条移除**：`Bridge.removeFile`，连带清掉该条的封面缓存。
- **硬件编码器探测**：`Bridge.detectHardware`（后台线程，探测要真编一次）。`_download_ffmpeg` 成功后**重置 `_hw_checked` 并重探** —— 启动那次因为找不到 ffmpeg 直接放弃，不重置的话用户装完 ffmpeg 仍然看到「未检测到可用硬件编码器」。
- **样本结构摘要**：`Bridge.specSummary`，摊开主视频/预览的分辨率帧率编码、色域、音频轨数。`setSample` 里必须单独 `specChanged.emit()` —— `specSummary` 是另一个 Property，漏了这行界面上「样本已读取」会亮而摘要一直空着。
- **下一序号提示**：`Bridge.refreshSequence`，显示「自动续接，下一序号 003」。没有它用户不知道这次从几号开始，容易和卡里已有文件撞号。
- **拖拽添加**：`main.qml` 加 `DropArea`（`z: 20`，**必须在内容之上**，压在 Column 下面怎么拖都没反应）→ `Bridge.addPaths`，文件夹展开一层，非视频文件给明确提示而不是静默无反应。

顺带修掉两个真缺陷：

- **封面预览永远是空的**：`Avatar` 的 `Image.source` 只认 URL，`coverImage` 原来返回裸路径 `C:/a.jpg`，QML 会解析成相对路径、加载状态是 Error 但**没有任何报错**，界面上就是一块空白（实测 `Image.status == 2`）。改为 `QUrl.fromLocalFile(path).toString()`。
- **`lastError` 粘性**：`InputFileView` 把 `state` 接到 `bridge.lastError`，一条「请先添加要转换的视频」会让文件区永久显示「出错了」，直到下次点开始才清。改为只反映列表自身状态，错误统一由 `ActionView` 显示，并加「知道了」按钮调 `Bridge.clearError`。

`desktop/tools/make_icon.py` 从 PyQt5 移植到 PySide6（否则删掉 PyQt5 后这个工具直接 ImportError）。

### 变更（4 个 QML signal 保留但禁用）

`OutputOptionView.encoderSelected`、`Sidebar.navigate`、`TextField.accepted`、`TitleBar.themeToggleRequested` 四个 signal 声明保留，发射点注释掉并注明「保留但禁用」。它们对应的交互要么已在别处实现（编码器由 `ActionView.start` 一并传参、主题由系统跟随），要么组件当前没有被引用；留着声明是为了将来接线时不必改 `qmldir` 与文档。

### 变更（删除零调用代码）

删掉 7 组确认无人调用的符号：`_num`、`_audio_map`（`core.py` + `insta_core.py` 各一份）、`add_file_entry`/`add_edit_entry`/`find_entry`（`insta_index.py` 两份）、`repair_inst_metadata_layout`、`patch_media_thumbnail`（`inst_transplant.py` + `insta360_tf_import.py`）。顺带删掉 `patch_nail_thumbnail` —— 它唯一的调用方 `patch_media_thumbnail` 被删后成孤儿，且与 `camera_udta` 里直接拼 nail box 的逻辑重复。

保留 `MediaError`（公开异常类型，外部 `except` 会引用）与 `_enc_dbl`（protobuf wire-type 1 原语，与 `_enc_bytes`/`_enc_uint` 成套）。`patch_inst_thumbnail` 实际在用，保留。

### 产物重建与核对（本轮）

- 桌面端 `desktop/dist/instatools.exe` 80,501,272 B，`--self-test` → `QML_OK roots=1`，exit 0。解包 `PYZ.pyz` 核对：`tray` 在包内、`gui` 不在；`bridge.start` 的关键字常量含 `('do_index','template_names')`、`bridge._run` 含 `('template','encoder','spec','progress','cancel','log','start_number','template_names')`；`autoDetectSample` 引用 `SAMPLE_EXTS`，常量含 `DEFGHIJ`、`DCIM`、`Camera01`；本轮补齐的 15 个函数（`addPaths`/`pickCover`/`clearCovers`/`verifyCard`/`repairCard`/`locateCard`/`removeFile`/`detectHardware`/`refreshSequence`/`checkResume`/`specSummary`/`hardwareEncoder`/`nextSequence`/`coverImage`/`clearError`）在 `bridge` 的 `co_names` 与函数定义表里全部存在，`fromLocalFile` 也在（封面预览要用 file:// URL）；`core._build_hw_transcode_cmd` 常量含 `qsv`/`amf`；`instbox.inst_transplant.video_gop` 的 `co_names` 含 `Path` 与 `read_bytes`；`moov_rewrap` 的 `co_names` 含 `_MAX_32BIT` 与 `zlib`、函数表含 `_chunk_offsets` 与 `udta_with_mcrc`；本轮 ffmpeg 改造的 15 个符号（`_portable_tool_dirs`/`global_install_dir`/`_system_tool_dirs`/`_registry_ffmpeg`/`_find_tool`/`ffmpeg_source`/`_staging_dir`/`_is_admin`/`_ShellExecInfo`/`_run_elevated`/`_install_to`/`install_ffmpeg_global`/`_download_ffmpeg_to`/`install_ffmpeg`/`download_and_install_ffmpeg`）全部在 `core` 的函数表里，`ctypes` 在 `co_names` 里，删掉的 `_tool_dirs` 已不在；`bridge` 的 `installFfmpeg`/`downloadFfmpeg`/`checkFfmpeg` 与 `ffmpegSource`/`ffmpegScope` 也都打包进去了。
- 安卓 `android/app/build/outputs/apk/release/app-release.apk` 75,279,539 B；单元测试 IndexTest 7 跳过 / ConsentLogicTest 5 / ImportCardStateTest 6，失败与错误均 0。解包 `assets/chaquopy/app.imy` 核对：7 组零调用符号（`_num`/`_audio_map`/`add_file_entry`/`add_edit_entry`/`find_entry`/`repair_inst_metadata_layout`/`patch_media_thumbnail`/`patch_nail_thumbnail`）在两份 pyc 里都已不存在；`camera_moov_rewrap` 的 `co_names` 含 `_MAX_32BIT` 与 `zlib`、函数表含 `_chunk_offsets` 与 `udta_with_mcrc`、`stco_box` 常量含 `b'co64'`、`rebuild_stbl` 的元组常量含 `(b'stco', b'co64')`。
- **APK 的字节数与 sha256 都不能当校验和**：同一份源码连编两次，签名（`META-INF/CERT.RSA`/`CERT.SF`/`MANIFEST.MF`）、`assets/chaquopy/build.json`、`assets/chaquopy/app.imy` 五项都会变。`app.imy` 里每个 pyc 只有第 8～12 字节（CPython 源文件 mtime 字段）不同，把这段清零后全部逐字节相同。要确认「装上去的就是这一轮构建的包」，解包比对 pyc 比比对哈希可靠。

### 修复（审查报告里的三处小缺陷）

- `desktop/gui.py:_resolve_encoder` 第一行是 `sel = self.hw_combo.currentText()`，把形参整个覆盖掉 —— 传什么进来都没用，永远读下拉框当前值。现在用形参，空串按「未选择」退回软件编码。同时把软件编码分支的返回值从字符串 `"software"` 改成三元组 `("", "", "software")`：`core.convert` 收到 `encoder=None` 会自动探测硬件，只有 `encoder[2] == "software"` 的元组才强制走软件编码；调用点原来还要再补一次 `enc if enc != "software" else (...)` 的隐式转换，两处都不该有这种约定。
- `desktop/core.py` 与 `android/.../insta_core.py` 的 `batch_convert` 里 `base_seq = ... int(start_number)` 没有 try，非整数会抛裸 `ValueError`。GUI 只捕获本项目定义的异常，裸 `ValueError` 表现为未捕获崩溃。现在与 `_build_spec_tasks` 同口径，抛 `ValidationError("start_number 必须为整数: ...")`。
- `desktop/core.py` 与 `android/.../insta_core.py` 的 `batch_convert` 把非硬件的 encoder 三元组一律折成 `None` 再传给 `convert`，而 `convert` 收到 `None` 会调 `detect_hw_encoder()` 自动探测 —— 用户在下拉框里明确选「自动（软件编码）」（三元组 `("", "", "software")`）时，在有 NVENC 的机器上会被静默改成硬件编码。现在原样把三元组传下去，`convert` 按 `encoder[2] == "software"` 判定走软件。
- `desktop/qml/Switch.qml` 的轨道色两个分支都写 `Theme.divider`（等于没有 hover 反馈），滑块写死 `"#FFFFFF"`（暗色主题下刺眼）。`Theme.qml` 新增语义色 `switchThumb`（亮色 `#FFFFFF` / 暗色 `textPrimaryDark`），轨道 hover 改走 `Theme.accentHover` 与 `Theme.sidebarBorder`。

新增 `test_resolve_encoder_returns_tuple_for_software`（形参优先 + 四种取值 + 空串/未知都退回三元组）、`test_batch_convert_rejects_non_integer_start_number`（两端源码都改了 + 真调一次确认抛 `ValidationError` 而不是 `ValueError`）、`test_batch_convert_does_not_override_explicit_software_choice`（桩掉 `convert` 记录它实际收到的 encoder，断言软件选择没被换成 `None`）。回滚验证：形参改回 `self.hw_combo.currentText()` → 红；`int(start_number)` 改回裸写法 → 红；`hw = encoder` 改回 `hw = None` → 红。全套 **117 passed, 2 skipped**。

### 修复（MCRC 按产物自己的 mdat 重算）

真机 GO Ultra 的 VID 在 udta 里有 `MCRC` box（LRV 没有，Ace Pro 2 两轨都没有），body 是三个**小端** u32：`crc32(mdat payload)`、payload 长度、0。实测真机 VID：`crc=0xbabae49c len=20843369`，与它自己 mdat 的 crc32 和长度逐项相等，语义确认。

`udta` 整个是从模板拷过来的，所以 MCRC 里存的一直是**模板那条码流**的校验和。端到端跑一遍就能看出来：产物的 mdat 是 `crc=0x55076e01 len=3239859`，而 MCRC 里还写着模板的 `0xbabae49c / 20843369`。相机目前不校验这个字段，但没理由留一个已知是错的值。

两份 `moov_rewrap` 各加 `udta_with_mcrc(udta, mdat)`：有 MCRC 就按本文件 mdat 重算（`zlib.crc32(payload)` + 长度 + 0），没有就原样返回 —— 不能给 LRV 凭空加一个模板里没有的 box。`rebuild_media` 里包在 `udta_with_audio_frames` 外层。

新增 `test_udta_with_mcrc_recomputes_for_own_mdat`（两份副本各验一遍：错的值必须被改成真的；没有 MCRC 的 udta 必须逐字节不变）。回滚验证：在函数里加一行提前 `return bytes(buf)` → 红。全套 **114 passed, 2 skipped**，真机素材重跑端到端确认产物 `MCRC crc/len` 与自身 mdat 一致。

### 修复（安卓副本补齐 co64，两份 rebuild_stbl 都认 co64）

`android/app/src/main/python/camera_moov_rewrap.py` 是 `shared/instbox/moov_rewrap.py` 的手工同步副本，但只跟了一半：shared 版早就支持 64 位 chunk offset 表（`_MAX_32BIT` / `_chunk_offsets` / `make_box` 的 largesize / `stco_box` 自动切 co64），安卓副本一样都没有。后果是读 co64 模板直接 `KeyError: b'stco'`，写超过 4 GiB 的偏移会静默截断成错位的值 —— 表现为相机能列出条目但打不开。

顺带发现两份的 `rebuild_stbl` 都只认 `b"stco"`：模板里若是 co64，这一块会被原样拷过去，偏移还是模板的，新文件全错位且不报错。现在改成 `if kind in (b"stco", b"co64"):`，写出时由 `stco_box` 按偏移量自动选 32/64 位。

新增 2 条测试：`test_rewrap_copies_read_co64`（**行为测试**：真造一个 co64 box 喂给两份副本的 `_chunk_offsets`，断言读出正确的 64 位偏移；顺带验 32 位 stco 仍能读）与 `test_stco_box_switches_to_co64_above_4gib`。回滚验证：安卓副本的 `if b"co64" in table:` 改成 `if False:` → 红；shared 的 `rebuild_stbl` 改回只认 stco → 红。全套 **113 passed, 2 skipped**，并用真机素材重跑端到端导入确认无回归（产物 GOP 120/10、AMBA 120/10、帧数 179/89）。

**教训**：这一对副本长期漂移的根因是**没有守卫测试**。第一版守卫只 grep 源码字符串，把 `if b"co64" in table:` 改成 `if False:` 仍然全绿 —— 必须真造 box 喂进去才拦得住。

### 修复（序列号定位从「碰巧对」改成有依据）

`extract_inst_meta` 原先靠「inst 里最后一个 `0a 0e` + 14 字节全字母数字」找序列号。逆向报告实测：真机 inst 里裸 `0a 0e` 各出现 **27 次**，严格过滤后只剩 1 个候选 —— 这两份样本上结果是对的，但传感器数据区里只要出现 14 个连续字母数字就会选错。

改成先找强特征 **`0a 0e` + 14B + `12 11` + `Insta360`**（f1 序列号紧接 f2 机型名），全 inst 唯一命中（VID@1453367 / LRV@1467082）；找不到再回退到老的宽松规则，兼顾不带机型名的老固件。桌面端与安卓端同步，新增 `test_extract_inst_meta_prefers_serial_followed_by_model` 守卫两份副本都保留强特征分支且排在回退之前（回滚验证：删掉安卓副本的回退注释即变红）。

### 修复（端到端跑通 GO Ultra 时发现的两处）

真机素材 + 仓库自带的 `desktop/dist/bin/ffmpeg.exe` 跑完整导入链路（转码 → inst 移植 → 索引登记）时暴露两处，桩测试都拦不住：

- **`video_gop` 只接受 `Path`，而调用方传的是 `str`**：`AttributeError` 被 `analyze_native` 的 `except Exception: pass` 吞掉，GOP 永远退化成 0，全项目回退到写死的 16。也就是说前一轮「GOP 跟随模板」的改动在真实链路上**一次都没生效**，只有单测里手写 `Path` 的用例是绿的。现在统一 `Path(path).read_bytes()`，两份副本同步。
- **QSV / AMF 分支没有 `-g`**：只有 nvenc 加了关键帧参数，QSV/AMF 走编码器默认（约 3 秒一个关键帧）。3 秒素材实测只出 1 个关键帧，而 AMBA 里声明 120 —— 相机按声明去找关键帧会失败。现在 `elif "qsv" in vcodec or "amf" in vcodec:` 同样显式给 `-g/-keyint_min/-sc_threshold 0/-bf 0`。

端到端验证（`.e2e/` 下自建假卡 + GO Ultra 真机模板对）：

```
[VID] codec=hevc_qsv -g=120   → keyframes=2  gap=120  AMBA_gop=120  frames=179
[LRV] codec=libx265 -g=<none> → keyframes=9  gap=10   AMBA_gop=10   frames=89
```

与真机模板完全一致（VID 120 / LRV 10）。产物 `inst` 元数据也核对过：f1 序列号 `IBEEA2605QGDFE`、f2 机型 `Insta360 GO Ultra`、f26 proxy 标志 LRV=1 / VID=0，AMBA 时间基 60000/1001 与 30000/1001 均对。

新增 3 条测试（`test_video_gop_accepts_str_path`、`test_analyze_native_reports_gop`、`test_hw_cmd_gives_qsv_and_amf_explicit_gop`），两个缺陷都做了回滚验证确认变红。全套 **110 passed, 2 skipped**。

### 新增（Go Ultra 机型适配）

用户提供了 GO Ultra 真机素材（`VID_20261104_141845_024.mp4` / `LRV_20261104_141845_024.lrv`），逆向比对后发现有四处规格是照着 Ace Pro 2 写死的，GO Ultra 上全部对不上。这不是「参数微调」，是产品在两种机型上行为不同。

真机实测差异：

| 项目 | Ace Pro 2 | GO Ultra |
| --- | --- | --- |
| VID 编码 | HEVC 1080p | HEVC 1080p @59.94 |
| VID 关键帧间隔 | 16 | **120** |
| LRV 编码 | **H.264 (avc1)** | **HEVC (hvc1)** |
| LRV 关键帧间隔 | 16 | **10** |
| AMBA[53] | 16 | 120 / 10 |

四处的修法：

- **AMBA[53] 写死 16 → 从产物量**。偏移 53 是关键帧间隔，相机按它算缩略图抽帧位置。实测两代机型的这个字段都精确等于 stss 里相邻 sync sample 的差（GO Ultra VID `[1,121]`→120、LRV `[1,11,21,…]`→10）。新增 `video_gop(path)` 直接读文件字节解 `moov/trak/mdia/minf/stbl/stss`，不依赖 ffprobe；`camera_udta(..., gop=)` 接受该值，`None` 时自己从模板量，量不出来（0）才退回 16。所有调用点都从**生成产物**量，因为 AMBA 声明的是这条码流的间隔，不是模板的。
- **LRV 编码器写死 libx264/avc1 → 跟随模板**。`_build_spec_tasks` 现在读 `lrv_video.codec` 与 `codec_tag`，handler/encoder 也跟着切换。GO Ultra 的 LRV 编成 HEVC，Ace Pro 2 仍是 H.264，两者互不影响。
- **GOP 参数写死 `-g 16 -keyint_min 16` → 跟随模板**。`analyze_native()` 新增 `gop` 字段（两端都加），`spec_from_template()` 自动带出；`_build_spec_tasks` 把 GOP 放进任务元组第 15 位；`_build_transcode_cmd` / `_build_hw_transcode_cmd` 新增 `gop` 参数，`-x265-params keyint=`、`-g`/`-keyint_min`、nvenc、mediacodec 四处全部改用模板值。任务里 GOP 为 0（老调用方/量不出）时仍退回 16。
- **`_shrink_avc1_entry` 只认 avc1 → 按 tag 选配置盒**。这个函数负责把采样条目的多余子 box（pasp/btrt）去掉，只留解码配置盒，相机才收。原来硬编码 `if tag != b"avc1": return False`，GO Ultra 的 LRV 是 hvc1 所以永远跳过精简，而且不报任何警告。改为 avc1→保留 avcC、hvc1/hev1→保留 hvcC，其余不动。

顺带确认了一处**不是缺陷**的：GO Ultra 的 LRV 与 VID 的 `nail` box 完全相同（688144 B = 896×512×1.5 裸 YUV420），说明两代机型共用同一张缩略图规格，`camera_udta` 里的 `nail_size != 688144` 校验对 GO Ultra 也成立。

### 修复（模板误选：桌面端补齐、两端统一）

`c6bbf01` 那次修的「上一轮产物被当成真机模板」只修了安卓端 —— 桌面端仍然走
`find_native_template()` 的「字典序第一个带 inst meta 的 VID_」。桌面端把产物
写回卡上同一个 `DCIM/Camera01` 之后，用户再导入第二段就会踩同一个坑，症状一样
是「相机不认」且不报错。

- 桌面端补 `template_from_names(card_root, vid_name, lrv_name)`，与安卓端逐行一致，
  并有 AST 守卫测试防漂移。
- `import_with_inst(..., template_names=)` 两端都支持：调用方指定了样本对就不再猜。
- 桌面端 GUI 真正接上了：`_analyze_spec` 记下用户选的那一对（`sp["__pair__"]`），
  `_run_all` 先试 `template_from_names` 再退回 `find_native_template`。原先
  `_run_all` 无条件调 `find_native_template`，而 `import_with_inst` 里 `template`
  优先于 `template_names` —— 用户选的样本对等于完全没生效。
- 新增 `test_import_with_inst_actually_uses_template_names` 做**行为**验证。
  第一版只 grep 源码字符串，把 `if template is None and template_names:` 改成
  `if False and template_names:` 仍然全绿，等于没测；改成真调一次、断言
  `template_from_names` 收到的参数后才拦住。

### 修复（安卓端跟齐桌面端的四处硬化）

审查报告指出四处「桌面端改了、安卓端忘了跟」，全部是安卓落后：

- `save_job`：安卓端 `except OSError: pass` 静默吞掉写失败，断点续跑进度丢了用户
  无感知。改成向上抛，与桌面端一致。
- `has_inst_box`：安卓端留着 `data = open(path,"rb").read(64)` —— 读了不用且句柄
  不关，`verify_card` 每条索引条目调一次，卡大时句柄累积。删除。
- `render_cover`：安卓端缺全部硬化（无参数校验、无 cancel、无 timeout、
  `find_ffmpeg()` 不判 None 直接当 argv[0]）。无 ffmpeg 时报 `TypeError` 而不是
  「未找到 ffmpeg」；`check=True` 的 `CalledProcessError` 裸冒泡。补齐，并让桌面端
  也加上同一处 `cancel.is_set()` 早退，两端实现逐行一致。
- `convert` 并发驱动：安卓端 `except BaseException: pass` 会吞掉构建命令行/探测
  时长阶段抛的异常，`convert()` 返回 `(None, None)` 而用户看不到报错 —— 即「失败
  报成成功」。与桌面端一样兜底记 `first_error`。

新增 `test_android_core_matches_desktop_on_hardened_helpers` 用 AST 比对这四个函数，
方向明确：桌面端是基准，安卓端跟齐。

### 修复（QML 版两处数据风险）

审查报告里的两个 BLOCKER，都是「只有 QML 版会踩」的：

- **转换中关窗不拦**。worker 是 `daemon=True`，进程退出时被直接丢弃，ffmpeg
  变成孤儿进程继续往卡里写，`set_awake(False)` 永不执行（防休眠锁残留），卡上
  留半截 VID/LRV 且索引没登记。经典版 `gui.py` 的 `closeEvent` 早就修过这条路，
  QML 版从建立起就没有。现在 worker 改 `daemon=False`，`Bridge` 新增
  `waitWorker(timeout_ms)`，`main.qml` 加 `onClosing` 弹「停止并退出 / 继续转换」，
  选前者时先 `bridge.cancel()` 再等 worker 收尾才 `Qt.quit()`。
- **路径用 `replace("file:///", "")` 还原**。`toString()` 默认 PrettyDecoded，会把
  `#` `%` `[` `]` `^` `` ` `` `{` `}` 这些在 Windows 上完全合法的字符转成 `%XX`，
  替换完路径就不存在；UNC 路径 `file://server/share/a.mp4` 只有两个斜杠，连前缀
  都剥不掉，网络共享 100% 不可用。新增 `@Slot(QUrl, result=str) localPath(url)`
  走 `url.toLocalFile()`，`main.qml` 四处对话框全部改用它。

新增 `desktop/tests/test_qml_bridge.py`（15 条）：11 个合法字符逐个往返、UNC、
worker 非 daemon、`waitWorker` 的两态、以及一条源码守卫（`replace("file:///")`
再出现、`onClosing` 消失都算回归）。

### 修复（逆向报告指出的四处机型硬编码）

拿到 GO Ultra 的完整 inst 结构分析后，又发现四处「照着 Ace Pro 2 写死」的地方。
前三处是真机必炸，第四处是元数据与真机不一致：

- **`visual_entry` 遍历 moov 子 box 时没过滤类型**。moov 的子 box 不只有 `trak`，
  真机两个文件的第一个子 box 都是 `mvhd`，直接对它调 `direct_child(mdia)` 抛
  `ValueError: invalid child MP4 box`。`shared/instbox/moov_rewrap.py` 与
  `android/app/src/main/python/camera_moov_rewrap.py` 各有一份，都改。
- **`filter_avc1_children` 硬编码 `{b"avcC"}`**。函数名里的 avc1 只是历史原因，
  HEVC 条目（`hvc1`/`hev1`）的配置盒叫 `hvcC`，照 avcC 过滤会把 `hvcC` 删光，
  entry 从 231 字节掉到 86 字节空壳。两种 entry 的固定头都是 86 字节，偏移不用改，
  只需按 entry tag 换配置盒名。
- **`--proxy-hevc` 只是诊断开关，不从模板读**。GO Ultra 的 LRV 本身是 HEVC，
  不显式加这个开关就强制要求 LRV=h264，产出的条目相机不认。现在
  `video_profile()` 返回里带 `codec`，`proxy_hevc` 由「显式开关 or 模板是 hevc」
  推导，三处调用点全部改用这个局部变量。
- **代理轨元数据过度改写**。真机 LRV 的 inst 元数据里 f19/f20/f44 与主视频
  **完全相同**（1920x1080 / 60fps），只有 f26.f2 标出 proxy；容器层的
  tkhd/stsd 才是 1280x720，两者不矛盾。原实现给 proxy 硬写 1280x720/30，
  和真机对不上。现在 `tailor_metadata` 只在非 proxy 时写 f19/f20，代理轨
  跟着模板走。

- **CLI 路径的 `-g` 仍写死 16**。`inst_transplant.py` 自己的命令行入口
  （`python inst_transplant.py ...`）与 `run_ffmpeg` 里的 NVENC/libx264 分支
  一共四处 `"-g", "16"`，而 `core.py` 主路径早已按模板 GOP 生成。现在
  `run_ffmpeg` 新增 `gop` 参数，两个 CLI 调用点分别传
  `video_gop(template_main) or 16` 与 `video_gop(template_proxy) or 16`，
  软件重试的递归调用也带上。

新增 5 条回归测试：`test_visual_entry_skips_non_trak_children`（mvhd 在前）、
`test_filter_avc1_children_keeps_hvcc_on_hevc`、`test_tailor_metadata_leaves_proxy_dimensions_alone`、
`test_video_profile_carries_codec`、`test_rewrap_and_transplant_copies_do_not_drift`
（AST 比对两份副本，这条守的是「moov_rewrap ↔ camera_moov_rewrap 曾漂移四处、
漂了整整一个发布周期没被发现」）、`test_cli_run_ffmpeg_uses_template_gop`
（桩掉 `subprocess.run` 与 `_tool`，断言真实命令里 `-g 120`）。全部做了回滚验证，
逐个确认缺陷版本会变红 —— 其中 CLI 那条第一次只回滚了四处中的一处，
测试仍然全绿，把四处全部还原后才变红，说明「只改一个分支」的缺陷必须整段回滚才能验证。

### 测试（Go Ultra 机型适配）

新增 11 条，全部用合成 MP4 覆盖，不需要真机素材也能守住：

- `test_video_gop_reads_keyframe_interval` —— 合成 stss，VID 型（[1,121]）得 120、LRV 型（[1,11,21,31]）得 10。
- `test_video_gop_returns_zero_for_single_keyframe` —— 单关键帧无从得知间隔，返回 0 让调用方回退。
- `test_video_gop_returns_one_without_stss` —— 无 stss = 全 I 帧，GOP 是 1。
- `test_camera_udta_writes_real_gop_into_amba` —— 传 gop=120 必须原样写进 AMBA[53]。
- `test_camera_udta_falls_back_to_16_when_gop_unknown` —— gop 为 0/None 时退回 16，老行为不坏。
- `test_spec_tasks_follow_template_lrv_codec_for_go_ultra` —— GO Ultra 模板下 LRV 的 vc/tag/handler 三者一致，不留 avc1。
- `test_spec_tasks_keep_ace_pro_2_lrv_as_h264` —— Ace Pro 2 模板下仍是 libx264/avc1。
- `test_spec_tasks_carry_template_gop` —— VID 任务带 120、LRV 任务带 10。
- `test_convert_passes_template_gop_into_ffmpeg_args` —— 端到端：桩掉 `_run_ffmpeg` 后检查真实命令里出现 `keyint=120` 与 `keyint=10`。
- `test_shrink_entry_strips_extras_from_hvc1` / `test_shrink_entry_strips_extras_from_avc1` —— hvc1 精简后只留 hvcC、avc1 只留 avcC，tag 不变。

五处缺陷逐一做了回滚验证（改回缺陷版本 → 对应测试变红 → 恢复后全绿），每个缺陷恰好被一条测试拦住。其中「GOP 不进命令」这一处第一版没被拦住 —— `_build_spec_tasks` 的任务元组里带着 GOP，但 `_run_one` 把 keyint 写死时，只看任务元组的测试照样通过；补了端到端那条才拦住。

全套 `80 passed, 2 skipped`。

### 修复（代码审查发现的镜像污染与几处静默失败）

对本轮待合并的导入操作卡与取消链路做了一次审查，发现一个会让产物「相机不认」的缺陷，以及若干「不报错但结果不对」的问题。

- **镜像目录不清空，上一轮的产物会被当成真机模板**（最严重）。安卓端把卡结构镜像到 `cacheDir/job/card`，转码产物也直接写进镜像的 `DCIM/Camera01`，与真机原片同目录；`CardMirror.build()` 只 `mkdirs()` + 拷贝，从不删旧文件，`jobDir` 全程没有任何清理代码。上一轮产物自带 inst box（正是上一轮自己移植进去的），完全符合 `find_native_template` 的挑选条件「字典序第一个带 inst meta 的 VID_」。只要它的文件名排在真机原片之前，就会被当成模板 —— moov 骨架、帧率、分辨率、音频参数全部来自上一轮产物，产出的东西相机不认，且不抛任何异常、不写任何错误日志，只在用户手里表现为「导进去相机看不见」。错误还会逐轮累积。已用脚本复现：镜像里放 `VID_20240101_090000_000.mp4`（真机）与 `VID_20230101_080000_000.mp4`（上一轮产物）时，`sorted(vids)[0]` 取到的是后者。修法双保险：`CardMirror.build()` 开头 `root.deleteRecursively()` 并校验确实清空（删不掉就返回 false，脏镜像比直接报错难查得多）；同时 Kotlin 把「从卡上拷过来的是哪两个文件」显式传给 Python，核心不再猜。
- **`template_from_names()` 新增**：按指定文件名取模板对，两个文件都存在、`VID_`/`LRV_` 去掉扩展名后主名一致、主文件带 inst box，三者缺一即返回 `None`。`android_bridge.run_import(..., template_names=...)` 与 `PythonEngine.runImport(..., templateNames=...)` 一路透传；取不到模板对时直接返回 `{"ok": false, "error": "模板对不可用：…"}`，不硬着头皮跑。
- **`writeBack` 把部分失败吞掉**：产物缺失时 `continue` 静默跳过，用户看到「全部完成」但卡上少文件；`writeDocument` 返回 `readableSize()`，而刚写完的文件在部分 provider 上读不到 SIZE 列，会把成功报成「写入失败」。改为 `writeDocument` 返回 `Boolean`，大小核对交给新增的 `verifySize()`，并区分「产物缺失 / 写入失败 / 大小不符」三种错误文案。
- **`scanCard()` 在主线程做 SAF IO 与 protobuf 解析**：`DocumentFile.fromTreeUri` / `listFiles()` 每次都要走 ContentResolver 往返，索引整块读进来解析。卡里几百个文件时足以触发 ANR，而且同步执行时 `scanning` 根本来不及渲染。拆成 `scanCard()`（suspend，写状态）+ `readCard()`（IO 线程，只读不写），并加 `try/finally` 保证任何情况下都退出「扫描中」。
- **`cancelEventSet()` 改成三态显式**：原写法 `try { ev?.callAttr("set"); ev != null } catch { false }` 三态恰好都对，但读起来像 bug，改成先判空再 try。
- **回调异常不再完全静默**：`_safe_call` / `_safe_log` 原来 `except Exception: pass`，Kotlin 侧抛异常时表现为「进度条卡在某个值 + 日志一片空白」，现场无法判断是编码慢还是桥接坏了。改为写一行到 `import.log`。
- **`android_bridge.py` 重复 import**：`threading` / `json` 在顶部已导入，第 188 行附近又导了一遍；`re` 与 `urllib.request` 是新增的却留在函数体里。统一提到顶部。
- **死代码清理**：`ImportCallback.lastLogAt`（只有声明与赋值，无任何读取）、`PythonEngine.statusVerbose()`（带 `@Suppress("unused")`，与 `status()` 重复，无调用）删除。
- **`ImportCardState` 推导抽成纯函数 `cardStateFor()`**：五态优先级从 `instatoolsApp` 的内联 `when` 移到可测的位置。

### 测试（镜像污染 / 模板固定 / 卡片状态）

新增 `desktop/tests/test_template_pick.py`（4 条）与 `desktop/tests/test_bridge_cancel.py` 的 3 条模板相关用例，以及 `android/app/src/test/java/com/duofreedom/instaace/ui/ImportCardStateTest.kt`（6 条 JUnit，纯逻辑无需设备）。

- `test_find_native_template_picks_stale_product_when_name_sorts_first` —— 记录危险行为本身。看着像「在测 bug」，但它守的是前提：一旦 `find_native_template` 改成别的挑选规则，这条会失败，提醒重新评估安卓侧是否还需要显式传模板名。
- `test_template_from_names_ignores_sort_order` / `test_template_from_names_rejects_missing_pair` / `test_template_from_names_rejects_file_without_inst_meta` —— 显式传名时必须拿到指定的那一对；只存在一半、主名不一致、或没有 inst box 时必须返回 `None`。
- `test_run_import_passes_template_names_into_core` / `test_run_import_without_template_names_lets_core_decide` / `test_run_import_rejects_unusable_template_pair` —— 桥接层三个方向：传了要用上、没传保持旧行为、取不到要失败。
- `ImportCardStateTest` 六条覆盖五态优先级：「导入中」压过一切（取消时不能跳回可点）、空队列优先于未选卡、「已取消」不算失败。

回滚验证：忽略 `template_names` → 2 条红；不把 `template` 传给 `import_with_inst` → 1 条红；模板对取不到时继续跑 → 1 条红；`cardStateFor` 里把 `queueEmpty` 提到 `running` 之前 → `runningWinsOverEverything` 红。恢复后全绿。

写测试时暴露出一处真实遗漏：`template_from_names` 最初只检查两个文件是否存在，不检查它们是不是一对。`test_template_from_names_rejects_missing_pair` 立刻抓到 —— `VID_20240101_090000_000.mp4` 与 `LRV_20230101_080000_000.lrv` 这种拼凑对会被接受。已补上主名一致性校验（比到扩展名前，因为两者扩展名本来就不同）。

全套 **68 passed, 2 skipped**（此前 61 passed）；Android `:app:testReleaseUnitTest` → IndexTest 7 skipped / ConsentLogicTest 5 passed / ImportCardStateTest 6 passed，零失败。

### 新增（安卓端导入操作卡）

导入页底部原来是一段内联布局：进度行、进度条、日志、明细卡、开始/取消按钮堆在一个 `Column` 里，五种数据状态全靠 `if/else` 散在 JSX 式条件里，按下反馈用的是 Material 默认 ripple（tween）。

抽成 `ImportActionCard`（`ui/ImportActionCard.kt`），六个状态各自有明确分支：

- **empty**：队列为空，主按钮显示「先添加视频」并禁用。占位大图标仍由列表区的 `EmptyState` 负责，卡片内不重复同一句话。
- **disabled**：有视频但没选存储卡，按钮显示「请先选择存储卡」。
- **ready**：可开始，按钮显示「开始导入」。
- **loading**：阶段文字 + 弹簧补间的进度条 + 实时日志，按钮变成「取消导入」，取消中显示「正在取消…」并禁用。
- **error**：卡片底色切 `errorContainer`，顶部出现错误文案区，按钮变成「重新导入」（`error` 底色）。
- **pressed**：`Animatable` 驱动 `graphicsLayer` 缩放 0.96，松手弹回，不走 tween。

动效按设计稿要求用 `spring(dampingRatio = 0.75f, stiffness = 400f)`（位移/缩放）与 `spring(dampingRatio = 1f, stiffness = 500f)`（透明度/颜色），与项目 `theme/Motion.kt` 的 Expressive 令牌（0.8/380 与 1.0/1600）不同——差异只在本组件内，全局令牌未动。进度条用 effects 弹簧而非 spatial，因为 spatial 的过冲会把进度顶过 100%。

错峰入场：`StaggeredIn` 按 index 延后 40ms 再打开 `AnimatedVisibility`，而不是给 tween 加 `delayMillis`——后者是固定时长动画，与「全部走弹簧」的约束冲突。

顺带清掉 `instatoolsApp.kt` 里因此不再使用的 4 个 import（`Icons.Rounded.Close`、`Icons.Rounded.PlayArrow`、`Button`、`LinearProgressIndicator`）。

验证：`:app:compileReleaseKotlin` 零 Kotlin 警告；`:app:assembleRelease` BUILD SUCCESSFUL，APK 75,272,122 B；`:app:testReleaseUnitTest` IndexTest 7 skipped / ConsentLogicTest 5 passed。

### 新增（README 重写）

按「陌生人 5 分钟跑通」的目标重写根目录 `README.md`：首屏只留项目名、一句话定位、5 个同风格徽章和一条最小命令；章节顺序改为 安装 → 快速开始 → 配置 → 常见问题 → 贡献 → 许可证，架构与设计说明折进文末 `<details>`。

内容全部来自仓库实际状态，新增的部分是之前 README 缺的：ffmpeg 的五级查找顺序表、命令行三个位置参数的默认值表、安卓设置页两个开关的说明、以及 5 个真实报错的排查步骤（未找到 ffmpeg、目标不是相机卡、卡里没有真机模板、缓存空间不足、Gradle 插件找不到）。演示图位置标注为 TODO——仓库里确实没有演示素材，不编造。

### 新增（安卓端导入取消）

桌面端早就有取消，安卓端一直没有：导入一旦开始，用户只能等整个队列跑完，或者杀掉 App —— 后者会留下半截暂存文件和一个还在跑的 ffmpeg 子进程。补齐三层：

- **Python 桥（`android_bridge.py`）**：新增 `new_cancel_event()` 返回一个真正的 `threading.Event`，Kotlin 以 `PyObject` 持有它并回传给 `run_import(..., cancel=...)`；`run_import` 再把事件透传给 `insta_core.import_with_inst`。取消令牌的生命周期由 Kotlin 的引用决定，不需要跨 JNI 的登记表。
- **返回契约**：取消与失败在 JSON 上分开——取消返回 `{"ok": false, "canceled": true}`，失败返回 `{"ok": false, "canceled": false}`。此前两者都只有一个 `error` 字符串，Kotlin 无法区分「用户主动停」和「出错了」。
- **Kotlin（`PythonEngine` / `AppState` / `instatoolsApp`）**：`PythonEngine.newCancelEvent()` / `cancelEventSet()`；`AppState.cancelImport()` 只置位事件、不阻塞，可从 UI 线程直接调用；队列循环在每条开始前检查取消标志，当前条被中断则不记入结果；导入中按钮换成「取消导入」，取消后显示「正在取消…」并在收尾时清空事件。
- **取消时的写回语义**：已经转好的条目是完整产物，照常写回卡；正在转的那条只留在镜像目录里，不会写回。取消后状态显示「已取消（已完成的 N 条已写回卡）」，而不是笼统的「部分完成」。

### 测试（安卓取消链路）

新增 `desktop/tests/test_bridge_cancel.py`，6 条，全部离线（不依赖 ffmpeg / 相机 / Android），都做过回滚验证：

- `test_new_cancel_event_is_a_threading_event`
- `test_run_import_passes_cancel_into_core` —— 事件必须原样传到 `import_with_inst`，否则取消按钮是装饰品。
- `test_run_import_without_cancel_passes_none` —— 旧调用点不传 cancel 时必须继续可用，不能凭空造事件。
- `test_run_import_reports_canceled_separately_from_failure` / `test_run_import_failure_is_not_marked_canceled` —— 两个方向都验：取消不能报成失败，失败也不能报成取消。
- `test_cancel_event_set_by_other_thread_is_visible` —— Kotlin 在 UI 线程置位、Python 在 IO 线程读取，验证跨线程可见。

回滚验证结果：不传 cancel 进 core → 2 条红；取消走通用失败分支 → 1 条红；成功分支不写 `canceled` 字段 → 1 条红。全套 **61 passed, 2 skipped**（此前 55 passed）。

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

- 安卓 release APK（含审查修复）：约 75,276,100 B（实测 75,276,100～75,276,114 之间浮动，见下）。核对内容同下，另确认
  `template_from_names` 在 `insta_core` 模块函数表中、`run_import` 的 `co_varnames`
  含 `template_names`、`_swallow` 在 `android_bridge` 模块 `co_names` 中；
  `javap` 确认 `PythonEngine.runImport(..., kotlin.Pair<String,String>)`、
  `SafeCard.writeDocument` 返回 `boolean`、`SafeCard.verifySize` 返回 `long`、
  `AppState.scanCard` 带 `Continuation` 参数（suspend）、`ImportActionCardKt.cardStateFor`
  为 `(boolean, boolean, boolean, String) -> ImportCardState`。
  `:app:testReleaseUnitTest` → IndexTest 7 skipped / ConsentLogicTest 5 passed / ImportCardStateTest 6 passed。
- **构建不可复现的实测结论（更正此前的说法）**：此前记录为「哈希不稳定、字节数稳定」，连编五次后发现字节数也在浮动（75,276,100 / 75,276,106 / 75,276,108 / 75,276,109 / 75,276,114）。逐条比对两次构建的产物，差异只有 5 个条目：`META-INF/CERT.RSA`、`META-INF/CERT.SF`、`META-INF/MANIFEST.MF`（签名，因为摘要变了）、`assets/chaquopy/build.json`（里面 `app.imy` 的摘要）、`assets/chaquopy/app.imy`。把 `app.imy` 里的 pyc 逐个比对，**每个文件只有第 8～12 字节不同**——那是 CPython 的源文件 mtime 字段；把这段清零后六个条目全部逐字节相同。所以：源码与字节码本身是可复现的，浮动来自 pyc 头部的时间戳，以及它带来的 zip 压缩长度变化和签名重算。**结论：这个 APK 的字节数与 sha256 都不能当校验和，只能用来确认「大概是不是这一轮」；要真正核对代码，得解包 `app.imy` 比对 pyc（清零 mtime 后应当逐字节相同）。**
- 上一轮安卓 release APK（含取消链路）：75,263,215 B。
  解包 `assets/chaquopy/app.imy` 核对字节码：`new_cancel_event` 在模块 `co_names` 中，
  `run_import` 的 `co_varnames` 含 `cancel`，其字典键常量含 `canceled`；
  `javap` 核对 `PythonEngine.runImport(..., PyObject)` / `newCancelEvent` / `cancelEventSet`
  与 `AppState.cancelImport()`（含 `Dispatchers.getIO` 调用）均已生成。
  `:app:testReleaseUnitTest` → IndexTest 7 skipped / ConsentLogicTest 5 passed。
- 桌面两个可执行文件此前都打包着旧 `core.py`（11-08 构建），已重建：
  `instatools.exe` 78,828,822 B / sha256 `2705143e589ee60029c136d6b4319eab033cad5451872c2e18eca7ecccaf55d7`；
  `instatoolsImporter.exe` 39,072,517 B / sha256 `d94aa3f60a7bf65b83ad40b4582ba20f55c55df8ada4c25bab03c332da16aede`。
  从两者内嵌的 `PYZ.pyz` 取出 `core` 模块核对：`convert` 有 `canceled`、`batch_convert` 有 `success`/`failed`、`_source_stamp` 存在。
  `instatools.exe --self-test` → `QML_OK roots=1`，exit 0。
- `docs/BUILD.md` 的实测产物同步更新，并记下「同一源码两次构建哈希不同、字节数稳定」，提醒不要把哈希当校验和。

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
- `desktop/dist/instatools.exe --self-test` → `QML_OK roots=1`，exit 0。

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
- **QML spec 补图标**：`instatools.spec:57` 补 `icon=['assets/app.ico']`。
- **相机卡判断降级留痕**：勾了「登记索引」但输出目录不是相机卡结构时，原先静默降级为纯转码；现在写日志并提示「改为仅转码」（`bridge.py:274-281`）。
- **更新检查不再吞异常**：`updater.py:105` 从裸 `pass` 改为写 `import.log`。

#### P2（文档与可移植性）

- **去掉写死的本机路径**：`android/app/build.gradle.kts` 的 `buildPython("D:/android-build/py311/python.exe")` 改为 `chaquopyPython()`，依次读环境变量 `CHAQUOPY_PYTHON`、`local.properties` 的 `chaquopy.python`，都没有则交给 Chaquopy 自探测。
- **文档重写**：根 `README.md`、`desktop/README.md`、`docs/BUILD.md` 按真实仓库层级重写（补 `main.py`/`bridge.py`/`updater.py`/`qml/` 两套界面说明、纠正「三个模块字节级一致」的错误表述、仓库名 `Insta-camara-tools` → `Insta-camera-tools`、Python 版本统一为 3.10+、产物哈希不再写死）。

### 第二轮补充（同日，具备完整构建环境后）

- **APK 已重打**：`versionCode 14 / versionName 1.2.0`，双 ABI，72,830,835 B。产物内设备序列号与第三方产品名均 0 命中（含 `assets/chaquopy` 下 5 个 `.pyc`）。
- **QML 版已实际打包**：`instatools.exe --self-test` 输出 `QML_OK roots=1`、退出码 0，产物 205 MB。
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

影石相机工具（原名 instatools Importer）正式发布。把普通视频转成影石
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
  `%LOCALAPPDATA%\instatoolsImporter\jobs\<dest>.json`；同一输出目录再次开跑时
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
