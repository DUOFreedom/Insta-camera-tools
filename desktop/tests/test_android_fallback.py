"""insta_core 转码回退与取消的离线回归。

不依赖 ffmpeg、不依赖相机：把 `_run_ffmpeg` 换成桩函数，
直接验证失败分支的分类是否正确。

为什么这几条重要：硬解/硬编失败后的自动回退一旦回归，用户看到的是
「明明没点取消却提示已取消」，或者「全部失败却报告成功」，两者都不会
抛异常，线上极难察觉。
"""

import os
import sys
import tempfile
import threading

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ANDROID_PY = os.path.abspath(
    os.path.join(HERE, "..", "..", "android", "app", "src", "main", "python")
)
if ANDROID_PY not in sys.path:
    sys.path.append(ANDROID_PY)

import insta_core as ic  # noqa: E402


def _fake_probe(_path):
    return {
        "video": {"codec_name": "hevc", "duration": "1.0"},
        "streams": [],
    }


@pytest.fixture()
def core(monkeypatch):
    """把 insta_core 的外部依赖全部打桩，只保留转码分支逻辑。"""
    monkeypatch.setattr(ic, "_is_android", lambda: True)
    monkeypatch.setattr(ic, "find_ffmpeg", lambda: sys.executable)
    monkeypatch.setattr(ic, "find_ffprobe", lambda: sys.executable)
    monkeypatch.setattr(ic, "probe", _fake_probe)
    monkeypatch.setattr(ic, "next_seq", lambda _d: 0)
    monkeypatch.setattr(ic, "probe_hw_decoder", lambda _c: "hevc_mediacodec")
    monkeypatch.setattr(ic, "available_decoders", lambda: {"hevc_mediacodec"})
    monkeypatch.setattr(ic, "_hw_dec_alive", {})
    monkeypatch.setattr(ic, "log_path",
                        lambda: os.path.join(tempfile.mkdtemp(), "t.log"))
    return ic


def _make_input():
    tmp = tempfile.mkdtemp()
    src = os.path.join(tmp, "in.mp4")
    with open(src, "wb") as fh:
        fh.write(b"\0" * 1024)
    out = os.path.join(tmp, "out")
    os.makedirs(out)
    return src, out


def _record(core, monkeypatch, behaviour):
    """behaviour(cmd) 返回 None 表示成功，抛异常表示该次失败。"""
    calls = []

    def fake_run(cmd, duration, progress=None, cancel=None,
                 procs=None, procs_lock=None):
        if cancel is not None and cancel.is_set():
            raise core.CanceledError("已取消")
        calls.append(list(cmd))
        behaviour(cmd)

    monkeypatch.setattr(core, "_run_ffmpeg", fake_run)
    return calls


def test_hwdecode_failure_falls_back_to_software(core, monkeypatch):
    """硬解失败应自动改用软解重跑，且不得误报「已取消」。"""
    src, out = _make_input()

    def behaviour(cmd):
        if "hevc_mediacodec" in cmd:
            raise core.FFmpegError("模拟硬解失败")

    calls = _record(core, monkeypatch, behaviour)
    cancel = threading.Event()

    core.convert(src, out, cancel=cancel)

    assert len(calls) >= 2, "应当至少有一次硬解尝试与一次软解重试"
    assert "hevc_mediacodec" in calls[0], "首次应尝试硬解"
    assert any("hevc_mediacodec" not in c for c in calls[1:]), "回退后应走软解"
    assert not cancel.is_set(), "回退成功不应置位取消"


def test_all_attempts_fail_raises_ffmpeg_error(core, monkeypatch):
    """硬解与软解都失败时，必须抛 FFmpegError，不能静默返回。"""
    src, out = _make_input()

    def behaviour(_cmd):
        raise core.FFmpegError("模拟失败")

    _record(core, monkeypatch, behaviour)

    with pytest.raises(core.FFmpegError):
        core.convert(src, out, cancel=threading.Event())


def test_user_cancel_still_propagates(core, monkeypatch):
    """用户取消必须抛 CanceledError，不能被回退逻辑吞掉。"""
    src, out = _make_input()
    _record(core, monkeypatch, lambda _cmd: None)

    cancel = threading.Event()
    cancel.set()

    with pytest.raises(core.CanceledError):
        core.convert(src, out, cancel=cancel)


def test_single_job_path_reports_failure(core, monkeypatch):
    """jobs=1 走非线程池分支，失败也必须向上抛出。"""
    src, out = _make_input()

    def behaviour(_cmd):
        raise core.FFmpegError("模拟失败")

    _record(core, monkeypatch, behaviour)

    with pytest.raises(core.FFmpegError):
        core.convert(src, out, cancel=threading.Event(), jobs=1)

# 这三个缺陷都不会让旧用例变红：它们只是「日志里的错因是假的」「取消被
# 报成成功」「每取消一次多跑一条注定失败的 ffmpeg」。所以下面的断言全部
# 落在日志文本、异常类型和「是否真的发生了回退」上，而不是只看有没有抛异常。


def test_hwdecode_fallback_log_reports_real_error(core, monkeypatch):
    """硬解回退日志必须给出 ffmpeg 的真实错因。

    回归背景：`_run_transcode` 的 defer_fail 分支曾读写未声明 nonlocal 的
    `first_error`，于是每次硬解失败，打进日志的都是
    `UnboundLocalError: cannot access local variable 'first_error' ...`，
    真实 ffmpeg 报错被顶掉。回退本身还能跑，用户只是永远查不出为什么硬解失败。
    """
    src, out = _make_input()
    logs = []

    def behaviour(cmd):
        if "hevc_mediacodec" in cmd:
            raise core.FFmpegError("模拟硬解失败")

    _record(core, monkeypatch, behaviour)
    core.convert(src, out, cancel=threading.Event(), log=logs.append)

    joined = "\n".join(logs)
    assert "cannot access local variable" not in joined, \
        "回退原因里出现了 Python 内部错误，真实 ffmpeg 报错被顶掉了"
    fallback = [m for m in logs if "硬件解码失败" in m]
    assert fallback, "没有打出硬解回退日志"
    assert any("模拟硬解失败" in m for m in fallback), \
        f"回退日志未包含真实错因：{fallback}"


def test_hwdecode_fallback_runs_for_every_task(core, monkeypatch):
    """一个任务回退成功，不得让兄弟任务被误判为「整批已失败」。

    回归背景：defer_fail 分支若把本任务的失败记进共享的 `first_error`，调用方
    的 `if first_error is not None: raise` 就会以为「兄弟任务已失败」，直接放弃
    自己的软解回退——硬解失败反而导致整批中止。
    """
    src, out = _make_input()

    def behaviour(cmd):
        if "hevc_mediacodec" in cmd:
            raise core.FFmpegError("模拟硬解失败")

    calls = _record(core, monkeypatch, behaviour)

    core.convert(src, out, cancel=threading.Event())

    hw = [c for c in calls if "hevc_mediacodec" in c]
    sw = [c for c in calls if "hevc_mediacodec" not in c]
    assert len(hw) == 2, "主视频与预览都应先尝试硬解"
    assert len(sw) == 2, "两者都应各自回退到软解，而不是整批中止"


def test_cancel_during_hwdecode_fallback_raises_canceled(core, monkeypatch):
    """硬解失败后用户在软解阶段取消，必须抛 CanceledError 而不是报成功。

    回归背景：并行驱动用 `except BaseException: pass` 吞掉所有异常、再靠
    `first_error` 汇总。取消一旦不再写进 `first_error`，就变成
    「用户点了取消，convert() 却正常返回两个输出路径」。
    """
    src, out = _make_input()
    cancel = threading.Event()
    hw_failed = []

    def behaviour(cmd):
        if "hevc_mediacodec" in cmd and not hw_failed:
            hw_failed.append(cmd)
            raise core.FFmpegError("模拟硬解失败")
        cancel.set()
        raise core.CanceledError("已取消")

    _record(core, monkeypatch, behaviour)

    with pytest.raises(core.CanceledError):
        core.convert(src, out, cancel=cancel)


def test_cancel_during_hwencode_does_not_retry_software(core, monkeypatch):
    """用户取消不是编码器故障，不应再补一次注定被取消的软编。

    回归背景：`CanceledError` 是 `Exception` 的子类，曾被 `except BaseException`
    当成「MediaCodec 硬编失败」，于是每取消一次就多跑一条软编 ffmpeg。
    """
    src, out = _make_input()
    cancel = threading.Event()
    logs = []

    def behaviour(_cmd):
        cancel.set()
        raise core.CanceledError("已取消")

    _record(core, monkeypatch, behaviour)

    with pytest.raises(core.CanceledError):
        core.convert(src, out, cancel=cancel, jobs=1,
                     encoder=("hevc_mediacodec", "h264_mediacodec", "MediaCodec"),
                     log=logs.append)

    assert not any("改用软件编码重试" in m for m in logs), \
        f"取消被当成了硬编失败并触发软编重试：{logs}"


def test_cancel_during_software_retry_keeps_sibling_error(core, monkeypatch):
    """软编回退阶段被取消，不能顶掉兄弟任务真实的失败原因。

    回归背景：`_fail()` 会把任何异常记成 `first_error`。取消若也走 `_fail()`，
    并行汇总时用户看到的会是「已取消」，而不是另一路真正失败的 ffmpeg 报错。
    """
    src, out = _make_input()
    cancel = threading.Event()

    def behaviour(cmd):
        if "hevc_mediacodec" in cmd:
            raise core.FFmpegError("模拟硬解失败")
        cancel.set()
        raise core.CanceledError("已取消")

    _record(core, monkeypatch, behaviour)

    with pytest.raises(core.CanceledError):
        core.convert(src, out, cancel=cancel, jobs=1)


def test_hwencode_failure_falls_back_to_software(core, monkeypatch):
    """硬编失败应改用软件编码重试，且不报取消。

    MediaCodec 的 i-frame-interval 只能整数秒，拿不到相机要求的 16 帧密集
    关键帧；这条路径必须能自动降级到 libx265/libx264。
    """
    src, out = _make_input()
    cancel = threading.Event()
    logs = []

    def behaviour(cmd):
        # 注意：cmd 是参数列表，`"mediacodec" in cmd` 只做「整元素相等」，
        # 永远匹配不到 "hevc_mediacodec"，必须逐元素做子串判断。
        if any("mediacodec" in a for a in cmd):
            raise core.FFmpegError("模拟硬编失败")

    calls = _record(core, monkeypatch, behaviour)

    core.convert(src, out, cancel=cancel, jobs=1,
                 encoder=("hevc_mediacodec", "h264_mediacodec", "MediaCodec"),
                 log=logs.append)

    assert any(any("mediacodec" in a for a in c) for c in calls), "应先尝试硬编"
    assert any(all("mediacodec" not in a for a in c) for c in calls), "硬编失败后应回退软编"
    assert not cancel.is_set(), "可恢复的硬编失败不应置位取消"
    assert any("改用软件编码重试" in m for m in logs)


def test_hwencode_nonuniform_gop_falls_back_to_software(core, monkeypatch):
    """硬编成功但关键帧间隔不恒定，必须改软编重跑。

    回归背景：MediaCodec 的 i-frame-interval 只接受整数秒，且完全不读
    -sc_threshold 0。厂商编码器在场景切换处额外插 IDR 时，整片的实际间隔
    不止一个值，而 AMBA[53] 只能写一个数。写进去的值对不上，相机按它抽帧
    就会失败——表现为「文件有、缩略图没有」，不抛任何异常。
    """
    src, out = _make_input()
    cancel = threading.Event()
    logs = []
    calls = _record(core, monkeypatch, lambda _cmd: None)
    # 硬编产物间隔不恒定：前段 60 帧一个关键帧，场景切换后 120 帧一个。
    monkeypatch.setattr(core, "_gop_uniform_of", lambda _p: (60, False))

    core.convert(src, out, cancel=cancel, jobs=1,
                 encoder=("hevc_mediacodec", "h264_mediacodec", "MediaCodec"),
                 log=logs.append)

    assert any(any("mediacodec" in a for a in c) for c in calls), "应先尝试硬编"
    assert any(all("mediacodec" not in a for a in c) for c in calls), \
        "间隔不恒定后应回退软编"
    assert any("关键帧间隔不恒定" in m for m in logs), \
        f"应打出间隔不恒定的回退日志：{logs}"
    assert not cancel.is_set(), "可恢复的间隔问题不应置位取消"


def test_hwencode_uniform_gop_keeps_hardware_result(core, monkeypatch):
    """硬编产物间隔恒定时必须保留硬编结果，不得无谓重跑。"""
    src, out = _make_input()
    logs = []
    calls = _record(core, monkeypatch, lambda _cmd: None)
    monkeypatch.setattr(core, "_gop_uniform_of", lambda _p: (60, True))

    core.convert(src, out, cancel=threading.Event(), jobs=1,
                 encoder=("hevc_mediacodec", "h264_mediacodec", "MediaCodec"),
                 log=logs.append)

    assert any(any("mediacodec" in a for a in c) for c in calls), "应走硬编"
    assert not any("关键帧间隔不恒定" in m for m in logs), \
        "间隔恒定不应触发软编回退"


def test_gop_uniform_check_skipped_for_software_encoding(core, monkeypatch):
    """软编路径不需要校验：libx265 的 keyint 是精确的帧数，不会漂。"""
    src, out = _make_input()
    probed = []

    def spy(path):
        probed.append(path)
        return 60, True

    monkeypatch.setattr(core, "_gop_uniform_of", spy)
    _record(core, monkeypatch, lambda _cmd: None)

    core.convert(src, out, cancel=threading.Event(), jobs=1,
                 encoder=("software", "", "software"))

    assert not probed, "软编不应触发关键帧间隔校验"


def test_hwencode_gop_mismatch_warns_but_keeps_result(core, monkeypatch):
    """间隔恒定但与模板不同时，保留硬编结果但必须告警。

    ace_pro_2 主轨要求 gop 16，MediaCodec 的 i-frame-interval 只能整数秒，
    60fps 下最小 1 秒 = 60 帧。这是接口约束、不是 bug，所以不能回退重跑
    （回退也拿不到 16）；但也不能静默——AMBA[53] 会写入实测值，相机是否
    接受非模板间隔未经验证，用户有权知道。
    """
    src, out = _make_input()
    logs = []
    calls = _record(core, monkeypatch, lambda _cmd: None)
    monkeypatch.setattr(core, "_gop_uniform_of", lambda _p: (60, True))

    core.convert(src, out, cancel=threading.Event(), jobs=1,
                 encoder=("hevc_mediacodec", "h264_mediacodec", "MediaCodec"),
                 log=logs.append)

    joined = "\n".join(logs)
    assert "与模板要求的" in joined, f"应告警间隔与模板不符：{logs}"
    assert "切回「自动」" in joined, f"应提示改回软编：{logs}"
    # 不能因为「对不上模板」就回退：软编重跑同样要花时间，而硬编产物是自洽的。
    assert any(all("mediacodec" not in a for a in c) for c in calls) is False, \
        "间隔恒定不应触发软编回退"


def test_gop_mismatch_warning_absent_when_gop_matches_template(core, monkeypatch):
    """间隔恰好等于模板时不该有多余告警（go_ultra 的 LRV gop 10 就会命中）。"""
    src, out = _make_input()
    logs = []
    _record(core, monkeypatch, lambda _cmd: None)
    monkeypatch.setattr(core, "_gop_uniform_of", lambda _p: (16, True))

    core.convert(src, out, cancel=threading.Event(), jobs=1,
                 encoder=("hevc_mediacodec", "h264_mediacodec", "MediaCodec"),
                 log=logs.append)

    assert not any("与模板要求的" in m for m in logs), \
        f"间隔与模板一致不应告警：{logs}"


def test_hwencode_unmeasurable_gop_warns_instead_of_passing_silently(
        core, monkeypatch):
    """量不出关键帧间隔时必须告警，不能静默放行。

    回归背景：_gop_uniform_of() 自己把异常吃成 (0, False)，调用方曾用
    try/except 再包一层，那个 except 永远不可达；而 (0, False) 又同时不满足
    「不恒定」和「与模板不同」两个条件，于是一条告警都不打。
    """
    src, out = _make_input()
    logs = []
    calls = _record(core, monkeypatch, lambda _cmd: None)
    monkeypatch.setattr(core, "_gop_uniform_of", lambda _p: (0, False))

    core.convert(src, out, cancel=threading.Event(), jobs=1,
                 encoder=("hevc_mediacodec", "h264_mediacodec", "MediaCodec"),
                 log=logs.append)

    assert any("无法量出" in m for m in logs), f"量不出来必须告警：{logs}"
    assert not any("关键帧间隔不恒定" in m for m in logs), "量不出来不等于不恒定"
    # 软编重跑会写一条 libx265 的 VID 命令，这里必须没有。
    assert not any("libx265" in " ".join(c) for c in calls), \
        "量不出来不应触发软编重跑"


def test_gop_check_skipped_when_hwencode_already_fell_back(core, monkeypatch):
    """硬编失败、内部已回退软编时，不该再对软编产物校验。

    否则会整文件多读一遍（白花 IO），日志还会反过来写「硬编产物不合格」。
    """
    src, out = _make_input()
    probed = []

    def spy(path):
        probed.append(path)
        return 16, True

    def behaviour(cmd):
        if any("mediacodec" in a for a in cmd) and any(
                a in ("hevc_mediacodec", "h264_mediacodec") for a in cmd):
            raise core.FFmpegError("模拟硬编失败")

    monkeypatch.setattr(core, "_gop_uniform_of", spy)
    _record(core, monkeypatch, behaviour)

    core.convert(src, out, cancel=threading.Event(), jobs=1,
                 encoder=("hevc_mediacodec", "h264_mediacodec", "MediaCodec"))

    assert not probed, "已回退软编后不应再校验关键帧间隔"
