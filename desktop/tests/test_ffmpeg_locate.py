"""ffmpeg 定位与安装逻辑的守卫测试。

用户提的顺序是：先看系统有没有装全局 ffmpeg，没有再找运行目录，都没有才
问用户装哪儿（全局要管理员权限，否则装到运行目录）。这几条测试守的就是
这个顺序，以及「提权失败/用户拒绝」时不能把下载好的东西丢掉。
"""

import os
import sys

import pytest

DESKTOP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if DESKTOP not in sys.path:
    sys.path.insert(0, DESKTOP)

import core  # noqa: E402


def _touch(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(b"x")
    return path


@pytest.fixture
def two_dirs(tmp_path, monkeypatch):
    """一个「系统目录」一个「程序目录」，两边都有 ffmpeg.exe。"""
    system = tmp_path / "ProgramFiles" / "instatools" / "bin"
    portable = tmp_path / "app" / "bin"
    for d in (system, portable):
        _touch(str(d / "ffmpeg.exe"))
        _touch(str(d / "ffprobe.exe"))
    monkeypatch.setattr(core, "_system_tool_dirs", lambda: [str(system)])
    monkeypatch.setattr(core, "_portable_tool_dirs", lambda: [str(portable)])
    monkeypatch.delenv("FFMPEG_PATH", raising=False)
    monkeypatch.setattr(core.shutil, "which", lambda name: None)
    monkeypatch.setattr(core, "_registry_ffmpeg", lambda: None)
    return str(system), str(portable)


def test_system_install_wins_over_portable(two_dirs):
    """系统里已经装了，就不该用程序目录里那份。"""
    system, _ = two_dirs
    got = core.find_ffmpeg()
    assert os.path.normcase(got) == os.path.normcase(os.path.join(system, "ffmpeg.exe"))


def test_portable_used_only_when_system_missing(two_dirs, monkeypatch):
    _, portable = two_dirs
    monkeypatch.setattr(core, "_system_tool_dirs", lambda: [])
    got = core.find_ffmpeg()
    assert os.path.normcase(got) == os.path.normcase(os.path.join(portable, "ffmpeg.exe"))


def test_registry_beats_directory_scan(two_dirs, monkeypatch):
    """注册表里登记的路径是安装器写的权威位置，优先于目录猜测。"""
    system, _ = two_dirs
    other = _touch(os.path.join(os.path.dirname(system), "other", "ffmpeg.exe"))
    monkeypatch.setattr(core, "_registry_ffmpeg", lambda: other)
    assert core.find_ffmpeg() == other


def test_env_var_beats_everything(two_dirs, monkeypatch, tmp_path):
    custom = _touch(str(tmp_path / "custom" / "ffmpeg.exe"))
    monkeypatch.setenv("FFMPEG_PATH", custom)
    assert core.find_ffmpeg() == custom


def test_ffmpeg_source_labels(two_dirs, monkeypatch, tmp_path):
    system, portable = two_dirs
    assert core.ffmpeg_source(os.path.join(portable, "ffmpeg.exe")) == "portable"
    assert core.ffmpeg_source(os.path.join(system, "ffmpeg.exe")) == "system"
    assert core.ffmpeg_source(str(tmp_path / "nope.exe")) == "system"
    assert core.ffmpeg_source("") == "missing"


def test_ffmpeg_source_reports_env(two_dirs, monkeypatch, tmp_path):
    custom = _touch(str(tmp_path / "custom" / "ffmpeg.exe"))
    monkeypatch.setenv("FFMPEG_PATH", custom)
    assert core.ffmpeg_source() == "env"


def test_global_install_asks_for_uac_when_not_admin(tmp_path, monkeypatch):
    """非管理员装全局：必须走提权，且脚本里要真的复制两个 exe 并登记注册表。"""
    src = tmp_path / "staging"
    _touch(str(src / "ffmpeg.exe"))
    _touch(str(src / "ffprobe.exe"))
    dest = tmp_path / "ProgramFiles" / "instatools" / "bin"
    monkeypatch.setattr(core, "global_install_dir", lambda: str(dest))
    monkeypatch.setattr(core, "_is_admin", lambda: False)
    monkeypatch.setattr(core, "_staging_dir", lambda: str(tmp_path / "stage"))
    seen = {}

    def fake_run(bat_path, timeout=300.0):
        seen["bat"] = open(bat_path, encoding="utf-8").read()
        #   模拟提权后的复制动作，让后续的存在性检查通过。
        _touch(str(dest / "ffmpeg.exe"))
        _touch(str(dest / "ffprobe.exe"))
        return True, "ok"

    monkeypatch.setattr(core, "_run_elevated", fake_run)
    ok, msg = core.install_ffmpeg_global(str(src))
    assert ok is True, msg
    assert msg == str(dest)
    assert "copy /y" in seen["bat"]
    assert "App Paths" in seen["bat"], "装完要登记注册表，否则「运行」里调不到"


def test_global_install_does_not_elevate_when_already_admin(tmp_path, monkeypatch):
    src = tmp_path / "staging"
    _touch(str(src / "ffmpeg.exe"))
    _touch(str(src / "ffprobe.exe"))
    dest = tmp_path / "ProgramFiles" / "instatools" / "bin"
    monkeypatch.setattr(core, "global_install_dir", lambda: str(dest))
    monkeypatch.setattr(core, "_is_admin", lambda: True)
    called = []
    monkeypatch.setattr(core, "_run_elevated", lambda *a, **k: called.append(1) or (True, "ok"))
    ok, msg = core.install_ffmpeg_global(str(src))
    assert ok is True, msg
    assert called == [], "已经是管理员就不该再弹一次 UAC"


def test_global_install_reports_uac_cancel(tmp_path, monkeypatch):
    """用户在 UAC 上点「否」要如实报出来，不能假装装好了。"""
    src = tmp_path / "staging"
    _touch(str(src / "ffmpeg.exe"))
    _touch(str(src / "ffprobe.exe"))
    monkeypatch.setattr(core, "global_install_dir", lambda: str(tmp_path / "ProgramFiles"))
    monkeypatch.setattr(core, "_is_admin", lambda: False)
    monkeypatch.setattr(core, "_staging_dir", lambda: str(tmp_path / "stage"))
    monkeypatch.setattr(core, "_run_elevated",
                        lambda *a, **k: (False, "已取消（未获得管理员权限）"))
    ok, msg = core.install_ffmpeg_global(str(src))
    assert ok is False
    assert "已取消" in msg


def test_install_portable_never_elevates(tmp_path, monkeypatch):
    """装到程序目录不需要任何权限，绝不能弹 UAC。"""
    staging = tmp_path / "stage"
    _touch(str(staging / "ffmpeg.exe"))
    _touch(str(staging / "ffprobe.exe"))
    dest = tmp_path / "app" / "bin"
    monkeypatch.setattr(core, "_staging_dir", lambda: str(staging))
    monkeypatch.setattr(core, "_download_ffmpeg_to", lambda st, cb=None: (True, st))
    monkeypatch.setattr(core, "ffmpeg_install_dir", lambda: str(dest))
    monkeypatch.setattr(core, "ffmpeg_available", lambda: (True, str(dest / "ffmpeg.exe")))
    monkeypatch.setattr(core, "_run_elevated",
                        lambda *a, **k: pytest.fail("portable 安装不该提权"))
    monkeypatch.setattr(core, "install_ffmpeg_global",
                        lambda *a, **k: pytest.fail("portable 安装不该走全局分支"))
    ok, msg = core.install_ffmpeg("portable")
    assert ok is True, msg
    assert os.path.isfile(str(dest / "ffmpeg.exe"))
    assert os.path.isfile(str(dest / "ffprobe.exe"))


def test_install_downloads_before_elevating(tmp_path, monkeypatch):
    """先下载到临时目录再提权：用户拒绝 UAC 时不必重下 200 MB。"""
    order = []
    monkeypatch.setattr(core, "_staging_dir", lambda: str(tmp_path / "stage"))
    monkeypatch.setattr(core, "_download_ffmpeg_to",
                        lambda staging, cb=None: order.append("download") or (True, staging))
    monkeypatch.setattr(core, "install_ffmpeg_global",
                        lambda src, cb=None: order.append("elevate") or (False, "已取消"))
    ok, msg = core.install_ffmpeg("global")
    assert ok is False
    assert order == ["download", "elevate"]


def test_install_fails_when_still_unusable(tmp_path, monkeypatch):
    """复制完了却跑不起来（比如架构不对），要报失败而不是「装好了」。"""
    staging = tmp_path / "stage"
    _touch(str(staging / "ffmpeg.exe"))
    _touch(str(staging / "ffprobe.exe"))
    monkeypatch.setattr(core, "_staging_dir", lambda: str(staging))
    monkeypatch.setattr(core, "_download_ffmpeg_to", lambda st, cb=None: (True, st))
    monkeypatch.setattr(core, "ffmpeg_install_dir", lambda: str(tmp_path / "app" / "bin"))
    monkeypatch.setattr(core, "ffmpeg_available", lambda: (False, "无法运行"))
    ok, msg = core.install_ffmpeg("portable")
    assert ok is False
    assert "无法运行" in msg


def test_install_reports_download_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "_staging_dir", lambda: str(tmp_path / "tmp"))
    monkeypatch.setattr(core, "_download_ffmpeg_to",
                        lambda staging, cb=None: (False, "所有下载源均不可用"))
    ok, msg = core.install_ffmpeg("portable")
    assert ok is False
    assert "所有下载源均不可用" in msg


def test_legacy_wrapper_still_works(tmp_path, monkeypatch):
    """老调用点（download_and_install_ffmpeg）不能因为重构就断掉。"""
    seen = []
    monkeypatch.setattr(core, "install_ffmpeg",
                        lambda scope="portable", cb=None: seen.append(scope) or (True, "ok"))
    ok, msg = core.download_and_install_ffmpeg(None)
    assert ok is True
    assert seen == ["portable"]
