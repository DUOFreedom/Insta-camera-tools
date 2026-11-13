# -*- coding: utf-8 -*-
"""Android 侧桥接模块：把桌面端已验证的导入核心原样跑在手机上。

思路
----
`insta_core.py` 是桌面端 1.3.0 的完整实现（转码 → inst box 移植 → 索引登记），
只依赖标准库 + 外部 ffmpeg/ffprobe；这里只做三件 Android 适配：

1. 把随包可执行文件路径写进 FFMPEG_PATH / FFPROBE_PATH（core 会优先读取）；
2. 把临时目录指到应用 cache（Android 没有可写的系统 /tmp）；
3. 关掉 Windows 专用的 set_awake / 窗口标志。

相机卡的读写由 Kotlin 侧用 SAF 负责：Kotlin 把卡上索引 + 一对真机模板镜像到
应用私有目录，Python 在镜像上做完整导入，Kotlin 再把新增媒体与更新后的索引写回卡。
"""

import json
import os
import re
import sys
import tempfile
import threading
import traceback
import urllib.request

import i18n

_core = None
_tf = None
_rw = None
_log_file = None


def set_lang(value):
    """Kotlin 调用：显式指定界面语言（"zh"/"en"），其它值复位为自动探测。"""
    i18n.set_lang(value)


def new_cancel_event():
    """创建一个取消事件，交给 Kotlin 侧持有并传回 run_import()。

    Kotlin 拿到的是一枚 PyObject，既可以作为参数回传给 Python（Chaquopy 会
    还原成真正的 threading.Event），也可以直接 callAttr("set") 置位。
    这样取消令牌的生命周期由 Kotlin 的引用决定，不需要额外的登记表。
    """
    return threading.Event()


def _core_version():
    """取 insta_core 的版本号。

    本模块自身不定义版本常量（版本号只存在于 insta_core.py）。早期在
    _Updater._run 里直接引用裸名，会抛 NameError 并被 except 静默吞掉，
    表现为更新检查永远无声失效。
    """
    return getattr(_core, "__version__", "?")


def init(ffmpeg_path, ffprobe_path, cache_dir):
    """初始化：设置工具路径与临时目录，导入核心模块。返回版本字符串。"""
    global _core, _tf, _rw, _log_file
    for name, path in (("FFMPEG_PATH", ffmpeg_path), ("FFPROBE_PATH", ffprobe_path)):
        if path:
            os.environ[name] = path

    tmp = os.path.join(cache_dir, "tmp")
    os.makedirs(tmp, exist_ok=True)
    tempfile.tempdir = tmp
    os.environ["TMPDIR"] = tmp
    os.environ["TMP"] = tmp
    os.environ["TEMP"] = tmp

    _log_file = os.path.join(cache_dir, "import.log")
    import insta_core
    insta_core._NO_WINDOW = 0                 # POSIX 下不接受 CREATE_NO_WINDOW
    insta_core.set_awake = lambda enable=False: False
    insta_core.log_path = lambda: _log_file   # 日志落到应用私有目录
    _core = insta_core
    try:
        _tf, _rw = insta_core._load_inst_modules()
    except Exception as e:
        raise RuntimeError(i18n.t("inst 模块加载失败: %s") % ("%s: %s" % (type(e).__name__, e)))
    return "insta_core %s" % getattr(insta_core, "__version__", "?")


def _swallow(where, exc):
    """回调异常不能往上抛（会打断转码），但也不能彻底消失。

    完全静默时表现为「进度条卡在某个值 + 日志一片空白」，现场无法判断是
    编码慢还是桥接坏了。写进 import.log，至少事后能查到。
    """
    try:
        if _log_file:
            with open(_log_file, "a", encoding="utf-8") as f:
                f.write("[bridge] %s 回调失败: %s: %s\n" % (where, type(exc).__name__, exc))
    except Exception:  # noqa: BLE001
        pass


def _safe_call(cb, *args):
    try:
        if cb is not None:
            getattr(cb, "onProgress")(*args)
    except Exception as e:  # noqa: BLE001
        _swallow("onProgress", e)


def _safe_log(cb, text):
    try:
        if cb is not None:
            getattr(cb, "onLog")(str(text))
    except Exception as e:  # noqa: BLE001
        _swallow("onLog", e)


def run_import(source, card_root, callback=None, cover=None, prefer_hardware=False,
               cancel=None, template_names=None, lang=None, model_override="auto"):
    """在镜像卡目录上执行完整导入，返回 JSON 字符串。

    source            已暂存到本地的源视频
    card_root         镜像卡根（内含 DCIM/Camera01 + 索引 + 一对真机模板）
    callback          Kotlin 对象，含 onProgress(frac:float, text:str) / onLog(text:str)
    prefer_hardware   True = 优先 MediaCodec 硬件编码（快，但关键帧间隔只能 1 秒）；
                      False = libx265/libx264 软件编码（与桌面端一致，相机识别最稳）
    cancel            可选 threading.Event；由 new_cancel_event() 创建、Kotlin 侧置位。
                      置位后 ffmpeg 子进程会被 kill，返回的 JSON 带 canceled=True。
    template_names    可选 (vid_name, lrv_name)：明确指定用哪一对文件当模板。
                      传了就不再让核心自己猜 —— 镜像目录里上一轮的产物同样带
                      inst box，猜错的后果是相机不认且不报错。

    lang              可选 "zh"/"en"：界面语言，决定进度标签与失败原因的语种。
                      不传则沿用上次 set_lang() 的值（Kotlin 侧 init 后已设过）。

    model_override    机型预设："auto"（默认，卡里有真机原片就跟着它量）/
                      "ace_pro_2" / "go_ultra"。非 auto 时，卡里没有真机原片
                      也能按预设参数生成，不再报「找不到模板」。

    返回 JSON：成功 {"ok": True, main, proxy, inst_ok, inst_error, index_error, registered}；
              取消 {"ok": False, canceled": True, error}；
              失败 {"ok": False, error, trace}。
    """
    i18n.set_lang(lang)

    def log(msg):
        _safe_log(callback, msg)

    def progress(frac, label="", speed=0.0, eta=0):
        _safe_call(callback, float(frac or 0.0), str(label or ""))

    try:
        log("核心 %s" % getattr(_core, "__version__", "?"))
        try:
            _core.set_prefer_hardware(bool(prefer_hardware))
        except Exception:  # noqa: BLE001
            pass
        tpl = None
        model = str(model_override or "auto")
        if model != "auto":
            presets = getattr(_core, "CAMERA_PRESETS", {}) or {}
            if model not in presets:
                return json.dumps({
                    "ok": False,
                    "canceled": False,
                    "error": i18n.t("未知机型预设: %s") % model,
                }, ensure_ascii=False)
        if template_names:
            vid_name, lrv_name = template_names
            tpl = _core.template_from_names(card_root, vid_name, lrv_name)
            if tpl is None:
                return json.dumps({
                    "ok": False,
                    "canceled": False,
                    "error": i18n.t("模板对不可用：%s / %s") % (vid_name, lrv_name),
                }, ensure_ascii=False)
            log("模板（指定）: %s" % vid_name)
        res = _core.import_with_inst(
            source, card_root, template=tpl, log=log, progress=progress,
            cover=cover if cover else None,
            cancel=cancel, model_override=model,
        )
        out = {
            "ok": True,
            "canceled": False,
            "main": os.path.basename(res.get("main") or ""),
            "proxy": os.path.basename(res.get("proxy") or ""),
            "inst_ok": bool(res.get("inst_ok")),
            "inst_error": res.get("inst_error") or "",
            "index_error": res.get("index_error") or "",
            "registered": list(res.get("registered") or []),
        }
        log("导入完成：inst_ok=%s" % out["inst_ok"])
        return json.dumps(out, ensure_ascii=False)
    except Exception as e:  # noqa: BLE001
        # 取消不是失败：Kotlin 侧据此显示「已取消」而不是「失败：…」，
        #   也不会把半成品写回卡。
        if isinstance(e, getattr(_core, "CanceledError", ())):
            log("已取消")
            return json.dumps({
                "ok": False,
                "canceled": True,
                "error": "%s: %s" % (type(e).__name__, i18n.t(str(e))),
            }, ensure_ascii=False)
        tb = traceback.format_exc()
        log("导入失败：%s: %s" % (type(e).__name__, e))
        return json.dumps({
            "ok": False,
            "canceled": False,
            "error": "%s: %s" % (type(e).__name__, i18n.t(str(e))),
            "trace": tb[-3000:],
        }, ensure_ascii=False)


def read_log_tail(lines=40):
    try:
        if not _log_file or not os.path.isfile(_log_file):
            return ""
        with open(_log_file, "r", encoding="utf-8", errors="replace") as f:
            return "".join(f.readlines()[-lines:])
    except Exception:  # noqa: BLE001
        return ""


def self_check():
    """返回 (ok, 说明)：确认模块、ffmpeg、编码能力、临时目录都就绪。"""
    try:
        ff = os.environ.get("FFMPEG_PATH", "")
        fp = os.environ.get("FFPROBE_PATH", "")
        if not os.path.isfile(ff):
            return False, i18n.t("ffmpeg 不存在: %s") % ff
        if not os.path.isfile(fp):
            return False, i18n.t("ffprobe 不存在: %s") % fp
        if _core is None:
            return False, i18n.t("核心模块未初始化")
        ok, msg = _core.check_encoding_capability()
        if not ok:
            return False, i18n.t("%s（%s）") % (i18n.t(str(msg)), getattr(_core, "__version__", "?"))
        return True, "OK %s / %s" % (getattr(_core, "__version__", "?"), msg)
    except Exception as e:  # noqa: BLE001
        return False, "%s: %s" % (type(e).__name__, i18n.t(str(e)))


_REPO = "duofreedom/Insta-camera-tools"
_API_URL = "https://api.github.com/repos/%s/releases/latest" % _REPO
_FALLBACK_URL = "https://github.com/%s/releases" % _REPO
_TIMEOUT = 6.0


def _parse_version(text: str):
    if not isinstance(text, str):
        return None
    value = text.strip().lstrip("vV")
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)(.*)$", value)
    if not match:
        return None
    major, minor, patch = (int(match.group(i)) for i in (1, 2, 3))
    suffix = match.group(4) or ""
    stable = 1 if suffix == "" else 0
    return major, minor, patch, stable


class _Updater:
    """后台检查 GitHub latest release，结果通过回调返回给 Kotlin。"""

    def __init__(self):
        self._checking = False
        self._available = False
        self._tag = ""
        self._url = ""
        self._ignored_tag = ""

    def check(self, callback):
        """启动一次检查。callback(tag, url) 在有新版本时调用。"""
        if self._checking:
            return
        # Demo mode via env var (for testing)
        if os.environ.get("INSTA_UPDATE_DEMO") == "1":
            if callback:
                callback("v1.3.0", _FALLBACK_URL)
            return
        self._checking = True
        threading.Thread(target=self._run, args=(callback,), daemon=True).start()

    def ignore(self, tag: str):
        if tag:
            self._ignored_tag = tag
        self._available = False

    def _run(self, callback):
        try:
            request = urllib.request.Request(_API_URL, headers={
                "User-Agent": "instatoolsAndroid/%s" % _core_version(),
                "Accept": "application/vnd.github+json",
            })
            with urllib.request.urlopen(request, timeout=_TIMEOUT) as resp:
                payload = json.loads(resp.read().decode("utf-8", "replace"))
            tag = str(payload.get("tag_name") or "")
            latest = _parse_version(tag)
            current = _parse_version(_core_version())
            if not tag or latest is None or current is None:
                return
            if tag == self._ignored_tag or latest <= current:
                return
            self._tag = tag
            self._url = str(payload.get("html_url") or _FALLBACK_URL)
            self._available = True
            if callback:
                callback(tag, self._url)
        except Exception as exc:  # noqa: BLE001
            # 早期是裸 pass：网络不通 / 仓库 404 / 无 INTERNET 权限都会静默失败。
            try:
                if _log_file:
                    with open(_log_file, "a", encoding="utf-8") as fh:
                        fh.write("[update] %s: %s\n" % (type(exc).__name__, exc))
            except Exception:  # noqa: BLE001
                pass
        finally:
            self._checking = False


_updater = _Updater()


def check_update(callback):
    """Kotlin 调用：启动后台更新检查。callback(tag: str, url: str) 有新版本时回调。"""
    _updater.check(callback)


def ignore_update(tag: str):
    """Kotlin 调用：忽略某版本（写入内存，进程重启失效；若需持久化由 Kotlin 落 SharedPreferences）。"""
    _updater.ignore(tag)
