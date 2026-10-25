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
"""把普通视频写入影石 Ace Pro 2 相机卡目录结构。

将源视频转码为相机兼容的主视频 / 代理文件双轨结构，从相机原生录制片段
移植 ``inst`` MP4 box，并追加 protobuf 索引记录。

使用前请备份相机卡。该格式未公开，操作有风险。
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable


VIDEO_NAME = re.compile(r"^VID_(\d{8})_(\d{6})_(\d{3})\.mp4$", re.I)


@dataclass
class Field:
    number: int
    wire: int
    value: int | bytes


def read_varint(data: bytes, pos: int) -> tuple[int, int]:
    value = 0
    for shift in range(0, 70, 7):
        if pos >= len(data):
            raise ValueError("truncated varint")
        byte = data[pos]
        pos += 1
        value |= (byte & 0x7F) << shift
        if byte < 0x80:
            return value, pos
    raise ValueError("varint is too long")


def encode_varint(value: int) -> bytes:
    if value < 0:
        raise ValueError("negative protobuf varint")
    out = bytearray()
    while value >= 0x80:
        out.append((value & 0x7F) | 0x80)
        value >>= 7
    out.append(value)
    return bytes(out)


def parse_message(data: bytes) -> list[Field]:
    fields: list[Field] = []
    pos = 0
    while pos < len(data):
        key, pos = read_varint(data, pos)
        number, wire = key >> 3, key & 7
        if number == 0:
            raise ValueError("invalid protobuf field zero")
        if wire == 0:
            value, pos = read_varint(data, pos)
        elif wire == 1:
            value = data[pos : pos + 8]
            pos += 8
        elif wire == 2:
            size, pos = read_varint(data, pos)
            value = data[pos : pos + size]
            pos += size
        elif wire == 5:
            value = data[pos : pos + 4]
            pos += 4
        else:
            raise ValueError(f"unsupported protobuf wire type {wire}")
        if isinstance(value, bytes) and pos > len(data):
            raise ValueError("truncated protobuf field")
        fields.append(Field(number, wire, value))
    return fields


def encode_field(field: Field) -> bytes:
    out = bytearray(encode_varint((field.number << 3) | field.wire))
    if field.wire == 0:
        out += encode_varint(int(field.value))
    elif field.wire == 1:
        out += bytes(field.value)
    elif field.wire == 2:
        raw = bytes(field.value)
        out += encode_varint(len(raw)) + raw
    elif field.wire == 5:
        out += bytes(field.value)
    else:
        raise ValueError(f"unsupported protobuf wire type {field.wire}")
    return bytes(out)


def encode_message(fields: Iterable[Field]) -> bytes:
    return b"".join(encode_field(field) for field in fields)


def field_value(fields: list[Field], number: int) -> int | bytes:
    return next(field.value for field in fields if field.number == number)


def set_field(fields: list[Field], number: int, wire: int, value: int | bytes) -> None:
    for field in fields:
        if field.number == number:
            if field.wire != wire:
                raise ValueError(f"field {number} has unexpected wire type")
            field.value = value
            return
    fields.append(Field(number, wire, value))
    fields.sort(key=lambda item: item.number)


def protobuf_pair(a: int, b: int) -> bytes:
    return encode_message([Field(1, 0, a), Field(2, 0, b)])


def tailor_metadata(
    template: bytes,
    *,
    catalog_path: str,
    timestamp_digits: int,
    epoch_ms: int,
    inst_payload_offset: int,
    duration: float,
    width: int,
    height: int,
    proxy: bool,
    fps: int | None = None,
) -> bytes:
    fields = parse_message(template)
    set_field(fields, 7, 0, timestamp_digits)
    set_field(fields, 9, 0, inst_payload_offset)
    set_field(fields, 10, 0, max(1, math.floor(duration)))
    set_field(fields, 19, 2, protobuf_pair(width, height))
    # ★ f20 = 帧率（真机 VID 为 60，LRV 为 30）；未指定时按 proxy 推断
    set_field(fields, 20, 0, int(fps) if fps else (30 if proxy else 60))
    set_field(fields, 36, 0, epoch_ms)

    nested = parse_message(bytes(field_value(fields, 26)))
    set_field(nested, 2, 0, 1 if proxy else 0)
    set_field(nested, 3, 2, catalog_path.encode("ascii"))
    set_field(fields, 26, 2, encode_message(nested))
    return encode_message(fields)


def mp4_boxes(data: bytes) -> list[tuple[int, int, bytes]]:
    boxes: list[tuple[int, int, bytes]] = []
    pos = 0
    while pos + 8 <= len(data):
        size = int.from_bytes(data[pos : pos + 4], "big")
        kind = data[pos + 4 : pos + 8]
        header = 8
        if size == 1:
            if pos + 16 > len(data):
                raise ValueError("truncated extended MP4 box")
            size = int.from_bytes(data[pos + 8 : pos + 16], "big")
            header = 16
        elif size == 0:
            size = len(data) - pos
        if size < header or pos + size > len(data):
            raise ValueError(f"invalid MP4 box at 0x{pos:x}")
        boxes.append((pos, size, kind))
        pos += size
    if pos != len(data):
        raise ValueError("bytes remain after the final MP4 box")
    return boxes


def child_boxes(data: bytes, start: int, end: int) -> list[tuple[int, int, bytes]]:
    boxes: list[tuple[int, int, bytes]] = []
    pos = start
    while pos + 8 <= end:
        size = int.from_bytes(data[pos : pos + 4], "big")
        kind = data[pos + 4 : pos + 8]
        if size < 8 or pos + size > end:
            raise ValueError(f"invalid child MP4 box at 0x{pos:x}")
        boxes.append((pos, size, kind))
        pos += size
    if pos != end:
        raise ValueError("bytes remain after the final child MP4 box")
    return boxes


def extract_udta(path: Path) -> bytes:
    data = path.read_bytes()
    moov_offset, moov_size, _ = next(box for box in mp4_boxes(data) if box[2] == b"moov")
    children = child_boxes(data, moov_offset + 8, moov_offset + moov_size)
    udta_offset, udta_size, _ = next(box for box in children if box[2] == b"udta")
    return data[udta_offset : udta_offset + udta_size]


def media_stats(path: Path) -> dict[str, int]:
    command = [
        _tool("ffprobe"), "-v", "error", "-show_entries",
        "stream=codec_type,time_base,duration_ts,nb_frames,sample_rate", "-of", "json", str(path),
    ]
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    streams = json.loads(result.stdout)["streams"]
    video = next(stream for stream in streams if stream["codec_type"] == "video")
    audio = next(stream for stream in streams if stream["codec_type"] == "audio")
    time_num, time_den = (int(part) for part in video["time_base"].split("/"))
    if time_num != 1:
        raise ValueError(f"unsupported video time base: {video['time_base']}")
    return {
        "video_timescale": time_den,
        "video_duration_ts": int(video["duration_ts"]),
        "video_frames": int(video["nb_frames"]),
        "audio_rate": int(audio["sample_rate"]),
        "audio_frames": int(audio["nb_frames"]),
    }


def camera_udta(
    template: Path,
    *,
    old_name: str,
    new_name: str,
    thumbnail: bytes,
    stats: dict[str, int],
) -> bytes:
    udta = bytearray(extract_udta(template))
    if len(old_name) != len(new_name):
        raise ValueError("media names must have equal lengths")
    udta = bytearray(bytes(udta).replace(old_name.encode("ascii"), new_name.encode("ascii")))
    children = child_boxes(udta, 8, len(udta))
    amba_offset, amba_size, _ = next(box for box in children if box[2] == b"AMBA")
    nail_offset, nail_size, _ = next(box for box in children if box[2] == b"nail")
    if amba_size != 97 or nail_size != 688144 or len(thumbnail) != 896 * 512 * 3 // 2:
        raise ValueError("unexpected AMBA/nail template layout")

    amba = bytearray(udta[amba_offset : amba_offset + amba_size])
    struct.pack_into("<I", amba, 25, stats["video_timescale"])
    struct.pack_into("<I", amba, 29, 1001)
    struct.pack_into("<I", amba, 41, stats["video_duration_ts"])
    struct.pack_into("<I", amba, 49, stats["video_frames"])
    struct.pack_into("<I", amba, 53, 16)
    struct.pack_into("<I", amba, 67, stats["audio_rate"])
    struct.pack_into("<I", amba, 71, 1024)
    struct.pack_into("<I", amba, 84, stats["audio_frames"] * 4)
    struct.pack_into("<I", amba, 91, stats["audio_frames"])
    udta[amba_offset : amba_offset + amba_size] = amba

    nail = struct.pack(">I4sII", 688144, b"nail", 896, 512) + thumbnail
    udta[nail_offset : nail_offset + nail_size] = nail
    return bytes(udta)


def inject_udta(path: Path, udta: bytes) -> None:
    data = path.read_bytes()
    boxes = mp4_boxes(data)
    moov_offset, moov_size, _ = next(box for box in boxes if box[2] == b"moov")
    moov_end = moov_offset + moov_size
    children = child_boxes(data, moov_offset + 8, moov_end)
    kept = [data[offset : offset + size] for offset, size, kind in children if kind != b"udta"]
    if not kept or kept[0][4:8] != b"mvhd":
        raise ValueError("unexpected generated moov layout")
    new_moov = struct.pack(">I4s", 8 + sum(map(len, kept)) + len(udta), b"moov")
    new_moov += kept[0] + udta + b"".join(kept[1:])
    path.write_bytes(data[:moov_offset] + new_moov + data[moov_end:])


def split_inst(path: Path) -> tuple[bytes, bytes]:
    data = path.read_bytes()
    boxes = mp4_boxes(data)
    if not boxes or boxes[-1][2] != b"inst":
        raise ValueError(f"{path} has no final Insta360 'inst' box")
    offset, size, _ = boxes[-1]
    return data[:offset], data[offset : offset + size]


def patch_ftyp(path: Path, template: Path) -> None:
    """Copy the camera's brand/minor-version prefix without shifting offsets."""
    with template.open("rb") as stream:
        donor = stream.read(24)
    if len(donor) < 24:
        raise ValueError("missing template MP4 ftyp box")
    with path.open("r+b") as stream:
        header = stream.read(24)
        if header[4:8] != b"ftyp" or donor[4:8] != b"ftyp" or len(header) < 24:
            raise ValueError("missing MP4 ftyp box")
        stream.seek(8)
        stream.write(donor[8:24])
        # FFmpeg emits an eight-byte ``free`` compatibility box here; the
        # camera emits ``wide`` at the same location and size.
        ftyp_size = int.from_bytes(header[:4], "big")
        stream.seek(ftyp_size)
        compatibility = stream.read(8)
        if compatibility[:4] == b"\x00\x00\x00\x08" and compatibility[4:] == b"free":
            stream.seek(ftyp_size + 4)
            stream.write(b"wide")


def replace_inst_metadata(
    inst_box: bytes,
    old_metadata: bytes,
    new_metadata: bytes,
    replacements: list[tuple[bytes, bytes]],
) -> bytes:
    if inst_box.count(old_metadata) != 1:
        raise ValueError("template metadata is not unique inside the inst box")
    old_length = len(old_metadata)
    delta = len(new_metadata) - old_length
    pos = inst_box.index(old_metadata)
    out = inst_box[:pos] + new_metadata + inst_box[pos + old_length :]

    # Firmware stores the protobuf length as a little-endian uint16 directly
    # after the metadata.  Update it when the encoded varint widths changed.
    footer = pos + len(new_metadata)
    if footer + 4 <= len(out) and out[footer + 2 : footer + 4] == struct.pack("<H", old_length):
        out = out[: footer + 2] + struct.pack("<H", len(new_metadata)) + out[footer + 4 :]

    for old, new in replacements:
        if len(old) != len(new):
            raise ValueError("media names must have equal lengths")
        out = out.replace(old, new)
    out = bytearray(struct.pack(">I", len(out)) + out[4:])

    # v3 stores a second payload-size value in its 72-byte trailer and a
    # type/format/size/start table in the final type-0 record.  A protobuf
    # varint-width change (for example duration 127 -> 128 seconds) changes
    # the metadata record size; updating only the MP4 box and record footer
    # makes the entire inst invalid and the camera drops the catalog item.
    payload = out[8:]
    trailer_size = 72
    if len(payload) >= trailer_size + 6 and payload[-32:] == b"8db42d694ccc418790edff439fe026bf":
        table_footer = len(payload) - trailer_size - 6
        table_fmt, table_kind, table_size = struct.unpack_from("<BBI", payload, table_footer)
        table_start = table_footer - table_size
        if (table_fmt, table_kind) != (0, 0) or table_start < 0 or table_size % 10:
            raise ValueError("invalid v3 inst offset table")
        metadata_start = pos - 8
        metadata_entry_found = False
        for table_pos in range(table_start, table_footer, 10):
            kind, fmt, size, start = struct.unpack_from("<BBII", payload, table_pos)
            if kind == 1 and start == metadata_start:
                struct.pack_into("<I", payload, table_pos + 2, len(new_metadata))
                metadata_entry_found = True
            elif delta and start > metadata_start:
                struct.pack_into("<I", payload, table_pos + 6, start + delta)
        if not metadata_entry_found:
            raise ValueError("v3 inst metadata is absent from offset table")
        struct.pack_into("<I", payload, len(payload) - 40, len(payload))
        out[8:] = payload
    return bytes(out)


def repair_inst_metadata_layout(path: Path, reference_meta: bytes) -> None:
    """Repair stale v3 metadata size/trailer fields without touching MP4 media."""
    media, inst_box = split_inst(path)
    metadata = locate_metadata(path, reference_meta)
    pos = inst_box.index(metadata)
    payload = bytearray(inst_box[8:])
    table_footer = len(payload) - 72 - 6
    table_fmt, table_kind, table_size = struct.unpack_from("<BBI", payload, table_footer)
    table_start = table_footer - table_size
    if (table_fmt, table_kind) != (0, 0) or table_start < 0 or table_size % 10:
        raise ValueError("invalid v3 inst offset table")
    metadata_start = pos - 8
    old_size = None
    for table_pos in range(table_start, table_footer, 10):
        kind, _fmt, size, start = struct.unpack_from("<BBII", payload, table_pos)
        if kind == 1 and start == metadata_start:
            old_size = size
            struct.pack_into("<I", payload, table_pos + 2, len(metadata))
            break
    if old_size is None:
        raise ValueError("v3 inst metadata is absent from offset table")
    struct.pack_into("<I", payload, len(payload) - 40, len(payload))
    repaired = struct.pack(">I4s", len(payload) + 8, b"inst") + payload
    path.write_bytes(media + repaired)


def locate_metadata(media: Path, template_metadata: bytes) -> bytes:
    _, inst = split_inst(media)
    fields = parse_message(template_metadata)
    serial = bytes(field_value(fields, 1))
    signature = encode_field(Field(1, 2, serial))
    start = inst.find(signature)
    if start < 0:
        raise ValueError(f"cannot locate protobuf metadata in {media}")
    candidate = inst[start : start + len(template_metadata)]
    parse_message(candidate)
    return candidate


def _tool(name: str) -> str:
    """定位 ffmpeg / ffprobe：环境变量 → exe/程序目录 → 模块附近 → PATH。

    ★ 打包成单文件 exe 后，__file__ 指向 _MEIxxxx/instbox/，
      而 ffmpeg.exe 通常在 exe 同目录的 bin 子目录下；
      旧版只查模块附近 → 找不到 → 返回裸名 → subprocess 抛 WinError 2。
    """
    env = os.environ.get(name.upper() + "_PATH")
    if env and os.path.isfile(env):
        return env
    exe_name = name + (".exe" if os.name == "nt" else "")
    here = os.path.dirname(os.path.abspath(__file__))
    cands = [
        here,
        os.path.join(here, "bin"),
        os.path.join(os.path.dirname(here), "bin"),
    ]
    # ★ 程序实际所在目录（打包后 = exe 所在目录；开发时 = 脚本目录）
    try:
        import sys as _sys
        if getattr(_sys, "frozen", False):
            base = os.path.dirname(os.path.abspath(_sys.executable))
            cands += [base, os.path.join(base, "bin")]
        else:
            main_mod = _sys.modules.get("__main__")
            mf = getattr(main_mod, "__file__", None)
            if mf:
                base = os.path.dirname(os.path.abspath(mf))
                cands += [base, os.path.join(base, "bin")]
    except Exception:  # noqa: BLE001
        pass
    for d in cands:
        p = os.path.join(d, exe_name)
        if os.path.isfile(p):
            return p
    found = shutil.which(name)
    if found:
        return found
    # ★ 真的找不到就报错，不要返回裸名让底层抛 WinError 2
    raise FileNotFoundError(
        f"找不到 {name}（已找: 环境变量 {name.upper()}_PATH、"
        f"{os.pathsep.join(cands)}、PATH）；请把 {exe_name} 放到程序同目录的 bin 下。")


def ffprobe(path: Path) -> dict:
    command = [
        _tool("ffprobe"), "-v", "error", "-show_entries",
        "format=duration:stream=codec_type,codec_name,width,height,has_b_frames,level,bit_rate,nb_frames",
        "-of", "json", str(path),
    ]
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


def run_ffmpeg(
    source: Path,
    output: Path,
    *,
    proxy: bool,
    created_utc: str,
    width: int,
    height: int,
    video_frames: int | None = None,
    b_frames: int = 0,
    bitrate: int | None = None,
    level: int | None = None,
    refs: int | None = None,
    cq: int | None = None,
    proxy_hevc: bool = False,
    dummy_video: bool = False,
    use_gpu: bool = True,
) -> None:
    info = ffprobe(source)
    has_audio = any(stream.get("codec_type") == "audio" for stream in info.get("streams", []))
    source_video = next(stream for stream in info.get("streams", []) if stream.get("codec_type") == "video")
    vf = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black,setsar=1,format=yuv420p,setrange=full"
    )
    if dummy_video:
        vf += ",drawbox=color=black:t=fill"
    command = [_tool("ffmpeg"), "-hide_banner", "-y"]
    if use_gpu:
        # NVIDIA NVDEC hardware decode.  Without -hwaccel_output_format the
        # decoded frames are copied back to software memory, so the software
        # scale filter and NVENC both accept them (NVENC uploads internally).
        command += ["-hwaccel", "cuda"]
        hardware_decoder = {"hevc": "hevc_cuvid", "h264": "h264_cuvid"}.get(source_video.get("codec_name"))
        if hardware_decoder:
            command += ["-c:v", hardware_decoder]
    command += ["-i", str(source)]
    if not has_audio:
        command += ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000"]
    command += ["-map", "0:v:0", "-map", "0:a:0" if has_audio else "1:a:0", "-vf", vf]
    if proxy and proxy_hevc:
        command += [
            "-c:v", "hevc_nvenc", "-preset", "p4", "-profile:v", "main", "-tier", "high",
            "-g", "16", "-keyint_min", "16", "-sc_threshold", "0", "-bf", "0",
            "-slices", "1", "-extra_sei", "0", "-udu_sei", "0", "-tag:v", "hvc1",
        ]
        if cq is not None:
            command += ["-rc", "vbr", "-cq", str(cq), "-b:v", "0"]
        else:
            target_rate = bitrate or 2_000_000
            command += [
                "-rc", "cbr", "-b:v", str(target_rate), "-maxrate", str(target_rate),
                "-bufsize", str(target_rate * 2),
            ]
    elif proxy:
        target_rate = bitrate or 4_000_000
        if use_gpu:
            command += [
                "-c:v", "h264_nvenc", "-preset", "p4", "-profile:v", "high",
                "-g", "16", "-keyint_min", "16", "-sc_threshold", "0", "-bf", str(b_frames),
                "-slices", "1", "-extra_sei", "0", "-udu_sei", "0", "-tag:v", "avc1",
            ]
            if cq is not None:
                command += ["-rc", "vbr", "-cq", str(cq), "-b:v", "0"]
            else:
                command += [
                    "-b:v", str(target_rate), "-maxrate", str(target_rate * 5 // 4),
                    "-bufsize", str(target_rate * 2),
                ]
            if refs is not None:
                command += ["-refs", str(refs), "-dpb_size", str(refs)]
        else:
            command += [
                "-c:v", "libx264", "-preset", "veryfast", "-profile:v", "high",
                "-level:v", "4.1", "-b:v", str(target_rate), "-maxrate", str(target_rate * 5 // 4),
                "-bufsize", str(target_rate * 2), "-tag:v", "avc1", "-g", "16",
                "-keyint_min", "16", "-sc_threshold", "0", "-bf", str(b_frames),
            ]
            if refs is not None:
                command += ["-refs", str(refs), "-x264-params", f"ref={refs}:weightp=0:open-gop=0"]
            if cq is not None:
                command += ["-crf", str(cq)]
    else:
        target_rate = bitrate
        if target_rate and level == 123:
            # This driver rejects 50 Mb/s at HEVC High Tier level 4.1 even
            # though short camera clips can report a higher measured average.
            # Keep NVENC active at the highest locally verified setting.
            target_rate = min(target_rate, 20_000_000)
        if use_gpu:
            command += [
                "-c:v", "hevc_nvenc", "-preset", "p4", "-profile:v", "main", "-tier", "high",
                "-g", "16", "-keyint_min", "16", "-sc_threshold", "0", "-bf", "0",
                "-slices", "2", "-extra_sei", "0", "-udu_sei", "0", "-tag:v", "hvc1",
            ]
            if cq is not None:
                command += ["-rc", "vbr", "-cq", str(cq), "-b:v", "0"]
            elif target_rate:
                command += [
                    "-rc", "cbr", "-b:v", str(target_rate), "-maxrate", str(target_rate),
                    "-bufsize", str(target_rate * 2),
                ]
            else:
                command += ["-rc", "vbr", "-cq", "24", "-b:v", "0"]
        else:
            command += [
                "-c:v", "libx265", "-preset", "ultrafast",
                "-pix_fmt", "yuv420p", "-tag:v", "hvc1",
                "-x265-params", "keyint=16:min-keyint=16:scenecut=0:bframes=0:range=full:info=0",
            ]
            if target_rate:
                command += [
                    "-b:v", str(target_rate), "-maxrate", str(target_rate),
                    "-bufsize", str(target_rate * 2),
                ]
            else:
                command += ["-crf", "24"]
    if level is not None:
        level_text = f"{level // 10}.{level % 10}" if proxy else f"{level // 30}.{(level % 30) // 3}"
        command += ["-level:v", level_text]
    if video_frames is not None:
        command += ["-frames:v", str(video_frames)]
    command += [
        "-r", "30000/1001", "-fps_mode", "cfr", "-movie_timescale", "30000",
        "-color_range", "pc", "-colorspace", "bt709", "-color_trc", "bt709", "-color_primaries", "bt709",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", "-shortest",
        "-metadata", f"creation_time={created_utc}",
        "-metadata:s:v:0", f"creation_time={created_utc}",
        "-metadata:s:v:0", f"handler_name={chr(16)}INS.{'AVC' if proxy and not proxy_hevc else 'HVC'}",
        "-metadata:s:v:0", "language=eng",
        "-metadata:s:v:0", f"encoder={'AVC encoder' if proxy and not proxy_hevc else 'HVC encoder'}",
        "-metadata:s:a:0", f"creation_time={created_utc}",
        "-metadata:s:a:0", f"handler_name={chr(16)}INS.AAC",
        "-metadata:s:a:0", "language=eng", "-f", "mp4", str(output),
    ]
    try:
        subprocess.run(command, check=True)
    except subprocess.CalledProcessError:
        if use_gpu:
            print("GPU encode failed; retrying with software encoders.", file=sys.stderr)
            run_ffmpeg(
                source, output, proxy=proxy, created_utc=created_utc,
                width=width, height=height, video_frames=video_frames,
                b_frames=b_frames, bitrate=bitrate, level=level, refs=refs, cq=cq,
                proxy_hevc=proxy_hevc, dummy_video=dummy_video, use_gpu=False,
            )
        else:
            raise


def make_thumbnail(source: Path, output: Path, at_seconds: float = 10.0) -> bytes:
    duration = float(ffprobe(source)["format"]["duration"])
    seek = at_seconds if duration > at_seconds + 0.1 else max(0.0, duration / 2)
    vf = "scale=896:512:force_original_aspect_ratio=decrease,pad=896:512:(ow-iw)/2:(oh-ih)/2:black"
    command = [
        _tool("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{seek:.6f}", "-i", str(source),
        "-vf", vf, "-frames:v", "1", "-pix_fmt", "nv12", "-f", "rawvideo", str(output),
    ]
    subprocess.run(command, check=True)
    thumbnail = output.read_bytes()
    if len(thumbnail) != 896 * 512 * 3 // 2:
        raise ValueError(f"unexpected thumbnail size: {len(thumbnail)}")
    return thumbnail


def patch_inst_thumbnail(path: Path, thumbnail: bytes) -> None:
    """Replace the v3 type-2 thumbnail record without changing inst size."""
    if len(thumbnail) != 896 * 512 * 3 // 2:
        raise ValueError("unexpected thumbnail size")
    media, inst_box = split_inst(path)
    payload = bytearray(inst_box[8:])
    magic = b"8db42d694ccc418790edff439fe026bf"
    header_size = 72
    if len(payload) < header_size + 6 or payload[-32:] != magic:
        raise ValueError("unsupported inst thumbnail layout")
    footer = len(payload) - header_size - 6
    fmt, kind, table_size = struct.unpack_from("<BBI", payload, footer)
    table_start = footer - table_size
    if (fmt, kind) != (0, 0) or table_size % 10:
        raise ValueError("missing v3 inst offset table")
    for pos in range(table_start, footer, 10):
        record_kind, record_fmt, record_size, record_start = struct.unpack_from("<BBII", payload, pos)
        if record_kind != 2:
            continue
        if record_fmt != 0 or record_size != 40 + len(thumbnail):
            raise ValueError("unexpected inst thumbnail record")
        payload[record_start + 40:record_start + record_size] = thumbnail
        path.write_bytes(media + struct.pack(">I4s", len(payload) + 8, b"inst") + payload)
        return
    raise ValueError("inst contains no type-2 thumbnail")


def patch_nail_thumbnail(path: Path, thumbnail: bytes) -> None:
    data = bytearray(path.read_bytes())
    moov = next(box for box in mp4_boxes(data) if box[2] == b"moov")
    udta = next(
        box for box in child_boxes(data, moov[0] + 8, moov[0] + moov[1]) if box[2] == b"udta"
    )
    nail = next(
        box for box in child_boxes(data, udta[0] + 8, udta[0] + udta[1]) if box[2] == b"nail"
    )
    if nail[1] != 16 + len(thumbnail):
        raise ValueError("unexpected nail box size")
    data[nail[0] + 16:nail[0] + nail[1]] = thumbnail
    path.write_bytes(data)


def patch_media_thumbnail(path: Path, thumbnail: bytes) -> None:
    patch_nail_thumbnail(path, thumbnail)
    patch_inst_thumbnail(path, thumbnail)


# Exact Ace Pro 2 AAC-LC AudioSampleEntry verified by the v17/v18 hardware
# matrix.  Construct it directly: generated AAC packets are compatible, but
# FFmpeg's larger 110-byte mp4a entry prevents the firmware from recognizing
# duration and dimensions.
CAMERA_MP4A_ENTRY = bytes.fromhex(
    "000000566d7034610000000000000001000000000000000000020000fffe0000"
    "bb80000000000032657364730000000003808022000000048080164015002000"
    "0002ee000002ee000580800511900000000680800102"
)


def direct_child(data: bytes, parent: tuple[int, int, bytes], kind: bytes) -> tuple[int, int, bytes]:
    return next(
        box for box in child_boxes(data, parent[0] + 8, parent[0] + parent[1])
        if box[2] == kind
    )


def audio_sample_entry(data: bytes) -> tuple[tuple[int, int, bytes], list[tuple[int, int, bytes]]]:
    moov = next(box for box in mp4_boxes(data) if box[2] == b"moov")
    for trak in (box for box in child_boxes(data, moov[0] + 8, moov[0] + moov[1]) if box[2] == b"trak"):
        mdia = direct_child(data, trak, b"mdia")
        hdlr = direct_child(data, mdia, b"hdlr")
        if data[hdlr[0] + 16:hdlr[0] + 20] != b"soun":
            continue
        minf = direct_child(data, mdia, b"minf")
        stbl = direct_child(data, minf, b"stbl")
        stsd = direct_child(data, stbl, b"stsd")
        offset = stsd[0] + 16
        size = struct.unpack_from(">I", data, offset)[0]
        return (offset, size, data[offset + 4:offset + 8]), [stsd, stbl, minf, mdia, trak, moov]
    raise ValueError("audio track not found")


def repoint_inst_metadata(path: Path, reference_meta: bytes) -> bytes:
    media, inst_box = split_inst(path)
    old_meta = locate_metadata(path, reference_meta)
    fields = parse_message(old_meta)
    set_field(fields, 9, 0, len(media) + 8)
    new_meta = encode_message(fields)
    inst_box = replace_inst_metadata(inst_box, old_meta, new_meta, [])
    path.write_bytes(media + inst_box)
    return new_meta


def install_camera_mp4a(path: Path, reference_meta: bytes) -> bytes:
    data = path.read_bytes()
    target, ancestors = audio_sample_entry(data)
    if target[2] != b"mp4a":
        raise ValueError("audio sample entry is not mp4a")
    delta = len(CAMERA_MP4A_ENTRY) - target[1]
    out = bytearray(data[:target[0]] + CAMERA_MP4A_ENTRY + data[target[0] + target[1]:])
    for ancestor in ancestors:
        struct.pack_into(">I", out, ancestor[0], ancestor[1] + delta)
    path.write_bytes(out)
    return repoint_inst_metadata(path, reference_meta)


def remove_audio_edts(path: Path, reference_meta: bytes) -> bytes:
    data = path.read_bytes()
    moov = next(box for box in mp4_boxes(data) if box[2] == b"moov")
    audio_trak = None
    for trak in (box for box in child_boxes(data, moov[0] + 8, moov[0] + moov[1]) if box[2] == b"trak"):
        mdia = direct_child(data, trak, b"mdia")
        hdlr = direct_child(data, mdia, b"hdlr")
        if data[hdlr[0] + 16:hdlr[0] + 20] == b"soun":
            audio_trak = trak
            break
    if audio_trak is None:
        raise ValueError("audio track not found")
    edts = next(
        (box for box in child_boxes(data, audio_trak[0] + 8, audio_trak[0] + audio_trak[1]) if box[2] == b"edts"),
        None,
    )
    if edts is None:
        return locate_metadata(path, reference_meta)
    out = bytearray(data[:edts[0]] + data[edts[0] + edts[1]:])
    struct.pack_into(">I", out, audio_trak[0], audio_trak[1] - edts[1])
    struct.pack_into(">I", out, moov[0], moov[1] - edts[1])
    path.write_bytes(out)
    return repoint_inst_metadata(path, reference_meta)


def video_template(template_root: Path, requested_name: str | None) -> tuple[str, bytes, Path, Path]:
    index = template_root / "DCIM" / "fileinfo_list.list"
    if not index.is_file():
        raise FileNotFoundError(f"missing template index: {index}")
    for outer in parse_message(index.read_bytes()):
        if outer.number != 1 or outer.wire != 2:
            continue
        record = parse_message(bytes(outer.value))
        path = bytes(field_value(record, 1)).decode("ascii")
        name = Path(path).name
        if VIDEO_NAME.match(name):
            if requested_name is not None and name.lower() != requested_name.lower():
                continue
            metadata = bytes(field_value(record, 2))
            main = template_root / "DCIM" / "Camera01" / name
            proxy = main.with_name(name.replace("VID_", "LRV_", 1)).with_suffix(".lrv")
            if not main.is_file() or not proxy.is_file():
                raise FileNotFoundError("template video is missing its MP4/LRV pair")
            return name, metadata, main, proxy
    if requested_name is not None:
        raise ValueError(f"template index contains no record for {requested_name}")
    raise ValueError("template index contains no video record")


def video_profile(path: Path) -> dict[str, int]:
    info = ffprobe(path)
    video = next(stream for stream in info["streams"] if stream["codec_type"] == "video")
    return {
        "width": int(video["width"]),
        "height": int(video["height"]),
        "frames": int(video["nb_frames"]),
        "b_frames": int(video["has_b_frames"]),
        "bitrate": int(video["bit_rate"]),
        "level": int(video["level"]),
    }


def choose_names(camera_dir: Path, when: datetime, requested: int | None) -> tuple[str, str]:
    used = {path.name.lower() for path in camera_dir.glob("*")}
    sequence = requested if requested is not None else 1
    if requested is None:
        sequence = max(
            [int(match.group(3)) for path in camera_dir.glob("VID_*.mp4") if (match := VIDEO_NAME.match(path.name))]
            or [0]
        ) + 1
    while sequence <= 999:
        stem = f"{when:%Y%m%d}_{when:%H%M%S}_{sequence:03d}"
        main, proxy = f"VID_{stem}.mp4", f"LRV_{stem}.lrv"
        if main.lower() not in used and proxy.lower() not in used:
            return main, proxy
        sequence += 1
    raise ValueError("no free three-digit sequence number")


def record_path(outer: Field) -> str | None:
    if outer.number != 1 or outer.wire != 2:
        return None
    try:
        inner = parse_message(bytes(outer.value))
        return bytes(field_value(inner, 1)).decode("ascii")
    except (StopIteration, UnicodeDecodeError, ValueError):
        return None


def write_preserving_windows_attributes(path: Path, data: bytes) -> None:
    """Rewrite an existing hidden file without Windows CREATE_ALWAYS.

    Opening a hidden file with ``wb`` can fail with ERROR_ACCESS_DENIED even
    for its owner/Administrator. ``r+b`` changes the existing file object and
    therefore preserves both the Hidden attribute and its ACL.
    """
    if path.exists():
        with path.open("r+b") as stream:
            stream.seek(0)
            stream.write(data)
            stream.truncate()
            stream.flush()
            os.fsync(stream.fileno())
    else:
        with path.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())


def build_indexes(
    card_root: Path,
    record: bytes,
    catalog_path: str,
    *,
    insert: str | None = None,
) -> dict[Path, bytes]:
    dcim = card_root / "DCIM"
    fileinfo = dcim / "fileinfo_list.list"
    editinfo = dcim / ".editinfo_list.list"
    fileinfo.parent.mkdir(parents=True, exist_ok=True)

    file_fields = parse_message(fileinfo.read_bytes()) if fileinfo.exists() else []
    file_fields = [field for field in file_fields if record_path(field) != catalog_path]
    new_file_field = Field(1, 2, record)
    if insert == "first":
        file_fields.insert(0, new_file_field)
    else:
        file_fields.append(new_file_field)
    if insert is None:
        file_fields.sort(key=lambda field: record_path(field) or "")

    edit_record = encode_message(
        [Field(1, 2, catalog_path.encode("ascii")), Field(2, 2, encode_message([Field(1, 0, 0)]))]
    )
    edit_fields = parse_message(editinfo.read_bytes()) if editinfo.exists() else []
    edit_fields = [field for field in edit_fields if record_path(field) != catalog_path]
    new_edit_field = Field(1, 2, edit_record)
    if insert == "first":
        edit_fields.insert(0, new_edit_field)
    else:
        edit_fields.append(new_edit_field)
    if insert is None:
        edit_fields.sort(key=lambda field: record_path(field) or "")
    return {fileinfo: encode_message(file_fields), editinfo: encode_message(edit_fields)}


def commit_indexes(index_data: dict[Path, bytes]) -> None:
    old_data = {path: path.read_bytes() if path.exists() else None for path in index_data}
    try:
        for path, data in index_data.items():
            write_preserving_windows_attributes(path, data)
    except Exception:
        for path, data in old_data.items():
            if data is not None:
                write_preserving_windows_attributes(path, data)
            elif path.exists():
                path.unlink()
        raise


def backup_indexes(card_root: Path) -> list[Path]:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backups: list[Path] = []
    for name in ("fileinfo_list.list", ".editinfo_list.list"):
        path = card_root / "DCIM" / name
        if path.exists():
            backup = path.with_name(f"{path.name}.{stamp}.bak")
            shutil.copy2(path, backup)
            backups.append(backup)
    return backups


def parse_when(value: str | None) -> datetime:
    if value is None:
        return datetime.now().astimezone().replace(microsecond=0)
    parsed = datetime.strptime(value, "%Y%m%d_%H%M%S")
    return parsed.astimezone()


def insertion_defaults(camera_dir: Path, insert: str) -> tuple[datetime, int]:
    existing: list[tuple[datetime, int]] = []
    for path in camera_dir.glob("VID_*.mp4"):
        match = VIDEO_NAME.match(path.name)
        if match:
            when = datetime.strptime(match.group(1) + match.group(2), "%Y%m%d%H%M%S").astimezone()
            existing.append((when, int(match.group(3))))
    if not existing:
        return datetime.now().astimezone().replace(microsecond=0), 1
    used_sequences = {sequence for _, sequence in existing}
    if insert == "first":
        when = min(item[0] for item in existing) - timedelta(seconds=1)
        candidate = min(used_sequences) - 1
        if candidate < 1:
            candidate = max(used_sequences) + 1
    else:
        when = max(item[0] for item in existing) + timedelta(seconds=1)
        candidate = max(used_sequences) + 1
    while candidate in used_sequences and candidate <= 999:
        candidate += 1
    if not 1 <= candidate <= 999:
        raise ValueError("no free sequence number for requested insertion")
    return when, candidate


def sequence_number(value: str) -> int:
    number = int(value)
    if not 1 <= number <= 999:
        raise argparse.ArgumentTypeError("sequence must be between 1 and 999")
    return number


def even_dimension(value: str) -> int:
    number = int(value)
    if number < 16 or number > 8192 or number % 2:
        raise argparse.ArgumentTypeError("dimension must be an even number between 16 and 8192")
    return number


def validate_output(path: Path, *, proxy: bool, width: int, height: int, frames: int | None) -> float:
    info = ffprobe(path)
    duration = float(info["format"]["duration"])
    video = next(stream for stream in info["streams"] if stream["codec_type"] == "video")
    expected = (("h264" if proxy else "hevc"), width, height)
    actual = (video.get("codec_name"), video.get("width"), video.get("height"))
    if actual != expected:
        raise ValueError(f"unexpected encoded stream {actual}, wanted {expected}")
    if frames is not None and int(video.get("nb_frames", -1)) != frames:
        raise ValueError(f"unexpected frame count {video.get('nb_frames')}, wanted {frames}")
    return duration


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="ordinary input video")
    parser.add_argument("card_root", type=Path, help="TF-card root or a backup directory")
    parser.add_argument("--template-root", type=Path, required=True, help="backup containing a genuine MP4/LRV pair")
    parser.add_argument(
        "--template-video", metavar="VID_*.mp4",
        help="select an exact genuine template record instead of the first indexed video",
    )
    parser.add_argument(
        "--match-template", action="store_true",
        help="match the selected template's dimensions, frame count, B-frames, level, and bitrate class",
    )
    parser.add_argument(
        "--full-duration", action="store_true",
        help="with --match-template, keep its format but do not cap output to its frame count",
    )
    parser.add_argument("--main-bitrate", type=int, help="override main HEVC bitrate in bits/s")
    parser.add_argument("--proxy-bitrate", type=int, help="override LRV H.264 bitrate in bits/s")
    parser.add_argument("--main-width", type=even_dimension, help="override main-track width")
    parser.add_argument("--main-height", type=even_dimension, help="override main-track height")
    parser.add_argument("--proxy-width", type=even_dimension, default=854, help="LRV width (default: 854)")
    parser.add_argument("--proxy-height", type=even_dimension, default=480, help="LRV height (default: 480)")
    parser.add_argument("--main-cq", type=int, choices=range(0, 52), default=40, help="main CQ (default: 40)")
    parser.add_argument("--proxy-cq", type=int, choices=range(0, 52), default=30, help="LRV CQ (default: 30)")
    main_mode = parser.add_mutually_exclusive_group()
    main_mode.add_argument(
        "--dummy-main", dest="dummy_main", action="store_true", default=True,
        help="encode a black ultra-low-bitrate HEVC main track (default)",
    )
    main_mode.add_argument(
        "--real-main", dest="dummy_main", action="store_false",
        help="encode the source image into the HEVC main track",
    )
    parser.add_argument("--proxy-hevc", action="store_true", help="diagnostic: encode the LRV as HEVC/hvc1")
    parser.add_argument("--timestamp", help="local YYYYMMDD_HHMMSS (default: now)")
    parser.add_argument("--sequence", type=sequence_number, metavar="1..999")
    parser.add_argument(
        "--insert", choices=("first", "last"),
        help="insert before the earliest or after the latest catalog item; also chooses time/sequence by default",
    )
    parser.add_argument("--dry-run", action="store_true", help="validate inputs and print the planned names")
    parser.add_argument("--keep-work", action="store_true", help="keep transcoded temporary files on failure")
    parser.add_argument(
        "--no-index-backup", action="store_true",
        help="do not create timestamped .bak copies (use for disposable card-image directories only)",
    )
    parser.add_argument(
        "--proxy-refs", type=int, choices=range(1, 17), metavar="1..16", default=1,
        help="H.264 LRV reference-frame and DPB count (default: 1)",
    )
    parser.add_argument(
        "--proxy-bframes", type=int, choices=range(0, 5), metavar="0..4",
        help="override the H.264 LRV B-frame count for diagnostics",
    )
    parser.add_argument(
        "--software-proxy", action="store_true",
        help="encode only the LRV with libx264 (main video remains NVHEVC)",
    )
    args = parser.parse_args()

    source = args.source.resolve()
    card_root = args.card_root.resolve()
    template_root = args.template_root.resolve()
    if not source.is_file():
        parser.error(f"source does not exist: {source}")
    shutil.which("ffmpeg") or parser.error("ffmpeg is not on PATH")
    shutil.which("ffprobe") or parser.error("ffprobe is not on PATH")

    old_main_name, template_meta, template_main, template_proxy = video_template(
        template_root, args.template_video,
    )
    old_proxy_name = old_main_name.replace("VID_", "LRV_", 1).replace(".mp4", ".lrv")
    if args.match_template:
        main_profile = video_profile(template_main)
        proxy_profile = video_profile(template_proxy)
        # ``has_b_frames`` reflects SPS decoder reorder capacity, not actual
        # frame types.  Ace Pro 2 LRV samples report 2 but contain I/P only.
        proxy_profile["b_frames"] = 0
        if main_profile["frames"] != proxy_profile["frames"]:
            raise ValueError("template MP4/LRV frame counts do not match")
        target_frames: int | None = None if args.full_duration else main_profile["frames"]
    else:
        main_profile = {"width": 1920, "height": 1080, "b_frames": 0, "bitrate": 0, "level": 0}
        proxy_profile = {"width": 1280, "height": 720, "b_frames": 0, "bitrate": 4_000_000, "level": 0}
        target_frames = None
    if args.full_duration and not args.match_template:
        parser.error("--full-duration requires --match-template")
    if args.main_bitrate is not None:
        main_profile["bitrate"] = args.main_bitrate
    if args.proxy_bitrate is not None:
        proxy_profile["bitrate"] = args.proxy_bitrate
    if args.main_width is not None:
        main_profile["width"] = args.main_width
    if args.main_height is not None:
        main_profile["height"] = args.main_height
    if args.proxy_width is not None:
        proxy_profile["width"] = args.proxy_width
    if args.proxy_height is not None:
        proxy_profile["height"] = args.proxy_height
    camera_dir = card_root / "DCIM" / "Camera01"
    if args.insert is not None:
        insertion_when, insertion_sequence = insertion_defaults(camera_dir, args.insert)
        when = parse_when(args.timestamp) if args.timestamp else insertion_when
        requested_sequence = args.sequence if args.sequence is not None else insertion_sequence
    else:
        when = parse_when(args.timestamp)
        requested_sequence = args.sequence
    main_name, proxy_name = choose_names(camera_dir, when, requested_sequence)
    catalog_path = f"/DCIM/Camera01/{main_name}"
    print(f"main : {main_name}")
    print(f"proxy: {proxy_name}")
    if args.dry_run:
        print("dry-run: template and toolchain checks passed")
        return 0

    camera_dir.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="insta360-import-", dir=card_root))
    main_base_path = work / "main.mp4"
    proxy_base_path = work / "proxy.mp4"
    thumbnail_path = work / "thumbnail.yuv"
    final_main = camera_dir / main_name
    final_proxy = camera_dir / proxy_name
    try:
        created_utc = when.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        run_ffmpeg(
            source, main_base_path, proxy=False, created_utc=created_utc,
            width=main_profile["width"], height=main_profile["height"],
            video_frames=target_frames, b_frames=main_profile["b_frames"],
            bitrate=main_profile["bitrate"] or None, level=main_profile["level"] or None,
            cq=args.main_cq, dummy_video=args.dummy_main,
        )
        run_ffmpeg(
            source, proxy_base_path, proxy=True, created_utc=created_utc,
            width=proxy_profile["width"], height=proxy_profile["height"],
            video_frames=target_frames,
            b_frames=(args.proxy_bframes if args.proxy_bframes is not None else proxy_profile["b_frames"]),
            bitrate=proxy_profile["bitrate"] or None, level=proxy_profile["level"] or None,
            refs=args.proxy_refs, cq=args.proxy_cq, proxy_hevc=args.proxy_hevc,
            use_gpu=not args.software_proxy,
        )
        thumbnail = make_thumbnail(source, thumbnail_path)
        main_udta = camera_udta(
            template_main, old_name=old_main_name, new_name=main_name,
            thumbnail=thumbnail, stats=media_stats(main_base_path),
        )
        proxy_udta = camera_udta(
            template_proxy, old_name=old_proxy_name, new_name=proxy_name,
            thumbnail=thumbnail, stats=media_stats(proxy_base_path),
        )
        inject_udta(main_base_path, main_udta)
        inject_udta(proxy_base_path, proxy_udta)
        patch_ftyp(main_base_path, template_main)
        patch_ftyp(proxy_base_path, template_proxy)
        duration = validate_output(
            main_base_path, proxy=False, width=main_profile["width"],
            height=main_profile["height"], frames=target_frames,
        )
        validate_output(
            proxy_base_path, proxy=not args.proxy_hevc, width=proxy_profile["width"],
            height=proxy_profile["height"], frames=target_frames,
        )

        _, main_inst = split_inst(template_main)
        _, proxy_inst = split_inst(template_proxy)
        old_proxy_meta = locate_metadata(template_proxy, template_meta)
        timestamp_digits = int(when.strftime("%Y%m%d%H%M%S"))
        epoch_ms = int(when.timestamp() * 1000)
        main_meta = tailor_metadata(
            template_meta, catalog_path=catalog_path, timestamp_digits=timestamp_digits,
            epoch_ms=epoch_ms, inst_payload_offset=main_base_path.stat().st_size + 8,
            duration=duration, width=main_profile["width"], height=main_profile["height"], proxy=False,
        )
        proxy_meta = tailor_metadata(
            old_proxy_meta, catalog_path=catalog_path, timestamp_digits=timestamp_digits,
            epoch_ms=epoch_ms, inst_payload_offset=proxy_base_path.stat().st_size + 8,
            duration=duration, width=main_profile["width"], height=main_profile["height"], proxy=True,
        )
        replacements = [
            (old_main_name.encode("ascii"), main_name.encode("ascii")),
            (old_proxy_name.encode("ascii"), proxy_name.encode("ascii")),
        ]
        main_inst = replace_inst_metadata(main_inst, template_meta, main_meta, replacements)
        proxy_inst = replace_inst_metadata(proxy_inst, old_proxy_meta, proxy_meta, replacements)
        with main_base_path.open("ab") as stream:
            stream.write(main_inst)
        with proxy_base_path.open("ab") as stream:
            stream.write(proxy_inst)
        patch_inst_thumbnail(main_base_path, thumbnail)
        patch_inst_thumbnail(proxy_base_path, thumbnail)

        # The successful v18-v21 path is not FFmpeg's moov.  Rebuild both
        # files around the camera-style one-sample-per-chunk skeleton, then
        # apply the two firmware-sensitive sample-entry rules.
        from moov_rewrap import rebuild_media
        filter_avc1_children = globals().get("filter_avc1_children")
        if filter_avc1_children is None:
            from moov_rewrap import filter_avc1_children

        main_rewrapped = work / "main-camera.mp4"
        proxy_rewrapped = work / "proxy-camera.lrv"
        main_meta = rebuild_media(
            main_base_path, template_main, main_rewrapped, main_meta,
        )
        proxy_meta = rebuild_media(
            proxy_base_path, template_proxy, proxy_rewrapped, proxy_meta,
        )
        if not args.proxy_hevc:
            filter_avc1_children(proxy_rewrapped, {b"avcC"}, proxy_meta)
        main_meta = install_camera_mp4a(main_rewrapped, main_meta)
        proxy_meta = install_camera_mp4a(proxy_rewrapped, proxy_meta)
        main_meta = remove_audio_edts(main_rewrapped, main_meta)
        proxy_meta = remove_audio_edts(proxy_rewrapped, proxy_meta)
        main_base_path = main_rewrapped
        proxy_base_path = proxy_rewrapped

        record = encode_message([Field(1, 2, catalog_path.encode("ascii")), Field(2, 2, main_meta)])
        index_data = build_indexes(card_root, record, catalog_path, insert=args.insert)
        backups = [] if args.no_index_backup else backup_indexes(card_root)
        main_base_path.replace(final_main)
        proxy_base_path.replace(final_proxy)
        commit_indexes(index_data)
        print(f"duration: {duration:.3f}s")
        print("updated: " + ", ".join(str(path) for path in index_data))
        if backups:
            print("backups: " + ", ".join(str(path) for path in backups))
        print("Import complete. Eject safely, then cold-boot the camera for the first test.")
        return 0
    except Exception:
        for path in (final_main, final_proxy):
            if path.exists():
                path.unlink()
        if args.keep_work:
            print(f"temporary files kept at: {work}", file=sys.stderr)
        raise
    finally:
        if work.exists() and not args.keep_work:
            shutil.rmtree(work)


if __name__ == "__main__":
    raise SystemExit(main())
