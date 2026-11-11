# -*- coding: utf-8 -*-
"""安卓侧界面文案的中英双语文案表。

键是中文原文，值是英文译文。查不到的键原样返回中文：漏译时界面显示中文，
既不崩也不会露出内部键名，可以增量补齐。

与桌面端 `desktop/i18n.py` 的区别只在校验语言来源：安卓既没有 Windows 用户
界面语言可读，也不能 import PySide6，所以只认两处 ——

    set_lang() 显式指定（Kotlin 侧按当前资源配置传下来）> 环境变量 INSTA_LANG
    > 英文

兜底选英文而**不是**中文：英文用户看到一屏中文比中文用户看到零星英文更糟。
中文用户由 Kotlin 侧显式传 "zh" 进来，不依赖兜底。

文案表只收 Python 侧真正会走到界面上的键（进度标签、自检说明、卡结构/模板
缺失、取消提示），不是桌面端那 206 条的完整表 —— 桌面端的 Qt 对话框文案在
安卓上不存在。日志（`say()` / import.log）保持中文原文，不在这里。
"""

from __future__ import annotations

import os
import re

ZH = "zh"
EN = "en"

_PRODUCT_EN = "instatools"
_PRODUCT_ZH = "影石相机工具"

#   Kotlin 侧 set_lang("zh"/"en") 写进来的显式语言；None = 没指定，走探测。
_forced: str | None = None


def set_lang(value: str | None) -> None:
    """显式指定语言。传空 / 非法值复位为自动探测。

    Kotlin 每次进 Python 前都会调一次：进程活着的时候用户可能切系统语言
    （Activity 会重建，但 Python 进程里的模块状态不会跟着重置），所以不能
    只在 init 时定一次。
    """
    global _forced
    _forced = value if value in (ZH, EN) else None


def detect() -> str:
    if _forced in (ZH, EN):
        return _forced
    env = (os.environ.get("INSTA_LANG") or "").strip().lower()
    if env in (ZH, EN):
        return env
    return EN


def lang() -> str:
    return detect()


def app_name() -> str:
    """产品名。英文全小写 instatools，中文是影石相机工具。"""
    return _PRODUCT_ZH if lang() == ZH else _PRODUCT_EN


_TEMPLATES: list[tuple[re.Pattern[str], str]] | None = None


def _templates() -> list[tuple[re.Pattern[str], str]]:
    """把带 %s/%d 的键编译成整串匹配的正则，供已套过参数的文案反查。

    核心层有些消息是 f-string 直接拼好的（"输入文件不存在: /sdcard/a.mp4"），
    到这儿时中文模板里的 %s 早被替换掉了，按原键查必然落空。这里用惰性通配
    把它们对回来，调用方就不必区分「先翻译再格式化」还是「先格式化再翻译」。
    """
    global _TEMPLATES
    if _TEMPLATES is None:
        built: list[tuple[re.Pattern[str], str]] = []
        #   长的键先匹配：泛用模板（"%s（%s）" 这种）一旦排在前面，
        #   会把 "模板文件 不存在: /a（卡可能被拔出…）" 抢走一半（只换掉
        #   冒号后面那段），留下半中半英的残句。按长度降序，
        #   专门的长模板优先于泛用短模板。
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
    """把一条中文界面文案翻成当前语言。查不到原样返回。"""
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
            #   被插进来的往往又是一条中文消息（"输入文件不存在: …"），
            #   递归再查一次，否则英文界面里会夹着中文尾巴。
            return t(rest.pop(0), _depth + 1) if rest else ""

        return re.sub(r"%[sd]", take, value)
    return text


#   英文文案。占位符沿用中文原文里的 %s / %d 顺序，调用方不用区分语言。
EN_TEXT: dict[str, str] = {
    # ---------- 通用 ----------
    "已取消": "Canceled",

    # ---------- 自检 / 设置页的 Python 核心状态 ----------
    "无法读取 ffmpeg 编码器列表": "Cannot read the ffmpeg encoder list",
    "ffmpeg 缺少编码器: %s": "ffmpeg is missing encoders: %s",
    "libx265 + libx264 就绪": "libx265 + libx264 ready",
    "%s（%s）": "%s (%s)",
    "核心模块未初始化": "The core module is not initialized",
    "ffmpeg 不存在: %s": "ffmpeg not found: %s",
    "ffprobe 不存在: %s": "ffprobe not found: %s",
    "inst 模块加载失败: %s": "Failed to load the inst modules: %s",

    # ---------- 进度标签（ImportCallback.label） ----------
    "转码": "Transcoding",
    "移植 inst box": "Transferring inst box",
    "登记索引": "Registering in index",
    "VID (主视频)": "VID (main video)",
    "LRV (低清预览)": "LRV (low-res preview)",

    # ---------- 失败原因（界面「失败：…」与条目明细） ----------
    "未找到 ffmpeg，无法构建转码命令": "ffmpeg not found; cannot build the transcode command",
    "未找到 ffmpeg，无法构建硬件转码命令":
        "ffmpeg not found; cannot build the hardware transcode command",
    "ffmpeg 可执行文件不存在: %s": "ffmpeg executable not found: %s",
    "模板对不可用：%s / %s": "Template pair unavailable: %s / %s",
    "%s: 转码产物不存在": "%s: the transcoded output is missing",

    # ---------- 卡结构 / 模板（装错目录或卡里没有真机原片） ----------
    "卡里找不到真机原片作模板。\n"
    "`.inst` 移植必须有一个真机视频提供 moov 骨架与 inst box。\n"
    "请先在 DCIM\\Camera01 放一对相机原生 VID_*.mp4 + LRV_*.lrv。":
        "No camera-recorded original was found on the card to use as a template.\n"
        "The `.inst` transfer needs one native video to supply the moov skeleton "
        "and the inst box.\n"
        "Put a pair of native VID_*.mp4 + LRV_*.lrv from the camera into "
        "DCIM\\Camera01 first.",
    "目标不是影石相机卡（缺少 DCIM\\Camera01 结构）：\n"
    "  %s\n"
    "为避免在普通文件夹里误建 DCIM 目录、污染数据，已中止索引写入。\n"
    "请把输出目录指向存储卡的 DCIM 或 DCIM\\Camera01。":
        "The target is not an Insta360 camera card (no DCIM\\Camera01 folder):\n"
        "  %s\n"
        "Index writing was aborted so that no DCIM folder is created inside an "
        "ordinary directory.\n"
        "Point the output folder at the card's DCIM or DCIM\\Camera01.",

    # ---------- 导入失败明细（界面的条目详情节选段） ----------
    #   这些是 insta_core 直接 raise 的异常正文，由 android_bridge 组装成
    #   error / inst_error / index_error 回给 Kotlin，最后原样显示在
    #   ImportResult.detail。不译就是英文界面里夹一段中文。
    "输入文件不存在: %s": "Input file not found: %s",
    "输出目录不可写: %s": "The output folder is not writable: %s",
    "无法创建或访问输出目录 %s: %s": "Cannot create or open the output folder %s: %s",
    "无法创建相机卡目录 %s: %s": "Cannot create the camera card folder %s: %s",
    "未在样文件中找到视频流": "No video stream found in the sample file",
    "ffprobe 读取失败: %s": "ffprobe could not read the file: %s",
    "ffprobe 超时（>60s）: %s": "ffprobe timed out (>60s): %s",
    "ffmpeg 退出码非 0: %s": "ffmpeg exited with a non-zero status: %s",
    "ffmpeg 转码超时（>600s）: %s": "ffmpeg transcoding timed out (>600s): %s",
    "ffmpeg 封面截取超时（>120s）: %s": "ffmpeg cover capture timed out (>120s): %s",
    "ffmpeg 封面截取失败: %s": "ffmpeg cover capture failed: %s",
    "%s 无视频流": "%s has no video stream",
    "%s 无音频流": "%s has no audio stream",
    "找不到 %s（已找: 环境变量 %s_PATH、%s、PATH）；请把 %s 放到程序同目录的 bin 下。":
        "Cannot find %s (looked in: env %s_PATH, %s, PATH); "
        "put %s in the bin folder next to the app.",
    "文件名不符合 VID_YYYYMMDD_HHMMSS_NNN: %s":
        "The filename does not match VID_YYYYMMDD_HHMMSS_NNN: %s",
    "文件名里没有 8+6 位时间戳: %s": "The filename has no 8+6 digit timestamp: %s",
    "stbl 里既没有 stco 也没有 co64，文件结构异常":
        "stbl has neither stco nor co64; the file structure is broken",
    "MCRC box 长度异常: %s": "The MCRC box has an invalid length: %s",
    "%s 缺少 VID_*.mp4 模板": "%s is missing a VID_*.mp4 template",
    "%s 缺少 LRV_*.lrv 模板": "%s is missing an LRV_*.lrv template",

    # ---------- 导入途中卡被拔 / 路径变化 ----------
    "模板文件": "Template file",
    "生成文件": "Output file",
    "临时目录": "Temp folder",
    "%s 不存在: %s（卡可能被拔出或盘符变了）":
        "%s not found: %s (the card may have been unplugged)",
    "%s 不可用: %s（卡可能被拔出或盘符变了）":
        "%s unavailable: %s (the card may have been unplugged)",
    "udta 内旧名与目标名长度不一致：%s(%s) vs %s(%s)；"
    "请使用相机原生的 VID_YYYYMMDD_HHMMSS_NNN.mp4 作模板。":
        "The old name stored in udta and the target name differ in length: "
        "%s(%s) vs %s(%s); use a camera-native "
        "VID_YYYYMMDD_HHMMSS_NNN.mp4 as the template.",

    # ---------- 机型预设 ----------
    "未知机型预设: %s": "Unknown camera model preset: %s",

    # ---------- 索引写入失败 ----------
    "无法写入索引 %s：权限被拒。\n"
    "    路径: %s\n"
    "    请确认：1) 卡的写保护开关没打开；"
    "2) 文件没被其他程序（相机软件/杀软）占用；"
    "3) 以管理员身份运行本程序。":
        "Cannot write the index %s: permission denied.\n"
        "    Path: %s\n"
        "    Please check: 1) the card's write-protect switch is off; "
        "2) no other program (camera software / antivirus) is using the file; "
        "3) the app really has write access to the card.",
}
