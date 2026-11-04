# -*- coding: utf-8 -*-
"""Android 侧桥接模块：把桌面端已验证的导入核心原样跑在手机上。

思路
----
`insta_core.py` 是桌面端 1.2.0 的完整实现（转码 → inst box 移植 → 索引登记），
只依赖标准库 + 外部 ffmpeg/ffprobe；这里只做三件 Android 适配：

1. 把随包可执行文件路径写进 FFMPEG_PATH / FFPROBE_PATH（core 会优先读取）；
2. 把临时目录指到应用 cache（Android 没有可写的系统 /tmp）；
3. 关掉 Windows 专用的 set_awake / 窗口标志。

相机卡的读写由 Kotlin 侧用 SAF 负责：Kotlin 把卡上索引 + 一对真机模板镜像到
应用私有目录，Python 在镜像上做完整导入，Kotlin 再把新增媒体与更新后的索引写回卡。
"""

import json
import os
import sys
import tempfile
import traceback

_core = None
_tf = None
_rw = None
_log_file = None


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
        raise RuntimeError("inst 模块加载失败: %s: %s" % (type(e).__name__, e))
    return "insta_core %s" % getattr(insta_core, "__version__", "?")


def _safe_call(cb, *args):
    try:
        if cb is not None:
            getattr(cb, "onProgress")(*args)
    except Exception:  # noqa: BLE001
        pass


def _safe_log(cb, text):
    try:
        if cb is not None:
            getattr(cb, "onLog")(str(text))
    except Exception:  # noqa: BLE001
        pass


def run_import(source, card_root, callback=None, cover=None, prefer_hardware=False):
    """在镜像卡目录上执行完整导入，返回 JSON 字符串。

    source            已暂存到本地的源视频
    card_root         镜像卡根（内含 DCIM/Camera01 + 索引 + 一对真机模板）
    callback          Kotlin 对象，含 onProgress(frac:float, text:str) / onLog(text:str)
    prefer_hardware   True = 优先 MediaCodec 硬件编码（快，但关键帧间隔只能 1 秒）；
                      False = libx265/libx264 软件编码（与桌面端一致，相机识别最稳）
    """
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
        res = _core.import_with_inst(
            source, card_root, log=log, progress=progress,
            cover=cover if cover else None,
        )
        out = {
            "ok": True,
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
        tb = traceback.format_exc()
        log("导入失败：%s: %s" % (type(e).__name__, e))
        return json.dumps({
            "ok": False,
            "error": "%s: %s" % (type(e).__name__, e),
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
            return False, "ffmpeg 不存在: %s" % ff
        if not os.path.isfile(fp):
            return False, "ffprobe 不存在: %s" % fp
        if _core is None:
            return False, "核心模块未初始化"
        ok, msg = _core.check_encoding_capability()
        if not ok:
            return False, "%s（%s）" % (msg, getattr(_core, "__version__", "?"))
        return True, "OK %s / %s" % (getattr(_core, "__version__", "?"), msg)
    except Exception as e:  # noqa: BLE001
        return False, "%s: %s" % (type(e).__name__, e)
