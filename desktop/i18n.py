"""界面文案的中英双语文案表。

键是中文原文，值是英文译文。查不到的键原样返回中文：漏译时界面显示中文，
既不崩也不会露出内部键名，可以增量补齐。

语言在进程内只判定一次（系统界面语言不会在程序运行期间改变），判定顺序：
环境变量 INSTA_LANG > Windows 用户界面语言 > Qt 的 QLocale > 英文。
"""

from __future__ import annotations

import os
import re

ZH = "zh"
EN = "en"

_PRODUCT_EN = "instatools"
_PRODUCT_ZH = "影石相机工具"

_cache: str | None = None


def _windows_ui_language() -> str:
    """Windows 用户界面语言的两位代码；拿不到返回空串。

    这里不用 locale.getdefaultlocale()：它读的是进程的 C locale，中文系统上
    照样可能返回 en_US，判断不了用户实际看到的界面语言。
    """
    if os.name != "nt":
        return ""
    try:
        import ctypes

        langid = int(ctypes.windll.kernel32.GetUserDefaultUILanguage())
    except Exception:  # noqa: BLE001
        return ""
    primary = langid & 0x3FF          # LANGID 低 10 位是主语言 ID
    return ZH if primary == 0x04 else EN   # 0x04 = LANG_CHINESE


def _qt_language() -> str:
    try:
        from PySide6.QtCore import QLocale

        name = QLocale.system().name().lower()
    except Exception:  # noqa: BLE001
        return ""
    return ZH if name.startswith("zh") else EN


def detect() -> str:
    env = (os.environ.get("INSTA_LANG") or "").strip().lower()
    if env in (ZH, EN):
        return env
    got = _windows_ui_language()
    if got:
        return got
    return _qt_language() or EN


def lang() -> str:
    global _cache
    if _cache is None:
        _cache = detect()
    return _cache


def set_lang(value: str) -> None:
    """测试与命令行参数用。传空串或非法值恢复自动探测。"""
    global _cache
    _cache = value if value in (ZH, EN) else None


def app_name() -> str:
    """产品名。英文全小写 instatools，中文是影石相机工具。"""
    return _PRODUCT_ZH if lang() == ZH else _PRODUCT_EN


_TEMPLATES: list[tuple[re.Pattern[str], str]] | None = None


def _templates() -> list[tuple[re.Pattern[str], str]]:
    """把带 %s/%d 的键编译成整串匹配的正则，供已套过参数的文案反查。

    核心层会先格式化再交给界面（log 直接接在状态栏上），到这儿时中文模板里的
    %s 早被替换成具体值了，按原键查必然落空。这里用惰性通配把它们对回来。
    """
    global _TEMPLATES
    if _TEMPLATES is None:
        built: list[tuple[re.Pattern[str], str]] = []
        #   长的键先匹配：泛用短模板会抢走长句。典型反例是
        #   "完成：成功 %d" 排在 "完成：成功 %d，失败 %d" 前面时，
        #   "完成：成功 3，失败 1" 会被对成 "Done: 3，失败 1 succeeded"。
        for key in sorted(EN_TEXT, key=len, reverse=True):
            value = EN_TEXT[key]
            if "%" not in key:
                continue
            parts = re.split(r"%[sd]", key)
            pattern = re.compile("(.+?)".join(re.escape(p) for p in parts), re.DOTALL)
            built.append((pattern, value))
        _TEMPLATES = built
    return _TEMPLATES


def t(text: str, _depth: int = 0) -> str:
    if not text or lang() == ZH:
        return text
    hit = EN_TEXT.get(text)
    if hit is not None:
        return hit
    if _depth >= 3:            # 防循环：模板里套模板
        return text
    for pattern, value in _templates():
        m = pattern.fullmatch(text)
        if m is None:
            continue
        rest = list(m.groups())

        def take(_m: re.Match[str]) -> str:
            #   被插进来的往往又是一条中文消息（"转换失败：源文件不存在"），
            #   递归再查一次，否则英文界面里会夹着中文尾巴。
            return t(rest.pop(0), _depth + 1) if rest else ""

        return re.sub(r"%[sd]", take, value)
    return text



#   英文文案。占位符沿用中文原文里的 %s / %d / %1 顺序，调用方不用区分语言。
EN_TEXT: dict[str, str] = {
    # ---------- 产品名与通用 ----------
    "影石相机工具": _PRODUCT_EN,
    "就绪。添加视频后点击「开始转换」。": "Ready. Add videos, then click Start.",
    "剩余 --:--": "ETA --:--",
    "剩余 %s": "%s left",
    "正在转换": "Converting",
    "正在转换…": "Converting…",
    "准备中…": "Preparing…",
    "完成": "Done",
    "进度": "Progress",
    "操作": "Actions",
    "知道了": "Got it",
    "取消转换": "Cancel",
    "开始转换": "Start",
    "输出与选项": "Output & options",
    "相机样本": "Camera sample",
    "导入文件": "Import files",
    "输出选项": "Output options",
    "待转换视频": "Videos to convert",
    "添加视频": "Add videos",
    "添加文件夹": "Add folder",
    "清空": "Clear",
    "重试": "Retry",
    "正在读取…": "Loading…",
    "出错了": "Something went wrong",
    "暂无待转换视频": "No videos yet",
    "浏览": "Browse",
    " 个": " files",
    # ---------- 错误态（界面占位） ----------
    "无法访问所选文件，请检查路径是否存在。":
        "Cannot access the selected files. Check that the paths still exist.",
    "转换失败：无法访问输出目录，请检查路径权限。":
        "Conversion failed: cannot write to the output folder. Check its permissions.",
    # ---------- 文件对话框 ----------
    "选择原生录制视频": "Select a camera-recorded video",
    "视频文件 (*.mp4 *.mov *.lrv *.insv *.ins)":
        "Video files (*.mp4 *.mov *.lrv *.insv *.ins)",
    "选择视频": "Select videos",
    "视频文件 (*.mp4 *.mov *.mkv *.avi *.ts *.flv *.wmv *.m4v)":
        "Video files (*.mp4 *.mov *.mkv *.avi *.ts *.flv *.wmv *.m4v)",
    "选择包含视频的文件夹": "Select a folder containing videos",
    "选择输出目录": "Select the output folder",
    "选择封面图片": "Select a cover image",
    "图片 (*.png *.jpg *.jpeg *.bmp *.webp)":
        "Images (*.png *.jpg *.jpeg *.bmp *.webp)",
    # ---------- ffmpeg 横幅 ----------
    "正在下载 ffmpeg… ": "Downloading ffmpeg… ",
    "未找到 ffmpeg。它是转码必需组件，先选一个安装位置。":
        "ffmpeg is required for transcoding and was not found. Pick where to install it.",
    "装到系统目录：所有程序都能用，需要管理员权限；装到程序目录：只给本程序用，不需要任何权限。":
        "System folder: usable by every app, needs administrator rights. "
        "Program folder: only this app, no extra permission needed.",
    "下载中…": "Downloading…",
    "装到系统目录": "Install system-wide",
    "装到程序目录": "Install for this app",
    "正在下载 ffmpeg，请稍候…": "Downloading ffmpeg, please wait…",
    "ffmpeg 安装完成，可开始转换": "ffmpeg is ready. You can start converting.",
    "ffmpeg 安装失败：%s": "ffmpeg installation failed: %s",
    "ffmpeg 不可用：%s": "ffmpeg is unavailable: %s",
    "已使用系统已安装的 ffmpeg：%s": "Using the ffmpeg already installed on this system: %s",
    # ---------- 相机样本 ----------
    "未设置样本（回退到影石默认结构）":
        "No sample set (falling back to the built-in Insta360 layout)",
    "样本：": "Sample: ",
    "相机样本 · 读取存储卡原生录制视频":
        "Camera sample · read a native recording from the card",
    "请插入存有原生录制视频的存储卡，程序将分析其编码、分辨率、帧率与音频轨结构，据此生成新文件。":
        "Insert the card that holds a camera-recorded video. Its codec, resolution, "
        "frame rate and audio layout are analysed and reused for the files being generated.",
    "自动从存储卡分析": "Analyse the card automatically",
    "正在扫描存储卡…": "Scanning the card…",
    "正在分析样本结构…": "Analysing the sample structure…",
    "样本文件不存在": "The sample file does not exist",
    "样本分析失败：%s": "Sample analysis failed: %s",
    "样本已读取：%sx%s @%s": "Sample read: %sx%s @%s",
    "未在存储卡中自动找到原生录制视频。请确认已插入存有原生录制视频的 SD 卡，再点「选择原生录制视频」手动指定。":
        "No camera-recorded video was found on the card automatically. Make sure the SD card "
        "is inserted, then use “Select a camera-recorded video” to pick one by hand.",
    "主视频: %sx%s @%s %s lvl%s": "Main video: %sx%s @%s %s lvl%s",
    "预览: %sx%s @%s %s": "Preview: %sx%s @%s %s",
    "色域: %s": "Colour: %s",
    "音频 %d 轨": "%d audio track(s)",
    # ---------- 硬件编码器 ----------
    "正在检测硬件编码器…": "Detecting hardware encoders…",
    "未检测到": "none found",
    "未检测到可用硬件编码器": "No usable hardware encoder found",
    "未检测到可用硬件编码器，将使用软件编码":
        "No usable hardware encoder found. Software encoding will be used.",
    "已检测到 ": "Detected ",
    "，可选它加快约 1.5～2 倍（默认仍用软件，与相机已验证的路径一致）":
        " — choosing it is roughly 1.5–2× faster (software stays the default, "
        "which is the path already verified on the camera).",
    # ---------- 输出选项 ----------
    "机型": "Camera model",
    "选机型后按预设参数生成；选「自动」时若有原片仍优先用原片":
        "Generation follows the preset of the selected model; with Automatic, "
        "a native recording on the card still wins when one is found.",
    "自动（从卡里原片量出）": "Automatic (measured from the card)",
    "输出目录": "Output folder",
    "建议存储卡 DCIM\\Camera01": "Card's DCIM\\Camera01 recommended",
    "定位 SD 卡": "Locate the SD card",
    "校验索引": "Verify index",
    "检查卡内索引与文件是否一致。相册里有条目却打不开，通常是索引登记了坏条目。":
        "Checks that the card's index matches the files on it. Entries that show up "
        "in the album but will not open usually mean a broken index record.",
    "登记相机索引": "Register in the camera index",
    "自动接续序号": "Continue the sequence automatically",
    "编码器": "Encoder",
    "自动": "Automatic",
    "软件 (CPU)": "Software (CPU)",
    "视频封面": "Video cover",
    "恢复自动": "Back to automatic",
    "封": "C",
    "从 000 开始": "Starting at 000",
    "自动续接，下一序号 %03d": "Auto-continue, next number %03d",
    # ---------- 操作区 ----------
    "只跑未完成": "Only unfinished",
    "全部重跑": "Run all again",
    "清理异常条目": "Clean up broken entries",
    "清理失败：%s": "Clean-up failed: %s",
    # ---------- 关窗 / 托盘 ----------
    "当前任务尚未完成。\n\n停止并退出：立刻中止，未完成的文件会留在输出目录，需要自行删除。\n最小化到托盘：窗口隐藏，转换继续跑完，跑完会弹提示。":
        "A task is still running.\n\nStop and exit: aborts right away. Unfinished files stay "
        "in the output folder and have to be deleted by hand.\nMinimise to tray: the window "
        "hides, the conversion runs to the end and you get a notification.",
    "停止并退出": "Stop and exit",
    "后台进程尚未退出，请稍候再关闭": "The background task has not exited yet. Try again shortly.",
    "最小化到托盘": "Minimise to tray",
    "最小化到托盘（不可用）": "Minimise to tray (unavailable)",
    "转换在后台继续，完成后会再提示一次。":
        "The conversion keeps running in the background; you will be notified when it finishes.",
    "继续转换": "Keep converting",
    # ---------- 更新 ----------
    "发现新版本": "Update available",
    "当前版本 %1，最新版本 %2。": "Current version %1, latest %2.",
    "未知": "unknown",
    "前往下载": "Download",
    "稍后": "Later",
    "关闭": "Close",
    # ---------- 封面 ----------
    "自动（源视频第 10 秒）": "Automatic (10 s into the source video)",
    "同名图自动配对（已配 %d/%d）": "Paired by file name (%d of %d)",
    "请先添加要转换的视频": "Add the videos to convert first",
    "请先添加要转换的视频文件": "Add the videos to convert first",
    "封面图片不存在": "The cover image does not exist",
    "封面只支持 %s": "Cover images support only %s",
    "自选封面仅支持单个视频。多视频请把封面图命名成与视频同名，放在同一文件夹（a.mp4 + a.jpg），添加时会自动配对。":
        "A hand-picked cover works for a single video only. For several videos, name each "
        "image after its video and keep them in the same folder (a.mp4 + a.jpg); they are "
        "paired automatically when added.",
    "封面已指定：%s → %s": "Cover set: %s → %s",
    "封面已恢复自动": "Cover reverted to automatic",
    # ---------- 转换流程与结果 ----------
    "未知机型预设: %s": "Unknown camera preset: %s",
    "上次这个输出目录已完成 %d 条，还有 %d 条没跑完。":
        "This output folder already finished %d clip(s); %d still to go.",
    "请先选择输出目录": "Choose an output folder first",
    "无法创建输出目录：%s": "Cannot create the output folder: %s",
    "输出目录不可写：%s": "The output folder is not writable: %s",
    "读取文件夹失败：%s": "Cannot read the folder: %s",
    "已定位到 %s": "Found: %s",
    "已拖入 %d 个视频，共 %d 个": "Added %d video(s) by drag and drop, %d in total",
    "已添加 %d 个视频，共 %d 个": "Added %d video(s), %d in total",
    "已移除 %s，剩余 %d 个": "Removed %s, %d left",
    "断点续跑进度保存失败: %s": "Could not save the resume progress: %s",
    "[失败] %s：%s": "[failed] %s: %s",
    "已取消：成功 %d，失败 %d": "Cancelled: %d succeeded, %d failed",
    "已取消，剩余 %d 个文件未处理": "Cancelled; %d file(s) left untouched",
    "%s（已取消）": "%s (cancelled)",
    "转换已取消": "Conversion cancelled",
    "完成：成功 %d": "Done: %d succeeded",
    "完成：成功 %d，失败 %d": "Done: %d succeeded, %d failed",
    "转换完成": "Conversion finished",
    "转换异常：%s": "Conversion error: %s",
    "转换失败：%s": "Conversion failed: %s",
}

#   核心层的运行期消息：异常与日志文案。这些字符串多数已经在 core.py 里套过
#   参数，靠 t() 的模板反查（把 %s 当通配）对回来；所以这里统一用 %s 写键，
#   不管原文是 %s 还是 f-string 的 {name}。
EN_TEXT.update({
    "ffmpeg 可执行文件不存在: %s": "ffmpeg executable not found: %s",
    "ffmpeg 封面截取失败: %s": "ffmpeg could not grab the cover frame: %s",
    "ffmpeg 封面截取超时（>120s）: %s": "ffmpeg timed out grabbing the cover frame (>120 s): %s",
    "ffmpeg 转码超时（>600s）: %s": "ffmpeg transcoding timed out (>600 s): %s",
    "ffprobe 读取失败: %s": "ffprobe could not read the file: %s",
    "ffprobe 超时（>60s）: %s": "ffprobe timed out (>60 s): %s",
    "stbl 里既没有 stco 也没有 co64，文件结构异常":
        "The stbl box has neither stco nor co64; the file structure is broken.",
    "MCRC box 长度异常: %s": "Odd MCRC box length: %s",
    "%s 不可用: %s（卡可能被拔出或盘符变了）":
        "%s is unavailable: %s (the card may have been unplugged or the drive letter changed)",
    "%s 不存在: %s（卡可能被拔出或盘符变了）":
        "%s does not exist: %s (the card may have been unplugged or the drive letter changed)",
    "%s 缺少 LRV_*.lrv 模板": "%s is missing an LRV_*.lrv sample",
    "%s 缺少 VID_*.mp4 模板": "%s is missing a VID_*.mp4 sample",
    "%s: 转码产物不存在": "%s: the transcoded file does not exist",
    "%s 下载失败，尝试下一个源 ...": "%s failed to download, trying the next mirror ...",
    "%s 无法运行": "%s cannot be run",
    "%s 无法运行: %s": "%s cannot be run: %s",
    "下载结果里缺少 %s": "The download is missing %s",
    "全局安装失败: %s": "System-wide installation failed: %s",
    "复制到 %s 失败: %s": "Copying to %s failed: %s",
    "安装后 %s 仍不存在": "%s is still missing after installation",
    "安装后仍无法运行: %s": "Still cannot run after installation: %s",
    "安装失败: %s": "Installation failed: %s",
    "安装脚本返回错误码 %d": "The installer returned error code %d",
    "安装超时": "Installation timed out",
    "正在申请管理员权限 ...": "Requesting administrator rights ...",
    "所有下载源均不可用": "No download mirror is reachable",
    "自动下载失败: %s": "Automatic download failed: %s",
    "无法申请管理员权限: %s": "Cannot request administrator rights: %s",
    "无法申请管理员权限（错误码 %s）": "Cannot request administrator rights (error code %s)",
    "无法写入安装脚本: %s": "Cannot write the installer script: %s",
    "已取消": "Cancelled",
    "已取消（未获得管理员权限）": "Cancelled (administrator rights not granted)",
    "封面图不存在: %s": "The cover image does not exist: %s",
    "封面尺寸异常: %s 字节": "Odd cover image size: %s bytes",
    "封面渲染失败: %s": "Rendering the cover failed: %s",
    "封面渲染超时（>%ss）: %s": "Rendering the cover timed out (>%s s): %s",
    "找不到 ffmpeg，无法转码。": "ffmpeg was not found; cannot transcode.",
    "未找到 ffmpeg/ffprobe": "ffmpeg/ffprobe not found",
    "未找到 ffmpeg，无法构建硬件转码命令":
        "ffmpeg not found; cannot build the hardware transcode command",
    "未找到 ffmpeg，无法构建转码命令": "ffmpeg not found; cannot build the transcode command",
    "未找到 ffmpeg，无法渲染封面": "ffmpeg not found; cannot render the cover",
    "文件不存在": "The file does not exist",
    "无法从 inst box 读出元数据": "Cannot read the metadata out of the inst box",
    "无法创建或访问输出目录 %s: %s": "Cannot create or access the output folder %s: %s",
    "无法创建相机卡目录 %s: %s": "Cannot create the camera folder %s: %s",
    "源文件不存在: %s": "The source file does not exist: %s",
    "输入文件不存在: %s": "The input file does not exist: %s",
    "输出目录不可用: %s（%s）": "The output folder is unusable: %s (%s)",
    "磁盘空间不足：需要约 %s MB，可用 %s MB。":
        "Not enough disk space: about %s MB needed, %s MB available.",
    "索引登记失败（inst 已移植，文件本身可用）: %s":
        "The index entry could not be written (the inst box is transplanted and the file itself "
        "is usable): %s",
    "读取失败: %s": "Reading failed: %s",
    "跳过登记（目标文件不存在）: %s": "Skipped the index entry (target file missing): %s",
    "跳过登记（缺少真实 meta 模板，拒绝编造）: %s":
        "Skipped the index entry (no real meta sample; refusing to make one up): %s",
    "请使用相机原生的 VID_YYYYMMDD_HHMMSS_NNN.mp4 作模板。":
        "Use a camera-native VID_YYYYMMDD_HHMMSS_NNN.mp4 as the sample.",
    "请先在 DCIM\\Camera01 放一对相机原生 VID_*.mp4 + LRV_*.lrv。":
        "Put a pair of camera-native VID_*.mp4 + LRV_*.lrv in DCIM\\Camera01 first.",
    "  [警告] LRV avc1 精简失败（不致命）: %s":
        "  [warn] could not slim the LRV avc1 entry (not fatal): %s",
    "  [警告] inst 缩略图写入失败（封面仍会是模板的）: %s":
        "  [warn] could not write the inst thumbnail (the cover stays the sample's): %s",
    "  %s: inst 移植失败（%s）": "  %s: inst transplant failed (%s)",
    "  失败: %s -> %s": "  failed: %s -> %s",
    "  缩略图生成失败（不致命）: %s": "  thumbnail generation failed (not fatal): %s",
    "  自定义封面处理失败，改用视频取帧: %s":
        "  custom cover failed, falling back to a frame from the video: %s",
    "\n成功 %s 个，失败 %s 个。": "\n%s succeeded, %s failed.",
    "无法写入索引 %s：权限被拒。\n    路径: %s\n"
    "    请确认：1) 卡的写保护开关没打开；2) 文件没被其他程序（相机软件/杀软）占用；"
    "3) 以管理员身份运行本程序。":
        "Cannot write the index %s: permission denied.\n    Path: %s\n"
        "    Check that: 1) the card's write-protect switch is off; 2) no other program "
        "(camera software, antivirus) is holding the file; 3) this app runs as administrator.",
    "目标不是影石相机卡（缺少 DCIM\\Camera01 结构）：\n  %s\n"
    "为避免在普通文件夹里误建 DCIM 目录、污染数据，已中止索引写入。\n"
    "请把输出目录指向存储卡的 DCIM 或 DCIM\\Camera01。":
        "That target is not an Insta360 card (no DCIM\\Camera01 layout):\n  %s\n"
        "Writing the index is aborted so a DCIM folder is not created in an ordinary folder "
        "and no data gets polluted.\nPoint the output folder at the card's DCIM or "
        "DCIM\\Camera01 instead.",
    "卡里找不到真机原片作模板（DCIM\\Camera01\\VID_*.mp4 + LRV_*.lrv）。\n"
    "没有它无法移植 inst box，相机不会认。":
        "No camera-recorded sample was found on the card "
        "(DCIM\\Camera01\\VID_*.mp4 + LRV_*.lrv).\nWithout one the inst box cannot be "
        "transplanted and the camera will not recognise the file.",
})

#   嵌在别的消息里被插进来的短因果，递归翻译时会用到。
EN_TEXT.update({
    "权限被拒": "permission denied",
    "权限不足": "insufficient permission",
    "文件被占用": "the file is in use",
    "磁盘已满": "the disk is full",
    "超时": "timed out",
    "已中断": "interrupted",
    "被用户取消": "cancelled by the user",
})

#    托盘菜单
EN_TEXT.update({
    "显示主窗口": "Show window",
    "退出": "Quit",
})


#   界面属性与校验/保存提示
EN_TEXT.update({
    "正在校验索引…": "Checking the card index…",
    "保留 %d 条，移除 %d 条。请重新插卡让相机刷新相册。": "Kept %d, removed %d. Re-insert the card so the camera rebuilds its album.",
    "列表里没有这个文件": "That file is not in the list",
    "列表已清空": "List cleared",
    "正在取消…": "Cancelling…",
    "未在 D 到 I 盘找到 DCIM 目录，请手动选择输出目录": "No DCIM folder found on drives D–I. Choose the output folder manually.",
    "请先选择存储卡目录（DCIM 或 DCIM\\Camera01）": "Choose the camera card folder first (DCIM or DCIM\\Camera01)",
    "共 %d 条索引：正常 %d，异常 %d": "%d index entries: %d OK, %d broken",
    "请先选择存储卡目录": "Choose the camera card folder first",
    "拖入的内容里没有可识别的视频文件": "Nothing dropped in was a supported video file",
    "文件夹不存在": "The folder does not exist",
    "校验失败：%s": "Index check failed: %s",
    "  … 另有 %d 条": "  … %d more",
    "输出目录不是相机卡结构，改为仅转码": "The output folder is not a camera card structure — transcoding only",
    "目录不存在": "The folder does not exist",
    "设置输出目录后显示下一序号": "Set the output folder to see the next number",
    "卡内未找到真机原片，改为仅转码": "No native recording on the card — transcoding only",
})

EN_TEXT.update({
    "inst 移植失败": "inst box transplant failed",
})

EN_TEXT.update({
    #   ffmpeg 安装/下载流程的进度文案：这些走 bridge 的 stage() 回调，
    #   直接显示在状态栏上，英文界面必须是英文。
    "ffmpeg 未就绪：%s。可以装到系统目录（需管理员权限），也可以只装到程序目录。":
        "ffmpeg is not ready: %s. You can install it into the system folder "
        "(needs administrator rights), or only into the program folder.",
    "正在为 ffmpeg 下载源测速...": "Checking the ffmpeg download sources...",
    "  %s 不可达": "  %s is unreachable",
    "正在从 %s 下载 ffmpeg ...": "Downloading ffmpeg from %s ...",
    "正在下载 ffmpeg %s% (%s)": "Downloading ffmpeg %s% (%s)",
    "正在下载 %s%": "Downloading %s%",
    "正在安装到 %s ...": "Installing to %s ...",
    "正在校验 ffmpeg ...": "Verifying ffmpeg ...",
    "ffmpeg 安装完成 ✓ (%s)": "ffmpeg installed ✓ (%s)",
})

EN_TEXT.update({
    #   进度阶段名与轨道标签：经 progress 回调显示在进度条旁。
    "转码": "Transcoding",
    "移植 inst box": "Transplanting inst box",
    "登记索引": "Registering index",
    "VID (主视频)": "VID (main video)",
    "LRV (低清预览)": "LRV (low-res preview)",
})

EN_TEXT.update({
    #   两条会进 UI 日志区的运行记录。日志整体保持中文，但这两条
    #   已由用户明确要求可读，且与相邻译文风格不一致会显得突兀。
    "[resume] 只跑未完成的 %d 条（已完成 %d 条）":
        "[resume] running only the %d unfinished item(s), %d already done",
    "[warn] 输出目录不是影石相机卡结构，跳过 inst 移植与索引登记：%s":
        "[warn] the output folder is not an Insta360 card layout, "
        "skipping inst transplant and index registration: %s",
})

EN_TEXT.update({
    #   ffmpeg 探测超时（新增的 10 秒上限）后返回的说明。
    "%s 无响应（>10s）": "%s is not responding (>10s)",
})

EN_TEXT.update({
    #   首次启动的欢迎窗（使用协议 / 使用须知 / 作者主页）。
    #   免责声明这块宁可译得笨一点也不能省：英文用户看到的必须是同一份意思。
    "使用协议": "Terms of use",
    "使用须知": "Before you start",
    "作者主页": "About the author",
    "第 1 页 / 共 3 页 · 用之前请先看完": "Page 1 of 3 · please read before you start",
    "第 2 页 / 共 3 页 · 几条容易踩的坑": "Page 2 of 3 · a few traps worth knowing",
    "第 3 页 / 共 3 页 · 关于这颗 star": "Page 3 of 3 · about that star",
    "本程序按 GPL-3.0-or-later 发布：源码公开，可以自由使用、修改、再分发；再分发时要保留同一许可证，并说明源码从哪拿。":
        "Released under GPL-3.0-or-later: the source is public, and you may use, "
        "modify and redistribute it. If you redistribute it, keep the same licence "
        "and say where the source can be obtained.",
    "只拿它处理你本人拍的、或者已经取得授权的素材。把别人的片子包装成自己相机拍的，不在授权范围内，后果自负。":
        "Use it only on footage you shot yourself, or that you are authorised to "
        "use. Passing someone else's footage off as shot on your own camera is "
        "outside that permission, and the responsibility is yours.",
    "导入会改写视频容器的元数据，并在相机卡里写索引文件。写卡有风险，动手之前请自己备份原片。":
        "Importing rewrites the video container's metadata and writes index files "
        "onto the camera card. Writing to a card carries risk — back up your "
        "originals before you start.",
    "软件按「现状」提供，不附带任何担保。素材损坏、相机不识别、数据丢失这类后果，作者不承担责任。":
        "The software is provided as is, without any warranty. Damage to footage, "
        "a camera that refuses to recognise it, or data loss are not the author's "
        "responsibility.",
    "程序完全在本机跑，不上传视频、路径或任何个人信息。只有检查更新的时候会访问 GitHub 的公开接口。":
        "Everything runs on your machine: no video, path or personal information is "
        "uploaded. The only network call is to GitHub's public API, when checking "
        "for updates.",
    "• 移植 inst box 要求卡里已经有一对真机原片（VID_*.mp4 和 LRV_*.lrv）当模板。没有模板只能纯转码，相机不会认。":
        "• Transplanting the inst box needs a pair of camera-recorded files on the "
        "card (VID_*.mp4 and LRV_*.lrv) to use as a template. Without one you only "
        "get plain transcodes, and the camera will not recognise them.",
    "• 机型预设只决定编码参数（分辨率、帧率、编码器、关键帧间隔、音轨数），不会解除上面那条。":
        "• A model preset only sets the encoding parameters (resolution, frame rate, "
        "encoder, keyframe interval, track count). It does not lift that requirement.",
    "• 第一次用，先拿一段短片走一遍：导入，插回相机，看相册能不能播、能不能下载到手机。":
        "• On your first run, take one short clip all the way through: import it, put "
        "the card back in the camera, then check that the album plays it and that it "
        "downloads to your phone.",
    "• 转换期间不要拔卡、不要拔读卡器。中途关窗程序会先问你要不要中止。":
        "• Do not unplug the card or the reader while converting. Closing the window "
        "mid-run asks you first whether to abort.",
    "• 需要 ffmpeg。没装的话程序会在顶部提示，可以一键装到系统目录或程序目录。":
        "• ffmpeg is required. If it is missing, a banner at the top offers a "
        "one-click install into the system folder or the program folder.",
    "• 机型不在列表里就选「自动」，程序会从卡里的原片把参数量出来。":
        "• If your model is not in the list, pick Automatic — the parameters are "
        "measured from the camera originals on the card.",
    "桌面端和安卓端都是一个人写的": "The desktop and Android apps are written by one person",
    "这个工具最初只是不想每次手动折腾视频元数据。后来越补越多，桌面端、安卓端，还有现在这个欢迎页。":
        "This started as a way to stop hand-editing video metadata every time. It "
        "grew: a desktop app, an Android app, and now this welcome screen.",
    "有问题、有想法，去仓库开 issue。如果它帮你省了事，点个 star 就是最实在的支持 —— 不点也完全没关系，功能一样不少。":
        "Bugs and ideas belong in the repo's issues. If it saved you some work, a "
        "star is the most concrete way to say thanks — and if you would rather not, "
        "that changes nothing about the app.",
    "去点个 star": "Give it a star",
    # 按钮要在 412 DIP 的页脚里和「上一步」「去点个 star」并排，英文不能
    # 照字面译成 "I really don't have a GitHub account"——那样三个按钮加起来
    # 比面板还宽，Back 会被挤出左边界。语气的补充放在正文里说了。
    "我真的没有 GitHub 账号": "I don't have GitHub",
    "下一步": "Next",
    "上一步": "Back",
    "[warn] 记录欢迎页状态失败：%s": "[warn] could not record the welcome state: %s",
})
