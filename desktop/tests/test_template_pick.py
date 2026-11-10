"""模板挑选的回归测试：镜像目录里混进上一轮产物时不能猜错。

背景：安卓端把卡结构镜像到 `cacheDir/job/card`，转码产物也直接写进
镜像的 `DCIM/Camera01`（与真机原片同目录）。上一轮产物自带 inst box
——正是上一轮自己移植进去的——所以它完全符合 `find_native_template`
的挑选条件「字典序第一个带 inst meta 的 VID_」。

结果：模板的 moov 骨架、帧率、分辨率、音频参数全部来自上一轮产物而非
真机，产出的东西相机不认，而且不抛任何异常、不写任何错误日志，只在
用户手里表现为「导进去相机看不见」。这个错误还会逐轮累积。

修法是双保险：镜像目录每轮先清空（Kotlin 侧 `CardMirror.build`），
并且 Kotlin 把「从卡上拷过来的是哪两个文件」显式传给 Python，核心不再猜。
"""

import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ANDROID_PY = os.path.abspath(
    os.path.join(HERE, "..", "..", "android", "app", "src", "main", "python")
)
if ANDROID_PY not in sys.path:
    sys.path.insert(0, ANDROID_PY)

import insta_core as ic  # noqa: E402

REAL_VID = "VID_20240101_090000_000.mp4"
REAL_LRV = "LRV_20240101_090000_000.lrv"
# 上一轮产物的名字排在真机原片之前，模拟「用得越久越容易踩」。
STALE_VID = "VID_20230101_080000_000.mp4"
STALE_LRV = "LRV_20230101_080000_000.lrv"


@pytest.fixture()
def mirror(tmp_path, monkeypatch):
    """造一个混有上一轮产物的镜像卡目录，并让 meta 解析对谁都成功。"""
    cam = tmp_path / "DCIM" / "Camera01"
    cam.mkdir(parents=True)
    for name in (REAL_VID, REAL_LRV, STALE_VID, STALE_LRV):
        (cam / name).write_bytes(b"\x00" * 64)
    # 只关心「谁被选中」，不关心 inst box 的真实字节。
    monkeypatch.setattr(ic, "extract_inst_meta", lambda _p: b"\x0a\x0e" + b"0" * 14)
    return str(tmp_path)


def test_find_native_template_picks_stale_product_when_name_sorts_first(mirror):
    """记录危险行为本身：自动挑选会选中上一轮产物。

    这条断言看着「在测 bug」，但它守的是前提——一旦 find_native_template
    改成按时间戳或别的规则挑，这里会失败，提醒我们重新评估安卓侧是否
    还需要显式传模板名。
    """
    picked = ic.find_native_template(mirror)
    assert picked is not None
    main, _proxy, _meta = picked
    assert os.path.basename(main) == STALE_VID


def test_template_from_names_ignores_sort_order(mirror):
    """显式传名字时，必须拿到指定的那一对，与字典序无关。"""
    picked = ic.template_from_names(mirror, REAL_VID, REAL_LRV)

    assert picked is not None
    main, proxy, meta = picked
    assert os.path.basename(main) == REAL_VID
    assert os.path.basename(proxy) == REAL_LRV
    assert meta


def test_template_from_names_rejects_missing_pair(mirror):
    """只存在一半时必须返回 None，不能拿半对去当模板。"""
    assert ic.template_from_names(mirror, REAL_VID, STALE_LRV) is None
    assert ic.template_from_names(mirror, "VID_nope.mp4", REAL_LRV) is None


def test_template_from_names_rejects_file_without_inst_meta(mirror, monkeypatch):
    """没有 inst box 的文件不是真机原片，不能当模板。"""
    monkeypatch.setattr(ic, "extract_inst_meta", lambda _p: b"")
    assert ic.template_from_names(mirror, REAL_VID, REAL_LRV) is None


def test_desktop_core_also_accepts_explicit_template_names(mirror, monkeypatch):
    """桌面端同样不能靠猜。

    这条修的是另一条真实路径：桌面端把产物写到卡上同一个 DCIM/Camera01
    之后，用户再导入第二段，`find_native_template` 就会把第一段产物当模板。
    桌面端原本没有 template_from_names，只有安卓端有。
    """
    desktop_dir = os.path.abspath(os.path.join(HERE, ".."))
    if desktop_dir not in sys.path:
        sys.path.insert(0, desktop_dir)
    import core

    monkeypatch.setattr(core, "extract_inst_meta", lambda _p: b"\x0a\x0e" + b"0" * 14)
    picked = core.template_from_names(mirror, REAL_VID, REAL_LRV)
    assert picked is not None
    main, proxy, _meta = picked
    assert os.path.basename(main) == REAL_VID
    assert os.path.basename(proxy) == REAL_LRV
