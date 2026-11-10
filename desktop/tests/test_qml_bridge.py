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


# --- 封面 / 断点续跑 / 卡校验（QML 版补齐的三项） ---------------------------


def test_add_files_pairs_sidecar_cover(bridge, tmp_path, monkeypatch):
    """同名 jpg 必须自动配成封面。

    以前只有经典版读同名图，QML 版一律走「视频第 10 秒」—— 用户把
    a.mp4 + a.jpg 放进文件夹，封面却不生效，且界面没有任何提示。
    """
    import bridge as bridge_mod
    monkeypatch.setattr(bridge_mod.core, "default_cover_for",
                        lambda p: str(tmp_path / "a.jpg"))
    src = tmp_path / "a.mp4"
    src.write_bytes(b"x")
    bridge.addFiles([str(src)])
    assert bridge.covers[os.path.normpath(str(src))] == str(tmp_path / "a.jpg")
    assert "自动配对" in bridge.coverSummary or "a.jpg" in bridge.coverSummary


def test_pick_cover_rejects_multiple_videos(bridge, tmp_path):
    """多视频时拒绝自选封面：猜错配对会让 A 视频用上 B 的封面。"""
    a = tmp_path / "a.mp4"
    b = tmp_path / "b.mp4"
    img = tmp_path / "cover.jpg"
    for p in (a, b, img):
        p.write_bytes(b"x")
    bridge._files = [str(a), str(b)]
    bridge.pickCover(str(img))
    assert bridge.lastError != ""
    assert bridge.covers == {}


def test_pick_cover_sets_single_video_cover(bridge, tmp_path, monkeypatch):
    import bridge as bridge_mod
    monkeypatch.setattr(bridge_mod.core, "default_cover_for", lambda p: None)
    src = tmp_path / "a.mp4"
    img = tmp_path / "cover.png"
    for p in (src, img):
        p.write_bytes(b"x")
    bridge._files = [str(src)]
    bridge.pickCover(str(img))
    assert bridge.covers[os.path.normpath(str(src))] == os.path.normpath(str(img))
    assert bridge.lastError == ""


def test_clear_covers_restores_sidecar_pairing(bridge, tmp_path, monkeypatch):
    """「恢复自动」不能只是清空：同名图还得配回去。"""
    import bridge as bridge_mod
    src = tmp_path / "a.mp4"
    src.write_bytes(b"x")
    bridge._files = [str(src)]
    bridge._covers = {os.path.normpath(str(src)): str(tmp_path / "manual.jpg")}
    monkeypatch.setattr(bridge_mod.core, "default_cover_for",
                        lambda p: str(tmp_path / "a.jpg"))
    bridge.clearCovers()
    assert bridge.covers[os.path.normpath(str(src))] == str(tmp_path / "a.jpg")


def test_run_passes_cover_into_import(bridge, tmp_path, monkeypatch):
    """封面必须真的传到核心，不能只存在界面上。"""
    import bridge as bridge_mod
    out = tmp_path / "card"
    (out / "DCIM" / "Camera01").mkdir(parents=True)
    src = tmp_path / "a.mp4"
    img = tmp_path / "a.jpg"
    for p in (src, img):
        p.write_bytes(b"x")
    seen = {}
    monkeypatch.setattr(bridge_mod.core, "is_camera_card", lambda p: True)
    monkeypatch.setattr(bridge_mod.core, "set_awake", lambda *a, **kw: None)
    monkeypatch.setattr(bridge_mod.core, "append_log", lambda *a, **kw: None)
    monkeypatch.setattr(bridge_mod.core, "save_job", lambda *a, **kw: None)
    monkeypatch.setattr(bridge_mod.core, "template_from_names",
                        lambda *a: ("m", "p", b"meta"))

    def fake_import(*a, **kw):
        seen.update(kw)
        return {"inst_ok": True}

    monkeypatch.setattr(bridge_mod.core, "import_with_inst", fake_import)
    bridge._spec_pair = ("VID_1.mp4", "LRV_1.lrv")
    bridge._covers[os.path.normpath(str(src))] = str(img)
    bridge._run([str(src)], str(out), True, True, ("", "", "software"))
    assert seen.get("cover") == str(img)


def test_run_saves_job_after_each_file(bridge, tmp_path, monkeypatch):
    """每条都要落盘：只在开头存一次的话，中途关窗就白跑了。"""
    import bridge as bridge_mod
    out = tmp_path / "out"
    out.mkdir()
    srcs = []
    for i in range(3):
        p = tmp_path / ("a%d.mp4" % i)
        p.write_bytes(b"x")
        srcs.append(str(p))
    saved = []
    monkeypatch.setattr(bridge_mod.core, "is_camera_card", lambda p: False)
    monkeypatch.setattr(bridge_mod.core, "set_awake", lambda *a, **kw: None)
    monkeypatch.setattr(bridge_mod.core, "append_log", lambda *a, **kw: None)
    monkeypatch.setattr(bridge_mod.core, "save_job",
                        lambda dest, job: saved.append([it["status"] for it in job["items"]]))
    monkeypatch.setattr(bridge_mod.core, "convert", lambda *a, **kw: ("m", "p"))
    bridge._run(srcs, str(out), False, True, ("", "", "software"))
    # 开头一次 + 每条两次（running / done）
    assert len(saved) >= 1 + 2 * len(srcs)
    assert saved[-1] == ["done", "done", "done"]


def test_run_marks_failed_items_in_job(bridge, tmp_path, monkeypatch):
    import bridge as bridge_mod
    out = tmp_path / "out"
    out.mkdir()
    src = tmp_path / "a.mp4"
    src.write_bytes(b"x")
    saved = []
    monkeypatch.setattr(bridge_mod.core, "is_camera_card", lambda p: False)
    monkeypatch.setattr(bridge_mod.core, "set_awake", lambda *a, **kw: None)
    monkeypatch.setattr(bridge_mod.core, "append_log", lambda *a, **kw: None)
    monkeypatch.setattr(bridge_mod.core, "save_job",
                        lambda dest, job: saved.append(dict(job["items"][0])))

    def boom(*a, **kw):
        raise RuntimeError("编码器炸了")

    monkeypatch.setattr(bridge_mod.core, "convert", boom)
    bridge._run([str(src)], str(out), False, True, ("", "", "software"))
    assert saved[-1]["status"] == "failed"
    assert "编码器炸了" in saved[-1]["err"]


def test_check_resume_reports_remaining(bridge, tmp_path, monkeypatch):
    import bridge as bridge_mod
    out = tmp_path / "out"
    out.mkdir()
    done = tmp_path / "a.mp4"
    todo = tmp_path / "b.mp4"
    for p in (done, todo):
        p.write_bytes(b"x")
    bridge._files = [str(done), str(todo)]
    monkeypatch.setattr(bridge_mod.core, "load_job", lambda dest: {
        "items": [{"src": str(done), "status": "done"},
                  {"src": str(todo), "status": "running"}]})
    bridge.checkResume(str(out))
    assert bridge.resumeOnly is True
    assert bridge.resumeSummary != ""
    assert "1" in bridge.resumeSummary


def test_start_skips_done_files_when_resume_only(bridge, tmp_path, monkeypatch):
    """勾了「只跑未完成」就必须真的跳过 —— 重跑一条要几分钟。"""
    import bridge as bridge_mod
    out = tmp_path / "out"
    out.mkdir()
    done = tmp_path / "a.mp4"
    todo = tmp_path / "b.mp4"
    for p in (done, todo):
        p.write_bytes(b"x")
    seen = []
    monkeypatch.setattr(bridge_mod.core, "ffmpeg_available", lambda: (True, ""))
    monkeypatch.setattr(bridge_mod.core, "preflight",
                        lambda *a, **kw: {"blocking": [], "warnings": []})
    monkeypatch.setattr(bridge_mod.core, "load_job", lambda dest: {
        "items": [{"src": str(done), "status": "done"}]})
    monkeypatch.setattr(bridge_mod.core, "append_log", lambda *a, **kw: None)
    monkeypatch.setattr(bridge_mod.core, "set_awake", lambda *a, **kw: None)
    monkeypatch.setattr(bridge_mod.core, "is_camera_card", lambda p: False)
    monkeypatch.setattr(bridge_mod.core, "save_job", lambda *a, **kw: None)
    monkeypatch.setattr(bridge_mod.core, "convert",
                        lambda src, *a, **kw: seen.append(src) or ("m", "p"))
    bridge._files = [str(done), str(todo)]
    bridge.start(str(out), False, True, "自动")
    bridge.waitWorker(20000)
    assert seen == [str(todo)], "已完成的 a.mp4 不该再跑"


def test_verify_card_reports_bad_entries(bridge, tmp_path, monkeypatch):
    import bridge as bridge_mod
    out = tmp_path / "card"
    out.mkdir()
    monkeypatch.setattr(bridge_mod.core, "append_log", lambda *a, **kw: None)
    monkeypatch.setattr(bridge_mod.core, "verify_card", lambda root: {
        "ok": ["/DCIM/Camera01/VID_1.mp4"],
        "bad": [("/DCIM/Camera01/VID_2.mp4", "文件不存在")],
        "entries": 2})
    bridge.verifyCard(str(out))
    for _ in range(200):
        if not bridge.verifying:
            break
        threading.Event().wait(0.02)
    assert "正常 1" in bridge.verifyResult
    assert "异常 1" in bridge.verifyResult
    assert bridge.verifyHasBad is True


def test_repair_card_reports_kept_and_removed(bridge, tmp_path, monkeypatch):
    import bridge as bridge_mod
    out = tmp_path / "card"
    out.mkdir()
    monkeypatch.setattr(bridge_mod.core, "append_log", lambda *a, **kw: None)
    monkeypatch.setattr(bridge_mod.core, "repair_card",
                        lambda root, log=None: {"removed": [("x", "y")], "kept": 7})
    msg = bridge.repairCard(str(out))
    assert "保留 7" in msg
    assert "移除 1" in msg
    assert bridge.verifyHasBad is False


def test_output_view_exposes_cover_and_verify():
    """QML 侧的洞必须真的接上：空 onClicked 与缺按钮都是「功能没做」。"""
    qml = os.path.join(DESKTOP, "qml", "OutputOptionView.qml")
    src = open(qml, encoding="utf-8").read()
    assert "onClicked: {}" not in src, "还有空处理的按钮"
    assert "signal pickCover()" in src
    assert "signal clearCovers()" in src
    assert "signal verifyCard()" in src
    main = open(os.path.join(DESKTOP, "qml", "main.qml"), encoding="utf-8").read()
    assert "bridge.pickCover(" in main
    assert "bridge.verifyCard(" in main
    assert "bridge.checkResume(" in main


def test_resume_run_keeps_previous_done_records(bridge, tmp_path, monkeypatch):
    """续跑只跑未完成的几条，但旧记录不能因此被抹掉。

    直接用「本次要跑的列表」重建 job 的话，已完成记录全没了 ——
    再取消一次，下一次就不知道哪些跑过，白跑一遍。
    """
    import bridge as bridge_mod
    out = tmp_path / "out"
    out.mkdir()
    done = tmp_path / "a.mp4"
    todo = tmp_path / "b.mp4"
    for p in (done, todo):
        p.write_bytes(b"x")
    saved = []
    monkeypatch.setattr(bridge_mod.core, "is_camera_card", lambda p: False)
    monkeypatch.setattr(bridge_mod.core, "set_awake", lambda *a, **kw: None)
    monkeypatch.setattr(bridge_mod.core, "append_log", lambda *a, **kw: None)
    monkeypatch.setattr(bridge_mod.core, "load_job", lambda dest: {
        "items": [{"src": str(done), "status": "done"},
                  {"src": str(todo), "status": "running"}]})
    monkeypatch.setattr(bridge_mod.core, "save_job",
                        lambda dest, job: saved.append(
                            {os.path.basename(i["src"]): i["status"] for i in job["items"]}))
    monkeypatch.setattr(bridge_mod.core, "convert", lambda *a, **kw: ("m", "p"))
    bridge._run([str(todo)], str(out), False, True, ("", "", "software"))
    assert saved[-1] == {"a.mp4": "done", "b.mp4": "done"}


def test_cover_image_is_normpath_safe(bridge, tmp_path, monkeypatch):
    """coverImage 要按 normpath 取，不能拿 files 里的原字符串直接当键。

    covers 的键统一 normpath 过，files 里存的可能是 `C:/a/b.mp4` 或
    `C:\a\b.mp4` —— 直接索引会取不到，界面预览就一直是空的。
    """
    import bridge as bridge_mod
    monkeypatch.setattr(bridge_mod.core, "default_cover_for", lambda p: None)
    src = tmp_path / "a.mp4"
    img = tmp_path / "a.jpg"
    for p in (src, img):
        p.write_bytes(b"x")
    # 故意把 files 里的路径写成正斜杠形式
    bridge._files = [str(src).replace(os.sep, "/")]
    bridge._covers[os.path.normpath(str(src))] = str(img)
    # 必须是 file:// URL：Image.source 只认 URL，给裸路径会静默加载失败。
    got = bridge.coverImage
    assert got.startswith("file:///"), got
    assert got.endswith("/a.jpg"), got
    from PySide6.QtCore import QUrl
    # toLocalFile 返回正斜杠形式，比路径要 normpath 过再比。
    assert os.path.normpath(QUrl(got).toLocalFile()) == os.path.normpath(str(img))
    bridge._files = [str(src), str(src)]
    assert bridge.coverImage == "", "多条视频不猜配对"


def test_ffmpeg_install_retriggers_hardware_probe(bridge, monkeypatch):
    """装完 ffmpeg 要重新探一次硬件编码器。

    启动那次探测因为找不到 ffmpeg 直接放弃，标记位已经置上了；不重置的话
    用户装完 ffmpeg 仍然看到「未检测到可用硬件编码器」，明明有 NVENC 却
    永远用不上。
    """
    import bridge as bridge_mod
    bridge._hw_checked = True
    bridge._hw = "未检测到"
    calls = []

    def fake_detect():
        calls.append(1)
        return ("hevc_nvenc", "h264_nvenc", "NVIDIA")

    monkeypatch.setattr(bridge_mod.core, "download_and_install_ffmpeg",
                        lambda stage: (True, "ok"))
    monkeypatch.setattr(bridge_mod.core, "detect_hw_encoder", fake_detect)
    monkeypatch.setattr(bridge_mod.core, "ffmpeg_available", lambda: (True, "ok"))
    bridge._download_ffmpeg()
    assert calls == [1], "装完 ffmpeg 必须重探硬件"
    assert bridge.hardwareEncoder == "NVIDIA"


def test_check_ffmpeg_surfaces_missing_state(bridge, monkeypatch):
    """ffmpeg 缺失必须在界面上有补救入口，不能只在点开始时报一句。"""
    import bridge as bridge_mod
    monkeypatch.setattr(bridge_mod.core, "ffmpeg_available",
                        lambda: (False, "未找到 ffmpeg/ffprobe"))
    bridge.checkFfmpeg()
    assert bridge.ffmpegMissing is True
    assert "下载" in bridge.status


def test_check_ffmpeg_clears_state_when_ready(bridge, monkeypatch):
    import bridge as bridge_mod
    bridge._ffmpeg_missing = True
    monkeypatch.setattr(bridge_mod.core, "ffmpeg_available",
                        lambda: (True, "C:/ffmpeg.exe"))
    bridge.checkFfmpeg()
    assert bridge.ffmpegMissing is False


def test_main_qml_wires_ffmpeg_banner():
    """界面必须真的调用 checkFfmpeg / downloadFfmpeg，否则横幅永不出现。"""
    main = open(os.path.join(DESKTOP, "qml", "main.qml"), encoding="utf-8").read()
    assert "bridge.checkFfmpeg()" in main
    assert "bridge.downloadFfmpeg()" in main
    assert "bridge.ffmpegMissing" in main


def test_remove_file_keeps_the_rest(bridge, tmp_path):
    """单个移除不能顺手把封面和别的文件一起清掉。"""
    import bridge as bridge_mod
    a = tmp_path / "a.mp4"
    b = tmp_path / "b.mp4"
    for p in (a, b):
        p.write_bytes(b"x")
    bridge._files = [str(a), str(b)]
    bridge._covers[os.path.normpath(str(a))] = str(tmp_path / "a.jpg")
    bridge._covers[os.path.normpath(str(b))] = str(tmp_path / "b.jpg")
    bridge.removeFile(str(a))
    assert bridge._files == [str(b)]
    assert os.path.normpath(str(a)) not in bridge.covers
    assert os.path.normpath(str(b)) in bridge.covers


def test_remove_file_unknown_path_reports_error(bridge, tmp_path):
    bridge._files = [str(tmp_path / "a.mp4")]
    bridge.removeFile(str(tmp_path / "nope.mp4"))
    assert bridge.lastError != ""


def test_locate_card_fills_directory(bridge, monkeypatch):
    """「定位 SD 卡」必须真的把找到的目录报回界面。

    只假造 isdir 的返回值，不动 os.path.join —— 上一版把 join 也换了，
    结果 pathlib 拿到坏路径直接 FileNotFoundError，测的根本不是被测代码。
    """
    import bridge as bridge_mod
    target = os.path.join("E:" + os.sep, "DCIM", "Camera01")
    roots = {"D:" + os.sep, "E:" + os.sep, "F:" + os.sep,
             "G:" + os.sep, "H:" + os.sep, "I:" + os.sep}

    def fake_isdir(p):
        return p in roots or p == target

    monkeypatch.setattr(bridge_mod.os.path, "isdir", fake_isdir)
    bridge.locateCard()
    assert bridge.locatedDir == target
    assert bridge.lastError == ""


def test_locate_card_reports_when_missing(bridge, monkeypatch):
    import bridge as bridge_mod
    monkeypatch.setattr(bridge_mod.os.path, "isdir", lambda p: False)
    bridge.locateCard()
    assert bridge.locatedDir == ""
    assert "DCIM" in bridge.lastError


def test_output_view_exposes_locate_and_remove():
    out = open(os.path.join(DESKTOP, "qml", "OutputOptionView.qml"), encoding="utf-8").read()
    assert "signal locateCard()" in out
    assert "定位 SD 卡" in out
    inp = open(os.path.join(DESKTOP, "qml", "InputFileView.qml"), encoding="utf-8").read()
    assert "signal removeFile(string path)" in inp
    main = open(os.path.join(DESKTOP, "qml", "main.qml"), encoding="utf-8").read()
    assert "bridge.locateCard()" in main
    assert "bridge.removeFile(" in main


# --- 硬件探测 / 样本摘要 / 下一序号 / 拖拽 --------------------------------


def test_refresh_sequence_reports_next_number(bridge, tmp_path, monkeypatch):
    """「下一序号」要跟目录里的实际文件对齐，否则会和卡上已有文件撞号。"""
    import bridge as bridge_mod
    out = tmp_path / "out"
    out.mkdir()
    for n in ("VID_20260101_100000_003.mp4", "VID_20260101_100001_007.mp4"):
        (out / n).write_bytes(b"x")
    bridge.refreshSequence(str(out), True)
    assert "008" in bridge.nextSequence


def test_refresh_sequence_handles_manual_start(bridge, tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    bridge.refreshSequence(str(out), False)
    assert "000" in bridge.nextSequence


def test_refresh_sequence_handles_missing_dir(bridge, tmp_path):
    bridge.refreshSequence(str(tmp_path / "nope"), True)
    assert bridge.nextSequence != ""


def test_detect_hardware_reports_result(bridge, monkeypatch):
    import bridge as bridge_mod
    monkeypatch.setattr(bridge_mod.core, "ffmpeg_available", lambda: (True, "ff"))
    monkeypatch.setattr(bridge_mod.core, "detect_hw_encoder",
                        lambda: ("hevc_nvenc", "h264_nvenc", "NVIDIA"))
    bridge.detectHardware()
    for _ in range(200):
        if bridge.hardwareEncoder:
            break
        threading.Event().wait(0.02)
    assert bridge.hardwareEncoder == "NVIDIA"


def test_detect_hardware_reports_absence(bridge, monkeypatch):
    import bridge as bridge_mod
    monkeypatch.setattr(bridge_mod.core, "ffmpeg_available", lambda: (True, "ff"))
    monkeypatch.setattr(bridge_mod.core, "detect_hw_encoder", lambda: None)
    bridge.detectHardware()
    for _ in range(200):
        if bridge.hardwareEncoder:
            break
        threading.Event().wait(0.02)
    assert bridge.hardwareEncoder == "未检测到"


def test_spec_summary_shows_structure(bridge, monkeypatch):
    """样本摘要必须摊开分辨率/帧率/编码，不能只说「已读取」。"""
    import bridge as bridge_mod
    src = None
    monkeypatch.setattr(bridge_mod.core, "analyze_native", lambda p: {
        "video": {"width": 1920, "height": 1080, "fps": "59.94",
                  "codec": "hevc", "level": "4.1", "color_range": "pc"},
        "audio_tracks": [{"index": 0}],
    })
    monkeypatch.setattr(bridge_mod.core, "default_cover_for", lambda p: None)
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "VID_1.mp4")
        open(p, "wb").write(b"x")
        bridge.setSample(p)
    s = bridge.specSummary
    assert "1920x1080" in s
    assert "hevc" in s
    assert "full-range" in s
    assert "音频 1 轨" in s


def test_add_paths_expands_folder(bridge, tmp_path, monkeypatch):
    """拖进文件夹要展开一层，否则拖 DCIM 目录毫无反应。"""
    import bridge as bridge_mod
    monkeypatch.setattr(bridge_mod.core, "default_cover_for", lambda p: None)
    folder = tmp_path / "DCIM"
    folder.mkdir()
    for n in ("a.mp4", "b.mp4", "notes.txt"):
        (folder / n).write_bytes(b"x")
    bridge.addPaths([str(folder)])
    assert len(bridge.files) == 2


def test_add_paths_rejects_non_video(bridge, tmp_path):
    txt = tmp_path / "a.txt"
    txt.write_bytes(b"x")
    bridge.addPaths([str(txt)])
    assert bridge.files == []
    assert bridge.lastError != ""


def test_main_qml_wires_detection_and_drop():
    main = open(os.path.join(DESKTOP, "qml", "main.qml"), encoding="utf-8").read()
    assert "bridge.detectHardware()" in main
    assert "bridge.refreshSequence(" in main
    assert "bridge.addPaths(" in main
    assert "DropArea {" in main
    sample = open(os.path.join(DESKTOP, "qml", "CameraSampleView.qml"), encoding="utf-8").read()
    assert "property string summary" in sample


def test_clear_error_releases_sticky_state(bridge):
    """错误提示必须能关掉。

    lastError 是粘性的：出错一次后，下一次点「开始转换」之前界面一直是红的，
    用户改完路径、加好文件也还红着。
    """
    bridge._set_error("请先添加要转换的视频")
    assert bridge.lastError != ""
    bridge.clearError()
    assert bridge.lastError == ""


def test_input_view_does_not_use_last_error_as_file_state():
    """文件区的错误态不能挂在全局 lastError 上。

    `bridge.lastError` 也会被「请先添加要转换的视频」「未找到 ffmpeg」这类
    与列表无关的错误写入；接上去的结果是列表永远显示「出错了」。
    """
    main = open(os.path.join(DESKTOP, "qml", "main.qml"), encoding="utf-8").read()
    start = main.index("InputFileView {")
    block = main[start:main.index("}", start)]
    assert "bridge.lastError" not in block
    action = open(os.path.join(DESKTOP, "qml", "ActionView.qml"), encoding="utf-8").read()
    assert "signal dismissError()" in action
    assert "onDismissError: bridge.clearError()" in main
