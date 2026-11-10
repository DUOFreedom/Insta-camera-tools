"""QML 桥接层的回归测试：路径还原与关窗拦截。

这两条都是「只有 QML 版才会踩、而且踩了没人知道」的缺陷：

1. 路径用 `toString().replace("file:///", "")` 还原。`toString()` 默认
   PrettyDecoded，会把 `#` `%` `[` `]` `^` `` ` `` `{` `}` 这些在 Windows 上
   完全合法的字符转成 `%XX`，替换完文件就不存在了；UNC 路径
   `file://server/share` 只有两个斜杠，连前缀都剥不掉。表现是「一批文件
   加不进来」和「网络路径全废」。

2. 转换中点 × 直接关窗。worker 是 daemon 线程，进程退出时被直接丢弃，
   ffmpeg 变孤儿继续往卡里写，`set_awake(False)` 也不执行。经典版
   `gui.py` 的 closeEvent 修过这条路，QML 版一度丢了。
"""

import os
import sys
import threading

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
DESKTOP = os.path.abspath(os.path.join(HERE, ".."))
if DESKTOP not in sys.path:
    sys.path.insert(0, DESKTOP)

pytest.importorskip("PySide6.QtCore")
from PySide6.QtCore import QUrl  # noqa: E402

pytest.importorskip("PySide6.QtWidgets")
from PySide6.QtWidgets import QApplication  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def bridge(app):
    import bridge as bridge_mod
    return bridge_mod.Bridge()


@pytest.mark.parametrize("name", [
    "a#1.mp4", "a%1.mp4", "a[1].mp4", "a^1.mp4", "a`1.mp4", "a{1}.mp4",
    "a&1.mp4", "a 1.mp4", "视频 1.mp4", "a+1.mp4", "a'1.mp4",
])
def test_local_path_roundtrips_every_legal_windows_char(bridge, tmp_path, name):
    """合法文件名必须原样还原。

    `#` `%` 这几种是 toString() 会转义的，`&` 空格 中文是它不转义的 ——
    两边都测，避免修好一个坏另一个。
    """
    target = tmp_path / name
    target.write_bytes(b"x")
    url = QUrl.fromLocalFile(str(target))
    assert bridge.localPath(url) == str(target).replace("\\", "/")


def test_local_path_keeps_unc_host(bridge):
    """UNC 路径必须保留前两个斜杠。

    `file://server/share/a.mp4` 用 replace("file:///","") 一个字符都剥不掉，
    返回的还是 URI 本身。
    """
    got = bridge.localPath(QUrl("file://server/share/a.mp4"))
    assert got == "//server/share/a.mp4"


def test_worker_is_not_daemon(app, monkeypatch):
    """转换线程不能是 daemon。

    daemon 线程在进程退出时被直接丢弃 —— ffmpeg 变孤儿继续写卡，
    防休眠锁也不会解除。
    """
    import bridge as bridge_mod
    b = bridge_mod.Bridge()
    # start() 会先过一道 ffmpeg 可用性检查，桩掉它才能走到起线程那一步
    monkeypatch.setattr(bridge_mod.core, "ffmpeg_available", lambda: (True, "ok"))

    started = threading.Event()

    def slow_run(*_a, **_kw):
        started.set()
        threading.Event().wait(0.2)

    monkeypatch.setattr(b, "_run", slow_run)
    b._files = ["x.mp4"]
    b.start("/tmp/out", False, True, "自动")
    assert started.wait(2.0)
    assert b._worker is not None
    assert b._worker.daemon is False
    assert b.waitWorker(5000) is True


def test_wait_worker_returns_false_while_running(app):
    """线程还在跑时必须返回 False，否则关窗会把它丢掉。"""
    import bridge as bridge_mod
    b = bridge_mod.Bridge()
    gate = threading.Event()
    b._worker = threading.Thread(target=gate.wait, daemon=False)
    b._worker.start()
    try:
        assert b.waitWorker(50) is False
    finally:
        gate.set()
        b._worker.join(2)
    assert b.waitWorker(100) is True


def test_main_qml_uses_local_path_and_guards_close():
    """QML 侧必须走 localPath、并且拦关窗。

    QML 绑定没法在单测里跑，只能检查源码：`replace("file:///", "")`
    只要重新出现就是回归（它会弄坏 # % [ ] ^ ` { } 和全部 UNC 路径）；
    `onClosing` 消失则意味着转换中关窗又会留下孤儿 ffmpeg。
    """
    qml = os.path.join(DESKTOP, "qml", "main.qml")
    src = open(qml, encoding="utf-8").read()
    assert 'replace("file:///"' not in src, \
        "main.qml 又用 replace(\"file:///\") 还原路径了，改用 bridge.localPath(url)"
    assert src.count("bridge.localPath(") >= 4, "四处对话框都要走 bridge.localPath"
    assert "onClosing:" in src, "main.qml 缺少 onClosing，转换中关窗会留下孤儿 ffmpeg"
    assert "bridge.waitWorker(" in src, "关窗前要先等 worker 收尾"
