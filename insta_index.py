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
"""
影石 Insta360 Ace Pro 2 —— 索引表解析 / 生成

背景
====
Insta360 相机相册不是靠"扫目录"认文件的（这点和 DJI 不同）。
它依赖两个 protobuf 索引文件：

    <卡根>/DCIM/fileinfo_list.list          主索引（媒体清单，含完整元数据）
    <卡根>/DCIM/.editinfo_list.list         编辑索引（"是否已编辑"标记）

★ 索引文件在 **DCIM 根目录** 下，不在 Camera01 里。
★ 但索引条目里记录的文件路径指向  /DCIM/Camera01/<文件名>

（实测与相机原生行为一致。）

格式（逆向自真机样本）
=====================
两个文件都是 **无长度前缀的 protobuf 流**：

fileinfo_list.list
    repeated FieldEntry msg = 1;
    message FieldEntry {
        string path = 1;        // "/DCIM/Camera01/VID_20260915_094907_002.mp4"
        MediaInfo meta = 2;     // 完整元数据块（可为空）
    }
    message MediaInfo {
        string device_serial = 1;    // 设备序列号
        string device_model  = 2;    // "Insta360 Ace Pro 2"
        string firmware      = 3;    // "v_2.0.50_build1"
        string gyro          = 5;    // "1_5144.896_4098.847_..."
        uint64 timestamp_digits = 7;  // 20260915094907 (YYYYMMDDHHMMSS)
        uint64 inst_payload_offset = 9; // inst box 在文件中的字节偏移
        uint32 duration_s    = 10;   // 时长（秒，向下取整，>=1）
        bytes  f14           = 14;
        uint32 f18 = 18;
        Dim    resolution     = 19;  // {w,h} = {1920,1080}
        uint32 fps = 20;             // 30
        string color_style = 22;     // "Leica_Viv"
        uint64 f24 = 24;
        double f25 = 25;             // 曝光/光圈类
        Track  track_ref = 26;       // {type=6, proxy:0|1, path=PATH, flag=0}
        Dim    f27 = 27;             // {8192,6144,8192,6144}
        double f28 = 28;             // 1.6
        uint32 f29 = 29;             // 1
        bytes  f31 = 31;             // 陀螺仪/姿态 float 数组
        uint64 epoch_ms = 36;        // 毫秒时间戳
        ... 其余 40+ 个字段原样保留
    }

.editinfo_list.list
    repeated EditEntry msg = 1;
    message EditEntry {
        string path = 1;
        bytes  flag = 2;   // 空(0B)=未编辑; 2 字节(常见 0x12 0x00)=已编辑
    }

逆向来源
========
真机样本反汇编交叉验证：
- 样本：本目录 *_list.list(+.bak 历史序列)
- 实现见 instbox/inst_transplant.py（build_indexes / tailor_metadata）
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field


# ---------------------------------------------------------------- protobuf 原语
def _read_varint(buf: bytes, i: int) -> tuple[int, int]:
    result = 0
    shift = 0
    while True:
        b = buf[i]
        i += 1
        result |= (b & 0x7F) << shift
        if not (b & 0x80):
            break
        shift += 7
    return result, i


def _write_varint(value: int) -> bytes:
    out = bytearray()
    while True:
        b = value & 0x7F
        value >>= 7
        if value:
            out.append(b | 0x80)
        else:
            out.append(b)
            break
    return bytes(out)


def _parse_fields(buf: bytes) -> list[tuple[int, int, object]]:
    """返回 [(field_number, wire_type, value), ...]；wt2 value 为 bytes。"""
    out: list[tuple[int, int, object]] = []
    i = 0
    n = len(buf)
    while i < n:
        key, i = _read_varint(buf, i)
        fnum, wt = key >> 3, key & 7
        if wt == 0:
            v, i = _read_varint(buf, i)
            out.append((fnum, 0, v))
        elif wt == 2:
            ln, i = _read_varint(buf, i)
            out.append((fnum, 2, buf[i:i + ln]))
            i += ln
        elif wt == 1:
            out.append((fnum, 1, buf[i:i + 8]))
            i += 8
        elif wt == 5:
            out.append((fnum, 5, buf[i:i + 4]))
            i += 4
        else:
            raise ValueError(f"unsupported wire type {wt} at field {fnum}")
    return out


def _enc_str(fnum: int, s: str) -> bytes:
    b = s.encode("utf-8")
    return _write_varint((fnum << 3) | 2) + _write_varint(len(b)) + b


def _enc_bytes(fnum: int, b: bytes) -> bytes:
    return _write_varint((fnum << 3) | 2) + _write_varint(len(b)) + b


def _enc_uint(fnum: int, v: int) -> bytes:
    return _write_varint(fnum << 3) + _write_varint(v)


def _enc_dbl(fnum: int, v: float) -> bytes:
    return _write_varint((fnum << 3) | 1) + struct.pack("<d", v)


# ---------------------------------------------------------------- 数据模型
@dataclass
class Dim:
    width: int
    height: int

    def to_bytes(self) -> bytes:
        return _enc_uint(1, self.width) + _enc_uint(2, self.height)

    @classmethod
    def from_bytes(cls, b: bytes) -> "Dim":
        d = {f: v for f, _, v in _parse_fields(b)}
        return cls(int(d.get(1, 0)), int(d.get(2, 0)))


@dataclass
class MediaInfo:
    """一条媒体文件的元数据块（fileinfo_list 的 field 2）。"""
    device_serial: str = ""
    device_model: str = "Insta360 Ace Pro 2"
    firmware: str = "v_2.0.50_build1"
    gyro: str = ""
    timestamp_digits: int = 0      # f7  YYYYMMDDHHMMSS
    inst_payload_offset: int = 0   # f9  inst box 在文件中的字节偏移
    duration_s: int = 0            # f10 时长（秒，>=1）
    resolution: Dim = field(default_factory=lambda: Dim(1920, 1080))
    fps: int = 30
    color_style: str = ""
    gyro_data: bytes = b""
    epoch_ms: int = 0
    track: bytes = b""             # f26 {type=6, proxy:0|1, path, flag}
    raw: dict[int, object] = field(default_factory=dict, repr=False)
    # 原始字段序列（保持真机顺序与重复次数），用于字节级回写
    _order: list = field(default_factory=list, repr=False)

    # ---- 兼容旧属性名 ----
    @property
    def datetime_num(self) -> int:
        return self.timestamp_digits

    @datetime_num.setter
    def datetime_num(self, v: int) -> None:
        self.timestamp_digits = v

    @property
    def file_size(self) -> int:
        return self.inst_payload_offset

    @file_size.setter
    def file_size(self, v: int) -> None:
        self.inst_payload_offset = v

    @property
    def duration_i(self) -> int:
        return self.duration_s

    @duration_i.setter
    def duration_i(self, v: int) -> None:
        self.duration_s = v

    def to_bytes(self) -> bytes:
        """序列化。

        策略与 set_field/encode_message 一致：
        以原始字段序列为基准，只对"已知且被改写"的字段做就地替换，
        未知字段原样保留 —— 这样重建结果与真机字节级一致。
        """
        if not self._order:
            parts: list[bytes] = [
                _enc_str(1, self.device_serial),
                _enc_str(2, self.device_model),
                _enc_str(3, self.firmware),
            ]
            if self.gyro:
                parts.append(_enc_str(5, self.gyro))
            parts += [
                _enc_uint(7, self.timestamp_digits),
                _enc_uint(9, self.inst_payload_offset),
                _enc_uint(10, self.duration_s),
                _enc_bytes(14, b""),
                _enc_uint(18, 1),
                _enc_bytes(19, self.resolution.to_bytes()),
                _enc_uint(20, self.fps),
            ]
            if self.color_style:
                parts.append(_enc_str(22, self.color_style))
            if self.gyro_data:
                parts.append(_enc_bytes(31, self.gyro_data))
            if self.epoch_ms:
                parts.append(_enc_uint(36, self.epoch_ms))
            return b"".join(parts)
        return b"".join(self._encode_field(f, wt, v) for f, wt, v in self._order)

    def _encode_field(self, fnum: int, wt: int, val) -> bytes:
        """把 (字段号, wire type, 值) 编回字节；已知字段用最新属性值。"""
        if fnum == 1:
            return _enc_str(1, self.device_serial)
        if fnum == 2:
            return _enc_str(2, self.device_model)
        if fnum == 3:
            return _enc_str(3, self.firmware)
        if fnum == 5:
            return _enc_str(5, self.gyro)
        if fnum == 7:
            return _enc_uint(7, self.timestamp_digits)
        if fnum == 9:
            return _enc_uint(9, self.inst_payload_offset)
        if fnum == 10:
            return _enc_uint(10, self.duration_s)
        if fnum == 26:
            return _enc_bytes(26, self.track) if self.track else _enc_bytes(26, val)
        if fnum == 19:
            return _enc_bytes(19, self.resolution.to_bytes())
        if fnum == 20:
            return _enc_uint(20, self.fps)
        if fnum == 22:
            return _enc_str(22, self.color_style)
        if fnum == 31:
            return _enc_bytes(31, self.gyro_data)
        if fnum == 36:
            return _enc_uint(36, self.epoch_ms)
        if wt == 2:
            return _enc_bytes(fnum, val)
        if wt == 1:
            return _write_varint((fnum << 3) | 1) + val
        if wt == 5:
            return _write_varint((fnum << 3) | 5) + val
        return _enc_uint(fnum, int(val))

    @classmethod
    def parse(cls, b: bytes) -> "MediaInfo":
        m = cls()
        raw: dict[int, object] = {}
        order: list = []
        for fnum, wt, v in _parse_fields(b):
            raw[fnum] = v
            order.append((fnum, wt, v))
            if fnum == 1 and wt == 2:
                m.device_serial = v.decode("utf-8", "replace")
            elif fnum == 2 and wt == 2:
                m.device_model = v.decode("utf-8", "replace")
            elif fnum == 3 and wt == 2:
                m.firmware = v.decode("utf-8", "replace")
            elif fnum == 5 and wt == 2:
                m.gyro = v.decode("utf-8", "replace")
            elif fnum == 7 and wt == 0:
                m.timestamp_digits = int(v)
            elif fnum == 9 and wt == 0:
                m.inst_payload_offset = int(v)
            elif fnum == 10 and wt == 0:
                m.duration_s = int(v)
            elif fnum == 19 and wt == 2:
                m.resolution = Dim.from_bytes(v)
            elif fnum == 20 and wt == 0:
                m.fps = int(v)
            elif fnum == 22 and wt == 2:
                m.color_style = v.decode("utf-8", "replace")
            elif fnum == 31 and wt == 2:
                m.gyro_data = v
            elif fnum == 36 and wt == 0:
                m.epoch_ms = int(v)
            elif fnum == 26 and wt == 2:
                m.track = v
        m.raw = raw
        m._order = order
        return m


@dataclass
class FileEntry:
    path: str = ""
    meta: MediaInfo | None = None

    def body(self) -> bytes:
        """条目内容体（不含外层 repeated 标签）。"""
        b = _enc_str(1, self.path)
        if self.meta is not None:
            b += _enc_bytes(2, self.meta.to_bytes())
        else:
            b += _enc_bytes(2, b"")
        return b

    def to_bytes(self) -> bytes:
        """完整 repeated 记录：field 1 (LEN) = body。"""
        return _enc_bytes(1, self.body())

    @classmethod
    def parse(cls, entry: bytes) -> "FileEntry":
        e = cls()
        for fnum, wt, v in _parse_fields(entry):
            if fnum == 1 and wt == 2:
                e.path = v.decode("utf-8", "replace")
            elif fnum == 2 and wt == 2:
                e.meta = MediaInfo.parse(v) if v else None
        return e


@dataclass
class EditEntry:
    path: str = ""
    flag: bytes = b""

    def body(self) -> bytes:
        return _enc_str(1, self.path) + _enc_bytes(2, self.flag)

    def to_bytes(self) -> bytes:
        return _enc_bytes(1, self.body())

    @classmethod
    def parse(cls, entry: bytes) -> "EditEntry":
        e = cls()
        for fnum, wt, v in _parse_fields(entry):
            if fnum == 1 and wt == 2:
                e.path = v.decode("utf-8", "replace")
            elif fnum == 2 and wt == 2:
                e.flag = v
        return e


# ---------------------------------------------------------------- 文件级 API
def parse_fileinfo(data: bytes) -> list[FileEntry]:
    return [FileEntry.parse(v) for f, wt, v in _parse_fields(data)
            if f == 1 and wt == 2]


def build_fileinfo(entries: list[FileEntry]) -> bytes:
    """无长度前缀，直接拼接各条目。"""
    return b"".join(e.to_bytes() for e in entries)


def parse_editinfo(data: bytes) -> list[EditEntry]:
    return [EditEntry.parse(v) for f, wt, v in _parse_fields(data)
            if f == 1 and wt == 2]


def build_editinfo(entries: list[EditEntry]) -> bytes:
    return b"".join(e.to_bytes() for e in entries)


# ---------------------------------------------------------------- 便捷操作
# editinfo 条目的 flag：作者 build_indexes 写作 encode_message([Field(1,0,0)]) = b'\x08\x00'
# （真机样本里也常见 b'\x08\x00'；完全空 b'' 是另一类残缺条目）
EDIT_FLAG_UNEDITED = b"\x08\x00"
EDIT_FLAG_EDITED = b"\x12\x00"


def add_file_entry(fileinfo: bytes, entry: FileEntry) -> bytes:
    """追加一条到主索引（真机行为就是 append-last）。"""
    return fileinfo + entry.to_bytes()


def add_edit_entry(editinfo: bytes, path: str,
                   flag: bytes = EDIT_FLAG_UNEDITED) -> bytes:
    return editinfo + EditEntry(path, flag).to_bytes()


def find_entry(fileinfo: bytes, path: str) -> FileEntry | None:
    for e in parse_fileinfo(fileinfo):
        if e.path == path:
            return e
    return None


def register_media(fileinfo: bytes, editinfo: bytes, path: str,
                   meta: MediaInfo, *, sort: bool = True) -> tuple[bytes, bytes]:
    """把一对媒体登记进两个索引（幂等：已存在则替换）。

    与作者 build_indexes(insert=None) 一致：去重后按 path 排序。
    """
    entries = [e for e in parse_fileinfo(fileinfo) if e.path != path]
    entries.append(FileEntry(path, meta))
    if sort:
        entries.sort(key=lambda e: e.path)
    new_file = build_fileinfo(entries)

    eentries = [e for e in parse_editinfo(editinfo) if e.path != path]
    eentries.append(EditEntry(path, EDIT_FLAG_UNEDITED))
    if sort:
        eentries.sort(key=lambda e: e.path)
    new_edit = build_editinfo(eentries)
    return new_file, new_edit


def main() -> None:
    """自检：解析随附样本并回写比对。"""
    import os
    import sys
    here = os.path.dirname(os.path.abspath(__file__))
    sample_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(here, "samples")

    fi = os.path.join(sample_dir, "fileinfo_list.list")
    ei = os.path.join(sample_dir, ".editinfo_list.list")
    if os.path.isfile(fi):
        data = open(fi, "rb").read()
        entries = parse_fileinfo(data)
        rebuilt = build_fileinfo(entries)
        print(f"fileinfo_list.list: {len(data)}B -> {len(entries)} entries, "
              f"rebuild {len(rebuilt)}B, identical={rebuilt == data}")
        for e in entries:
            m = e.meta
            res = f"{m.resolution.width}x{m.resolution.height}" if m else "—"
            print(f"   {e.path}  {res}  {m.device_model if m else ''}")
    if os.path.isfile(ei):
        data = open(ei, "rb").read()
        entries = parse_editinfo(data)
        rebuilt = build_editinfo(entries)
        print(f".editinfo_list.list: {len(data)}B -> {len(entries)} entries, "
              f"rebuild {len(rebuilt)}B, identical={rebuilt == data}")
        for e in entries:
            print(f"   {e.path}  flag={e.flag.hex() or 'empty'}")


if __name__ == "__main__":
    main()
