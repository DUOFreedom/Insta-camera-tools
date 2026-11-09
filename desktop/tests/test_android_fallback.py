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
    sys.path.insert(0, ANDROID_PY)

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
