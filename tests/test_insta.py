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
import struct
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import core                  # noqa: E402
import insta_index as ix     # noqa: E402

SAMPLES = os.path.join(ROOT, "samples")
FILEINFO = os.path.join(SAMPLES, "fileinfo_list.list")


def _sample_paths() -> list[str]:
    if not os.path.isdir(SAMPLES):
        return []
    names = [n for n in os.listdir(SAMPLES)
             if n.startswith(("fileinfo", "editinfo", ".editinfo"))]
    return [os.path.join(SAMPLES, n) for n in sorted(names)]


# ---------------------------------------------------------------- 索引字节级
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


# ---------------------------------------------------------------- f7 位数
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


# ---------------------------------------------------------------- 隐藏文件写入
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


# ---------------------------------------------------------------- inst box 探测
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


# ---------------------------------------------------------------- 进度分段
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


# ---------------------------------------------------------------- 编码器参数
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


# ---------------------------------------------------------------- 封面 / 体检 / 续跑
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
