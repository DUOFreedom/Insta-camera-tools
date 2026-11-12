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


def test_already_starred_starts_thanked(state_dir):
    star.mark_starred()
    pytest.importorskip("PySide6.QtCore")
    import bridge as bridge_mod

    fresh = bridge_mod.Bridge()
    assert fresh.starState == "thanked"


def test_check_turns_thanked_when_count_grows(bridge, monkeypatch):
    counts = iter([7, 8])
    monkeypatch.setattr(star, "POLL_INTERVAL", 0)
    monkeypatch.setattr(star, "POLL_ATTEMPTS", 1)
    monkeypatch.setattr(star, "fetch_stars", lambda timeout=None: next(counts))

    bridge.startStarCheck()
    assert _wait_state(bridge, ("thanked", "unchanged", "unknown")) == "thanked"
    assert bridge.starCount == 8
    assert star.is_starred() is True


def test_check_turns_unchanged_when_count_stays(bridge, monkeypatch):
    monkeypatch.setattr(star, "POLL_INTERVAL", 0)
    monkeypatch.setattr(star, "POLL_ATTEMPTS", 2)
    monkeypatch.setattr(star, "fetch_stars", lambda timeout=None: 9)

    bridge.startStarCheck()
    assert _wait_state(bridge, ("thanked", "unchanged", "unknown")) == "unchanged"
    # 没确认就不该写本地记录，下次还能再点一次。
    assert star.is_starred() is False


def test_check_turns_unknown_when_network_is_down(bridge, monkeypatch):
    monkeypatch.setattr(star, "POLL_INTERVAL", 0)
    monkeypatch.setattr(star, "POLL_ATTEMPTS", 1)
    monkeypatch.setattr(star, "fetch_stars", lambda timeout=None: None)

    bridge.startStarCheck()
    assert _wait_state(bridge, ("thanked", "unchanged", "unknown")) == "unknown"


def test_start_check_ignores_double_click_while_checking(bridge, monkeypatch):
    calls = []

    def slow(timeout=None):
        calls.append(1)
        return 5

    monkeypatch.setattr(star, "POLL_INTERVAL", 0.05)
    monkeypatch.setattr(star, "POLL_ATTEMPTS", 3)
    monkeypatch.setattr(star, "fetch_stars", slow)

    bridge.startStarCheck()
    state_after_first = bridge.starState
    bridge.startStarCheck()  # 检查中再点，不该再起一轮
    assert state_after_first == "checking"
    assert bridge.starState == "checking"


# ---------------------------------------------------------------- QML 守卫


def _read(name):
    path = os.path.join(QML, name)
    assert os.path.isfile(path), "%s 不见了" % name
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def test_avatar_is_a_network_image_with_fallback():
    src = _read("WelcomeDialog.qml")
    assert "bridge.authorAvatarUrl" in src
    # 圆形靠遮罩剪，Item.clip 只按矩形裁。
    assert "OpacityMask" in src
    # 图没回来时用首字母顶着，不能是空框。
    assert 'text: "D"' in src


def test_star_button_reflects_state():
    src = _read("WelcomeDialog.qml")
    for token in ("bridge.starState", "bridge.startStarCheck()",
                  "bridge.starCount"):
        assert token in src, token
    # 检查中禁止连点。
    assert 'enabled: bridge.starState !== "checking"' in src


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
