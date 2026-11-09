"""android_bridge 取消链路的离线回归。

不依赖 ffmpeg / 相机 / Android：把 insta_core 的导入函数换成桩，
验证 `new_cancel_event()` → `run_import(cancel=...)` → JSON 契约
这一层不丢取消信号，且取消与失败在返回值上可区分。

为什么重要：Kotlin 侧完全靠 `canceled` 字段决定显示「已取消」还是
「失败」，以及是否把半成品写回相机卡。这个字段一旦丢失或与 ok 混同，
用户会看到「已取消」被报成成功，或者取消被当成失败吓一跳。
"""

import json
import os
import sys
import threading

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ANDROID_PY = os.path.abspath(
    os.path.join(HERE, "..", "..", "android", "app", "src", "main", "python")
)
if ANDROID_PY not in sys.path:
    sys.path.insert(0, ANDROID_PY)

import android_bridge as br  # noqa: E402
import insta_core as ic  # noqa: E402


class _FakeCore:
    """冒充 insta_core：只需要 CanceledError 与 import_with_inst。"""

    __version__ = "test"
    CanceledError = ic.CanceledError

    def __init__(self, behaviour):
        self._behaviour = behaviour
        self.seen_cancel = "unset"

    def set_prefer_hardware(self, _enabled):
        pass

    def import_with_inst(self, source, card_root, log=None, progress=None,
                         cover=None, cancel=None):
        self.seen_cancel = cancel
        return self._behaviour(cancel)


@pytest.fixture()
def bridge(monkeypatch):
    """把 _core 换成桩，保留 android_bridge 的真实取消逻辑。"""
    def install(behaviour):
        fake = _FakeCore(behaviour)
        monkeypatch.setattr(br, "_core", fake)
        return fake
    return install


def _ok_result():
    return {
        "main": "/tmp/VID_20260101_000000_001.mp4",
        "proxy": "/tmp/LRV_20260101_000000_001.lrv",
        "inst_ok": True,
        "inst_error": "",
        "index_error": "",
        "registered": ["VID_20260101_000000_001.mp4"],
    }


def test_new_cancel_event_is_a_threading_event():
    ev = br.new_cancel_event()
    assert isinstance(ev, threading.Event)
    assert not ev.is_set()


def test_run_import_passes_cancel_into_core(bridge):
    """取消事件必须真的传到 import_with_inst，否则取消按钮是装饰品。"""
    fake = bridge(lambda cancel: _ok_result())
    ev = br.new_cancel_event()

    out = json.loads(br.run_import("in.mp4", "/card", cancel=ev))

    assert fake.seen_cancel is ev
    assert out["ok"] is True
    assert out["canceled"] is False


def test_run_import_without_cancel_passes_none(bridge):
    """不传 cancel 时不应凭空造一个事件——旧调用点必须继续可用。"""
    fake = bridge(lambda cancel: _ok_result())

    out = json.loads(br.run_import("in.mp4", "/card"))

    assert fake.seen_cancel is None
    assert out["ok"] is True


def test_run_import_reports_canceled_separately_from_failure(bridge):
    """取消要带 canceled=True；失败要带 canceled=False。

    Kotlin 侧只看这个字段区分「用户主动停」和「出错了」。
    """
    def raise_canceled(_cancel):
        raise ic.CanceledError("已取消")

    bridge(raise_canceled)
    out = json.loads(br.run_import("in.mp4", "/card",
                                   cancel=br.new_cancel_event()))

    assert out["ok"] is False
    assert out["canceled"] is True
    assert "CanceledError" in out["error"]


def test_run_import_failure_is_not_marked_canceled(bridge):
    def boom(_cancel):
        raise RuntimeError("编码器炸了")

    bridge(boom)
    out = json.loads(br.run_import("in.mp4", "/card",
                                   cancel=br.new_cancel_event()))

    assert out["ok"] is False
    assert out["canceled"] is False
    assert "编码器炸了" in out["error"]
    assert out.get("trace")


def test_cancel_event_set_by_other_thread_is_visible(bridge):
    """Kotlin 在 UI 线程 set，Python 在 IO 线程读——必须跨线程可见。"""
    seen = {}

    def behaviour(cancel):
        # 模拟 ffmpeg 正在跑：另一个线程置位后，这里必须能读到。
        threading.Timer(0.05, cancel.set).start()
        deadline = threading.Event()
        for _ in range(100):
            if cancel.wait(0.01):
                seen["canceled"] = True
                break
        if not seen.get("canceled"):
            seen["canceled"] = False
        return _ok_result()

    bridge(behaviour)
    ev = br.new_cancel_event()
    br.run_import("in.mp4", "/card", cancel=ev)

    assert seen["canceled"] is True
    assert ev.is_set()
