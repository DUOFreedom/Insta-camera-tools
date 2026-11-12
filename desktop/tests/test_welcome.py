"""首次启动欢迎窗（使用协议 / 使用须知 / 作者主页）的回归测试。

这里钉的是三件事：

1. 「看过就不再弹」只靠一个版本号。写进 `consent` 的 JSON 而不是 QSettings，
   是为了能用 `INSTA_STATE_DIR` 把状态顶到临时目录——测试不能去动真实用户
   的 %LOCALAPPDATA%。
2. 状态文件坏掉、写不进去，都不能让人卡在欢迎页前面。坏文件当成没看过
   （最多再弹一次），写入失败只记一行日志。
3. QML 那边必须真的挂上、真的有三页。上一轮机型下拉就是「代码写好了但没人
   接线」，只测 Python 侧看不出来。
"""

import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
DESKTOP = os.path.abspath(os.path.join(HERE, ".."))
if DESKTOP not in sys.path:
    sys.path.insert(0, DESKTOP)

import consent  # noqa: E402

QML_DIR = os.path.join(DESKTOP, "qml")


@pytest.fixture()
def state_dir(tmp_path, monkeypatch):
    """把状态目录顶到临时目录，顺带保证每个用例从「没看过」开始。"""
    target = tmp_path / "state"
    monkeypatch.setenv("INSTA_STATE_DIR", str(target))
    return target


def _read(name: str) -> str:
    with open(os.path.join(QML_DIR, name), encoding="utf-8") as fh:
        return fh.read()


# ---------- consent：什么时候该弹 ----------

def test_shows_when_nothing_recorded(state_dir):
    assert not state_dir.exists()
    assert consent.should_show() is True


def test_mark_seen_stops_it_showing(state_dir):
    path = consent.mark_seen()
    assert os.path.isfile(path)
    with open(path, encoding="utf-8") as fh:
        payload = json.load(fh)
    assert payload["version"] == consent.CONSENT_VERSION
    assert payload["seen_at"]
    assert consent.should_show() is False


def test_version_bump_brings_it_back(state_dir, monkeypatch):
    """协议文字改了就得让老用户重新看一遍，否则免责声明白加。"""
    consent.mark_seen()
    assert consent.should_show() is False
    monkeypatch.setattr(consent, "CONSENT_VERSION", consent.CONSENT_VERSION + 1)
    assert consent.should_show() is True


def test_corrupt_state_file_counts_as_unseen(state_dir):
    os.makedirs(state_dir, exist_ok=True)
    with open(os.path.join(state_dir, "welcome.json"), "w", encoding="utf-8") as fh:
        fh.write("{not json at all")
    assert consent.should_show() is True
    # 再写一次就要能覆盖掉坏文件，不能一直卡在「每次启动都弹」。
    consent.mark_seen()
    assert consent.should_show() is False


def test_version_field_of_wrong_type_is_tolerated(state_dir):
    os.makedirs(state_dir, exist_ok=True)
    with open(os.path.join(state_dir, "welcome.json"), "w", encoding="utf-8") as fh:
        json.dump({"version": "wat"}, fh)
    assert consent.should_show() is True


def test_mark_seen_leaves_no_temp_file(state_dir):
    """写一半断电不能留下半个 JSON，也不能留下 .tmp 残文件。"""
    consent.mark_seen()
    leftovers = [n for n in os.listdir(state_dir) if n.endswith(".tmp")]
    assert leftovers == []


def test_reset_makes_it_show_again(state_dir):
    consent.mark_seen()
    consent.reset()
    assert consent.should_show() is True
    consent.reset()  # 文件已经不在了也不能抛


# ---------- Bridge：QML 看到的那几个属性 ----------

@pytest.fixture()
def bridge(state_dir):
    pytest.importorskip("PySide6.QtCore")
    import bridge as bridge_mod
    return bridge_mod.Bridge()


def test_bridge_reports_welcome_needed_on_first_run(bridge):
    assert bridge.welcomeNeeded is True


def test_bridge_mark_welcome_seen_flips_it_and_persists(bridge, state_dir):
    bridge.markWelcomeSeen()
    assert bridge.welcomeNeeded is False
    assert consent.should_show() is False
    # 新进程（新建一个 Bridge）读盘也应该是 False。
    import bridge as bridge_mod
    assert bridge_mod.Bridge().welcomeNeeded is False


def test_bridge_show_welcome_reopens_it(bridge):
    bridge.markWelcomeSeen()
    assert bridge.welcomeNeeded is False
    bridge.showWelcome()
    assert bridge.welcomeNeeded is True


def test_bridge_author_url_is_the_repo(bridge):
    assert bridge.authorUrl == "https://github.com/DUOFreedom/Insta-camera-tools"


# ---------- QML：真的挂上了、真的三页 ----------

def test_welcome_dialog_qml_exists():
    assert os.path.isfile(os.path.join(QML_DIR, "WelcomeDialog.qml"))


def test_main_qml_mounts_the_welcome_dialog():
    src = _read("main.qml")
    assert "WelcomeDialog {" in src
    # 挂载时没接线的话，关上就不记录，下次开机继续弹。
    assert "bridge.markWelcomeSeen()" in src
    # 启动时的打开条件
    assert "bridge.welcomeNeeded" in src


def test_welcome_dialog_has_three_pages():
    src = _read("WelcomeDialog.qml")
    assert "pageCount: 3" in src
    # 三块内容各自用 page 控制可见性，逐页数一遍确认没有被删成一页。
    for index in (0, 1, 2):
        assert src.count("visible: root.page === %d\n" % index) == 1
    # 最后一页的两个按钮：点 star 与「我真的没有账号」，少一个就没法关。
    assert "去点个 star" in src
    assert "算了" in src


def test_last_page_buttons_fit_one_row():
    """页脚只有一行：左侧圆点 + 右侧三个按钮，加起来不能超过面板内宽（412 DIP）。

    英文按字面译成 "I really don't have a GitHub account" 时，三个按钮比面板
    还宽，Back 会被挤到左边界外面——真机上截过图才发现。这里用字数当代理指标，
    超了就说明该换短标签（或者改版式），不要指望约束会被布局自动吃掉。
    """
    import i18n

    budget = {"zh": 16, "en": 24}
    for key in ("上一步", "去点个 star", "我真的没有 GitHub 账号"):
        for lang in ("zh", "en"):
            label = i18n.EN_TEXT[key] if lang == "en" else key
            assert len(label) <= budget[lang], (
                "%s 下的按钮文案太长，页脚一行放不下：%r" % (lang, label)
            )
