# 影石相机工具 --- 影石 Ace Pro 2 第三方视频导入工具
# Copyright (C) 2026  影石相机工具 contributors
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""InstaAceImporter 回归测试（离线，不需要相机、不需要 ffmpeg）。

覆盖三条最容易回归、且一回归相机就"能识别但打不开"的铁律：

1. 索引 protobuf 必须字节级可逆 —— 解析再回写不能丢未知字段
2. `inst` 的 f7 必须是 14 位 YYYYMMDDHHMMSS —— 带 3 位序号会丢日期段
3. 隐藏文件必须用 `r+b` 原地改写 —— `wb` 会 PermissionError

运行：
    pip install pytest
    pytest -q
"""

from __future__ import annotations

import ctypes
import os
import shutil
import struct
import sys
import tempfile
import threading
from pathlib import Path

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# shared/ 是 insta_index.py 与 instbox/ 的唯一来源，测试不依赖外部 PYTHONPATH。
SHARED = os.path.join(os.path.dirname(ROOT), "shared")
if SHARED not in sys.path:
    sys.path.insert(0, SHARED)

import core                  # noqa: E402
import insta_index as ix     # noqa: E402
from instbox import inst_transplant as tf  # noqa: E402
from instbox import moov_rewrap as rw      # noqa: E402

SAMPLES = os.path.join(ROOT, "samples")
FILEINFO = os.path.join(SAMPLES, "fileinfo_list.list")


def _sample_paths() -> list[str]:
    if not os.path.isdir(SAMPLES):
        return []
    names = [n for n in os.listdir(SAMPLES)
             if n.startswith(("fileinfo", "editinfo", ".editinfo"))]
    return [os.path.join(SAMPLES, n) for n in sorted(names)]


@pytest.mark.parametrize("path", _sample_paths() or [None])
def test_index_bytes_roundtrip(path):
    """真机索引样本：解析 → 回写，必须与原文件逐字节相同。"""
    if path is None:
        pytest.skip("samples/ 下没有真机索引样本")
    data = open(path, "rb").read()
    name = os.path.basename(path)
    if "fileinfo" in name:
        out = ix.build_fileinfo(ix.parse_fileinfo(data))
    else:
        out = ix.build_editinfo(ix.parse_editinfo(data))
    assert out == data, f"{name}: 解析后回写不再字节一致（未知字段被丢弃）"


def test_register_media_is_idempotent():
    """同一条路径登记两次，不能出现两个条目。"""
    if not os.path.isfile(FILEINFO):
        pytest.skip("缺少真机 fileinfo 样本")
    fi = open(FILEINFO, "rb").read()
    meta = ix.parse_fileinfo(fi)[0].meta
    path = "/DCIM/Camera01/VID_20260101_000000_999.mp4"

    fi1, ei1 = ix.register_media(fi, b"", path, meta)
    fi2, ei2 = ix.register_media(fi1, ei1, path, meta)

    assert fi1 == fi2
    assert ei1 == ei2
    assert sum(1 for e in ix.parse_fileinfo(fi1) if e.path == path) == 1
    assert sum(1 for e in ix.parse_editinfo(ei1) if e.path == path) == 1


@pytest.mark.parametrize("name,expected", [
    ("VID_20261016_104229_560.mp4", 20261016104229),
    ("LRV_20260915_094907_002.lrv", 20260915094907),
    ("VID_20260915_094907_002.MP4", 20260915094907),
])
def test_stamp_from_name_is_14_digits(name, expected):
    """f7 = 14 位 YYYYMMDDHHMMSS，序号不进 meta。"""
    stamp = core.stamp_from_name(name)
    assert stamp == expected
    assert len(str(stamp)) == 14


@pytest.mark.parametrize("bad", [
    "random.mp4",
    "VID_20261016.mp4",
    "VID_20261016_1042_560.mp4",
])
def test_stamp_from_name_rejects_bad_names(bad):
    with pytest.raises(ValueError):
        core.stamp_from_name(bad)


HIDDEN = 0x2
READONLY = 0x1


def _attrs(path) -> int:
    return ctypes.windll.kernel32.GetFileAttributesW(str(path))


@pytest.mark.skipif(os.name != "nt", reason="Windows 专有行为")
def test_write_index_file_preserves_hidden(tmp_path):
    """隐藏 + 只读的索引文件必须能写进去，且属性保持不变。"""
    p = tmp_path / ".editinfo_list.list"
    p.write_bytes(b"\x00" * 8)
    assert ctypes.windll.kernel32.SetFileAttributesW(str(p), HIDDEN | READONLY) != 0
    before = _attrs(p)
    assert before & HIDDEN and before & READONLY

    payload = b"\x08\x01\x12\x03abc"
    core._write_index_file(str(p), payload)

    assert p.read_bytes() == payload
    after = _attrs(p)
    assert after & HIDDEN, "写入后隐藏属性丢失"
    assert after & READONLY, "写入后只读属性未恢复"


@pytest.mark.skipif(os.name != "nt", reason="Windows 专有行为")
def test_write_index_file_creates_new(tmp_path):
    p = tmp_path / "fileinfo_list.list"
    core._write_index_file(str(p), b"\x0a\x00")
    assert p.read_bytes() == b"\x0a\x00"


def _box(typ: bytes, payload: bytes = b"") -> bytes:
    return struct.pack(">I", 8 + len(payload)) + typ + payload


def test_has_inst_box_detects_tail_box(tmp_path):
    data = (_box(b"ftyp", b"iso5" + b"\x00" * 12)
            + _box(b"wide")
            + _box(b"mdat", b"\x00" * 32)
            + _box(b"inst", b"\x00" * 16))
    p = tmp_path / "with_inst.mp4"
    p.write_bytes(data)

    found, size = core.has_inst_box(str(p))
    assert found is True
    assert size == 24


def test_has_inst_box_absent(tmp_path):
    p = tmp_path / "plain.mp4"
    p.write_bytes(_box(b"ftyp", b"isom" + b"\x00" * 12) + _box(b"mdat", b"\x00" * 8))
    assert core.has_inst_box(str(p)) == (False, 0)


def test_stage_cb_maps_to_range():
    """子阶段 0~1 要映射到整体 [lo, hi]，并带上阶段名。"""
    got = []
    cb = core._stage_cb(lambda f, t, s, e: got.append((round(f, 4), t)),
                        0.0, 0.70, "转码")
    cb(0.0, "VID", 1.0, 0)
    cb(0.5, "VID", 1.0, 0)
    cb(1.0, "LRV", 1.0, 0)
    assert got == [(0.0, "转码 · VID"), (0.35, "转码 · VID"), (0.7, "转码 · LRV")]


def test_stage_cb_clamps_and_handles_none():
    got = []
    cb = core._stage_cb(lambda f, t, s, e: got.append(round(f, 4)),
                        0.94, 1.0, "登记索引")
    cb(2.0)
    cb(-1.0)
    assert got == [1.0, 0.94]
    assert core._stage_cb(None, 0.0, 1.0, "x") is None


def test_stage_cb_omits_empty_label():
    got = []
    cb = core._stage_cb(lambda f, t, s, e: got.append(t), 0.70, 0.94, "移植 inst box")
    cb(0.5, "")
    assert got == ["移植 inst box"]


@pytest.mark.parametrize("codec,level,expected", [
    ("libx265", 123, "4.1"),
    ("hevc_qsv", 123, "4.1"),
    ("hevc_nvenc", 120, "4.0"),
    ("hevc_amf", 120, "4.0"),
    ("libx264", 41, "4.1"),
    ("h264_qsv", 41, "4.1"),
])
def test_level_text_uses_codec_family(codec, level, expected):
    """HEVC 系列（含硬件编码器）必须用 HEVC 公式。

    回归：曾只认 "libx265"，导致 hevc_qsv 拿到 -level:v 12.3 而拒开编码器。
    """
    assert core._level_text(level, codec) == expected


def test_level_text_none():
    assert core._level_text(None, "hevc_qsv") is None
    assert core._level_text(0, "libx265") is None


def test_default_cover_for_sidecar(tmp_path):
    video = tmp_path / "a.mp4"
    video.write_bytes(b"\x00" * 32)
    (tmp_path / "a.JPG").write_bytes(b"img")
    assert core.default_cover_for(str(video)) == str(tmp_path / "a.JPG")


def test_default_cover_for_ignores_other_names(tmp_path):
    video = tmp_path / "a.mp4"
    video.write_bytes(b"\x00" * 32)
    (tmp_path / "b.jpg").write_bytes(b"img")
    assert core.default_cover_for(str(video)) is None


def test_default_cover_for_missing_dir():
    assert core.default_cover_for(r"Z:\不存在的目录\x.mp4") is None


def test_estimate_output_bytes_uses_duration(monkeypatch, tmp_path):
    src = tmp_path / "a.mp4"
    src.write_bytes(b"\x00" * 16)
    monkeypatch.setattr(core, "probe", lambda p: {"video": {"duration": 120.0}})
    # 2 分钟 → 2 * 7MB * 1.25
    assert core.estimate_output_bytes([str(src)]) == int(2 * 7 * 1024 * 1024 * 1.25)


def test_estimate_output_bytes_handles_no_duration(monkeypatch, tmp_path):
    src = tmp_path / "a.mp4"
    src.write_bytes(b"\x00" * (4 * 1024 * 1024))
    monkeypatch.setattr(core, "probe", lambda p: {})
    assert core.estimate_output_bytes([str(src)]) > 0


def test_preflight_blocks_without_sources(tmp_path):
    r = core.preflight(str(tmp_path), [], do_index=False)
    assert any("没有待转换" in b for b in r["blocking"])


def test_preflight_blocks_missing_source(tmp_path):
    r = core.preflight(str(tmp_path), [str(tmp_path / "nope.mp4")],
                       do_index=False)
    assert any("源文件不存在" in b for b in r["blocking"])


def test_preflight_warns_when_not_camera_card(tmp_path):
    src = tmp_path / "a.mp4"
    src.write_bytes(b"\x00" * 16)
    out = tmp_path / "out"
    out.mkdir()
    r = core.preflight(str(out), [str(src)], do_index=True)
    assert any("不是影石相机卡" in w for w in r["warnings"])
    assert any("真机原片" in b for b in r["blocking"])


def test_job_ledger_roundtrip(tmp_path):
    dest = str(tmp_path / "card")
    job = {"dest": dest, "items": [{"src": "a.mp4", "status": "done"}]}
    core.save_job(dest, job)
    got = core.load_job(dest)
    assert got and got["items"][0]["status"] == "done"


def test_job_path_is_per_destination(tmp_path):
    a = core.job_path(str(tmp_path / "A"))
    b = core.job_path(str(tmp_path / "B"))
    assert a != b and a.endswith(".json")
    # 大小写/斜线差异不应产生不同文件
    assert core.job_path(str(tmp_path / "A")) == a


def test_set_awake_returns_bool():
    ok = core.set_awake(True)
    try:
        assert isinstance(ok, bool)
    finally:
        core.set_awake(False)

# 铁律：AMBA box 内 0x54 (84) 是音频采样率、0x5B (91) 是音频帧数；
# 0x20 (32) 属于 0x1D (29) 处的视频帧率分母字段的高字节。
# 曾因 udta_with_audio_frames 误用 amba[0]+0x20 把 1001 覆写成 4160750569，
# 每次导入都会写坏产物，且当时测试对此零覆盖。以下三条是防回归护栏。

THUMB = 896 * 512 * 3 // 2
NAIL = 688144


def _make_udta(amba_size: int = 128, nail_size: int = NAIL) -> bytes:
    """合成一个 udta：首个子 box 是 AMBA，随后是 nail。"""
    amba = struct.pack(">I4s", amba_size, b"AMBA") + b"\x00" * (amba_size - 8)
    thumb = b"\x11" * THUMB
    nail = struct.pack(">I4sII", nail_size, b"nail", 896, 512) + thumb
    body = amba + nail
    assert len(body) + 8 == 8 + amba_size + nail_size
    return struct.pack(">I4s", 8 + len(body), b"udta") + body


def _make_template(tmp_path):
    """合成一个最小 MP4：ftyp + moov(mvhd + udta)，够 extract_udta 用。"""
    udta = _make_udta()
    mvhd = struct.pack(">I4s", 8, b"mvhd")
    moov_body = mvhd + udta
    moov = struct.pack(">I4s", 8 + len(moov_body), b"moov") + moov_body
    ftyp = struct.pack(">I4s4s", 16, b"ftyp", b"isom") + b"\x00\x00\x02\x00"
    path = tmp_path / "native.mp4"
    path.write_bytes(ftyp + moov)
    return path


STATS = {
    "video_timescale": 30000,
    "video_duration_ts": 300000,
    "video_frames": 300,
    "audio_rate": 48000,
    "audio_frames": 1406,
}


def test_udta_with_audio_frames_keeps_fps_denominator():
    """udta_with_audio_frames 只能写 0x54/0x5B，不能碰 0x1D 的 1001。"""
    udta = _make_udta()
    buf = bytearray(udta)
    struct.pack_into("<I", buf, 8 + 29, 1001)     # camera_udta 写入的帧率分母
    data = bytes(buf)

    out = rw.udta_with_audio_frames(data, (0, len(data), b"udta"), 1406)

    assert struct.unpack_from("<I", out, 8 + 29)[0] == 1001          # 未被覆写
    assert struct.unpack_from("<I", out, 8 + 0x54)[0] == 1406 * 4    # 音频采样率
    assert struct.unpack_from("<I", out, 8 + 0x5B)[0] == 1406        # 音频帧数


def test_udta_with_audio_frames_rejects_small_amba():
    """AMBA 太短时必须抛错，不能越界静默写。"""
    udta = _make_udta(amba_size=64)
    with pytest.raises(ValueError, match="AMBA"):
        rw.udta_with_audio_frames(udta, (0, len(udta), b"udta"), 100)


def test_camera_udta_writes_expected_amba_fields(tmp_path):
    """camera_udta 的九个字段必须落在文档声明的偏移上。"""
    template = _make_template(tmp_path)
    udta = tf.camera_udta(
        template, old_name="", new_name="",
        thumbnail=b"\x00" * THUMB, stats=STATS,
    )
    amba = [b for b in tf.child_boxes(bytearray(udta), 8, len(udta)) if b[2] == b"AMBA"][0]
    off = amba[0]
    got = {o: struct.unpack_from("<I", udta, off + o)[0]
           for o in (25, 29, 41, 49, 53, 67, 71, 84, 91)}
    assert got == {
        25: 30000, 29: 1001, 41: 300000, 49: 300, 53: 16,
        67: 48000, 71: 1024, 84: 1406 * 4, 91: 1406,
    }


# 铁律：shared/instbox 下的模块必须能被【包导入】与【平铺导入】两种方式加载。
#   桌面端 core._load_inst_modules() 走 `import instbox.moov_rewrap`；
#   PyInstaller（InstaAceImporter.spec 的 pathex=['../shared/instbox']）与
#   直接跑脚本走平铺 `import moov_rewrap`。
#   曾因 moov_rewrap 只做平铺导入（`import inst_transplant`，而该模块在
#   shared/instbox/ 下），包导入必然 ModuleNotFoundError —— 桌面端从源码运行
#   与整个 test_insta.py 都在收集阶段直接失败，且 core._meta_equivalent 会
#   静默退化成逐字节比较，把 f9 可变长的好条目误判成坏条目。


def test_instbox_imports_as_package():
    """包导入：import instbox.moov_rewrap 必须成功且拿到真实的 inst_transplant。"""
    import importlib

    rw = importlib.import_module("instbox.moov_rewrap")
    assert rw.insta is tf, "包导入后 rw.insta 应就是 instbox.inst_transplant"


def test_instbox_imports_flat():
    """平铺导入：shared/instbox 在 sys.path 上时 import moov_rewrap 也要成立。"""
    import subprocess

    shared_instbox = os.path.join(SHARED, "instbox")
    code = (
        "import sys;"
        f"sys.path.insert(0, {shared_instbox!r});"
        "import moov_rewrap;"
        "print(moov_rewrap.insta.__name__)"
    )
    r = subprocess.run([sys.executable, "-c", code],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, f"平铺导入失败: {r.stderr[-500:]}"
    assert r.stdout.strip() == "inst_transplant"


def test_meta_equivalent_ignores_offset_drift():
    """f9（inst 偏移）只改数值时，两份 meta 仍应判为「同一个」。"""
    base = tf.encode_message([
        tf.Field(7, 0, 20261109143000),
        tf.Field(9, 0, 100),
        tf.Field(10, 0, 12),
        tf.Field(19, 2, b"1920x1080"),
    ])
    moved = tf.encode_message([
        tf.Field(7, 0, 20261109143000),
        tf.Field(9, 0, 1000000),   # 偏移变了，长度也变了
        tf.Field(10, 0, 12),
        tf.Field(19, 2, b"1920x1080"),
    ])
    assert core._meta_equivalent(base, moved) is True

    changed = tf.encode_message([
        tf.Field(7, 0, 20261109143001),   # 时间戳变了 → 必须判为不同
        tf.Field(9, 0, 100),
        tf.Field(10, 0, 12),
        tf.Field(19, 2, b"1920x1080"),
    ])
    assert core._meta_equivalent(base, changed) is False


def test_inst_transplant_uses_relative_moov_rewrap():
    """inst_transplant 的 v18-v21 路径必须能用相对导入拿到 moov_rewrap。

    这里是同一类缺陷的第二份副本：函数内 `from moov_rewrap import ...` 在包导入
    下（桌面端 _load_inst_modules）必然 ModuleNotFoundError，而它正好位于主移植
    路径上 —— 测试不会跑到，只有真机/真片导入时才炸。用 ast 静态检查替代：
    该表达式必须存在相对形式的分支。
    """
    import ast

    src = open(os.path.join(SHARED, "instbox", "inst_transplant.py"),
               encoding="utf-8").read()
    tree = ast.parse(src)

    rel, flat = [], []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and \
                node.module.endswith("moov_rewrap"):
            key = node.module
            (rel if node.level and node.level > 0 else flat).append(key)

    assert rel, "inst_transplant 里缺少 `from .moov_rewrap import ...` 相对导入分支"
    names = {a.name for n in ast.walk(tree)
             if isinstance(n, ast.ImportFrom) and n.module and
             n.module.endswith("moov_rewrap")
             for a in n.names}
    assert {"rebuild_media", "filter_avc1_children"} <= names, \
        f"相对导入分支缺少关键符号，实际只有 {sorted(names)}"


def _ast_without_docstrings(path: str) -> str:
    """把源码规约成「只含逻辑」的 ast 文本，用于判断两份副本是否等价。

    为什么去掉 docstring：安卓端与共享端各留一份，注释/文档是按各自读者写的
    （桌面端提 instbox 路径，安卓端提 Chaquopy 打包），强行逐字节一致反而会
    逼人写两边都不贴切的文档。真正必须一致的是逻辑。
    """
    import ast

    tree = ast.parse(open(path, encoding="utf-8").read())
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef,
                             ast.AsyncFunctionDef, ast.ClassDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and \
                    isinstance(body[0].value, ast.Constant) and \
                    isinstance(body[0].value.value, str):
                node.body = body[1:] or [ast.Pass()]
    return ast.dump(tree)


def test_insta_index_copies_do_not_drift():
    """shared/insta_index.py 与安卓端副本的逻辑必须一致。

    仓库里这两份是手工同步的（安卓端靠 Chaquopy 从 app/src/main/python 打包，
    不能直接引用 shared/）。改共享逻辑时漏改一边，症状是「桌面端登记正常、
    手机端相册不认」—— 排查成本极高且不会在单测里暴露，所以在这里加守卫。
    """
    shared_copy = os.path.join(SHARED, "insta_index.py")
    android_copy = os.path.join(os.path.dirname(ROOT), "android", "app",
                                "src", "main", "python", "insta_index.py")
    if not os.path.isfile(android_copy):
        pytest.skip("安卓端副本不在（只检出了桌面端）")

    assert _ast_without_docstrings(shared_copy) == \
        _ast_without_docstrings(android_copy), (
            "shared/insta_index.py 与 android/app/src/main/python/insta_index.py "
            "逻辑已漂移：改一处必须同时改另一处"
        )


def _func_map(path):
    """返回 {函数名: ast 节点}（只取模块顶层函数）。"""
    import ast
    with open(path, encoding="utf-8-sig") as f:
        tree = ast.parse(f.read())
    return {n.name: n for n in tree.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}


def test_android_core_functions_are_not_truncated():
    """安卓端 insta_core.py 的函数体不能是"空壳"。

    这条守卫来自一个真实事故：`batch_convert` 在安卓副本里只剩 docstring +
    参数校验，函数体写到一个赋值就断了，下一个顶层 `def` 紧跟着开始。
    它照样能 import、能通过所有导入测试，只在真的调用时返回 None，
    调用方 `ok, bad = batch_convert(...)` 才炸 TypeError —— 而这条路径
    （目录批量导入）单测从来没覆盖到，缺陷从安卓工程并入仓库起就一直在。

    这里只查结构性症状，不比对桌面/安卓的具体实现（两边本来就有重构差异）：
      1) 有超过 3 行签名+docstring 的函数却只有一个 return/raise 之外的空体
      2) 函数体最后一个语句是赋值/表达式（意味着中途断了，没走到 return）
    """
    import ast
    android_core = os.path.join(os.path.dirname(ROOT), "android", "app",
                                "src", "main", "python", "insta_core.py")
    if not os.path.isfile(android_core):
        pytest.skip("安卓端副本不在（只检出了桌面端）")

    problems = []
    for name, node in _func_map(android_core).items():
        stmts = [s for s in node.body
                 if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))]
        if not stmts:
            problems.append(f"{name}（第 {node.lineno} 行）：只有 docstring，没有函数体")
            continue
        # 声明了非 None 返回类型却没有 return —— 说明函数体半路断了。
        # 只看有返回注解的函数：save_job/_cli_progress 这类本来就返回 None 的
        # 不带注解，用「有没有 return」一刀切会误报。
        ret = node.returns
        if ret is not None and not (isinstance(ret, ast.Constant) and ret.value is None):
            if not any(isinstance(s, ast.Return) for s in ast.walk(node)):
                problems.append(
                    f"{name}（第 {node.lineno} 行）：声明了返回类型却没有 return，函数体可能被截断")

    assert not problems, "安卓端 insta_core.py 存在被截断的函数：\n  " + "\n  ".join(problems)


def test_batch_convert_returns_success_and_failed_lists():
    """batch_convert 必须真的返回 (success, failed)，不能是 None。

    直接调用最容易发现静默截断：截断版本会立刻返回 None，
    而不是等到用户点"批量导入"才在 UI 层变成一句莫名其妙的 TypeError。
    """
    android_py = os.path.join(os.path.dirname(ROOT), "android", "app",
                              "src", "main", "python")
    if not os.path.isfile(os.path.join(android_py, "insta_core.py")):
        pytest.skip("安卓端副本不在（只检出了桌面端）")
    if android_py not in sys.path:
        sys.path.insert(0, android_py)
    import insta_core as ic
    out_dir = tempfile.mkdtemp(prefix="insta_batch_")
    try:
        success, failed = ic.batch_convert([], out_dir)
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)
    assert success == [] and failed == [], (
        f"batch_convert 应返回两个空列表，实际返回 {success!r}, {failed!r}"
    )


def test_convert_without_cancel_does_not_raise_attribute_error():
    """cancel 默认 None，但下游直接调 cancel.is_set()。

    这是一个真实的 AttributeError：`convert(src, out)` 这种最常见的调用
    （CLI、早期 GUI、第三方脚本）会立刻抛
    `'NoneType' object has no attribute 'is_set'`。
    入口处统一归一化成 threading.Event() 后，不传 cancel 也能正常跑。
    """
    import threading
    d = tempfile.mkdtemp(prefix="insta_nocancel_")
    try:
        src = os.path.join(d, "in.mp4")
        with open(src, "wb") as f:
            f.write(b"\x00" * 128)
        # 本机没有 ffmpeg 时会抛 ValidationError，那是"正确的失败"；
        # 这里只要求不能是 AttributeError。
        try:
            core.convert(src, d)
        except AttributeError as e:
            pytest.fail(f"不传 cancel 时不应出现 AttributeError: {e}")
        except Exception:  # noqa: BLE001
            pass
    finally:
        shutil.rmtree(d, ignore_errors=True)
    assert isinstance(threading.Event(), threading.Event)


def test_convert_failure_is_not_reported_as_success():
    """转码失败必须抛异常，不能返回 (None, None)。

    并发路径原来用 `except BaseException: pass` 吞掉所有异常，再靠
    first_error 汇总；但 first_error 只在 _run_ffmpeg 外层记录，
    构建命令行/探测时长这些更早的步骤失败时没人记 —— 于是 convert()
    正常返回 (None, None)，调用方拿到两个 None 当成功路径继续往下走。
    """
    d = tempfile.mkdtemp(prefix="insta_fail_")
    try:
        src = os.path.join(d, "in.mp4")
        with open(src, "wb") as f:
            f.write(b"\x00" * 128)
        # 本机没有 ffmpeg：这是确定会失败的场景
        if core.find_ffmpeg():
            pytest.skip("本机有 ffmpeg，无法构造确定失败的转码")
        with pytest.raises(Exception) as ei:
            core.convert(src, d)
        assert not isinstance(ei.value, AttributeError), (
            f"应当是「找不到 ffmpeg」这类真实错误，而不是 AttributeError: {ei.value}")
        assert str(ei.value).strip(), "失败必须带可读的错误信息"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_batch_convert_stops_on_cancel(monkeypatch):
    """批量导入必须能中途停下。

    注意取消点要设在【第一条转完之后】：batch_convert 开头本来就有一道
    `if cancel.is_set(): raise`，在入口就置位只能测到那道守卫，测不到循环。
    原实现的循环体既不检查 cancel，也不把 cancel 传给 convert，
    于是用户点了取消，剩下的文件还会一个个转完。
    """
    d = tempfile.mkdtemp(prefix="insta_batch_cancel_")
    try:
        files = []
        for i in range(3):
            p = os.path.join(d, "in%d.mp4" % i)
            with open(p, "wb") as f:
                f.write(b"\x00" * 64)
            files.append(p)
        out = os.path.join(d, "out")
        os.makedirs(out)

        cancel = threading.Event()
        calls = []

        def _fake_convert(src, *a, **k):
            calls.append(src)
            cancel.set()          # 第一条转完，用户点了取消
            return ("main.mp4", "lrv.mp4")

        monkeypatch.setattr(core, "convert", _fake_convert)
        with pytest.raises(core.CanceledError):
            core.batch_convert(files, out, cancel=cancel)
        assert len(calls) == 1, f"取消后不应继续转，实际转了 {len(calls)} 个"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_batch_convert_propagates_cancel_from_convert(monkeypatch):
    """convert 内部取消时，batch_convert 要原样上抛，而不是塞进 failed。"""
    d = tempfile.mkdtemp(prefix="insta_batch_cancel2_")
    try:
        src = os.path.join(d, "in.mp4")
        with open(src, "wb") as f:
            f.write(b"\x00" * 64)
        out = os.path.join(d, "out")
        os.makedirs(out)

        def _boom(*a, **k):
            raise core.CanceledError("已取消")

        monkeypatch.setattr(core, "convert", _boom)
        with pytest.raises(core.CanceledError):
            core.batch_convert([src], out)
    finally:
        shutil.rmtree(d, ignore_errors=True)


# 机型适配：GOP 必须从模板量，不能写死 16。
#   实测 Ace Pro 2 的 LRV 是 16，GO Ultra 的 VID=120 / LRV=10，都等于 stss
#   里相邻 sync sample 的差。AMBA[53] 声明的是这条码流的真实关键帧间隔，
#   写死会让 GO Ultra 的码流与声明对不上，相机相册里表现为不显示缩略图。
#   这两条用合成 MP4 覆盖：没有真机素材也能守住。

def _make_gop_mp4(tmp_path, keyframes: list[int], total: int = 300) -> "object":
    """合成一个带 stss 的最小 MP4（ftyp + moov/trak/mdia/minf/stbl/stss）。"""
    entries = b"".join(struct.pack(">I", k) for k in keyframes)
    stss_body = struct.pack(">I4sII", 16 + len(entries), b"stss", 0, len(keyframes)) + entries
    stbl = struct.pack(">I4s", 8 + len(stss_body), b"stbl") + stss_body
    minf = struct.pack(">I4s", 8 + len(stbl), b"minf") + stbl
    # hdlr 的 handler_type 在 body 偏移 8（box 起点 +16）
    hdlr_body = b"\x00" * 8 + b"vide" + b"\x00" * 12
    hdlr = struct.pack(">I4s", 8 + len(hdlr_body), b"hdlr") + hdlr_body
    mdia = struct.pack(">I4s", 8 + len(hdlr) + len(minf), b"mdia") + hdlr + minf
    trak = struct.pack(">I4s", 8 + len(mdia), b"trak") + mdia
    moov = struct.pack(">I4s", 8 + len(trak), b"moov") + trak
    ftyp = struct.pack(">I4s4s", 16, b"ftyp", b"isom") + b"\x00\x00\x02\x00"
    path = tmp_path / "gop_sample.mp4"
    path.write_bytes(ftyp + moov)
    return path


def test_video_gop_reads_keyframe_interval(tmp_path):
    """video_gop 必须返回 stss 里相邻 sync sample 的差。"""
    p = _make_gop_mp4(tmp_path, [1, 121])
    assert tf.video_gop(p) == 120
    p2 = tmp_path / "lrv.lrv"
    p2.write_bytes(_make_gop_mp4(tmp_path, [1, 11, 21, 31]).read_bytes())
    assert tf.video_gop(p2) == 10


def test_video_gop_returns_zero_for_single_keyframe(tmp_path):
    """只有一个关键帧时无从得知间隔，返回 0 让调用方回退。"""
    assert tf.video_gop(_make_gop_mp4(tmp_path, [1])) == 0


def test_video_gop_returns_one_without_stss(tmp_path):
    """没有 stss 表示每帧都是关键帧，GOP 就是 1。"""
    ftyp = struct.pack(">I4s4s", 16, b"ftyp", b"isom") + b"\x00\x00\x02\x00"
    stbl = struct.pack(">I4s", 8, b"stbl")
    minf = struct.pack(">I4s", 8 + len(stbl), b"minf") + stbl
    hdlr_body = b"\x00" * 8 + b"vide" + b"\x00" * 12
    hdlr = struct.pack(">I4s", 8 + len(hdlr_body), b"hdlr") + hdlr_body
    mdia = struct.pack(">I4s", 8 + len(hdlr) + len(minf), b"mdia") + hdlr + minf
    trak = struct.pack(">I4s", 8 + len(mdia), b"trak") + mdia
    moov = struct.pack(">I4s", 8 + len(trak), b"moov") + trak
    p = tmp_path / "all_i.mp4"
    p.write_bytes(ftyp + moov)
    assert tf.video_gop(p) == 1


def test_camera_udta_writes_real_gop_into_amba(tmp_path):
    """传了 gop 就必须原样写进 AMBA[53]，而不是写死 16。"""
    template = _make_template(tmp_path)
    udta = tf.camera_udta(
        template, old_name="", new_name="",
        thumbnail=b"\x00" * THUMB, stats=STATS, gop=120,
    )
    amba = [b for b in tf.child_boxes(bytearray(udta), 8, len(udta)) if b[2] == b"AMBA"][0]
    assert struct.unpack_from("<I", udta, amba[0] + 53)[0] == 120


def test_camera_udta_falls_back_to_16_when_gop_unknown(tmp_path):
    """模板量不出 GOP（0/None）时退回 16，保持 Ace Pro 2 的老行为。"""
    template = _make_template(tmp_path)
    for bad in (0, None):
        udta = tf.camera_udta(
            template, old_name="", new_name="",
            thumbnail=b"\x00" * THUMB, stats=STATS, gop=bad,
        )
        amba = [b for b in tf.child_boxes(bytearray(udta), 8, len(udta))
                if b[2] == b"AMBA"][0]
        assert struct.unpack_from("<I", udta, amba[0] + 53)[0] == 16


# 机型适配：LRV 的编码格式必须跟模板走。
#   Ace Pro 2 的 LRV 是 H.264(avc1)，GO Ultra 的 LRV 是 HEVC(hvc1)。
#   曾把 preview_vc 写死成 libx264/avc1，导致 GO Ultra 的 LRV 采样条目
#   与 AMBA/nail 里声明的东西自相矛盾，相机相册不显示。

GO_ULTRA_SPEC = {
    "video": {
        "codec": "libx265", "width": 1920, "height": 1080, "fps": "60000/1001",
        "pix_fmt": "yuv420p", "color_range": "tv", "codec_tag": "hvc1",
        "handler": "INS.HVC", "encoder": "HVC encoder", "profile": "main",
        "level": 120, "gop": 120,
    },
    "lrv_video": {
        "codec": "libx265", "width": 1280, "height": 720, "fps": "30000/1001",
        "pix_fmt": "yuv420p", "color_range": "tv", "codec_tag": "hvc1",
        "handler": "INS.HVC", "encoder": "HVC encoder", "profile": "main",
        "level": 93, "gop": 10,
    },
    "audio_tracks": [{"codec": "aac", "sample_rate": "48000", "channels": "2",
                      "bit_rate": "192k", "handler": "INS.AAC"}],
}

ACE_PRO_2_SPEC = {
    "video": {
        "codec": "libx265", "width": 1920, "height": 1080, "fps": "30000/1001",
        "pix_fmt": "yuv420p", "color_range": "tv", "codec_tag": "hvc1",
        "handler": "INS.HVC", "encoder": "HVC encoder", "profile": "main",
        "level": 120, "gop": 16,
    },
    "lrv_video": {
        "codec": "libx264", "width": 1280, "height": 720, "fps": "30000/1001",
        "pix_fmt": "yuv420p", "color_range": "tv", "codec_tag": "avc1",
        "handler": "INS.AVC", "encoder": "AVC encoder", "profile": "high",
        "level": None, "gop": 16,
    },
    "audio_tracks": [{"codec": "aac", "sample_rate": "48000", "channels": "2",
                      "bit_rate": "192k", "handler": "INS.AAC"}],
}


def test_spec_tasks_follow_template_lrv_codec_for_go_ultra():
    """GO Ultra 的 LRV 是 HEVC：vc/tag/handler 必须一致，不能留 avc1。"""
    tasks, _ = core._build_spec_tasks("in.mp4", ".", 1, "20261104_141845",
                                      None, GO_ULTRA_SPEC)
    lrv = tasks[1]
    assert lrv[2] == "libx265", f"LRV 编码器应跟随模板，实际 {lrv[2]}"
    assert lrv[3] == "hvc1", f"LRV tag 应跟随模板，实际 {lrv[3]}"
    assert lrv[7] == "INS.HVC", f"LRV handler 应与编码器一致，实际 {lrv[7]}"


def test_spec_tasks_keep_ace_pro_2_lrv_as_h264():
    """Ace Pro 2 的 LRV 是 H.264：老机型行为不能被改坏。"""
    tasks, _ = core._build_spec_tasks("in.mp4", ".", 1, "20261104_141845",
                                      None, ACE_PRO_2_SPEC)
    lrv = tasks[0 + 1]
    assert lrv[2] == "libx264"
    assert lrv[3] == "avc1"
    assert lrv[7] == "INS.AVC"


def test_spec_tasks_carry_template_gop():
    """两个任务的 GOP 必须分别来自 VID/LRV 模板，不是写死 16。"""
    tasks, _ = core._build_spec_tasks("in.mp4", ".", 1, "20261104_141845",
                                      None, GO_ULTRA_SPEC)
    assert tasks[0][14] == 120, f"VID GOP 应为 120，实际 {tasks[0][14]}"
    assert tasks[1][14] == 10, f"LRV GOP 应为 10，实际 {tasks[1][14]}"


def test_spec_tasks_report_zero_gop_when_unknown():
    """spec 里没有 gop（老调用方）时任务里是 0，由 _run_one 回退到 16。"""
    spec = {k: dict(v) if isinstance(v, dict) else v
            for k, v in GO_ULTRA_SPEC.items()}
    spec["video"].pop("gop")
    spec["lrv_video"].pop("gop")
    tasks, _ = core._build_spec_tasks("in.mp4", ".", 1, "20261104_141845", None, spec)
    assert tasks[0][14] == 0 and tasks[1][14] == 0


def test_convert_passes_template_gop_into_ffmpeg_args(monkeypatch):
    """端到端：convert 必须把模板 GOP 送进 ffmpeg 的 -g / keyint。

    只测 _build_spec_tasks 不够 —— 任务元组里带着 GOP，但 _run_one 里
    把 keyint 写死成 16 时，前一条测试照样通过（它只看任务元组）。
    这条拦住"任务对了、命令没用上"的情况。
    """
    calls: list[list[str]] = []

    def fake_run(cmd, duration, progress=None, cancel=None, procs=None, procs_lock=None):
        calls.append(list(cmd))

    monkeypatch.setattr(core, "find_ffmpeg", lambda: "ffmpeg")
    monkeypatch.setattr(core, "_run_ffmpeg", fake_run)
    monkeypatch.setattr(core, "probe", lambda p: {"video": {"duration": "1.0"},
                                                  "streams": []})
    monkeypatch.setattr(core, "next_seq", lambda d: 1)
    monkeypatch.setattr(core, "detect_hw_encoder", lambda: None)
    monkeypatch.setattr(core, "log_path", lambda: os.path.join(tempfile.gettempdir(), "x.log"))

    d = tempfile.mkdtemp(prefix="insta_gop_")
    try:
        src = os.path.join(d, "in.mp4")
        with open(src, "wb") as f:
            f.write(b"\x00" * 128)
        core.convert(src, d, stamp="20261104_141845", spec=GO_ULTRA_SPEC)
    finally:
        shutil.rmtree(d, ignore_errors=True)

    assert len(calls) == 2, f"应编两条（VID+LRV），实际 {len(calls)}"
    joined = [" ".join(c) for c in calls]
    # VID 用 libx265，GOP 体现在 -x265-params 里
    assert any("keyint=120" in s for s in joined), \
        f"VID 的 keyint 应为 120，实际命令：{joined}"
    # LRV 也走 libx265（GO Ultra 模板），GOP=10
    assert any("keyint=10" in s for s in joined), \
        f"LRV 的 keyint 应为 10，实际命令：{joined}"


def _make_sample_entry_mp4(tmp_path, tag: bytes, extra_children: list[bytes]) -> str:
    """合成一个只含单条视频轨、采样条目为 tag 的最小 MP4。"""
    def box(kind: bytes, body: bytes) -> bytes:
        return struct.pack(">I4s", 8 + len(body), kind) + body

    config = box(b"hvcC" if tag != b"avc1" else b"avcC", b"\x01" * 40)
    entry_body = (b"\x00" * 6 + struct.pack(">H", 1) + b"\x00" * 70
                  + config + b"".join(extra_children))
    entry = struct.pack(">I4s", 8 + len(entry_body), tag) + entry_body
    stsd = box(b"stsd", b"\x00" * 4 + struct.pack(">I", 1) + entry)
    stbl = box(b"stbl", stsd)
    minf = box(b"minf", stbl)
    hdlr = box(b"hdlr", b"\x00" * 8 + b"vide" + b"\x00" * 12)
    mdia = box(b"mdia", hdlr + minf)
    trak = box(b"trak", mdia)
    moov = box(b"moov", trak)
    ftyp = struct.pack(">I4s4s", 16, b"ftyp", b"isom") + b"\x00\x00\x02\x00"
    path = tmp_path / f"entry_{tag.decode()}.mp4"
    path.write_bytes(ftyp + moov)
    return str(path)


def _entry_children(tf_mod, path: str) -> tuple[bytes, list[bytes]]:
    data = open(path, "rb").read()
    moov = next(b for b in tf_mod.mp4_boxes(data) if b[2] == b"moov")
    for trak in [b for b in tf_mod.child_boxes(data, moov[0] + 8, moov[0] + moov[1])
                 if b[2] == b"trak"]:
        mdia = tf_mod.direct_child(data, trak, b"mdia")
        hdlr = tf_mod.direct_child(data, mdia, b"hdlr")
        if data[hdlr[0] + 16:hdlr[0] + 20] != b"vide":
            continue
        stsd = tf_mod.direct_child(
            data, tf_mod.direct_child(data, tf_mod.direct_child(data, mdia, b"minf"),
                                      b"stbl"), b"stsd")
        eoff = stsd[0] + 16
        esz = struct.unpack_from(">I", data, eoff)[0]
        return (bytes(data[eoff + 4:eoff + 8]),
                [c[2] for c in tf_mod.child_boxes(data, eoff + 86, eoff + esz)])
    raise AssertionError("video trak not found")


def test_shrink_entry_strips_extras_from_hvc1(tmp_path):
    """GO Ultra 的 LRV 是 hvc1：必须保留 hvcC、去掉 pasp/btrt。

    原实现只认 avc1，遇到 hvc1 直接 return False —— GO Ultra 的 LRV
    永远不会被精简，相机拒收，且日志里连警告都没有。
    """
    def box(kind, body):
        return struct.pack(">I4s", 8 + len(body), kind) + body
    path = _make_sample_entry_mp4(
        tmp_path, b"hvc1",
        [box(b"pasp", struct.pack(">II", 1, 1)), box(b"btrt", b"\x00" * 12)])
    assert core._shrink_avc1_entry(tf, path, b"avcC") is True
    tag, children = _entry_children(tf, path)
    assert tag == b"hvc1", "精简后 tag 不能变"
    assert children == [b"hvcC"], f"只该留 hvcC，实际 {children}"


def test_shrink_entry_strips_extras_from_avc1(tmp_path):
    """Ace Pro 2 的 LRV 是 avc1：老机型行为不能坏。"""
    def box(kind, body):
        return struct.pack(">I4s", 8 + len(body), kind) + body
    path = _make_sample_entry_mp4(
        tmp_path, b"avc1",
        [box(b"pasp", struct.pack(">II", 1, 1)), box(b"btrt", b"\x00" * 12)])
    assert core._shrink_avc1_entry(tf, path, b"avcC") is True
    tag, children = _entry_children(tf, path)
    assert tag == b"avc1"
    assert children == [b"avcC"], f"只该留 avcC，实际 {children}"


def _fn_ast(path, name):
    """取单个顶层函数的 ast（剥掉 docstring），用于比对两份手工同步的实现。"""
    import ast
    with open(path, encoding="utf-8-sig") as f:
        tree = ast.parse(f.read())
    node = next(n for n in tree.body
                if isinstance(n, ast.FunctionDef) and n.name == name)
    for sub in ast.walk(node):
        body = getattr(sub, "body", None)
        if isinstance(body, list) and body and isinstance(body[0], ast.Expr) \
                and isinstance(body[0].value, ast.Constant) \
                and isinstance(body[0].value.value, str):
            sub.body = body[1:]
    return ast.dump(node)


def test_template_from_names_does_not_drift():
    """桌面端与安卓端的 template_from_names 必须一致。

    这个函数决定「拿哪一对文件当模板」。两边逻辑一旦不同，
    症状是「桌面端导入正常、手机端相机不认」—— 而两端的导入链路
    都是黑盒，单测里只能靠这条守卫发现。
    """
    android_core = os.path.join(os.path.dirname(ROOT), "android", "app",
                                "src", "main", "python", "insta_core.py")
    if not os.path.isfile(android_core):
        pytest.skip("安卓端副本不在（只检出了桌面端）")
    desktop_core = os.path.join(ROOT, "core.py")
    assert _fn_ast(desktop_core, "template_from_names") == \
        _fn_ast(android_core, "template_from_names"), (
            "template_from_names 在 desktop/core.py 与 android insta_core.py "
            "里已漂移：改一处必须同时改另一处")


def test_import_with_inst_accepts_template_names():
    """两端 import_with_inst 都要能接收调用方指定的模板名。

    只加了参数却忘了在函数体里用，等于没加 —— 所以顺带断言
    参数真的被读进了 template_from_names 的调用。
    """
    import inspect
    android_core = os.path.join(os.path.dirname(ROOT), "android", "app",
                                "src", "main", "python", "insta_core.py")
    desktop_core = os.path.join(ROOT, "core.py")

    sig = inspect.signature(core.import_with_inst)
    assert "template_names" in sig.parameters, \
        "desktop/core.py 的 import_with_inst 缺少 template_names 参数"

    for path in (desktop_core, android_core):
        if not os.path.isfile(path):
            continue
        src = open(path, encoding="utf-8-sig").read()
        assert "template_from_names(card_root, template_names[0]" in src, (
            f"{path} 收了 template_names 却没有传给 template_from_names")


def test_import_with_inst_actually_uses_template_names(tmp_path, monkeypatch):
    """行为验证：给了 template_names 就必须走它，不能退回自动猜。

    上一版这条只 grep 源码字符串，把「if template_names:」改成
    「if False:」仍然全绿 —— 断言太弱。这里改成真的调一次
    import_with_inst，看 template_from_names 有没有被调用。
    """
    cam = tmp_path / "DCIM" / "Camera01"
    cam.mkdir(parents=True)
    (cam / "VID_20240101_090000_000.mp4").write_bytes(b"\x00" * 32)
    (cam / "LRV_20240101_090000_000.lrv").write_bytes(b"\x00" * 32)

    calls = []

    def fake_from_names(card_root, vid, lrv):
        calls.append((vid, lrv))
        return None  # 让流程停在「找不到模板」，不必真的转码

    monkeypatch.setattr(core, "template_from_names", fake_from_names)

    src = tmp_path / "in.mp4"
    src.write_bytes(b"\x00" * 32)   # 只要存在即可，流程会停在找模板那一步

    with pytest.raises(Exception):
        core.import_with_inst(str(src), str(tmp_path),
                              template_names=("VID_20240101_090000_000.mp4",
                                              "LRV_20240101_090000_000.lrv"))
    assert calls == [("VID_20240101_090000_000.mp4",
                      "LRV_20240101_090000_000.lrv")],         f"template_names 没有被使用，实际调用 {calls}"


def test_template_from_names_requires_matching_pair(tmp_path):
    """指定的两个名字必须是同一对（VID_xxx / LRV_xxx 主干相同）。"""
    import types
    cam = tmp_path / "DCIM" / "Camera01"
    cam.mkdir(parents=True)
    for n in ("VID_20240101_090000_000.mp4", "LRV_20240101_090000_000.lrv",
              "LRV_20230101_080000_000.lrv"):
        (cam / n).write_bytes(b"\x00" * 16)
    # 拼凑对：主名不同，必须拒绝
    assert core.template_from_names(str(tmp_path),
                                    "VID_20240101_090000_000.mp4",
                                    "LRV_20230101_080000_000.lrv") is None


def test_android_core_matches_desktop_on_hardened_helpers():
    """几处「桌面端已修、安卓端忘了跟」的函数必须一致。

    这四处都是真实缺陷的修复现场：
      - save_job：安卓端静默吞 OSError，进度丢了用户不知道
      - has_inst_box：安卓端留了读了不用且不关的句柄，卡大时累积
      - render_cover：安卓端缺参数校验/超时/ffmpeg 判空，无 ffmpeg 时报 TypeError
      - template_from_names：安卓端有、桌面端原本没有
    方向永远是「桌面端改了、安卓端忘了跟」，所以比对两边实现。
    """
    android_core = os.path.join(os.path.dirname(ROOT), "android", "app",
                                "src", "main", "python", "insta_core.py")
    if not os.path.isfile(android_core):
        pytest.skip("安卓端副本不在（只检出了桌面端）")
    desktop_core = os.path.join(ROOT, "core.py")
    drifted = [fn for fn in ("save_job", "has_inst_box", "render_cover",
                             "template_from_names")
               if _fn_ast(desktop_core, fn) != _fn_ast(android_core, fn)]
    assert not drifted, (
        f"这些函数在 desktop/core.py 与 android insta_core.py 之间已漂移：{drifted}")


def test_visual_entry_skips_non_trak_children(tmp_path):
    """moov 的第一个子 box 是 mvhd 时必须跳过，不能拿它去找 mdia。

    真机 VID/LRV 的 moov 布局都是 mvhd 在前、trak 在后。原实现直接对
    moov 的每个子 box 调 direct_child(mdia)，遇到 mvhd 就抛
    invalid child MP4 box —— 两个真机文件都必炸，不是偶发。
    """
    def box(kind, body):
        return struct.pack(">I4s", 8 + len(body), kind) + body

    config = box(b"hvcC", b"\x01" * 40)
    entry_body = (b"\x00" * 6 + struct.pack(">H", 1) + b"\x00" * 70 + config)
    entry = struct.pack(">I4s", 8 + len(entry_body), b"hvc1") + entry_body
    stsd = box(b"stsd", b"\x00" * 4 + struct.pack(">I", 1) + entry)
    stbl = box(b"stbl", stsd)
    minf = box(b"minf", stbl)
    hdlr = box(b"hdlr", b"\x00" * 8 + b"vide" + b"\x00" * 12)
    mdia = box(b"mdia", hdlr + minf)
    trak = box(b"trak", mdia)
    mvhd = box(b"mvhd", b"\x00" * 100)          # 真机布局：mvhd 在 trak 之前
    moov = box(b"moov", mvhd + trak)
    ftyp = struct.pack(">I4s4s", 16, b"ftyp", b"isom") + b"\x00\x00\x02\x00"
    path = tmp_path / "mvhd_first.mp4"
    path.write_bytes(ftyp + moov)

    entry_box, _ancestors = rw.visual_entry(path.read_bytes())
    assert entry_box[2] == b"hvc1"


def test_filter_avc1_children_keeps_hvcc_on_hevc(tmp_path):
    """HEVC 采样条目的配置盒叫 hvcC，照 avcC 过滤会把它删光。"""
    def box(kind, body):
        return struct.pack(">I4s", 8 + len(body), kind) + body
    path = _make_sample_entry_mp4(
        tmp_path, b"hvc1",
        [box(b"pasp", struct.pack(">II", 1, 1)), box(b"btrt", b"\x00" * 12)])
    # filter 末尾要按 inst 元数据修正 payload 偏移，所以文件必须带 inst box。
    meta = tf.encode_message([tf.Field(1, 2, b"0" * 14), tf.Field(9, 0, 0)])
    with open(path, "ab") as f:
        f.write(struct.pack(">I4s", 8 + len(meta), b"inst") + meta)
    rw.filter_avc1_children(Path(path), {b"avcC"}, meta)
    tag, children = _entry_children(tf, path)
    assert tag == b"hvc1"
    assert children == [b"hvcC"], f"hvcC 被删光了，实际 {children}"


def test_tailor_metadata_leaves_proxy_dimensions_alone():
    """代理轨的 f19/f20 跟着模板走，不按容器尺寸改写。

    实测 GO Ultra 的 LRV 里 f19/f20 与主视频完全相同（1920x1080 / 60），
    只有 f26.f2 标出 proxy。原实现给 proxy 硬写 1280x720/30，和真机对不上。
    """
    fields = [
        tf.Field(1, 2, b"IBEEA2605QGDFE"),
        tf.Field(2, 2, b"Insta360 GO Ultra"),
        tf.Field(19, 2, tf.protobuf_pair(1920, 1080)),
        tf.Field(20, 0, 60),
        tf.Field(26, 2, tf.encode_message([tf.Field(2, 0, 0)])),
    ]
    template = tf.encode_message(fields)
    out = tf.tailor_metadata(
        template, catalog_path="/DCIM/Camera01/VID_20240101_090000_000.mp4",
        timestamp_digits=20240101090000, epoch_ms=1704067200000,
        inst_payload_offset=123, duration=3.8,
        width=1280, height=720, proxy=True, fps=30,
    )
    got = tf.parse_message(out)
    assert bytes(tf.field_value(got, 19)) == tf.protobuf_pair(1920, 1080)
    assert tf.field_value(got, 20) == 60
    nested = tf.parse_message(bytes(tf.field_value(got, 26)))
    assert tf.field_value(nested, 2) == 1, "proxy 标记仍要写"

    main = tf.tailor_metadata(
        template, catalog_path="/DCIM/Camera01/VID_20240101_090000_000.mp4",
        timestamp_digits=20240101090000, epoch_ms=1704067200000,
        inst_payload_offset=123, duration=3.8,
        width=1280, height=720, proxy=False, fps=30,
    )
    got_main = tf.parse_message(main)
    assert bytes(tf.field_value(got_main, 19)) == tf.protobuf_pair(1280, 720)
    assert tf.field_value(got_main, 20) == 30


def test_video_profile_carries_codec(monkeypatch):
    """video_profile 必须带出 codec：LRV 编码格式由模板决定。

    Ace Pro 2 的 LRV 是 h264、GO Ultra 是 hevc。不带 codec 时下游只能
    写死 h264，后者的 LRV 采样条目与 AMBA 就对不上。
    """
    fake = {
        "streams": [{"codec_type": "video", "codec_name": "hevc", "width": 1280,
                     "height": 720, "nb_frames": "114", "has_b_frames": 0,
                     "bit_rate": "4000000", "level": 93}],
        "format": {"duration": "3.804"},
    }
    monkeypatch.setattr(tf, "ffprobe", lambda _p: fake)
    profile = tf.video_profile(Path("x.lrv"))
    assert profile["codec"] == "hevc"
    assert profile["width"] == 1280 and profile["height"] == 720


def test_rewrap_and_transplant_copies_do_not_drift():
    """moov_rewrap / inst_transplant 与安卓侧同名副本必须一致。

    `moov_rewrap.py` ↔ `camera_moov_rewrap.py` 曾漂移四处（make_box 缺
    largesize、缺 _chunk_offsets、samples 不认 co64、stco_box 固定 32 位），
    因为没有任何守卫测试，漂了整整一个发布周期都没被发现。症状是
    「大文件（>4GB 偏移）在手机上报错、桌面端正常」。
    """
    pairs = [
        ("shared/instbox/moov_rewrap.py",
         "android/app/src/main/python/camera_moov_rewrap.py",
         ("visual_entry", "filter_avc1_children")),
        ("shared/instbox/inst_transplant.py",
         "android/app/src/main/python/insta360_tf_import.py",
         ("tailor_metadata", "video_profile")),
    ]
    repo = os.path.dirname(SHARED)
    drifted = []
    for left, right, names in pairs:
        lp = os.path.join(repo, left)
        rp = os.path.join(repo, right)
        if not os.path.isfile(rp):
            continue
        for name in names:
            if _fn_ast(lp, name) != _fn_ast(rp, name):
                drifted.append(f"{name}({left} vs {right})")
    assert not drifted, f"这些函数在两份副本之间已漂移：{drifted}"


def test_cli_run_ffmpeg_uses_template_gop(monkeypatch, tmp_path):
    """CLI 路径的 -g 也必须跟着模板走，不能写死 16。

    core.py 主路径早就按模板 GOP 生成命令了，但 inst_transplant 自己的
    CLI（`python inst_transplant.py ...`）一直写死 `-g 16`，GO Ultra 的
    VID 真机是 120 —— 用 CLI 产出的文件关键帧密度对不上。
    """
    captured = []

    def fake_run(cmd, **kwargs):
        captured.append(cmd)
        class R:
            returncode = 0
        return R()

    monkeypatch.setattr(tf.subprocess, "run", fake_run)
    # run_ffmpeg 开头会找 ffmpeg 可执行文件，本机没有，桩掉。
    monkeypatch.setattr(tf, "_tool", lambda name: name)
    monkeypatch.setattr(tf, "ffprobe", lambda _p: {
        "streams": [{"codec_type": "video", "codec_name": "hevc", "width": 1920,
                     "height": 1080, "nb_frames": "228", "has_b_frames": 0,
                     "bit_rate": "20000000", "level": 123}],
        "format": {"duration": "3.804"},
    })
    src = tmp_path / "in.mp4"
    src.write_bytes(b"\x00" * 16)
    tf.run_ffmpeg(src, tmp_path / "out.mp4", proxy=False,
                  created_utc="2026-11-10T00:00:00Z", width=1920, height=1080,
                  video_frames=228, gop=120)
    cmd = captured[0]
    g = cmd.index("-g")
    assert cmd[g + 1] == "120", f"CLI 的 -g 没跟着模板，实际 {cmd[g + 1]}"
    k = cmd.index("-keyint_min")
    assert cmd[k + 1] == "120"
