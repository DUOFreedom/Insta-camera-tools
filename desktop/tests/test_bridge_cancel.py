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
    """冒充 insta_core：只需要 CanceledError、template_from_names 与 import_with_inst。"""

    __version__ = "test"
    CanceledError = ic.CanceledError
    # run_import 用它做机型白名单校验，真核心里有这张表。
    CAMERA_PRESETS = {"auto": {"spec": None}, "ace_pro_2": {"spec": None},
                      "go_ultra": {"spec": None}}

    def __init__(self, behaviour, template_ok=True):
        self._behaviour = behaviour
        self._template_ok = template_ok
        self.seen_cancel = "unset"
        self.seen_template = "unset"
        self.seen_model = "unset"
        self.seen_template_names = "unset"

    def set_prefer_hardware(self, _enabled):
        pass

    def template_from_names(self, card_root, vid_name, lrv_name):
        self.seen_template_names = (card_root, vid_name, lrv_name)
        if not self._template_ok:
            return None
        return ("/card/DCIM/Camera01/" + vid_name,
                "/card/DCIM/Camera01/" + lrv_name,
                b"\x0a\x0e" + b"0" * 14)

    def import_with_inst(self, source, card_root, template=None, log=None,
                         progress=None, cover=None, cancel=None,
                         model_override="auto"):
        self.seen_cancel = cancel
        self.seen_template = template
        self.seen_model = model_override
        return self._behaviour(cancel)


@pytest.fixture()
def bridge(monkeypatch):
    """把 _core 换成桩，保留 android_bridge 的真实取消逻辑。"""
    def install(behaviour, template_ok=True):
        fake = _FakeCore(behaviour, template_ok=template_ok)
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


def test_run_import_passes_template_names_into_core(bridge):
    """Kotlin 指定了模板名，就必须按名字取，不能退回去让核心猜。

    镜像目录里上一轮的产物同样带 inst box，猜错的后果是相机不认且不报错。
    """
    fake = bridge(lambda _cancel: _ok_result())

    out = json.loads(br.run_import(
        "in.mp4", "/card",
        template_names=("VID_20240101_090000_000.mp4",
                        "LRV_20240101_090000_000.lrv"),
    ))

    assert out["ok"] is True
    assert fake.seen_template_names[1:] == (
        "VID_20240101_090000_000.mp4", "LRV_20240101_090000_000.lrv")
    assert fake.seen_template is not None, "取到的模板对必须传给 import_with_inst"


def test_run_import_without_template_names_lets_core_decide(bridge):
    """不传模板名时保持旧行为：template=None，由核心自己找。"""
    fake = bridge(lambda _cancel: _ok_result())

    br.run_import("in.mp4", "/card")

    assert fake.seen_template is None
    assert fake.seen_template_names == "unset"


def test_run_import_rejects_unusable_template_pair(bridge):
    """指定了名字但取不到模板对时，必须直接失败，不能硬着头皮跑。"""
    fake = bridge(lambda _cancel: _ok_result(), template_ok=False)

    # 显式传 lang：android 那份 i18n 的 detect() 没有系统语言探测，兜底英文
    # （真机上语言由 Kotlin 的 langTag 传下来），不传就断言不到中文文案。
    out = json.loads(br.run_import(
        "in.mp4", "/card", template_names=("VID_x.mp4", "LRV_x.lrv"),
        lang="zh"))

    assert out["ok"] is False
    assert out["canceled"] is False
    assert "模板对不可用" in out["error"]
    assert fake.seen_template == "unset", "模板不可用时不应继续调用导入"


# ============== 机型预设：run_import → import_with_inst 的透传 ==============
#
# 这一层最容易出的错是「参数加了但没往下传」——界面选得动、日志里也看不出，
# 只有产物参数不对。所以断言落在 import_with_inst 实际收到的 kw 上。

def test_run_import_forwards_model_override(bridge):
    """选定的机型必须传到 import_with_inst，否则预设等于没选。"""
    fake = bridge(lambda _cancel: _ok_result())

    out = json.loads(br.run_import("in.mp4", "/card", model_override="go_ultra"))

    assert out["ok"] is True
    assert fake.seen_model == "go_ultra"


def test_run_import_defaults_to_auto(bridge):
    """不传时保持旧行为：auto（跟着卡里的真机原片量参数）。"""
    fake = bridge(lambda _cancel: _ok_result())

    br.run_import("in.mp4", "/card")

    assert fake.seen_model == "auto"


def test_run_import_rejects_unknown_model(bridge):
    """未知机型要在调用核心之前就拒掉，并说清是哪个值。

    静默回落到 auto 会让用户以为选了机型、其实没有。
    """
    fake = bridge(lambda _cancel: _ok_result())
    fake.CAMERA_PRESETS = {"auto": {}, "ace_pro_2": {}, "go_ultra": {}}

    out = json.loads(br.run_import("in.mp4", "/card", model_override="nope"))

    assert out["ok"] is False
    assert out["canceled"] is False
    assert "nope" in out["error"]
    assert fake.seen_model == "unset", "未知机型不应继续调用导入"


def test_run_import_accepts_known_models(bridge):
    """白名单里的三个值必须都能过——包括 auto 不查表也不报错。"""
    fake = bridge(lambda _cancel: _ok_result())
    fake.CAMERA_PRESETS = {"auto": {}, "ace_pro_2": {}, "go_ultra": {}}

    for code in ("auto", "ace_pro_2", "go_ultra"):
        out = json.loads(br.run_import("in.mp4", "/card", model_override=code))
        assert out["ok"] is True, code
        assert fake.seen_model == code
