#!/usr/bin/env python3
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
"""把生成的视频样本重新封装进相机原生 MP4 骨架。

保留编码器产出的视频样本，改用相机原生片段的 moov 布局、
单样本单 chunk 表、零偏移 ctts，以及原生音频轨与样本。
用于把封装器与编码器的影响隔离开来。
"""
from __future__ import annotations

import argparse
import shutil
import struct
import sys
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import inst_transplant as insta  # noqa: E402


def box_bytes(data: bytes, box) -> bytes:
    off, size, _ = box
    return data[off:off + size]


_MAX_32BIT = 0xFFFFFFFF


def make_box(kind: bytes, payload: bytes) -> bytes:
    """构造一个 MP4 box。

    ★ size 字段是 32 位的，但 MP4 规范允许用 largesize 形式表达超过 4 GiB 的 box：
      size=1 + kind + 8 字节 64 位长度。生成的视频一旦超过 4 GiB（1080p HEVC
      约 30 分钟以上），mdat 必然超限，旧实现在这里静默写出非法长度。
    """
    size = len(payload) + 8
    if size <= _MAX_32BIT:
        return struct.pack(">I4s", size, kind) + payload
    return struct.pack(">I4sQ", 1, kind, len(payload) + 16) + payload


def _chunk_offsets(data: bytes, table: dict) -> list:
    """读取 chunk offset 表，同时支持 32 位的 stco 与 64 位的 co64。

    ★ 旧实现只认 stco，遇到 co64（长视频/大文件必然出现）会抛裸 KeyError。
    """
    if b"stco" in table:
        box = table[b"stco"]
        count = struct.unpack_from(">I", data, box[0] + 12)[0]
        return list(struct.unpack_from(f">{count}I", data, box[0] + 16))
    if b"co64" in table:
        box = table[b"co64"]
        count = struct.unpack_from(">I", data, box[0] + 12)[0]
        return list(struct.unpack_from(f">{count}Q", data, box[0] + 16))
    raise ValueError("stbl 里既没有 stco 也没有 co64，文件结构异常")


def children(data: bytes, box):
    off, size, _ = box
    return insta.child_boxes(data, off + 8, off + size)


def child(data: bytes, box, kind: bytes):
    return next(item for item in children(data, box) if item[2] == kind)


def tracks(data: bytes):
    moov = next(item for item in insta.mp4_boxes(data) if item[2] == b"moov")
    result = {}
    for trak in (item for item in children(data, moov) if item[2] == b"trak"):
        mdia = child(data, trak, b"mdia")
        hdlr = child(data, mdia, b"hdlr")
        handler = data[hdlr[0] + 16:hdlr[0] + 20]
        result[handler] = trak
    return moov, result


def sample_table(data: bytes, trak):
    mdia = child(data, trak, b"mdia")
    minf = child(data, mdia, b"minf")
    stbl = child(data, minf, b"stbl")
    return stbl, {item[2]: item for item in children(data, stbl)}


def samples(data: bytes, trak) -> list[bytes]:
    _, table = sample_table(data, trak)
    stsz = table[b"stsz"]
    constant, count = struct.unpack_from(">II", data, stsz[0] + 12)
    sizes = [constant] * count if constant else list(
        struct.unpack_from(f">{count}I", data, stsz[0] + 20)
    )
    offsets = _chunk_offsets(data, table)
    stsc = table[b"stsc"]
    entry_count = struct.unpack_from(">I", data, stsc[0] + 12)[0]
    entries = [struct.unpack_from(">III", data, stsc[0] + 16 + i * 12) for i in range(entry_count)]

    result = []
    sample_index = 0
    entry_index = 0
    for chunk_no, offset in enumerate(offsets, 1):
        while entry_index + 1 < len(entries) and chunk_no >= entries[entry_index + 1][0]:
            entry_index += 1
        per_chunk = entries[entry_index][1]
        cursor = offset
        for _ in range(per_chunk):
            size = sizes[sample_index]
            result.append(data[cursor:cursor + size])
            cursor += size
            sample_index += 1
    if sample_index != count or any(not item for item in result):
        raise ValueError(f"failed to extract all {count} samples")
    return result


def stco_box(offsets: list) -> bytes:
    """写出 chunk offset 表：任一偏移超 32 位时自动改用 co64。

    ★ 若强行用 stco 写超过 0xFFFFFFFF 的偏移，struct 会抛 error 或
      写出静默错位的值，表现为相机能列出条目但打不开。
    """
    if any(value > _MAX_32BIT for value in offsets):
        payload = b"\0\0\0\0" + struct.pack(">I", len(offsets))
        payload += b"".join(struct.pack(">Q", value) for value in offsets)
        return make_box(b"co64", payload)
    payload = b"\0\0\0\0" + struct.pack(">I", len(offsets))
    payload += b"".join(struct.pack(">I", value) for value in offsets)
    return make_box(b"stco", payload)


def stsz_box(sizes: list[int]) -> bytes:
    payload = b"\0\0\0\0" + struct.pack(">II", 0, len(sizes))
    payload += b"".join(struct.pack(">I", value) for value in sizes)
    return make_box(b"stsz", payload)


def ctts_box(sample_count: int) -> bytes:
    payload = b"\0\0\0\0" + struct.pack(">I", 1) + struct.pack(">II", sample_count, 0)
    return make_box(b"ctts", payload)


def strip_sei(sample: bytes, *, hevc: bool) -> bytes:
    pos = 0
    kept = bytearray()
    while pos + 4 <= len(sample):
        size = int.from_bytes(sample[pos:pos + 4], "big")
        end = pos + 4 + size
        if size <= 0 or end > len(sample):
            raise ValueError("invalid length-prefixed NAL unit")
        payload = sample[pos + 4:end]
        kind = (payload[0] >> 1) & 0x3F if hevc else payload[0] & 0x1F
        if kind not in ((39, 40) if hevc else (6,)):
            kept += sample[pos:end]
        pos = end
    if pos != len(sample) or not kept:
        raise ValueError("invalid or empty access unit after stripping SEI")
    return bytes(kept)


def udta_with_audio_frames(data: bytes, udta_box, audio_frames: int) -> bytes:
    udta = bytearray(box_bytes(data, udta_box))
    amba = next(item for item in insta.child_boxes(udta, 8, len(udta)) if item[2] == b"AMBA")
    struct.pack_into("<I", udta, amba[0] + 84, audio_frames * 4)
    struct.pack_into("<I", udta, amba[0] + 91, audio_frames)
    return bytes(udta)


def rebuild_stbl(
    native_data: bytes,
    native_stbl,
    generated_data: bytes,
    generated_stbl,
    offsets: list[int],
    sample_sizes: list[int],
    *,
    video: bool,
) -> bytes:
    generated = {item[2]: item for item in children(generated_data, generated_stbl)}
    rebuilt = []
    for item in children(native_data, native_stbl):
        kind = item[2]
        if kind == b"stco":
            rebuilt.append(stco_box(offsets))
        elif kind == b"stsd":
            rebuilt.append(box_bytes(generated_data, generated[kind]))
        elif kind == b"stsz":
            rebuilt.append(stsz_box(sample_sizes))
        elif kind == b"stts":
            rebuilt.append(box_bytes(generated_data, generated[kind]))
        elif video and kind == b"ctts":
            rebuilt.append(ctts_box(len(sample_sizes)))
        elif video and kind == b"stss":
            rebuilt.append(box_bytes(generated_data, generated[kind]))
        else:
            rebuilt.append(box_bytes(native_data, item))
    return make_box(b"stbl", b"".join(rebuilt))


def rebuild_minf(native_data, native_minf, generated_data, generated_minf, offsets, sample_sizes, *, video):
    native_stbl = child(native_data, native_minf, b"stbl")
    generated_stbl = child(generated_data, generated_minf, b"stbl")
    parts = []
    for item in children(native_data, native_minf):
        if item[2] == b"stbl":
            parts.append(rebuild_stbl(
                native_data, native_stbl, generated_data, generated_stbl, offsets, sample_sizes, video=video,
            ))
        else:
            parts.append(box_bytes(native_data, item))
    return make_box(b"minf", b"".join(parts))


def rebuild_mdia(native_data, native_mdia, generated_data, generated_mdia, offsets, sample_sizes, *, video):
    parts = []
    for item in children(native_data, native_mdia):
        if item[2] == b"mdhd":
            parts.append(box_bytes(generated_data, child(generated_data, generated_mdia, b"mdhd")))
        elif item[2] == b"minf":
            parts.append(rebuild_minf(
                native_data, item, generated_data, child(generated_data, generated_mdia, b"minf"),
                offsets, sample_sizes, video=video,
            ))
        else:
            parts.append(box_bytes(native_data, item))
    return make_box(b"mdia", b"".join(parts))


def rebuild_trak(native_data, native_trak, generated_data, generated_trak, offsets, sample_sizes, *, video):
    parts = []
    native_kinds = {item[2] for item in children(native_data, native_trak)}
    generated_children = {item[2]: item for item in children(generated_data, generated_trak)}
    for item in children(native_data, native_trak):
        if item[2] == b"tkhd":
            parts.append(box_bytes(generated_data, child(generated_data, generated_trak, b"tkhd")))
            if b"edts" not in native_kinds and b"edts" in generated_children:
                parts.append(box_bytes(generated_data, generated_children[b"edts"]))
        elif item[2] == b"edts" and b"edts" in generated_children:
            parts.append(box_bytes(generated_data, generated_children[b"edts"]))
        elif item[2] == b"mdia":
            parts.append(rebuild_mdia(
                native_data, item, generated_data, child(generated_data, generated_trak, b"mdia"),
                offsets, sample_sizes, video=video,
            ))
        else:
            parts.append(box_bytes(native_data, item))
    return make_box(b"trak", b"".join(parts))


def _scan_meta_at(inst_box: bytes, start: int) -> tuple[int, list] | None:
    """从 start 处逐字段解析 protobuf，返回 (消耗字节数, fields)。

    ★ 不能用 len(reference) 切片：tailor_metadata 会改变字段宽度，
      使长度与 inst box 内实测不一致。只能按实际编码逐个解析。
    """
    pos = start
    fields = []
    end = len(inst_box)
    while pos < end:
        try:
            key, np = insta.read_varint(inst_box, pos)
        except Exception:  # noqa: BLE001
            break
        n, w = key >> 3, key & 7
        if n == 0:
            break
        if w == 0:
            try:
                v, np = insta.read_varint(inst_box, np)
            except Exception:  # noqa: BLE001
                break
        elif w == 2:
            try:
                sz, np = insta.read_varint(inst_box, np)
            except Exception:  # noqa: BLE001
                break
            if np + sz > end:
                break
            v = inst_box[np:np + sz]
            np += sz
        elif w == 1:
            if np + 8 > end:
                break
            v = inst_box[np:np + 8]
            np += 8
        elif w == 5:
            if np + 4 > end:
                break
            v = inst_box[np:np + 4]
            np += 4
        else:
            break
        fields.append(insta.Field(n, w, v))
        pos = np
    if not fields:
        return None
    return pos - start, fields


def metadata_in_inst(inst_box: bytes, reference: bytes) -> bytes:
    serial = bytes(insta.field_value(insta.parse_message(reference), 1))
    signature = insta.encode_field(insta.Field(1, 2, serial))
    start = inst_box.rfind(signature)      # ★ 取最后一个（meta 在 inst box 尾部）
    if start < 0:
        raise ValueError("cannot locate inst metadata")
    # ★ 按实际编码长度解析，不用 len(reference)
    scanned = _scan_meta_at(inst_box, start)
    if scanned is None:
        raise ValueError("cannot parse inst metadata")
    size, _fields = scanned
    return inst_box[start:start + size]


def patch_inst_offset(inst_box: bytes, reference: bytes, payload_offset: int):
    """把 inst box 内的元数据换成 reference（并刷新 f9 偏移与长度表）。

    ★ reference 必须是【已经把路径/时间戳/规格改成目标文件自己】的 meta。
      旧实现只改 f9，会把路径等改动丢掉，导致
      inst box 内仍写着模板文件名 → 相机按该路径找不到文件。
    """
    old = metadata_in_inst(inst_box, reference)
    fields = insta.parse_message(reference)
    insta.set_field(fields, 9, 0, payload_offset)
    new = insta.encode_message(fields)
    # 允许长度变化（tailor_metadata 可能改变 varint 宽度）
    return insta.replace_inst_metadata(inst_box, old, new, []), new


def rebuild_media(generated: Path, native: Path, output: Path, reference_meta: bytes):
    generated_data = generated.read_bytes()
    native_data = native.read_bytes()
    gen_moov, gen_tracks = tracks(generated_data)
    native_moov, native_tracks = tracks(native_data)
    generated_probe = insta.ffprobe(generated)
    generated_video = next(stream for stream in generated_probe["streams"] if stream["codec_type"] == "video")
    is_hevc = generated_video["codec_name"] == "hevc"
    video_samples = [strip_sei(item, hevc=is_hevc) for item in samples(generated_data, gen_tracks[b"vide"])]
    video_sizes = [len(item) for item in video_samples]
    audio_samples = samples(generated_data, gen_tracks[b"soun"])
    audio_sizes = [len(item) for item in audio_samples]
    if not audio_samples:
        raise ValueError("native template has no AAC samples")

    prefix = b"".join(
        box_bytes(native_data, item)
        for item in insta.mp4_boxes(native_data)
        if item[2] in (b"ftyp", b"wide")
    )
    payload_start = len(prefix) + 8
    schedule = [(Fraction(i * 1001, 30000), 0, i) for i in range(len(video_samples))]
    schedule += [(Fraction(i * 1024, 48000), 1, i) for i in range(len(audio_samples))]
    schedule.sort()
    payload = bytearray()
    video_offsets = [0] * len(video_samples)
    audio_offsets = [0] * len(audio_samples)
    for _, stream, index in schedule:
        offset = payload_start + len(payload)
        if stream == 0:
            video_offsets[index] = offset
            payload += video_samples[index]
        else:
            audio_offsets[index] = offset
            payload += audio_samples[index]
    mdat = make_box(b"mdat", bytes(payload))

    native_children = children(native_data, native_moov)
    gen_children = {item[2]: item for item in children(generated_data, gen_moov)}
    moov_parts = []
    for item in native_children:
        kind = item[2]
        if kind == b"mvhd":
            moov_parts.append(box_bytes(generated_data, gen_children[kind]))
        elif kind == b"udta":
            moov_parts.append(udta_with_audio_frames(generated_data, gen_children[kind], len(audio_samples)))
        elif kind == b"trak":
            mdia = child(native_data, item, b"mdia")
            hdlr = child(native_data, mdia, b"hdlr")
            handler = native_data[hdlr[0] + 16:hdlr[0] + 20]
            if handler == b"vide":
                moov_parts.append(rebuild_trak(
                    native_data, item, generated_data, gen_tracks[b"vide"], video_offsets, video=True,
                    sample_sizes=video_sizes,
                ))
            else:
                moov_parts.append(rebuild_trak(
                    native_data, item, generated_data, gen_tracks[b"soun"], audio_offsets, video=False,
                    sample_sizes=audio_sizes,
                ))
        else:
            moov_parts.append(box_bytes(native_data, item))
    moov = make_box(b"moov", b"".join(moov_parts))

    _, inst_box = insta.split_inst(generated)
    inst_start = len(prefix) + len(mdat) + len(moov)
    inst_box, new_meta = patch_inst_offset(inst_box, reference_meta, inst_start + 8)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(prefix + mdat + moov + inst_box)
    return new_meta


def visual_entry(data: bytes):
    """定位视频 sample entry：返回 (entry, ancestors)。"""
    moov = next(item for item in insta.mp4_boxes(data) if item[2] == b"moov")
    for trak in insta.child_boxes(data, moov[0] + 8, moov[0] + moov[1]):
        mdia = insta.direct_child(data, trak, b"mdia")
        hdlr = insta.direct_child(data, mdia, b"hdlr")
        if data[hdlr[0] + 16:hdlr[0] + 20] != b"vide":
            continue
        minf = insta.direct_child(data, mdia, b"minf")
        stbl = insta.direct_child(data, minf, b"stbl")
        stsd = insta.direct_child(data, stbl, b"stsd")
        offset = stsd[0] + 16
        size = struct.unpack_from(">I", data, offset)[0]
        return (offset, size, data[offset + 4:offset + 8]), [stsd, stbl, minf, mdia, trak, moov]
    raise ValueError("video sample entry not found")


def filter_avc1_children(path: Path, keep: set[bytes], reference_meta: bytes) -> None:
    """只保留 avc1 sample entry 里 keep 集合的子 box，并修正各级 box 尺寸。

    相机固件对 LRV 的 avc1 sample entry 有严格期望：多余子 box 会导致整段素材被丢弃。
    """
    data = path.read_bytes()
    entry, ancestors = visual_entry(data)
    fixed = data[entry[0]:entry[0] + 86]
    children = insta.child_boxes(data, entry[0] + 86, entry[0] + entry[1])
    kept = b"".join(
        data[off:off + size] for off, size, kind in children if kind in keep
    )
    new_entry = struct.pack(">I", len(fixed) + len(kept)) + fixed[4:] + kept
    delta = len(new_entry) - entry[1]

    out = bytearray(data[:entry[0]] + new_entry + data[entry[0] + entry[1]:])
    for ancestor in ancestors:
        struct.pack_into(">I", out, ancestor[0], ancestor[1] + delta)
    path.write_bytes(bytes(out))

    # box 尺寸变化后，inst 元数据里的 payload 偏移需要跟着修正
    media, inst_box = insta.split_inst(path)
    old_meta = insta.locate_metadata(path, reference_meta)
    fields = insta.parse_message(old_meta)
    insta.set_field(fields, 9, 0, len(media) + 8)
    new_meta = insta.encode_message(fields)
    inst_box = insta.replace_inst_metadata(inst_box, old_meta, new_meta, [])
    path.write_bytes(media + inst_box)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("generated_card", type=Path)
    parser.add_argument("native_root", type=Path)
    parser.add_argument("output_card", type=Path)
    parser.add_argument("--native-video", required=True)
    args = parser.parse_args()
    if args.output_card.exists():
        raise FileExistsError(args.output_card)

    generated_camera = args.generated_card / "DCIM" / "Camera01"
    native_camera = args.native_root / "DCIM" / "Camera01"
    generated_main = next(generated_camera.glob("VID_*.mp4"))
    generated_proxy = next(generated_camera.glob("LRV_*.lrv"))
    native_main = native_camera / args.native_video
    native_proxy = native_main.with_name(args.native_video.replace("VID_", "LRV_", 1)).with_suffix(".lrv")

    fileinfo = args.generated_card / "DCIM" / "fileinfo_list.list"
    outer = insta.parse_message(fileinfo.read_bytes())
    record = insta.parse_message(bytes(outer[0].value))
    reference_meta = bytes(insta.field_value(record, 2))
    output_camera = args.output_card / "DCIM" / "Camera01"
    main_meta = rebuild_media(
        generated_main, native_main, output_camera / generated_main.name, reference_meta,
    )
    rebuild_media(generated_proxy, native_proxy, output_camera / generated_proxy.name, reference_meta)

    insta.set_field(record, 2, 2, main_meta)
    outer[0].value = insta.encode_message(record)
    (args.output_card / "DCIM").mkdir(parents=True, exist_ok=True)
    (args.output_card / "DCIM" / "fileinfo_list.list").write_bytes(insta.encode_message(outer))
    shutil.copy2(
        args.generated_card / "DCIM" / ".editinfo_list.list",
        args.output_card / "DCIM" / ".editinfo_list.list",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
