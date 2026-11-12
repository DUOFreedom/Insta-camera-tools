# -*- coding: utf-8 -*-
"""头像地址与 star 状态检查。

这里最要紧的一条：检查失败绝不能影响任何功能。网络不通、接口限流、返回
脏数据，都只能让按钮停在「确认不了」，不能抛到界面上，也不能把欢迎窗卡住。
"""

import json
import os
import re
import sys
import time

import pytest

DESKTOP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if DESKTOP not in sys.path:
    sys.path.insert(0, DESKTOP)

import consent  # noqa: E402
import star  # noqa: E402

QML = os.path.join(DESKTOP, "qml")
CJK = re.compile(r"[\u4e00-\u9fff]")


@pytest.fixture()
def state_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("INSTA_STATE_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture()
def bridge(state_dir):
    pytest.importorskip("PySide6.QtCore")
    import bridge as bridge_mod

    return bridge_mod.Bridge()


def _wait_state(obj, wanted, timeout=3.0):
    """等后台线程把状态写回来。线程里 sleep 已被测试改成 0。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if obj.starState in wanted:
            return obj.starState
        time.sleep(0.01)
    return obj.starState


# ---------------------------------------------------------------- 接口解析


def test_fetch_stars_returns_count(monkeypatch):
    monkeypatch.setattr(star, "_get_json", lambda url, timeout=None: {
        "stargazers_count": 42, "full_name": "DUOFreedom/Insta-camera-tools"})
    assert star.fetch_stars() == 42


def test_fetch_stars_rejects_bool(monkeypatch):
    # bool 是 int 的子类，{"stargazers_count": true} 不能被当成 1。
    monkeypatch.setattr(star, "_get_json", lambda url, timeout=None: {
        "stargazers_count": True})
    assert star.fetch_stars() is None


def test_fetch_stars_handles_missing_and_wrong_shape(monkeypatch):
    monkeypatch.setattr(star, "_get_json", lambda url, timeout=None: {})
    assert star.fetch_stars() is None
    monkeypatch.setattr(star, "_get_json", lambda url, timeout=None: [1, 2, 3])
    assert star.fetch_stars() is None
    monkeypatch.setattr(star, "_get_json",
                        lambda url, timeout=None: {"stargazers_count": "12"})
    assert star.fetch_stars() is None


def test_fetch_stars_swallows_network_errors(monkeypatch):
    def boom(url, timeout=None):
        raise OSError("no route to host")

    monkeypatch.setattr(star, "_get_json", boom)
    assert star.fetch_stars() is None


def test_fetch_stars_swallows_urlopen_failure(monkeypatch):
    # 走到真正的 _get_json，只把 urlopen 换掉：确认这层异常也被吃掉。
    def boom(*args, **kwargs):
        raise TimeoutError("timed out")

    monkeypatch.setattr(star.urllib.request, "urlopen", boom)
    assert star.fetch_stars() is None


# ---------------------------------------------------------------- 本地记录


def test_starred_state_roundtrip(state_dir):
    assert star.is_starred() is False
    path = star.mark_starred()
    assert os.path.isfile(path)
    assert star.is_starred() is True
    data = json.loads(open(path, encoding="utf-8").read())
    assert data["starred"] is True
    assert re.match(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d$", data["seen_at"])


def test_mark_starred_leaves_no_temp_file(state_dir):
    star.mark_starred()
    leftovers = [n for n in os.listdir(state_dir) if n.endswith(".tmp")]
    assert leftovers == []


def test_broken_star_file_is_treated_as_unstarred(state_dir):
    path = os.path.join(str(state_dir), "starred.json")
    open(path, "w", encoding="utf-8").write("{not json")
    assert star.is_starred() is False
    # 坏文件不该挡住重新写入。
    star.mark_starred()
    assert star.is_starred() is True


# ---------------------------------------------------------------- 状态机


def test_avatar_url_points_at_github(bridge):
    assert bridge.authorAvatarUrl == star.AVATAR_URL
    assert "avatars.githubusercontent.com" in bridge.authorAvatarUrl


def test_initial_state_is_idle(bridge):
    assert bridge.starState == "idle"
    assert bridge.starCount == 0
    assert bridge.starDone is False


def test_already_starred_reads_from_disk(state_dir):
    star.mark_starred()
    pytest.importorskip("PySide6.QtCore")
    import bridge as bridge_mod

    fresh = bridge_mod.Bridge()
    #  记住的是「他已经点过」，不是「现在正在读」——所以状态仍是 idle。
    assert fresh.starDone is True
    assert fresh.starState == "idle"


def test_refresh_reads_count(bridge, monkeypatch):
    monkeypatch.setattr(star, "fetch_stars", lambda timeout=None: 12)

    bridge.refreshStars()
    assert _wait_state(bridge, ("ok", "unknown")) == "ok"
    assert bridge.starCount == 12


def test_refresh_unknown_when_network_is_down(bridge, monkeypatch):
    monkeypatch.setattr(star, "fetch_stars", lambda timeout=None: None)

    bridge.refreshStars()
    assert _wait_state(bridge, ("ok", "unknown")) == "unknown"
    assert bridge.starCount == 0


def test_refresh_ignores_second_call_while_loading(bridge, monkeypatch):
    calls = []
    release = []

    def slow(timeout=None):
        calls.append(1)
        #  第一轮卡住不返回，好让第二次调用撞上 loading。
        while not release:
            time.sleep(0.01)
        return 5

    monkeypatch.setattr(star, "fetch_stars", slow)

    bridge.refreshStars()
    assert bridge.starState == "loading"
    bridge.refreshStars()
    assert bridge.starState == "loading"
    assert len(calls) == 1

    release.append(1)
    assert _wait_state(bridge, ("ok", "unknown")) == "ok"


def test_open_author_page_opens_and_marks(bridge, monkeypatch):
    seen = []
    monkeypatch.setattr(bridge, "_open_url", lambda url: seen.append(url) or True)

    assert bridge.openAuthorPage() is True
    assert seen == [bridge.authorUrl]
    assert bridge.starDone is True
    #  点过就落盘，下次启动不再问。
    assert star.is_starred() is True


def test_open_author_page_reports_failure(bridge, monkeypatch):
    monkeypatch.setattr(bridge, "_open_url", lambda url: False)

    assert bridge.openAuthorPage() is False
    assert bridge.starDone is False
    assert star.is_starred() is False
    assert bridge.lastError


def test_open_url_prefers_startfile_on_windows(bridge, monkeypatch):
    opened = []
    #  bridge 是实例，模块要从 sys.modules 取。
    mod = sys.modules["bridge"]
    monkeypatch.setattr(mod.os, "startfile", opened.append, raising=False)
    monkeypatch.setattr(mod.sys, "platform", "win32")

    assert bridge._open_url(bridge.authorUrl) is True
    assert opened == [bridge.authorUrl]


# ---------------------------------------------------------------- QML 守卫


def _read(name):
    path = os.path.join(QML, name)
    assert os.path.isfile(path), "%s 不见了" % name
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def test_avatar_is_a_network_image_with_fallback():
    src = _read("WelcomeDialog.qml")
    assert "assets/avatar.png" in src
    # 圆形靠遮罩剪，Item.clip 只按矩形裁。
    assert "ShaderEffect" in src
    # 图没回来时用首字母顶着，不能是空框。
    assert 'text: "D"' in src


def test_star_button_reflects_done_state():
    src = _read("WelcomeDialog.qml")
    for token in ("bridge.starDone", "bridge.openAuthorPage()",
                  "bridge.refreshStars()", "bridge.starCount"):
        assert token in src, token
    # 旧的「点完盯着星数看一分钟」那套是死代码，别留回来。
    #  注释里提到这两个名字是在解释为什么不用，所以先剥掉注释再查。
    code = chr(10).join(line.split("//")[0] for line in src.splitlines())
    assert "startStarCheck" not in code
    assert "Qt.openUrlExternally" not in code
    assert "bridge.openAuthorPage()" in code


def test_star_count_is_read_once_on_author_page():
    src = _read("WelcomeDialog.qml")
    # 翻到最后一页就自动读一次，不需要用户先点开仓库。
    assert "onPageChanged" in src
    assert "page === pageCount - 1" in src
    assert "starRequested" in src


def test_titlebar_drag_is_hand_rolled_with_damping():
    src = _read("TitleBar.qml")
    assert "function damp(" in src
    # 手接管拖动之后不该在普通按下时再叫系统移动，否则位置由系统写，
    # 阻尼根本拦不住。
    pressed = src.split("onPressed:", 1)[1].split("onPositionChanged", 1)[0]
    assert "startSystemMove" in pressed  # 只剩最大化还原那一路
    assert "visibility === Window.Maximized" in pressed

def test_titlebar_drag_limits_and_settles():
    src = _read("TitleBar.qml")
    # QQuickScreenInfo 上没有 availableGeometry，读出来是 undefined，
    # 赋给 rect 静默失败会让 area 停在 0x0，整窗口被夹死、表现是「拖不动」。
    #   注释里提到过这个属性名（说明为什么不能用），所以只查真正的取用点。
    assert ".screen.availableGeometry" not in src
    assert "s.availableGeometry" not in src
    assert "desktopAvailableWidth" in src
    assert "desktopAvailableHeight" in src
    # 松手回收必须用不带阻尼的硬夹：limitX/limitY 会给已经阻尼过的
    # 位移再来一次衰减，停在离边缘二十来像素的地方。
    assert "settleTargetX = Math.round(clampX(" in src
    assert "settleTargetY = Math.round(clampY(" in src
    # 每帧只走 40% 再取整，剩 1 px 时会被舍回原值、定时器走不到头。
    assert "if (Math.abs(dx) <= 1 && Math.abs(dy) <= 1)" in src
    # 贴顶最大化看光标是否顶到屏幕上沿，不看位移阈值：
    # 窗口本身占满高度时能拖出的位移取决于按在标题栏哪个位置。
    assert "pointerY <= area.y + 1" in src


# ---------------------------------------------------------------- 应用内阻尼


def _flickables():
    return ("main.qml", "InputFileView.qml", "WelcomeDialog.qml")


def test_drag_damping_component_exists():
    src = _read("DragDamping.qml")
    assert "function damp(" in src
    # 只压回「超出量」，超出为零时偏移必须为零，否则内容会一直偏。
    assert "over <= 0 ? 0 :" in src
    assert "contentX" in src and "contentY" in src


def test_every_scroll_area_uses_drag_over_bounds():
    for name in _flickables():
        src = _read(name)
        assert "DragDamping {" in src, name
        assert "contentItem.transform" in src, name
        assert "DragOverBounds" in src, name
        # 停在边界就拖不动，也就没有阻尼可言。
        assert "StopAtBounds" not in src, name


def test_main_content_area_is_a_plain_flickable():
    src = _read("main.qml")
    # ScrollView 把滚动交给内部 Flickable，外面拿不到 contentY，做不了阻尼。
    assert "ScrollView {" not in src
    assert "id: scroll" in src
    assert "contentHeight: pageColumn.height" in src
