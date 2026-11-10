"""QML 桥接层的回归测试：路径还原与关窗拦截。

这两条都是「只有 QML 版才会踩、而且踩了没人知道」的缺陷：

1. 路径用 `toString().replace("file:///", "")` 还原。`toString()` 默认
   PrettyDecoded，会把 `#` `%` `[` `]` `^` `` ` `` `{` `}` 这些在 Windows 上
   完全合法的字符转成 `%XX`，替换完文件就不存在了；UNC 路径
   `file://server/share` 只有两个斜杠，连前缀都剥不掉。表现是「一批文件
   加不进来」和「网络路径全废」。

2. 转换中点 × 直接关窗。worker 是 daemon 线程，进程退出时被直接丢弃，
   ffmpeg 变孤儿继续往卡里写，`set_awake(False)` 也不执行。
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
    # start() 会先过 ffmpeg 可用性检查与开工前体检，桩掉它们才能走到起线程那一步
    monkeypatch.setattr(bridge_mod.core, "ffmpeg_available", lambda: (True, "ok"))
    monkeypatch.setattr(bridge_mod.core, "preflight",
                        lambda *a, **kw: {"blocking": [], "warnings": []})

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


def test_start_blocks_when_preflight_reports_problem(bridge, monkeypatch):
    """开工前体检不通过时必须停在原地，不能起线程。

    QML 版此前完全跳过 preflight：选错目录、卡里没有真机原片、空间不够，
    都要等转码跑完才在状态栏冒一行字，用户以为成功了。
    """
    import bridge as bridge_mod
    monkeypatch.setattr(bridge_mod.core, "ffmpeg_available", lambda: (True, "ok"))
    monkeypatch.setattr(bridge_mod.core, "preflight",
                        lambda *a, **kw: {"blocking": ["卡里找不到真机原片作模板"],
                                          "warnings": []})
    started = []
    monkeypatch.setattr(bridge, "_run", lambda *a, **kw: started.append(1))
    bridge._files = ["x.mp4"]

    bridge.start("/tmp/out", True, True, "自动")

    assert started == []
    assert bridge._worker is None
    assert "开始前检查未通过" in bridge.lastError
    assert "卡里找不到真机原片作模板" in bridge.lastError
    assert bridge.busy is False


def test_start_passes_sample_pair_into_preflight(bridge, monkeypatch):
    """体检必须知道用户选了哪一对样本。

    否则用户明明选过样本，体检还是会说「卡里找不到真机原片」——
    因为 preflight 自己按字典序猜，而卡里可能只有上一轮的产物。
    """
    import bridge as bridge_mod
    monkeypatch.setattr(bridge_mod.core, "ffmpeg_available", lambda: (True, "ok"))
    seen = {}

    def fake_preflight(dest, sources, do_index=True, template_names=None):
        seen["dest"] = dest
        seen["template_names"] = template_names
        return {"blocking": ["停在这里"], "warnings": []}

    monkeypatch.setattr(bridge_mod.core, "preflight", fake_preflight)
    bridge._files = ["x.mp4"]
    bridge._spec_pair = ("VID_1.mp4", "LRV_1.lrv")

    bridge.start("/tmp/out", True, True, "自动")

    assert seen["template_names"] == ("VID_1.mp4", "LRV_1.lrv")


def test_auto_detect_sample_picks_vid_from_output_dir(bridge, tmp_path, monkeypatch):
    """输出目录里就有真机原片时，自动分析必须挑到它。

    QML 版此前把这个按钮做成「请手动选择」的提示，等于功能缺失。
    """
    import bridge as bridge_mod
    out = tmp_path / "DCIM" / "Camera01"
    out.mkdir(parents=True)
    (out / "LRV_20261104_141845_024.lrv").write_bytes(b"x")
    vid = out / "VID_20261104_141845_024.mp4"
    vid.write_bytes(b"x")

    picked = []
    monkeypatch.setattr(bridge, "setSample", lambda p: picked.append(p))

    bridge.autoDetectSample(str(out))

    assert picked == [str(vid)]
    assert bridge.lastError == ""


def test_auto_detect_sample_prefers_vid_over_lrv(bridge, tmp_path, monkeypatch):
    """同名对里要挑 VID 而不是 LRV —— LRV 是代理轨，当样本会取错规格。"""
    out = tmp_path / "DCIM" / "Camera01"
    out.mkdir(parents=True)
    (out / "LRV_20261104_141845_024.lrv").write_bytes(b"x")
    vid = out / "VID_20261104_141845_024.mp4"
    vid.write_bytes(b"x")

    picked = []
    monkeypatch.setattr(bridge, "setSample", lambda p: picked.append(p))

    bridge.autoDetectSample(str(out))

    assert picked == [str(vid)]


def test_auto_detect_sample_reports_when_nothing_found(bridge, tmp_path, monkeypatch):
    """找不到时必须说清下一步怎么做，不能静默什么都不发生。"""
    empty = tmp_path / "empty"
    empty.mkdir()
    real_isdir = os.path.isdir
    # 让「扫盘符」那一路全部落空，避免真的去翻本机的 D: ~ I: 盘
    monkeypatch.setattr(os.path, "isdir",
                        lambda p: False if p.endswith(":\\") else real_isdir(p))

    bridge.autoDetectSample(str(empty))

    assert "未在存储卡中自动找到原生录制视频" in bridge.lastError


def test_run_uses_sample_pair_as_template(bridge, tmp_path, monkeypatch):
    """用户选过样本对时，模板必须按名字取，不能退回按字典序猜。

    卡里除了真机原片还躺着上一轮的产物，它们同样带 inst box；
    猜中产物的后果是 moov 骨架/帧率/分辨率全来自产物，相机不认且不报错。
    """
    import bridge as bridge_mod
    out = tmp_path / "card"
    (out / "DCIM" / "Camera01").mkdir(parents=True)
    src = tmp_path / "src.mp4"
    src.write_bytes(b"x")

    calls = {"names": [], "find": 0}
    monkeypatch.setattr(bridge_mod.core, "is_camera_card", lambda p: True)
    monkeypatch.setattr(bridge_mod.core, "set_awake", lambda *a, **kw: None)
    monkeypatch.setattr(bridge_mod.core, "append_log", lambda *a, **kw: None)

    def fake_from_names(root, vid, lrv):
        calls["names"].append((vid, lrv))
        return ("tpl-main", "tpl-proxy", b"meta")

    def fake_find(root):
        calls["find"] += 1
        return None

    monkeypatch.setattr(bridge_mod.core, "template_from_names", fake_from_names)
    monkeypatch.setattr(bridge_mod.core, "find_native_template", fake_find)

    def fake_import(*a, **kw):
        calls["import_kw"] = kw
        return {"inst_ok": True}

    monkeypatch.setattr(bridge_mod.core, "import_with_inst", fake_import)

    bridge._spec_pair = ("VID_1.mp4", "LRV_1.lrv")
    bridge._run([str(src)], str(out), True, True, ("", "", "software"))

    assert calls["names"] == [("VID_1.mp4", "LRV_1.lrv")]
    assert calls["find"] == 0, "指定了样本对就不该再按字典序猜"
    assert calls["import_kw"]["template"] == ("tpl-main", "tpl-proxy", b"meta")
    assert calls["import_kw"]["template_names"] == ("VID_1.mp4", "LRV_1.lrv")


def test_tray_reports_unavailable_without_crashing(app, monkeypatch):
    """托盘不可用时 show/notify 必须安静地什么都不做。

    否则点了「最小化到托盘」窗口消失、图标也没出现，等于把程序弄丢了。
    """
    import tray as tray_mod
    monkeypatch.setattr(tray_mod.QSystemTrayIcon, "isSystemTrayAvailable",
                        staticmethod(lambda: False))
    t = tray_mod.Tray("")
    assert t.available is False
    t.show()
    t.notify("标题", "正文")
    t.hide()


def test_main_qml_offers_both_close_choices():
    """关窗弹窗必须同时给出「停止并退出」和「最小化到托盘」。

    只留一个都不对：只留退出会打断正在跑的转换，只留最小化会让不想
    留后台的用户没法干净退出。
    """
    qml = open(os.path.join(DESKTOP, "qml", "main.qml"), encoding="utf-8").read()
    assert "停止并退出" in qml
    assert "最小化到托盘" in qml
    assert "tray.available" in qml, "托盘不可用时必须显式禁用该选项"
    assert "tray.notify(" in qml, "跑完要提示，否则最小化等于干等"


def test_tray_created_with_qapplication():
    """托盘要 QMenu，QMenu 是 QWidget —— main.py 必须用 QApplication。"""
    main_py = open(os.path.join(DESKTOP, "main.py"), encoding="utf-8").read()
    assert "QApplication(" in main_py
    assert "setQuitOnLastWindowClosed(False)" in main_py, (
        "否则「最小化到托盘」刚藏起窗口进程就结束了")
