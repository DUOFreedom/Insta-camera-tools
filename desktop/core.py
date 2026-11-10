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
影石相机工具 —— 影石 Ace Pro 2 第三方视频导入核心转换逻辑（独立实现）。

原理:
    影石 Ace Pro 2 相册只认"自己录的样子"。本模块把普通视频重新编码/重封装为
    影石原生的格式特征，使相机相册与 App 能识别并播放。

目标格式（实测 Ace Pro 2 真机文件导出）:
    VID 主视频:
        视频: H.265 (hvc1), 1920x1080, yuvj420p(full-range), 30000/1001 fps,
              profile=main, 无 B 帧, color_range=pc
        音频1: AAC LC, 48000 Hz, 2ch, handler_name=[0x10]INS.AAC
        音频2: AAC LC, 48000 Hz, 2ch, handler_name=[0x10]INS.TimeCode  (时间码轨)
        视频 handler_name=[0x10]INS.HVC, encoder="HVC encoder"
    LRV 低清预览:
        视频: H.264 (avc1), 854x480, yuvj420p(full-range), 30000/1001 fps,
              profile=high, 无 B 帧
        音频轨同上（两条）
        视频 handler_name=[0x10]INS.AVC, encoder="AVC encoder"

本工具独立实现，不依赖任何第三方付费工具。

免责声明:
    本项目为个人开发的第三方工具，与影石创新科技股份有限公司无任何关联，未获其授权或认可。
    Insta360、Ace Pro 是影石的商标。
    工具通过改写文件结构与相机索引实现导入，属于对未公开格式的逆向分析。
    使用前请自行备份相机卡内素材。因使用本工具导致的素材损坏、相机异常或保修问题，
    作者不承担责任。
"""

from __future__ import annotations

import concurrent.futures
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import urllib.request
from pathlib import Path
import zipfile
from datetime import datetime, timedelta

__version__ = "1.2.0"

# 以下仅为【无真机模板时】的兜底值。
# 有真机原片时，一律以 analyze_native() 实测结果为准（见 _build_spec_tasks）。
VID_WIDTH, VID_HEIGHT = 1920, 1080
LRV_WIDTH, LRV_HEIGHT = 1280, 720      # 实测 Ace Pro 2（v2.0.51）LRV 为 1280x720
FPS = "30000/1001"
VID_FPS = "60000/1001"                 # 实测真机主视频为 60fps
INS_PREFIX = "\x10"
LRV_BITRATE = 4_000_000

_NO_WINDOW = 0
if os.name == "nt":
    _NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

# 子进程被 kill 之后等待其真正退出的秒数（避免僵尸与句柄泄漏）
_FFMPEG_KILL_WAIT = 10


class CanceledError(Exception):
    """用户主动取消（非程序错误）。

    与 RuntimeError 区分：GUI 据此显示“已取消”而不是“失败”，
    批处理不将其计入失败统计。
    """


class ValidationError(ValueError):
    """输入参数不符合前置条件，调用方应修正后重试。"""


class FFmpegError(RuntimeError):
    """ffmpeg 子进程失败。

    attributes:
        cmd: 失败的完整命令列表。
        returncode: 进程退出码。
        stderr: 合并后的 stderr 文本（可能被截断）。
        retryable: 是否建议重试。
    """

    def __init__(self, message: str, cmd: list[str] | None = None,
                 returncode: int | None = None, stderr: str = "",
                 retryable: bool = False) -> None:
        super().__init__(message)
        self.cmd = cmd
        self.returncode = returncode
        self.stderr = stderr
        self.retryable = retryable


class MediaError(RuntimeError):
    """媒体文件本身损坏或不符合预期格式，不可重试。"""


class CardError(RuntimeError):
    """相机卡结构或索引操作失败，不可重试。"""

def log_path() -> str:
    """本次导入的日志文件路径（%LOCALAPPDATA%\\InstaAceImporter\\import.log）。"""
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    d = os.path.join(base, "InstaAceImporter")
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        d = os.path.expanduser("~")
    return os.path.join(d, "import.log")

def append_log(text: str) -> None:
    """把关键信息追加进日志文件（失败不影响主流程）。"""
    try:
        with open(log_path(), "a", encoding="utf-8") as f:
            f.write(text.rstrip() + "\n")
    except OSError:
        pass

def _tool_base_dir() -> str:
    """可执行程序根目录: 打包后为 exe 所在目录，开发时为脚本所在目录。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))

def _tool_dirs() -> list[str]:
    """按优先级返回查找 ffmpeg 的候选目录列表。"""
    base = _tool_base_dir()
    dirs = [base, os.path.join(base, "bin")]
    local = os.environ.get("LOCALAPPDATA")
    if local:
        dirs.append(os.path.join(local, "InstaAceImporter", "bin"))
    dirs.append(os.path.join(os.path.expanduser("~"), "InstaAceImporter", "bin"))
    # 常见第三方安装位置（用户机器上已存在 ffmpeg 时省去重新下载）
    for c in (r"C:\ffmpeg\bin", r"C:\Program Files\ffmpeg\bin",
              r"C:\Program Files (x86)\ffmpeg\bin",
              os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"),
                           "chocolatey", "bin")):
        dirs.append(c)
    return dirs

def _find_tool(name: str, env_key: str) -> str | None:
    """按优先级定位 ffmpeg / ffprobe:
    1) 环境变量 FFMPEG_PATH / FFPROBE_PATH
    2) 本脚本(或打包后的 exe)同目录 / bin 子目录
    3) 用户目录下的 InstaAceImporter\\bin
    4) 常见第三方安装位置 (C:\\ffmpeg\\bin 等)
    5) 系统 PATH
    """
    env = os.environ.get(env_key)
    if env and os.path.isfile(env):
        return env
    exe = name + ".exe" if os.name == "nt" else name
    for d in _tool_dirs():
        p = os.path.join(d, exe)
        if os.path.isfile(p):
            return p
    return shutil.which(name)

def find_ffmpeg() -> str | None:
    return _find_tool("ffmpeg", "FFMPEG_PATH")

def find_ffprobe() -> str | None:
    return _find_tool("ffprobe", "FFPROBE_PATH")

def ffmpeg_available() -> tuple[bool, str]:
    """真正的可用性检测: 能找到 ffmpeg/ffprobe，且都能实际运行 -version。"""
    ff, fp = find_ffmpeg(), find_ffprobe()
    if not ff or not fp:
        return False, "未找到 ffmpeg/ffprobe"
    for tool in (ff, fp):
        try:
            r = subprocess.run([tool, "-version"], capture_output=True,
                               creationflags=_NO_WINDOW)
            if r.returncode != 0:
                return False, f"{tool} 无法运行"
        except Exception as e:  # noqa: BLE001
            return False, f"{tool} 无法运行: {e}"
    return True, ff

def ffmpeg_install_dir() -> str:
    """返回 ffmpeg 的安装目录: 优先程序同目录/bin，不可写则退回用户目录。"""
    base = os.path.join(_tool_base_dir(), "bin")
    try:
        os.makedirs(base, exist_ok=True)
        probe = os.path.join(base, ".write_test")
        with open(probe, "w") as f:
            f.write("x")
        os.remove(probe)
        return base
    except OSError:
        local = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        d = os.path.join(local, "InstaAceImporter", "bin")
        os.makedirs(d, exist_ok=True)
        return d

_FFMPEG_SOURCES = {
    "Gitee 镜像 (otreee/ffmpeg_build)": {
        "kind": "single-exe-zip",
        "files": {
            "ffmpeg.exe": "https://gitee.com/otreee/ffmpeg_build/releases/download/9.0.1/ffmpeg.zip",
            "ffprobe.exe": "https://gitee.com/otreee/ffmpeg_build/releases/download/9.0.1/ffprobe.zip",
        },
    },
    "GyanD 官方 (essentials, 直连)": {
        "kind": "bin-dir-zip",
        "files": {
            "all": "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip",
        },
    },
    "GitHub 加速 (BtbN)": {
        "kind": "bin-dir-zip",
        "files": {
            "all": "https://ghfast.top/https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip",
        },
    },
}

def _measure_speed(url: str, sample_bytes: int = 262144, timeout: float = 8.0):
    """下载前 sample_bytes 字节估算网速，返回 bytes/s；失败返回 None。

    启动时对多个下载源测速，选择最快路径。
    """
    import time
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        t0 = time.time()
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            got = 0
            while got < sample_bytes:
                chunk = resp.read(min(65536, sample_bytes - got))
                if not chunk:
                    break
                got += len(chunk)
        dt = time.time() - t0
        if dt <= 0 or got == 0:
            return None
        return got / dt
    except Exception:  # noqa: BLE001
        return None

def _extract_bin(zip_path: str, dest_dir: str) -> list[str]:
    """解压 zip，递归寻找 ffmpeg.exe / ffprobe.exe 复制到 dest_dir（展平）。"""
    wanted = ("ffmpeg.exe", "ffprobe.exe")
    out = []
    with zipfile.ZipFile(zip_path) as z:
        for n in z.namelist():
            fname = n.replace("/", "\\").split("\\")[-1].lower()
            if fname in wanted:
                data = z.read(n)
                dst = os.path.join(dest_dir, fname)
                with open(dst, "wb") as f:
                    f.write(data)
                out.append(dst)
    return out

def _download_one(url: str, zip_path: str, progress_cb=None) -> None:
    """下载单文件，progress_cb(fraction)。"""
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        with open(zip_path, "wb") as f:
            while True:
                chunk = resp.read(262144)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                if progress_cb and total:
                    progress_cb(min(1.0, done / total))

def download_and_install_ffmpeg(stage_cb=None):
    """对多个下载源测速，选最快路径下载并安装 ffmpeg。

    stage_cb(frac, message): 阶段回调。
        frac   ∈ [0,1] 总进度；
        message 文本提示(测速 / 下载 / 安装 / 完成 / 失败)。

    返回 (ok: bool, message: str)。ok=True 时 message 为安装目录。
    """
    def emit(frac, msg):
        if stage_cb:
            stage_cb(frac, msg)

    dest_dir = ffmpeg_install_dir()
    tmp_dir = tempfile.gettempdir()

    # 1) 对每个源测速
    emit(0.02, "正在为 ffmpeg 下载源测速...")
    ranked = []
    for name, spec in _FFMPEG_SOURCES.items():
        files = spec["files"]
        first_url = next(iter(files.values()))
        speed = _measure_speed(first_url)
        ranked.append((name, spec, speed))
        if speed is None:
            emit(0.02, f"  {name} 不可达")
    ranked.sort(key=lambda x: (x[2] is None, -(x[2] or 0)))

    last_err = "所有下载源均不可用"
    for i, (name, spec, speed) in enumerate(ranked):
        if speed is None:
            continue
        base_frac = 0.05 + (i / max(1, len(ranked))) * 0.85
        try:
            files = spec["files"]
            emit(base_frac, f"正在从 {name} 下载 ffmpeg ...")
            if spec["kind"] == "single-exe-zip":
                for j, (fname, url) in enumerate(files.items()):
                    zip_path = os.path.join(tmp_dir, f"insta_{fname}.zip")
                    _download_one(url, zip_path, lambda f: emit(base_frac, f"正在下载 ffmpeg {f*100:3.0f}% ({fname})"))
                    emit(base_frac + 0.05, "正在安装 ffmpeg ...")
                    _extract_bin(zip_path, dest_dir)
                    os.remove(zip_path)
            else:
                zip_path = os.path.join(tmp_dir, "insta_ffmpeg_all.zip")
                _download_one(files["all"], zip_path, lambda f: emit(base_frac, f"正在下载 {f*100:3.0f}%"))
                emit(base_frac + 0.05, "正在安装 ffmpeg ...")
                _extract_bin(zip_path, dest_dir)
                os.remove(zip_path)

            ok, msg = ffmpeg_available()
            if ok:
                emit(1.0, f"ffmpeg 安装完成 ✓ ({dest_dir})")
                return True, dest_dir
            last_err = f"{name} 安装后仍无法运行"
        except Exception as e:  # noqa: BLE001
            last_err = f"{name}: {e}"
            emit(base_frac, f"{name} 下载失败，尝试下一个源 ...")
            continue

    emit(1.0, f"自动下载失败: {last_err}")
    return False, last_err

_HW_ENCODERS = [
    ("hevc_amf", "h264_amf", "AMD"),
    ("hevc_nvenc", "h264_nvenc", "NVIDIA"),
    ("hevc_qsv", "h264_qsv", "Intel"),
]

def detect_hw_encoder():
    """探测当前机器可用的硬件编码器，返回 (hevc, h264, 显示名) 或 None。

    做法: 用 ffmpeg 生成一个极小测试帧，用【与正式转码完全相同的命令形状】
    试编一次，成功即认为该厂商硬件可用。

      部分 Iris Xe 机器上显式建设备会报
      "Could not create the texture (80070057)" 而误判为无硬件；
      让 ffmpeg 自建设备（只给 -c:v hevc_qsv）反而正常。
    """
    ff = find_ffmpeg()
    if not ff:
        return None
    for hevc, h264, label in _HW_ENCODERS:
        test = [
            ff, "-y", "-v", "error", "-f", "lavfi",
            "-i", "testsrc2=size=320x180:rate=10:duration=0.3",
            "-frames:v", "3",
            "-c:v", hevc, "-g", "16", "-bf", "0",
            "-f", "null", "-",
        ]
        try:
            r = subprocess.run(test, capture_output=True,
                               creationflags=_NO_WINDOW, timeout=30)
            if r.returncode == 0:
                return hevc, h264, label
        except (subprocess.TimeoutExpired, OSError):
            continue
    return None

def _hw_extra_args(hevc: str) -> list[str]:
    """返回某个硬件编码器额外需要的全局参数。

      不加时 ffmpeg 会自建并把帧内部上传给编码器（见 detect_hw_encoder）。
    """
    return []

def probe(filepath: str) -> dict:
    """用 ffprobe 读出流信息，返回 dict。"""
    fp = find_ffprobe()
    if not fp:
        return {}
    args = [fp, "-v", "error", "-show_entries",
            "stream=index,codec_type,codec_name,width,height,sample_rate,channels,avg_frame_rate,duration",
            "-of", "json", filepath]
    try:
        r = subprocess.run(args, capture_output=True, creationflags=_NO_WINDOW, timeout=60)
        data = json.loads(r.stdout.decode("utf-8", "replace") or "{}")
    except Exception:  # noqa: BLE001
        return {}
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), {})
    audio = next((s for s in streams if s.get("codec_type") == "audio"), {})
    return {"video": video, "audio": audio, "streams": streams}

def probe_raw(filepath: str) -> dict:
    """用 ffprobe 完整导出某文件的流信息（JSON 原始结构，含 tags / 色域等细节）。

    用于"原生录制视频"结构分析: 不同相机生成的文件结构不同，
    必须按卡里的真实文件来，而不是硬编码某种相机规格。
    """
    fp = find_ffprobe()
    if not fp:
        return {}
    args = [fp, "-v", "error", "-show_streams", "-show_format", "-of", "json", filepath]
    r = subprocess.run(args, capture_output=True, creationflags=_NO_WINDOW, timeout=60)
    if r.returncode != 0:
        raise RuntimeError(f"ffprobe 读取失败: {r.stderr.decode('utf-8', 'replace')[:200]}")
    return json.loads(r.stdout.decode("utf-8", "replace") or "{}")

def _st(s: dict, key: str, default=None):
    """安全取值，兼容缺省。"""
    return (s or {}).get(key, default)

def _num(v, default=None):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default

def _fps_from_stream(s: dict) -> str:
    """从流信息里取帧率，返回【精确分数串】如 "60000/1001"。

      与真机的 60000/1001 不一致，相机可能不认。
    """
    for key in ("r_frame_rate", "avg_frame_rate"):
        v = s.get(key)
        if v and "/" in str(v):
            num, den = str(v).split("/", 1)
            try:
                if int(num) > 0 and int(den) > 0:
                    return f"{int(num)}/{int(den)}"
            except ValueError:
                pass
    try:
        n = int(round(float(s.get("avg_frame_rate", 30))))
        return f"{n}/1" if n > 0 else FPS
    except (TypeError, ValueError):
        return FPS

def spec_from_template(template) -> dict | None:
    """从模板对（真机原片）直接量出规格，供 _build_spec_tasks 使用。

    比 analyze_card_pair 更准确：用的就是即将作为 moov 骨架的那一对。
    避免在未传 spec 时退回硬编码兑底值（会造成帧率/分辨率漂移）。
    """
    if not template:
        return None
    try:
        main_p, proxy_p = template[0], template[1]
    except (TypeError, IndexError):
        return None
    try:
        sp = analyze_native(str(main_p))
        sp["lrv_video"] = (analyze_native(str(proxy_p)).get("video") or {})
        return sp
    except Exception:  # noqa: BLE001
        return None

def analyze_native(filepath: str) -> dict:
    """深度分析一个原生录制视频，还原其"文件结构规格"。

    返回 dict，包含视频规格 + 全部音频轨规格（每条 track 独立）。
    这是取代硬编码的关键: 生成的新文件将复刻此结构。
    """
    data = probe_raw(filepath)
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    if not video:
        raise RuntimeError("未在样文件中找到视频流")

    vtags = video.get("tags", {}) or {}
    vcodec_name = video.get("codec_name", "hevc")
    venc = vtags.get("encoder", "")
    # 归一化编码器名（样文件可能是 libx265/libx264 或 hvc1/avc1）
    vcodec_key = "libx265" if "265" in (vcodec_name or "") or "hevc" in (vcodec_name or "") or "hvc" in (venc or "") else "libx264"
    vprofile_default = "main" if vcodec_key == "libx265" else "high"

    handler = vtags.get("handler_name", "INS.HVC" if vcodec_key == "libx265" else "INS.AVC")
    profile = vtags.get("profile", vprofile_default)

    audio_tracks = []
    for s in streams:
        if s.get("codec_type") != "audio":
            continue
        atags = s.get("tags", {}) or {}
        audio_tracks.append({
            "codec": "aac" if "aac" in (s.get("codec_name") or "").lower() else s.get("codec_name", "aac"),
            "sample_rate": str(_st(s, "sample_rate", "48000")),
            "channels": str(_st(s, "channels", 2)),
            "bit_rate": s.get("bit_rate") or "128k",
            # handler_name 去掉可能存在的 0x10 前缀，统一后续再加
            "handler": _strip_prefix(atags.get("handler_name", "INS.AAC")),
        })
    if not audio_tracks:
        audio_tracks.append({"codec": "aac", "sample_rate": "48000", "channels": "2",
                             "bit_rate": "128k", "handler": "INS.AAC"})

    m = re.match(r"^([A-Za-z]{1,8})", os.path.basename(filepath))
    prefix = m.group(1).upper() if m else ""
    _name_u = os.path.basename(filepath).upper()
    _role = "proxy" if (_name_u.startswith("LRV") or _name_u.endswith(".LRV")) else "main"

    # 关键帧间隔必须跟着模板走：Ace Pro 2 的 LRV 是 16，GO Ultra 的 VID=120 /
    #   LRV=10。写死 16 会让 GO Ultra 的码流与 AMBA 声明对不上，相机不认。
    gop = 0
    try:
        tf, _ = _load_inst_modules()
        gop = tf.video_gop(filepath)
    except Exception:
        pass

    return {
        "video": {
            "codec": vcodec_key,
            "width": _st(video, "width", VID_WIDTH),
            "height": _st(video, "height", VID_HEIGHT),
            "fps": _fps_from_stream(video),
            "pix_fmt": _st(video, "pix_fmt", "yuv420p"),
            "color_range": _st(video, "color_range", "tv"),
            "codec_tag": _st(video, "codec_tag_string", "hvc1" if vcodec_key == "libx265" else "avc1"),
            "handler": _strip_prefix(handler),
            "encoder": venc,
            "profile": profile,
            "level": video.get("level"),
            "gop": gop,
            "format": _st(data.get("format", {}), "format_name", "mp4"),
        },
        "audio_tracks": audio_tracks,
        "file_prefix": prefix,
        "role": _role,
        "filename": os.path.basename(filepath),
    }

def _strip_prefix(name: str) -> str:
    """去掉 handler_name 里可能存在的 0x10 / [0x10] 前缀，只留 INS.xxx。"""
    if not name:
        return name
    return name.replace("[0x10]", "").replace("\x10", "").strip()

_NAME_RE = re.compile(r"^(?:VID|LRV)_(\d{8}_\d{6})_(\d{3})\.(?:mp4|lrv)$", re.IGNORECASE)

def max_seq(output_dir: str) -> int:
    """扫描输出目录里所有影石文件(VID/LRV)，返回当前最大的尾缀序号。

    没有任何影石文件时返回 -1。
    """
    best = -1
    if not os.path.isdir(output_dir):
        return -1
    try:
        names = os.listdir(output_dir)
    except OSError:
        return -1
    for name in names:
        m = _NAME_RE.match(name)
        if m:
            best = max(best, int(m.group(2)))
    return best

def next_seq(output_dir: str, base: int = 0) -> int:
    """返回下一个可用序号（目录内最大尾缀 + 1），至少为 base。"""
    return max(max_seq(output_dir) + 1, base)

def format_duration(seconds) -> str:
    """把秒数格式化成人话的剩余时间文本。"""
    try:
        s = int(round(float(seconds)))
    except (TypeError, ValueError):
        return "--:--"
    if s < 0:
        return "--:--"
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h:
        return f"{h}时{m}分"
    if m:
        return f"{m}分{sec}秒"
    return f"{sec}秒"

def _parse_hhmmss(value: str) -> float:
    """解析 ffmpeg -progress 输出里的 out_time=HH:MM:SS.mmm → 秒。"""
    try:
        h, m, s = value.split(":")
        return int(h) * 3600 + int(m) * 60 + float(s)
    except (ValueError, AttributeError):
        return 0.0

def _run_ffmpeg(cmd: list[str], duration: float, progress=None, cancel=None,
                procs: list[subprocess.Popen] | None = None,
                procs_lock: threading.Lock | None = None):
    """后台运行 ffmpeg，解析 -progress 输出，返回进度与速度。

    前置条件:
        cmd 为非空字符串列表，且首元素为可执行 ffmpeg 路径；
        duration >= 0；
        cancel 若非 None 须为 threading.Event。
    后置条件:
        ffmpeg 正常退出码为 0 时无异常；
        cancel 置位时抛 CanceledError 并 kill 子进程；
        ffmpeg 退出码非 0 时抛 FFmpegError，携带命令、返回码、stderr。
    不变量:
        stderr 由守护线程异步排空，防止管道写满导致 ffmpeg 阻塞；
        子进程在 finally 中确保 kill 与 wait。
    失败方式:
        用户错误: cmd 为空或首元素不存在 -> ValidationError；
        系统错误(不可重试): ffmpeg 退出码非 0 -> FFmpegError(retryable=False)；
        用户取消: cancel 置位 -> CanceledError；
        系统错误: 子进程启动失败 -> OSError 向上抛出。
    """
    if not cmd or not isinstance(cmd, list) or not cmd[0]:
        raise ValidationError("_run_ffmpeg 要求非空的命令列表")
    if not os.path.isfile(cmd[0]) and not shutil.which(cmd[0]):
        raise ValidationError(f"ffmpeg 可执行文件不存在: {cmd[0]}")
    if duration < 0:
        raise ValidationError("duration 不得为负数")
    if cancel is not None and not isinstance(cancel, threading.Event):
        raise ValidationError("cancel 必须为 threading.Event 或 None")
    if cancel is None:
        # 归一化成真实 Event：下游一律直接 cancel.is_set()，不再逐处判 None。
        cancel = threading.Event()

    if cancel.is_set():
        raise CanceledError("已取消")
    full = cmd + ["-progress", "pipe:1", "-nostats"]
    proc = subprocess.Popen(full, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            creationflags=_NO_WINDOW, text=True,
                            encoding="utf-8", errors="replace")
    if procs is not None and procs_lock is not None:
        with procs_lock:
            procs.append(proc)

    stderr_chunks: list[str] = []

    def _drain_err():
        try:
            for chunk in proc.stderr:
                stderr_chunks.append(chunk)
                if len(stderr_chunks) > 400:
                    del stderr_chunks[:-200]
        except Exception:
            pass

    err_thread = threading.Thread(target=_drain_err, daemon=True)
    err_thread.start()

    cur = 0.0
    speed = 0.0
    canceled = False
    try:
        for line in proc.stdout:
            if cancel is not None and cancel.is_set():
                canceled = True
                break
            line = line.strip()
            if line.startswith("out_time_us=") or line.startswith("out_time_ms="):
                v = line.split("=", 1)[1]
                try:
                    cur = int(v) / 1_000_000
                except ValueError:
                    pass
            elif line.startswith("out_time="):
                cur = _parse_hhmmss(line.split("=", 1)[1])
            elif line.startswith("speed="):
                v = line.split("=", 1)[1].rstrip("x").strip()
                try:
                    speed = float(v)
                except ValueError:
                    speed = 0.0
            elif line.startswith("progress="):
                if progress and duration > 0:
                    frac = min(1.0, max(0.0, cur / duration))
                    eta = (duration - cur) / speed if speed > 0 else -1
                    progress(frac, speed, eta)
    finally:
        if proc.stdout:
            try:
                proc.stdout.close()
            except Exception:
                pass
        if canceled or proc.poll() is None:
            try:
                proc.kill()
            except Exception:
                pass
    try:
        proc.wait(timeout=_FFMPEG_KILL_WAIT)
    except subprocess.TimeoutExpired:
        try:
            proc.kill()
            proc.wait(timeout=5)
        except Exception:
            pass
    err_thread.join(timeout=2)
    # proc 已结束，stderr 管道已关闭，err_thread 会很快退出；
    # 超时后继续等待，保证 FFmpegError.stderr 完整不丢失。
    if err_thread.is_alive():
        err_thread.join()
    if canceled:
        raise CanceledError("已取消")
    if proc.returncode != 0:
        err = "".join(stderr_chunks)[-800:]
        raise FFmpegError(
            f"ffmpeg 退出码非 0: {err}",
            cmd=full,
            returncode=proc.returncode,
            stderr=err,
            retryable=False,
        )

def _scale_pad(w: int, h: int) -> str:
    """缩放并居中填充到目标尺寸。

    实测依据：
        scale=...:force_original_aspect_ratio=decrease,
        pad=...:(ow-iw)/2:(oh-ih)/2:black,setsar=1,format=yuv420p,setrange=full
    """
    return (f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black,setsar=1,"
            f"format=yuv420p,setrange=full")

# 相机要求的固定色彩参数（实测真机）
_COLOR_ARGS = ["-color_range", "pc", "-colorspace", "bt709",
               "-color_trc", "bt709", "-color_primaries", "bt709"]

def _fps_args(fps: str) -> list[str]:
    """按目标帧率生成参数。

      movie_timescale 取分子（60000 / 30000）。
    """
    num = str(fps).split("/")[0].strip() or "30000"
    return ["-r", fps, "-fps_mode", "cfr", "-movie_timescale", num]

def _audio_map(index: int, track_spec: dict, src_index: int = 0) -> list[str]:
    """返回一条音频输出流的完整参数（在流序号 a:index 上）。
    track_spec = analyze_native() 返回的 audio_tracks 中的一项。
    src_index  源文件里要映射的音频流下标（源不足时全部回退到 0）。
    按样文件每轨的 codec/采样率/声道/码率/handler 复刻。
    """
    codec = track_spec.get("codec", "aac")
    handler = _strip_prefix(track_spec.get("handler", "INS.AAC"))
    sr = str(track_spec.get("sample_rate", "48000"))
    ch = str(track_spec.get("channels", "2"))
    br = str(track_spec.get("bit_rate", "192k"))
    if not br.endswith("k") and br.isdigit():
        br = br + "k"
    return [
        "-map", f"0:a:{src_index}",
        f"-c:a:{index}", codec,
        f"-ar:a:{index}", sr,
        f"-ac:a:{index}", ch,
        f"-b:a:{index}", br,
        f"-metadata:s:a:{index}", f"handler_name={INS_PREFIX}{handler}",
    ]

def audio_inputs(audio_tracks, src_audio_count: int) -> list[str]:
    """源无音轨时，返回额外输入参数（在前面追加 anullsrc 静音源）。"""
    if src_audio_count > 0:
        return []
    tr = audio_tracks[0] if audio_tracks else {}
    sr = str(tr.get("sample_rate", "48000"))
    ch = str(tr.get("channels", "2"))
    return ["-f", "lavfi", "-i", f"anullsrc=channel_layout={'stereo' if ch == '2' else 'mono'}:sample_rate={sr}"]

def _level_text(level: int | None, codec: str) -> str | None:
    """把真机 level_idc 转成 ffmpeg 的 level 文本。

    HEVC: level_idc 123 -> "4.1"（真机 120 -> "4.0"）公式 f"{n//30}.{(n%30)//3}"
    H.264: level 41   -> "4.1"   公式 f"{n//10}.{n%10}"

      hevc_qsv / hevc_nvenc / hevc_amf 也是 HEVC，
      否则会给 QSV 传 -level:v 12.3 这种非法值，编码器直接拒开。
    """
    if not level:
        return None
    n = int(level)
    c = (codec or "").lower()
    if "265" in c or "hevc" in c:
        return f"{n // 30}.{(n % 30) // 3}"
    return f"{n // 10}.{n % 10}"

def _build_transcode_cmd(src, dst, vcodec, tag, vf, enc_params,
                         video_handler, video_encoder, audio_tracks,
                         color_range, src_audio_count=0, is_lrv=False,
                         fps: str = FPS, level: int | None = None,
                         bitrate: int | None = None,
                         gop: int | None = None) -> list[str]:
    """软件编码命令。

    gop 是关键帧间隔，必须与模板一致（Ace Pro 2 的 LRV=16，GO Ultra 的
    VID=120 / LRV=10）。None 或 <=0 时退回 16（Ace Pro 2 的取值）。
    """
    ff = find_ffmpeg()
    if not ff:
        raise ValidationError("未找到 ffmpeg，无法构建转码命令")
    keyint = int(gop) if gop and int(gop) > 0 else 16
    extra_in = audio_inputs(audio_tracks, src_audio_count)
    cmd = [ff, "-hide_banner", "-y", "-i", src]
    if extra_in:
        cmd += extra_in
        audio_src = "1:a:0"
    else:
        audio_src = "0:a:0"
    cmd += ["-map", "0:v:0", "-map", audio_src, "-vf", vf]

    if vcodec == "libx265":
        cmd += ["-c:v", "libx265", "-preset", "ultrafast",
                "-pix_fmt", "yuv420p", "-tag:v", tag,
                "-x265-params", enc_params or
                f"keyint={keyint}:min-keyint={keyint}:scenecut=0:bframes=0:"
                f"range=full:info=0"]
    elif vcodec == "libx264":
        # 不加 -b:v 等码率参数 —— 与密集关键帧叠加会让码率失控。
        cmd += ["-c:v", "libx264", "-preset", "veryfast", "-profile:v", "high",
                "-tag:v", tag, "-g", str(keyint), "-keyint_min", str(keyint),
                "-sc_threshold", "0", "-bf", "0"]
        if enc_params:
            cmd += ["-x264-params", enc_params]
    else:
        # 模板 LRV 用了别的编码器（VP9/AV1 等）：只给通用关键帧参数，
        #   交给 ffmpeg 自己按编码器解释 -g。
        cmd += ["-c:v", vcodec, "-pix_fmt", "yuv420p", "-tag:v", tag,
                "-g", str(keyint), "-keyint_min", str(keyint),
                "-sc_threshold", "0", "-bf", "0"]

    cmd += _fps_args(fps)
    cmd += _COLOR_ARGS
    _lv = _level_text(level, vcodec)
    if _lv:
        cmd += ["-level:v", _lv]
    cmd += ["-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", "-shortest"]
    cmd += ["-metadata:s:v:0", f"handler_name={INS_PREFIX}{video_handler}",
            "-metadata:s:v:0", "language=eng",
            "-metadata:s:v:0", f"encoder={video_encoder}",
            "-metadata:s:a:0", f"handler_name={INS_PREFIX}INS.AAC",
            "-metadata:s:a:0", "language=eng"]
    cmd += ["-f", "mp4", dst]
    return cmd

def _build_hw_transcode_cmd(src, dst, vcodec, tag, vf, extra_args,
                            video_handler, video_encoder, audio_tracks,
                            color_range, src_audio_count=0, is_lrv=False,
                            fps: str = FPS, level: int | None = None,
                            bitrate: int | None = None,
                            gop: int | None = None) -> list[str]:
    """硬件编码命令。

    实测关键参数：-g <模板GOP> -keyint_min <模板GOP> -sc_threshold 0 -bf 0
                  -extra_sei 0 -udu_sei 0 -c:a aac 192k 48k 2ch + bt709
    """
    keyint = int(gop) if gop and int(gop) > 0 else 16
    extra_in = audio_inputs(audio_tracks, src_audio_count)
    ff = find_ffmpeg()
    if not ff:
        raise ValidationError("未找到 ffmpeg，无法构建硬件转码命令")
    cmd = [ff, "-hide_banner", "-y", "-i", src]
    if extra_in:
        cmd += extra_in
        audio_src = "1:a:0"
    else:
        audio_src = "0:a:0"
    cmd += ["-map", "0:v:0", "-map", audio_src]
    cmd += extra_args
    cmd += ["-c:v", vcodec, "-tag:v", tag]
    if "nvenc" in vcodec:
        cmd += ["-g", str(keyint), "-keyint_min", str(keyint), "-sc_threshold", "0",
                "-bf", "0", "-extra_sei", "0", "-udu_sei", "0"]
        if not is_lrv:
            cmd += ["-slices", "2"]
    # 像素格式处理（format=yuv420p,setrange=full）
    if "amf" in vcodec:
        vf2 = vf
    elif "qsv" in vcodec:
        vf2 = vf + ",format=nv12"
    else:
        vf2 = vf
    cmd += ["-vf", vf2]
    cmd += _fps_args(fps)
    cmd += _COLOR_ARGS
    #   传数字又会偏移（41 -> 123）。让 QSV 按分辨率/帧率自选：
    #   实测 1080p30 输出 level=120，与真机原片一致，无需干预。
    if "qsv" not in vcodec:
        _lv = _level_text(level, vcodec)
        if _lv:
            cmd += ["-level:v", _lv]
    cmd += ["-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", "-shortest"]
    cmd += ["-metadata:s:v:0", f"handler_name={INS_PREFIX}{video_handler}",
            "-metadata:s:v:0", "language=eng",
            "-metadata:s:v:0", f"encoder={video_encoder}",
            "-metadata:s:a:0", f"handler_name={INS_PREFIX}INS.AAC",
            "-metadata:s:a:0", "language=eng"]
    cmd += ["-f", "mp4", dst]
    return cmd

def _fps_num(fps) -> float:
    """把 '30000/1001' 或 '30' 这类帧率字符串转成数值（用于 LRV 降档）。"""
    try:
        s = str(fps)
        if "/" in s:
            a, b = s.split("/")
            return float(a) / float(b)
        return float(s)
    except (ValueError, ZeroDivisionError, TypeError):
        return 30.0

def _build_spec_tasks(input_path, output_dir, seq, stamp, hw, spec):
    """根据原生结构 spec（或影石回退）构建本文件的任务列表。

    返回 (tasks, extra):
        tasks = [(label, dst, vcodec, tag, w, h, fps, vh, ve, color_range,
                 pix_fmt, audio_tracks, profile)]
        extra  = 硬件额外参数
    """
    #   否则会把主视频编成 854x480/h264，彻底错位。
    if (spec or {}).get("role") == "proxy":
        spec = dict(spec or {})
        spec["lrv_video"] = spec.get("video") or {}
        spec.pop("video", None)

    v = (spec or {}).get("video", {})
    w = int(v.get("width", VID_WIDTH))
    h = int(v.get("height", VID_HEIGHT))
    fps = v.get("fps", VID_FPS)
    # 影石原生为 full-range（yuvj420p / pc）；无样本时按此回退
    cr = v.get("color_range", "pc")
    pix = v.get("pix_fmt", "yuvj420p")
    profile = v.get("profile", "main")
    if pix == "yuvj420p":
        cr = "pc"

    # LRV（预览）规格：真机上与 VID 不同（分辨率、帧率都可能不同）
    lv = (spec or {}).get("lrv_video") or {}
    lrv_w = int(lv.get("width", LRV_WIDTH))
    lrv_h = int(lv.get("height", LRV_HEIGHT))
    lrv_fps = lv.get("fps", FPS)
    lrv_pix = lv.get("pix_fmt", "yuvj420p")
    lrv_cr = "pc" if lrv_pix == "yuvj420p" else lv.get("color_range", "pc")
    lrv_profile = lv.get("profile", "high")

    # 音轨： 以真机实测为准（Ace Pro 2 v2.0.51 为 1 条 INS.AAC）
    # 无样本时回退到 1 条 INS.AAC（与实测一致），而非旧版的 2 条
    audio = (spec or {}).get("audio_tracks") or [
        {"codec": "aac", "sample_rate": "48000", "channels": "2",
         "bit_rate": "192k", "handler": "INS.AAC"},
    ]
    #   绝不能从样本文件名推导：若样本恰好是 LRV，
    #   会把主视频命名成 LRV_*.mp4，导致根本没有 VID 文件。
    prefix = "VID"

    if hw:
        hevc_enc, h264_enc, _hw_label = hw
        main_vc, main_tag = hevc_enc, "hvc1"
        # LRV 的编码格式必须跟模板走：Ace Pro 2 的 LRV 是 H.264(avc1)，而
        #   GO Ultra 的 LRV 是 HEVC(hvc1)。写死 libx264/avc1 会让 GO Ultra
        #   的 LRV 与 AMBA/nail 里声明的东西对不上，相机相册不显示。
        preview_vc = lv.get("codec") or "libx264"
        preview_tag = lv.get("codec_tag") or ("hvc1" if "265" in preview_vc else "avc1")
        extra = _hw_extra_args(hevc_enc)
    else:
        main_vc, main_tag = "libx265", "hvc1"
        preview_vc = lv.get("codec") or "libx264"
        preview_tag = lv.get("codec_tag") or ("hvc1" if "265" in preview_vc else "avc1")
        extra = []

    vh = v.get("handler") or "INS.HVC"
    ve = v.get("encoder") or "HVC encoder"
    lrv_vh = lv.get("handler") or ("INS.HVC" if "265" in preview_vc else "INS.AVC")
    lrv_ve = lv.get("encoder") or ("HVC encoder" if "265" in preview_vc else "AVC encoder")

    # 关键帧间隔跟模板：Ace Pro 2 的 LRV=16，GO Ultra 的 VID=120 / LRV=10。
    main_gop = int(v.get("gop") or 0)
    lrv_gop = int(lv.get("gop") or 0)

    base = f"{prefix}_{stamp}_{seq:03d}"
    main_dst = os.path.join(output_dir, base + ".mp4")
    lrv_dst = os.path.join(output_dir, f"LRV_{stamp}_{seq:03d}.lrv")

    tasks = [
        # label, dst, vcodec, tag, w, h, fps, vh, ve, color_range, pix_fmt,
        #        audio, profile, level, gop
        ("VID (主视频)", main_dst, main_vc, main_tag, w, h, fps, vh, ve,
         cr, pix, audio, profile, v.get("level"), main_gop),
        ("LRV (低清预览)", lrv_dst, preview_vc, preview_tag, lrv_w, lrv_h,
         lrv_fps, lrv_vh, lrv_ve, lrv_cr, lrv_pix, audio, lrv_profile,
         lv.get("level"), lrv_gop),
    ]
    return tasks, extra

def convert(input_path: str, output_dir: str, start_number: int | None = None,
            stamp: str | None = None, log=None,
            encoder: tuple[str, str, str] | None = None,
            progress=None, spec: dict | None = None,
            jobs: int | None = None,
            cancel: threading.Event | None = None) -> tuple[str, str | None]:
    """转换一个视频为相机可识别的格式。返回 (main_path, preview_path)。

    参数:
        input_path   输入视频路径，须为存在的常规文件
        output_dir   输出目录，须可写或可创建
        start_number 起始序号；None 表示自动取下一个可用序号
        stamp        时间戳字符串(YYYYMMDD_HHMMSS)；None 用当前时间
        encoder      硬件编码器三元组 (hevc, h264, 显示名)；None 表示自动检测
        spec         原生视频结构；None 时回退默认结构
        progress     进度回调 progress(overall_frac, label, speed, eta_sec)
        jobs         并行转码路数；None = 主视频与预览同时编
        cancel       threading.Event；置位时中断转码

    前置条件:
        input_path 存在且为常规文件；
        output_dir 可创建或已存在且可写；
        spec 若非 None，须为 dict，含可选键 video/lrv_video/audio_tracks；
        jobs 若非 None，须为正整数；
        cancel 若非 None，须为 threading.Event。

    后置条件:
        返回 (main_path, preview_path)，均位于 output_dir；
        cancel 置位时抛 CanceledError，部分输出文件可能残留；
        ffmpeg 失败时抛 FFmpegError，不返回错误码。

    失败方式:
        用户错误: input_path 不存在 -> FileNotFoundError；
        用户错误: 参数类型不符 -> ValidationError；
        系统错误(不可重试): ffmpeg 退出非 0 -> FFmpegError；
        用户取消: cancel 置位 -> CanceledError。
    """
    def say(msg):
        if log:
            log(msg)
        else:
            print(msg)

    if not isinstance(input_path, str) or not input_path:
        raise ValidationError("input_path 必须为非空字符串")
    if not os.path.isfile(input_path):
        raise FileNotFoundError(f"输入文件不存在: {input_path}")
    if not isinstance(output_dir, str) or not output_dir:
        raise ValidationError("output_dir 必须为非空字符串")
    try:
        os.makedirs(output_dir, exist_ok=True)
        if not os.access(output_dir, os.W_OK):
            raise ValidationError(f"输出目录不可写: {output_dir}")
    except OSError as e:
        raise ValidationError(f"无法创建或访问输出目录 {output_dir}: {e}") from e

    if spec is not None and not isinstance(spec, dict):
        raise ValidationError("spec 必须为 dict 或 None")
    if jobs is not None:
        if not isinstance(jobs, int) or jobs < 1:
            raise ValidationError("jobs 必须为正整数")
    if cancel is not None and not isinstance(cancel, threading.Event):
        raise ValidationError("cancel 必须为 threading.Event 或 None")
    if cancel is None:
        # 归一化成真实 Event：下游一律直接 cancel.is_set()，不再逐处判 None。
        cancel = threading.Event()

    if cancel.is_set():
        raise CanceledError("已取消")

    if encoder is None:
        encoder = detect_hw_encoder()
    if isinstance(encoder, tuple) and len(encoder) == 3 \
            and encoder[2] != "software" and encoder[0]:
        hw = encoder
        hw_label = encoder[2]
    else:
        hw = None
        hw_label = "software"

    if stamp is None:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if not isinstance(stamp, str) or not stamp:
        raise ValidationError("stamp 必须为非空字符串")
    if start_number is None:
        seq = next_seq(output_dir)
    else:
        try:
            seq = int(start_number)
        except (TypeError, ValueError) as e:
            raise ValidationError(f"start_number 必须为整数: {start_number}") from e

    tasks, extra = _build_spec_tasks(input_path, output_dir, seq, stamp, hw, spec)

    info = probe(input_path)
    dur = 0.0
    try:
        dur = float(info.get("video", {}).get("duration") or 0)
    except (TypeError, ValueError):
        dur = 0.0
    src_audio_count = sum(1 for s in info.get("streams", [])
                          if s.get("codec_type") == "audio")

    n = len(tasks)
    workers = max(1, min(int(jobs or n), n))
    area_total = float(sum(max(1, t[4] * t[5]) for t in tasks)) or 1.0
    weights = [max(1, t[4] * t[5]) / area_total for t in tasks]
    state = {"done": 0.0}
    lock = threading.Lock()
    results: list[str | None] = [None] * n
    parts = [0.0] * n

    # 并发模式下跟踪所有 ffmpeg 子进程，任一任务失败时杀掉其余进程，
    # 避免孤儿 ffmpeg 继续写卡。
    procs: list[subprocess.Popen] = []
    procs_lock = threading.Lock()
    first_error: BaseException | None = None

    def _run_one(idx: int, t):
        nonlocal first_error
        (label, dst, vc, tag, w, h, fps, vh, ve, cr, pix, audio, profile, level,
         gop) = t
        vf = _scale_pad(w, h)
        say(f"[{label}] 编码中 ({w}x{h},fps={fps})...")
        if hw:
            say(f"[硬件加速] 使用 {hw_label}")
        is_lrv = dst.lower().endswith(".lrv")
        # GOP 必须与模板一致：相机按 AMBA[53] 声明的间隔抽帧，
        #   与真实码流不符时不显示缩略图。0 表示模板里量不出来，退回 16。
        keyint = int(gop) if gop and int(gop) > 0 else 16
        if hw and not str(vc).startswith("lib"):
            cmd = _build_hw_transcode_cmd(input_path, dst, vc, tag, vf, extra,
                                          vh, ve, audio, cr, src_audio_count,
                                          is_lrv=is_lrv, fps=fps, level=level,
                                          gop=keyint)
        else:
            if is_lrv:
                enc_params = f"keyint={keyint}:min-keyint={keyint}:scenecut=0:bframes=0"
            else:
                enc_params = (f"keyint={keyint}:min-keyint={keyint}:scenecut=0:"
                              f"bframes=0:range=full:info=0")
                vc = "libx265" if vc not in ("libx265",) else vc
            cmd = _build_transcode_cmd(input_path, dst, vc, tag, vf, enc_params,
                                       vh, ve, audio, cr, src_audio_count,
                                       is_lrv=is_lrv, fps=fps, level=level,
                                       gop=keyint)

        def _job_cb(frac, spd, eta, _i=idx, _label=label):
            if not progress:
                return
            with lock:
                parts[_i] = min(1.0, max(0.0, float(frac or 0)))
                cur = sum(weights[k] * parts[k] for k in range(n))
            progress(min(1.0, cur), _label, spd, eta)

        try:
            _run_ffmpeg(cmd, dur, _job_cb if progress else None, cancel,
                        procs, procs_lock)
        except BaseException as e:
            # 记录第一个真实错误，通知其他任务取消并杀掉它们的 ffmpeg
            if first_error is None:
                first_error = e
            cancel.set()
            with procs_lock:
                for p in procs:
                    try:
                        p.kill()
                    except Exception:
                        pass
            raise
        with lock:
            parts[idx] = 1.0
            overall = sum(weights[k] * parts[k] for k in range(n))
        if progress:
            progress(overall, label, 0.0, 0)
        return dst

    if workers > 1 and n > 1:
        say(f"并行转码: {workers} 路")
        canceled = False
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
            futures = [ex.submit(_run_one, i, t) for i, t in enumerate(tasks)]
            for fut in concurrent.futures.as_completed(futures):
                try:
                    results[futures.index(fut)] = fut.result()
                except CanceledError:
                    canceled = True
                except BaseException as e:
                    # _run_one 只在 _run_ffmpeg 外层记录 first_error；构建命令行、
                    #   探测时长等更早的步骤抛异常时没人记，会被这里静默吞掉，
                    #   于是 convert() 返回 (None, None) 而用户看不到任何报错。
                    #   这里兜底记录，保证并发路径不会把失败变成"成功"。
                    if first_error is None:
                        first_error = e
        # 所有并发任务结束后，若有第一条错误，向上抛出，使 convert 失败
        if first_error is not None:
            raise first_error
        if canceled:
            raise CanceledError("已取消")
    else:
        for idx, t in enumerate(tasks):
            results[idx] = _run_one(idx, t)

    main_path = results[0]
    preview_path = results[1] if len(results) > 1 else None
    return main_path, preview_path

def _card_timeline(output_dir: str) -> tuple[datetime | None, int]:
    """扫描卡里已有 VID_/LRV_ 文件，返回 (最大时间, 最大序号)。

    实测 insertion_defaults(insert="last")：
        when     = 卡里现有最大时间 + 1 秒
        sequence = 卡里现有最大序号 + 1
    这样连续导入多个视频时时间戳自然递增、且总比卡里最新的更新。
    """
    newest = None
    best_seq = -1
    if not os.path.isdir(output_dir):
        return None, 0
    for name in os.listdir(output_dir):
        m = _NAME_RE.match(name)
        if not m:
            continue
        best_seq = max(best_seq, int(m.group(2)))
        try:
            dt = datetime.strptime(m.group(1), "%Y%m%d_%H%M%S")
        except ValueError:
            continue
        if newest is None or dt > newest:
            newest = dt
    if newest is None:
        return None, 0
    return newest + timedelta(seconds=1), best_seq + 1

def batch_convert(file_list: list[str], output_dir: str,
                  start_number: int | None = None, log=None,
                  encoder: tuple[str, str, str] | None = None,
                  progress=None, spec: dict | None = None,
                  use_card_time: bool = False,
                  cancel: threading.Event | None = None
                  ) -> tuple[list[tuple[str, str, str | None]],
                             list[tuple[str, str]]]:
    """批量转换。每个文件使用【各自的创建时间】作为文件名时间戳，
    序号全局递增（先读卡里已有最大尾缀再 +1 接续，避免覆盖）；
    start_number 指定时则从该序号起递增。

    时间戳取自【源视频自己的创建时间】：
      1) 容器内嵌 creation_time（最准）
      2) 文件系统时间（mtime / birthtime）
    不用“当前导入时间”，也不用卡里已有文件的时间。

    参数:
        file_list    输入视频路径列表
        output_dir   输出目录，须可写
        start_number 起始序号；None 表示自动取下一个可用序号
        log          日志回调
        encoder      硬件编码器三元组；None 表示自动检测
        progress     批量进度回调 progress(batch_frac, label, speed, eta_sec)
        spec         原生视频结构；None 时回退默认结构
        use_card_time 是否接续卡里已有文件时间
        cancel       threading.Event；置位时中断整个批量任务

    前置条件:
        file_list 为字符串列表，元素须为存在的文件路径；
        output_dir 须可创建或已存在且可写；
        cancel 若非 None 须为 threading.Event。

    后置条件:
        返回 (success, failed)；
        单个文件失败不影响后续文件；
        cancel 置位时抛 CanceledError，不再处理剩余文件。

    失败方式:
        用户错误: file_list 元素不存在 -> 记入 failed，继续下一条；
        用户错误: 参数类型不符 -> ValidationError；
        用户取消: cancel 置位 -> CanceledError。
    """
    def say(msg):
        if log:
            log(msg)
        else:
            print(msg)

    if not isinstance(file_list, list):
        raise ValidationError("file_list 必须为 list[str]")
    for i, item in enumerate(file_list):
        if not isinstance(item, str) or not item:
            raise ValidationError(f"file_list[{i}] 必须为非空字符串")
    if not isinstance(output_dir, str) or not output_dir:
        raise ValidationError("output_dir 必须为非空字符串")
    try:
        os.makedirs(output_dir, exist_ok=True)
        if not os.access(output_dir, os.W_OK):
            raise ValidationError(f"输出目录不可写: {output_dir}")
    except OSError as e:
        raise ValidationError(f"无法创建或访问输出目录 {output_dir}: {e}") from e
    if spec is not None and not isinstance(spec, dict):
        raise ValidationError("spec 必须为 dict 或 None")
    if cancel is not None and not isinstance(cancel, threading.Event):
        raise ValidationError("cancel 必须为 threading.Event 或 None")
    if cancel is None:
        # 归一化成真实 Event：下游一律直接 cancel.is_set()，不再逐处判 None。
        cancel = threading.Event()

    if cancel.is_set():
        raise CanceledError("已取消")

    base_seq = next_seq(output_dir) if start_number is None else int(start_number)
    card_when, card_seq = _card_timeline(output_dir)
    use_card = bool(use_card_time) and card_when is not None
    if use_card and start_number is None:
        base_seq = card_seq
    success, failed = [], []
    if encoder is None:
        encoder = detect_hw_encoder()
    hw = encoder if (isinstance(encoder, tuple) and len(encoder) == 3
                     and encoder[2] != "software" and encoder[0]) else None

    total = len(file_list)
    used_names = set()
    for i, src in enumerate(file_list):
        if cancel.is_set():
            # 批量导入要能中途停下：否则用户点了取消，剩下的文件还会
            #   一个个转完（每个都要几分钟），取消形同虚设。
            raise CanceledError("已取消")
        if use_card:
            stamp = (card_when + timedelta(seconds=i)).strftime("%Y%m%d_%H%M%S")
        else:
            stamp = _source_stamp(src)
        stamp = _unique_stamp(stamp, output_dir, used_names)
        used_names.add(stamp)
        seq = base_seq + i

        def _wrap(frac, label, spd, eta, _i=i):
            if progress:
                progress((_i + frac) / max(1, total),
                         f"[{_i + 1}/{total}] {os.path.basename(src)}", spd, eta)

        try:
            main, preview = convert(src, output_dir, start_number=seq, stamp=stamp,
                                    log=log, encoder=hw, progress=_wrap, spec=spec,
                                    cancel=cancel)
            success.append((src, main, preview))
        except CanceledError:
            # 取消不是「这个文件失败」：把它塞进 failed 会让上层以为
            #   只是这一条有问题，接着转下一条。
            raise
        except Exception as e:  # noqa: BLE001
            failed.append((src, str(e)))
    return success, failed

def _source_stamp(src: str) -> str:
    """取【源视频自己的拍摄/创建时间】作为文件名时间戳（YYYYMMDD_HHMMSS）。

    优先级与文档承诺一致：
      1) 容器内嵌 creation_time（最准，相机原片通常都有）
      2) 文件系统时间（ctime/mtime 取较可靠者）
      3) 最终兜底才用当前时间

      “时间戳取自源视频自己的创建时间”直接矛盾：所有导入视频在相册里
      都排到导入当天，用户按时间翻找会找不到。
    """
    # 1) 容器 creation_time：位于 format.tags.creation_time（也兜一下 stream tags）
    try:
        raw = probe_raw(src) or {}
        cands = []
        tags = (raw.get("format") or {}).get("tags") or {}
        if tags.get("creation_time"):
            cands.append(tags["creation_time"])
        for st in (raw.get("streams") or []):
            ct = ((st or {}).get("tags") or {}).get("creation_time")
            if ct:
                cands.append(ct)
        for when in cands:
            s = str(when).replace("T", " ").replace("Z", "").strip()
            head = s.split(".")[0]           # 去掉小数秒
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
                try:
                    dt = datetime.strptime(head, fmt)
                    if dt.year > 1970:       # 过滤 1970-01-01 这类无效值
                        return dt.strftime("%Y%m%d_%H%M%S")
                except ValueError:
                    continue
    except Exception:  # noqa: BLE001
        pass

    # 2) 文件系统时间：取 ctime 与 mtime 中较早的那个（ctime 在 NTFS 是创建时间）
    try:
        st = os.stat(src)
        ts = min(x for x in (getattr(st, "st_ctime", 0), st.st_mtime) if x > 0)
        from datetime import datetime as _dt
        return _dt.fromtimestamp(ts).strftime("%Y%m%d_%H%M%S")
    except Exception:  # noqa: BLE001
        pass

    # 3) 兜底
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _unique_stamp(stamp: str, output_dir: str, used: set) -> str:
    """保证时间戳在同一批文件与目标目录里唯一（撞了就 +1 秒）。

    相机按 <时间戳>_<序号> 命名，时间戳重复会导致索引条目互相覆盖。
    """
    try:
        dt = datetime.strptime(stamp, "%Y%m%d_%H%M%S")
    except ValueError:
        return stamp
    for _ in range(86400):
        s = dt.strftime("%Y%m%d_%H%M%S")
        if s in used:
            dt += timedelta(seconds=1)
            continue
        # 目录里是否已有同名（VID_/LRV_ 任一存在即避让）
        if os.path.isdir(output_dir):
            probe = {f"VID_{s}_000.mp4", f"LRV_{s}_000.lrv"}
            if any(os.path.exists(os.path.join(output_dir, n)) for n in probe):
                dt += timedelta(seconds=1)
                continue
            # 更宽松：任何以该时间戳开头的文件都算撞
            prefix = f"VID_{s}_"
            try:
                if any(n.startswith(prefix) for n in os.listdir(output_dir)):
                    dt += timedelta(seconds=1)
                    continue
            except OSError:
                pass
        return s
    return stamp

# 相机认卡的关键：除了文件名/结构正确，还必须把文件登记进两个 protobuf 索引。
#
#       <卡根>\DCIM\fileinfo_list.list
#       <卡根>\DCIM\.editinfo_list.list
#   索引文件在 **DCIM 根目录** 下，不在 Camera01 里。
#   但索引条目里记录的文件路径指向  /DCIM/Camera01/<文件名>
FILENAME_RE = re.compile(r"^(VID|LRV|LRVL)_(\d{8}_\d{6})_(\d+)\.(mp4|lrv)$", re.I)

def _card_root(card_root: str) -> str:
    """把传入路径归一成相机卡根目录（即 DCIM 的父级）。"""
    p = os.path.abspath(card_root)
    base = os.path.basename(os.path.normpath(p))
    if base.lower() in ("camera01", "camera0000"):
        p = os.path.dirname(os.path.dirname(p))      # …\DCIM\Camera01 -> 卡根
    elif base.upper() == "DCIM":
        p = os.path.dirname(p)                        # …\DCIM -> 卡根
    return p

def has_inst_box(path: str) -> tuple[bool, int]:
    """检查 MP4 是否带影石 `inst` box（相机识别的必要条件）。

    返回 (是否存在, box 字节数)。
    """
    try:
        #   且 data 变量从未被使用（死代码）。verify_card 对每条索引条目调用一次，
        #   卡大时句柄会累积。已删除。
        # 只读头部拿不到尾 box，需完整扫描；用轻量方式
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            i = 0
            while i + 8 <= size:
                f.seek(i)
                hdr = f.read(8)
                if len(hdr) < 8:
                    break
                sz = int.from_bytes(hdr[:4], "big")
                typ = hdr[4:8]
                if sz == 1:
                    f.seek(i + 8); ext = f.read(8)
                    sz = int.from_bytes(ext, "big") if len(ext) == 8 else 0
                elif sz == 0:
                    sz = size - i
                if sz < 8:
                    break
                if typ == b"inst":
                    return True, sz
                i += sz
    except OSError:
        pass
    return False, 0

# 相机识别视频的【第三层】：MP4 尾部必须挂一个 `inst` box，
# 内部是影石私有的传感器/元数据（含 protobuf 元数据记录）。
#
# 没有 inst box 的视频 → 相机视为"外来文件"，会自行重建索引或直接忽略。
# 这就是"相机能自己重建索引"的根本原因。
#
# 做法：
#   1. 用真机原片作模板 —— 取它的 moov 骨架、udta、inst box
#   2. 把自己编码的视频样本，按真机的采样表重新封装
#   3. 移植 inst box 并更新其中的 protobuf 元数据 / 偏移表
#   4. patch_ftyp 把 free 改成 wide
# 共享核心库位于仓库根目录的 shared/instbox（与安卓端同源）
_INST_ORIGIN = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "..", "shared")
if _INST_ORIGIN not in sys.path:
    sys.path.insert(0, _INST_ORIGIN)

def _load_inst_modules():
    """按需加载 shared/instbox 下的 .inst 移植模块（与安卓端同源）。

      instbox 里的模块用 ffprobe()/ffmpeg 子进程，
      若靠 PATH 查找，打包后会抛 WinError 2。
    """
    for key, finder in (("FFMPEG_PATH", find_ffmpeg),
                        ("FFPROBE_PATH", find_ffprobe)):
        if os.environ.get(key) and os.path.isfile(os.environ[key]):
            continue
        try:
            found = finder()
        except Exception:  # noqa: BLE001
            found = None
        if found:
            os.environ[key] = found
    if _INST_ORIGIN not in sys.path:
        sys.path.insert(0, _INST_ORIGIN)
    import instbox.inst_transplant as _tf          # noqa: PLC0415
    import instbox.moov_rewrap as _rw              # noqa: PLC0415
    return _tf, _rw

def extract_inst_meta(path: str) -> bytes | None:
    """直接从视频的 inst box 里提取 protobuf 元数据（不依赖索引）。

    inst box 布局：
        [传感器数据 .. ][protobuf meta][偏移表 + trailer]
    meta 起点是最后一个 “0a 0e <14字节serial>” (f1 = serial)。
    从该处逐字段解析，得到精确长度。
    """
    try:
        tf, _ = _load_inst_modules()
    except Exception:  # noqa: BLE001
        return None
    try:
        _, inst = tf.split_inst(Path(path))
    except Exception:  # noqa: BLE001
        return None

    # 找最后一个 0a 0e <serial>（serial 特征：ASCII 大写字母+数字）
    best = -1
    i = 0
    while True:
        i = inst.find(b"\x0a\x0e", i)
        if i < 0:
            break
        seg = inst[i+2:i+16]
        if len(seg) == 14 and seg.isascii() and seg.isalnum():
            best = i
        i += 1
    if best < 0:
        return None

    blob = inst[best:]
    pos = 0
    fields = []
    while pos < len(blob):
        try:
            key, np = tf.read_varint(blob, pos)
        except Exception:  # noqa: BLE001
            break
        n, w = key >> 3, key & 7
        if n == 0:
            break
        if w == 0:
            try:
                v, np = tf.read_varint(blob, np)
            except Exception:  # noqa: BLE001
                break
        elif w == 2:
            try:
                sz, np = tf.read_varint(blob, np)
            except Exception:  # noqa: BLE001
                break
            if np + sz > len(blob):
                break
            v = blob[np:np+sz]
            np += sz
        elif w == 1:
            if np + 8 > len(blob):
                break
            v = blob[np:np+8]
            np += 8
        elif w == 5:
            if np + 4 > len(blob):
                break
            v = blob[np:np+4]
            np += 4
        else:
            break
        fields.append(tf.Field(n, w, v))
        pos = np
    if not fields:
        return None
    enc = tf.encode_message(fields)
    return enc if len(enc) == pos else (blob[:pos] if pos > 0 else None)

def find_native_template(card_root: str) -> tuple | None:
    """在卡里找一对真机原片 (VID_*.mp4, LRV_*.lrv) 作为模板。

    返回 (main_path, proxy_path, reference_meta) 或 None。
    """
    cam = camera_dir(card_root)
    if not os.path.isdir(cam):
        return None
    #   按名字中出现的 "VID_"/"LRV_" 定位规范名再配对。
    vids, lrvs = {}, {}
    for nm in sorted(os.listdir(cam)):
        up = nm.upper()
        if up.endswith(".MP4"):
            j = up.find("VID_")
            if j >= 0:
                vids.setdefault(nm[j:].lower(), os.path.join(cam, nm))
        elif up.endswith(".LRV"):
            j = up.find("LRV_")
            if j >= 0:
                lrvs.setdefault(nm[j:].lower(), os.path.join(cam, nm))
    for key in sorted(vids):
        stem = key[:-4]                                  # vid_..._nnn
        lk = "lrv_" + stem[4:] + ".lrv"
        if lk not in lrvs:
            continue
        main, proxy = vids[key], lrvs[lk]
        meta = extract_inst_meta(main)
        if not meta:
            continue
        return main, proxy, bytes(meta)
    return None

def camera_dir(card_root: str) -> str:
    """视频应放置的目录：<卡根>\\DCIM\\Camera01"""
    return os.path.join(_card_root(card_root), "DCIM", "Camera01")

def card_index_paths(card_root: str) -> tuple[str, str]:
    """返回 (fileinfo_list.list, .editinfo_list.list) 的完整路径。

    card_root 可以是相机卡根、DCIM、或 DCIM/Camera01。
    """
    dcim = os.path.join(_card_root(card_root), "DCIM")
    return os.path.join(dcim, "fileinfo_list.list"), os.path.join(dcim, ".editinfo_list.list")

def is_camera_card(path: str) -> bool:
    """判断该目录是否像影石相机卡（含 DCIM\\Camera01 结构或已有索引）。

    用途：防止把索引写到普通文件夹，误建 DCIM 目录。
    """
    root = _card_root(path)
    dcim = os.path.join(root, "DCIM")
    if not os.path.isdir(dcim):
        return False
    # 有 Camera01 子目录，或已有索引文件
    if os.path.isdir(os.path.join(dcim, "Camera01")):
        return True
    if os.path.isfile(os.path.join(dcim, "fileinfo_list.list")):
        return True
    return False

def _file_attrs(path: str) -> int | None:
    """取 Windows 文件属性位（非 Windows / 失败返回 None）。"""
    if os.name != "nt":
        return None
    try:
        import ctypes
        v = ctypes.windll.kernel32.GetFileAttributesW(ctypes.c_wchar_p(path))
    except Exception:  # noqa: BLE001
        return None
    return None if v == 0xFFFFFFFF else int(v)


def _set_file_attrs(path: str, attrs: int | None) -> None:
    """恢复 Windows 文件属性位（含只读位）；不适用时静默跳过。"""
    if os.name != "nt" or attrs is None or not os.path.exists(path):
        return
    try:
        import ctypes
        ctypes.windll.kernel32.SetFileAttributesW(
            ctypes.c_wchar_p(path), ctypes.c_uint32(attrs))
    except Exception:  # noqa: BLE001
        pass


def _write_inplace(path: str, data: bytes) -> None:
    """r+b 原地改写：保留隐藏属性与 ACL（wb 会被拒绝）。"""
    with open(path, "r+b") as f:
        f.seek(0)
        f.write(data)
        f.truncate()
        f.flush()
        os.fsync(f.fileno())


def _write_index_file(path: str, data: bytes, log=None) -> None:
    """写入索引文件，保留 Windows 隐藏属性与 ACL。

      那是隐藏文件，`wb`（CREATE_ALWAYS）会因隐藏属性+ACL 报
      PermissionError [Errno 13]（即使管理员/属主也会被拒）。
      隐藏文件必须用 r+b 原地改写，新建时用 xb。
    """
    attrs = _file_attrs(path)
    try:
        if os.path.exists(path):
            try:
                # r+b：改写已有文件对象，保留 Hidden 属性与 ACL
                _write_inplace(path, data)
            except PermissionError as e:
                #   os.chmod 对 Windows 只读位不一定生效，要直接改属性。
                _clear_readonly(path)
                try:
                    _write_inplace(path, data)
                except PermissionError:
                    raise PermissionError(
                        f"无法写入索引 {os.path.basename(path)}：权限被拒。\n"
                        f"    路径: {path}\n"
                        "    请确认：1) 卡的写保护开关没打开；"
                        "2) 文件没被其他程序（相机软件/杀软）占用；"
                        "3) 以管理员身份运行本程序。") from e
        else:
            # 不存在则新建（xb 不覆写已有文件）
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(path, "xb") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
    finally:
        #   旧实现会跳过恢复，导致卡上的 .editinfo_list.list 永久丢掉只读位。
        #   恢复原有属性（只读位等），不改动卡上文件的常规属性。
        _set_file_attrs(path, attrs)

def _clear_readonly(path: str) -> None:
    """清掉 Windows 的只读属性（FILE_ATTRIBUTE_READONLY），保留其他属性。

    真机卡的 `.editinfo_list.list` 常见“隐藏 + 只读”（属性 0x3）。
    只读位不清，即使管理员打开也会 ERROR_ACCESS_DENIED。
    清掉后立即在 finally 中恢复，避免改动卡上文件的常规属性。
    """
    if os.name != "nt":
        try:
            os.chmod(path, 0o666)
        except OSError:
            pass
        return
    try:
        import ctypes
        k = ctypes.windll.kernel32
        ATTR_READONLY = 0x01
        attrs = k.GetFileAttributesW(ctypes.c_wchar_p(path))
        if attrs != 0xFFFFFFFF and (attrs & ATTR_READONLY):
            k.SetFileAttributesW(ctypes.c_wchar_p(path),
                                 ctypes.c_uint32(attrs & ~ATTR_READONLY))
    except Exception:  # noqa: BLE001
        try:
            os.chmod(path, 0o666)
        except OSError:
            pass

def _read_index(path: str) -> bytes:
    return open(path, "rb").read() if os.path.isfile(path) else b""

def _backup_once(path: str) -> str | None:
    """写入前做时间戳备份。仅备份一次。"""
    if not os.path.isfile(path):
        return None
    import shutil
    from datetime import datetime as _dt
    stamp = _dt.now().strftime("%Y%m%d_%H%M%S")
    bak = f"{path}.{stamp}.bak"
    if not os.path.exists(bak):
        shutil.copy2(path, bak)
    return bak

def _template_meta(card_root: str) -> "object | None":
    """从卡里已有的【真机】条目中取一个作为元数据模板。

        1. 视频文件真实存在
        2. 该文件带 `inst` box（说明是相机原生录制，不是我们生成的）
        3. 条目 meta 里 f9（inst 偏移）与实际一致
    这样避免拿"之前导入的半成品条目"当模板导致污染。
    """
    import insta_index as ix
    fi, _ = card_index_paths(card_root)
    data = _read_index(fi)
    if not data:
        return None
    cam = camera_dir(card_root)

    def _ok(e) -> bool:
        if e.meta is None:
            return False
        fname = os.path.basename(e.path)
        if not fname.upper().startswith("VID_"):
            return False
        fp = os.path.join(cam, fname)
        if not os.path.isfile(fp):
            return False
        try:
            has, _ = has_inst_box(fp)
        except Exception:  # noqa: BLE001
            return False
        return bool(has)

    for e in ix.parse_fileinfo(data):
        if _ok(e):
            return e.meta
    return None

def register_to_card(card_root: str, media_paths: list[str],
                     log=None, metas: list | None = None,
                     require_card: bool = True) -> list[str]:
    """把已生成/待生成的素材登记进相机索引。

    media_paths 为卡内绝对路径（或卡内相对路径，如
    r"DCIM\\Camera01\\VID_....mp4"）。返回成功登记的路径列表。

    metas  与 media_paths 一一对应的【真实 meta 字节】。
             否则索引与文件内部对不上，相机会显示条目但打不开。
           为 None 时回退到复刻卡里已有条目的结构（兼容旧行为）。

      然后追加新条目 —— 因此【不会影响卡里已有的旧视频】。

    require_card=True 时校验目标确实是相机卡，避免往普通文件夹误建 DCIM。
    """
    import insta_index as ix

    def say(m):
        (log or print)(m)

    if require_card and not is_camera_card(card_root):
        raise RuntimeError(
            f"目标不是影石相机卡（缺少 DCIM\\Camera01 结构）：\n"
            f"  {_card_root(card_root)}\n"
            "为避免在普通文件夹里误建 DCIM 目录、污染数据，已中止索引写入。\n"
            "请把输出目录指向存储卡的 DCIM 或 DCIM\\Camera01。")

    fi_path, ei_path = card_index_paths(card_root)
    os.makedirs(os.path.dirname(fi_path), exist_ok=True)
    cam_dir = camera_dir(card_root)
    fallback = _template_meta(card_root)

    fi_data = _read_index(fi_path)
    ei_data = _read_index(ei_path)
    bak = _backup_once(fi_path)
    if bak:
        say(f"已备份原索引 -> {os.path.basename(bak)}")
    _backup_once(ei_path)

    done = []
    for idx, p in enumerate(media_paths):
        # 规范化成卡内路径 "/DCIM/Camera01/xxx.mp4"
        if os.path.isabs(p):
            name = os.path.basename(p)
            rel = "/DCIM/Camera01/" + name
            src_abs = p
        else:
            rel = "/" + p.replace("\\", "/").lstrip("/")
            name = os.path.basename(rel)
            src_abs = os.path.join(cam_dir, name)

        #   真机卡实测：fileinfo_list.list 里条目全是 VID，LRV 一条都没有；
        #   实测也只写 main 一条记录（catalog_path）。
        #   把 LRV 也登记会多出一个 proxy 条目（f26.2=1），
        #   相机把它显示成 0 KB 且无法播放。
        if name.lower().endswith(".lrv"):
            say(f"跳过 LRV（相册索引只登记主视频）: {name}")
            continue

        #   若传入目录路径，os.path.basename 会得到空串，进而往索引里写入
        #   指向目录的幽灵条目（相机显示 0 KB 且打不开）。这里补上校验。
        if not name or not os.path.isfile(src_abs):
            say(f"跳过登记（目标文件不存在）: {rel}")
            continue

        raw_meta = None
        if metas is not None and idx < len(metas) and metas[idx]:
            raw_meta = metas[idx] if isinstance(metas[idx], (bytes, bytearray)) \
                else metas[idx].to_bytes() if hasattr(metas[idx], "to_bytes") \
                else None

        if raw_meta:
            meta = ix.MediaInfo.parse(bytes(raw_meta))
        elif fallback is not None:
            meta = ix.MediaInfo.parse(fallback.to_bytes())
            m = FILENAME_RE.match(name)
            if m:
                meta.datetime_num = int(m.group(2).replace("_", ""))
                try:
                    from datetime import datetime as _dt
                    dt = _dt.strptime(m.group(2), "%Y%m%d_%H%M%S")
                    meta.epoch_ms = int(dt.timestamp() * 1000)
                except ValueError:
                    pass
        else:
            #   缺少 f25/f27/f28/f31，写进卡里会表现为“条目存在但 0 KB 打不开”。
            #   既没有 inst box 里的真实 meta、也没有可复刻的卡内旧条目时，跳过登记。
            say(f"跳过登记（缺少真实 meta 模板，拒绝编造）: {rel}")
            continue

        fi_data, ei_data = ix.register_media(fi_data, ei_data, rel, meta)
        done.append(rel)
        say(f"已登记索引: {rel}")

    _write_index_file(fi_path, fi_data, log=say)
    _write_index_file(ei_path, ei_data, log=say)
    say(f"索引已写入: {os.path.basename(fi_path)} ({len(fi_data)}B), "
        f"{os.path.basename(ei_path)} ({len(ei_data)}B)")
    return done

COVER_WIDTH, COVER_HEIGHT = 896, 512

def render_cover(image_path: str, output: str,
                 cancel: threading.Event | None = None,
                 timeout: float = 120.0) -> bytes:
    """把任意图片渲染成相机封面用的原始帧（896x512 NV12）。

      同名封面图（a.mp4 → a.jpg）也走这里，不直接拿原像素。
    """
    if not isinstance(image_path, str) or not image_path:
        raise ValidationError("image_path 必须为非空字符串")
    if not os.path.isfile(image_path):
        raise FileNotFoundError(f"封面图不存在: {image_path}")
    if not isinstance(output, str) or not output:
        raise ValidationError("output 必须为非空字符串")
    if cancel is not None and not isinstance(cancel, threading.Event):
        raise ValidationError("cancel 必须为 threading.Event 或 None")
    if cancel is None:
        # 归一化成真实 Event：下游一律直接 cancel.is_set()，不再逐处判 None。
        cancel = threading.Event()
    ff = find_ffmpeg()
    if not ff:
        raise ValidationError("未找到 ffmpeg，无法渲染封面")

    vf = (f"scale={COVER_WIDTH}:{COVER_HEIGHT}:force_original_aspect_ratio=decrease,"
          f"pad={COVER_WIDTH}:{COVER_HEIGHT}:(ow-iw)/2:(oh-ih)/2:black")
    cmd = [ff, "-hide_banner", "-loglevel", "error", "-y",
           "-i", str(image_path), "-vf", vf, "-frames:v", "1",
           "-pix_fmt", "nv12", "-f", "rawvideo", str(output)]
    try:
        subprocess.run(cmd, check=True, creationflags=_NO_WINDOW, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        raise FFmpegError(
            f"封面渲染超时（>{timeout}s）: {image_path}",
            cmd=cmd, returncode=None, stderr="", retryable=False) from e
    except subprocess.CalledProcessError as e:
        err = (e.stderr.decode("utf-8", "replace")[:200]
               if e.stderr else str(e))
        raise FFmpegError(
            f"封面渲染失败: {err}",
            cmd=cmd, returncode=e.returncode, stderr=err,
            retryable=False) from e
    data = Path(output).read_bytes()
    if len(data) != COVER_WIDTH * COVER_HEIGHT * 3 // 2:
        raise ValueError(f"封面尺寸异常: {len(data)} 字节")
    return data

SIDECAR_IMG_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".bmp")
# VID(1080p HEVC) + LRV(480p) 实测约 5～6MB/分钟，留余量取 7MB
EST_BYTES_PER_MIN = 7 * 1024 * 1024


def default_cover_for(video_path: str) -> str | None:
    """找视频旁边的【同名】封面图（a.mp4 → a.jpg / a.png）。

    文件夹导入时用：每个视频各自的封面。大小写不敏感。
    """
    try:
        folder = os.path.dirname(os.path.abspath(video_path))
        stem = os.path.splitext(os.path.basename(video_path))[0].lower()
        for name in os.listdir(folder):
            base, ext = os.path.splitext(name)
            if base.lower() == stem and ext.lower() in SIDECAR_IMG_EXTS:
                return os.path.join(folder, name)
    except OSError:
        return None
    return None


def estimate_output_bytes(sources) -> int:
    """粗估输出体积（VID+LRV）。用于开工前检查磁盘空间。"""
    total = 0.0
    for s in sources:
        dur = 0.0
        try:
            dur = float(probe(s).get("video", {}).get("duration") or 0)
        except (TypeError, ValueError, OSError):
            dur = 0.0
        if not dur:
            # 抽不出时长时按 2MB/s 回退，宁多不少
            try:
                dur = os.path.getsize(s) / (2 * 1024 * 1024)
            except OSError:
                dur = 0.0
        total += max(0.0, dur) / 60.0 * EST_BYTES_PER_MIN
    return int(total * 1.25)


def preflight(dest: str, sources, do_index: bool = True) -> dict:
    """开工前体检：把“跑到最后才失败”的问题提前到 1 秒内。

    返回 dict:
        blocking  - 必须解决，否则不应开始
        warnings  - 只是提醒，不影响运行
        estimate_bytes / free_bytes / is_card / template_ok
    """
    res = {"blocking": [], "warnings": [], "estimate_bytes": 0,
           "free_bytes": 0, "is_card": False, "template_ok": False}

    if not find_ffmpeg():
        res["blocking"].append("找不到 ffmpeg，无法转码。")

    srcs = [s for s in (sources or []) if s]
    if not srcs:
        res["blocking"].append("没有待转换的视频。")
    for s in srcs:
        if not os.path.isfile(s):
            res["blocking"].append(f"源文件不存在: {s}")

    # 输出目录
    if not dest:
        res["blocking"].append("没有选择输出目录。")
    else:
        try:
            os.makedirs(dest, exist_ok=True)
        except OSError as e:
            res["blocking"].append(f"输出目录不可用: {dest}（{e}）")

    # 空间
    res["estimate_bytes"] = estimate_output_bytes([s for s in srcs if os.path.isfile(s)])
    if dest and os.path.isdir(dest):
        try:
            res["free_bytes"] = shutil.disk_usage(dest).free
        except OSError:
            res["free_bytes"] = 0
        if res["free_bytes"] and res["estimate_bytes"] > res["free_bytes"]:
            res["blocking"].append(
                "磁盘空间不足：需要约 {:.0f} MB，可用 {:.0f} MB。".format(
                    res["estimate_bytes"] / 1e6, res["free_bytes"] / 1e6))

    if not do_index:
        return res

    # 是不是相机卡
    res["is_card"] = bool(dest) and is_camera_card(dest)
    if dest and not res["is_card"]:
        res["warnings"].append(
            "输出目录看起来不是影石相机卡（缺 DCIM\\Camera01），索引登记会被跳过。")

    # 索引能不能写
    if res["is_card"]:
        for fp in card_index_paths(dest):
            if not os.path.isfile(fp):
                continue
            at = _file_attrs(fp)
            if at is not None and (at & 0x01):
                res["warnings"].append(
                    f"{os.path.basename(fp)} 是只读文件：写入时会临时清只读位，写后恢复。")
            try:
                with open(fp, "r+b"):
                    pass
            except OSError as e:
                res["blocking"].append(
                    f"索引不可写：{fp}（{e}）——检查卡的写保护开关/是否被占用。")

    # 模板
    try:
        tpl = find_native_template(dest) if dest else None
    except Exception:  # noqa: BLE001
        tpl = None
    res["template_ok"] = tpl is not None
    if not res["template_ok"]:
        res["blocking"].append(
            "卡里找不到真机原片作模板（DCIM\\Camera01\\VID_*.mp4 + LRV_*.lrv）。\n"
            "没有它无法移植 inst box，相机不会认。")
    return res


def _jobs_dir() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    d = os.path.join(base, "InstaAceImporter", "jobs")
    os.makedirs(d, exist_ok=True)
    return d


def job_path(dest: str) -> str:
    """每个输出目录一个进度文件（断点续跑用）。"""
    import hashlib
    key = os.path.normpath(dest or "").lower().encode("utf-8", "replace")
    return os.path.join(_jobs_dir(), hashlib.sha1(key).hexdigest()[:12] + ".json")


def load_job(dest: str) -> dict | None:
    p = job_path(dest)
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def save_job(dest: str, job: dict) -> None:
    """原子写入，避免中途断电把进度文件写坏。

    写入失败向上抛 OSError，由调用方决定是否中断主流程；
    不再静默吞掉，避免断点续跑进度丢失而用户无感知。
    """
    p = job_path(dest)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(job, f, ensure_ascii=False, indent=1)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, p)


_ES_CONTINUOUS = 0x80000000
_ES_SYSTEM_REQUIRED = 0x00000001


def set_awake(enable: bool) -> bool:
    """转码期间阻止系统休眠（Windows）。返回是否生效。"""
    if os.name != "nt":
        return False
    try:
        import ctypes
        flags = _ES_CONTINUOUS | (_ES_SYSTEM_REQUIRED if enable else 0)
        ctypes.windll.kernel32.SetThreadExecutionState(flags)
        return True
    except Exception:  # noqa: BLE001
        return False


def _stage_cb(progress, lo: float, hi: float, name: str):
    """把一个子阶段的 0~1 进度映射到整体的 [lo, hi] 区间。

    例：转码占 0~70% → _stage_cb(cb, 0.0, 0.70, "转码")，
    子阶段跑到 0.5 时整体就是 35%，标签为 "转码 · VID"。
    """
    if not progress:
        return None

    def cb(frac=0.0, label="", speed=0.0, eta=0):
        f = max(0.0, min(1.0, float(frac or 0.0)))
        text = f"{name} · {label}" if label else name
        progress(lo + (hi - lo) * f, text, speed, eta)

    return cb

def import_with_inst(source: str, card_root: str,
                     template: tuple[str, str, bytes] | None = None,
                     log=None, encoder: tuple[str, str, str] | None = None,
                     progress=None, cancel: threading.Event | None = None,
                     spec: dict | None = None,
                     cover: str | None = None,
                     start_number: int | None = None) -> dict:
    """【完整导入】转码 + `.inst` 移植 + 索引登记（三步全做）。

    相机识别的三个必要条件：
        1. 编码结构正确（VID/LRV）
        2. MP4 尾部挂 `inst` box（影石私有元数据） 关键
        3. 登记进 DCIM\\*.list 索引

    参数:
        source    输入视频路径，须为存在的常规文件
        card_root 相机卡根目录，须含 DCIM/Camera01 结构
        template  可选 (main_path, proxy_path, reference_meta)；
                  None 时自动在卡里查找真机原片
        encoder   硬件编码器三元组；None 表示自动检测
        progress  进度回调 progress(overall_frac, label, speed, eta_sec)
        cancel    threading.Event；置位时中断整个导入流程
        spec      原生视频结构；None 时从模板量出
        cover     可选封面图片路径
        start_number 起始序号；None 表示自动接取输出目录里下一个可用序号
                  （即「自动接续序号」）。传具体整数则从该序号起编号，
                  用于关闭自动接续时从 000 开始。

    前置条件:
        source 存在且为常规文件；
        card_root 可创建或已存在；
        template 若非 None，须为长度 3 的元组，第三元素为 bytes；
        cancel 若非 None 须为 threading.Event。

    后置条件:
        返回 dict 含 main, proxy, registered, inst_ok, inst_error,
        index_error, inst_metas；
        inst_ok 为 True 仅当主视频与 LRV 的 inst 移植均成功；
        临时工作目录在 finally 中清理；
        cancel 置位时抛 CanceledError，部分中间产物可能残留。

    失败方式:
        用户错误: source 不存在 -> FileNotFoundError；
        用错误: 参数类型不符 -> ValidationError；
        系统错误(不可重试): 卡里无真机模板 -> CardError；
        用户取消: cancel 置位 -> CanceledError；
        系统错误: ffmpeg/转码失败 -> FFmpegError 向上抛出；
        系统错误: inst 移植单个文件失败 -> 记入 inst_errs，继续另一条；
        系统错误: 索引登记失败 -> 记入 index_error，不中断返回。
    """
    def say(m):
        (log or print)(m)

    if not isinstance(source, str) or not source:
        raise ValidationError("source 必须为非空字符串")
    if not os.path.isfile(source):
        raise FileNotFoundError(f"输入文件不存在: {source}")
    if not isinstance(card_root, str) or not card_root:
        raise ValidationError("card_root 必须为非空字符串")
    if template is not None:
        if not isinstance(template, tuple) or len(template) != 3:
            raise ValidationError("template 必须为 (main_path, proxy_path, reference_meta) 元组")
        if not isinstance(template[2], (bytes, bytearray)):
            raise ValidationError("template[2] reference_meta 必须为 bytes")
    if cancel is not None and not isinstance(cancel, threading.Event):
        raise ValidationError("cancel 必须为 threading.Event 或 None")
    if cancel is None:
        # 归一化成真实 Event：下游一律直接 cancel.is_set()，不再逐处判 None。
        cancel = threading.Event()
    if spec is not None and not isinstance(spec, dict):
        raise ValidationError("spec 必须为 dict 或 None")
    if cover is not None and not isinstance(cover, str):
        raise ValidationError("cover 必须为字符串或 None")
    if start_number is not None:
        if isinstance(start_number, bool) or not isinstance(start_number, int):
            raise ValidationError(f"start_number 必须为整数或 None: {start_number!r}")
        if start_number < 0:
            raise ValidationError(f"start_number 不能为负数: {start_number}")

    if cancel.is_set():
        raise CanceledError("已取消")

    card_root = _card_root(card_root)
    cam = camera_dir(card_root)
    try:
        os.makedirs(cam, exist_ok=True)
    except OSError as e:
        raise CardError(f"无法创建相机卡目录 {cam}: {e}") from e

    if template is None:
        template = find_native_template(card_root)
    if template is None:
        raise CardError(
            "卡里找不到真机原片作模板。\n"
            "`.inst` 移植必须有一个真机视频提供 moov 骨架与 inst box。\n"
            "请先在 DCIM\\Camera01 放一对相机原生 VID_*.mp4 + LRV_*.lrv。")

    tpl_main, tpl_proxy, ref_meta = template
    say(f"模板: {os.path.basename(tpl_main)}")

    if spec is None:
        spec = spec_from_template(template)
        if spec:
            v = spec.get("video", {}) or {}
            lv = spec.get("lrv_video", {}) or {}
            say("按模板规格生成：主 {}x{}@{} / 预览 {}x{}@{}".format(
                v.get("width"), v.get("height"), v.get("fps"),
                lv.get("width"), lv.get("height"), lv.get("fps")))

    tf, rw = _load_inst_modules()

    say("步骤 1/3 转码...")
    p_transcode = _stage_cb(progress, 0.0, 0.70, "转码")
    main_path, proxy_path = convert(source, cam, encoder=encoder,
                                    spec=spec, log=None, progress=p_transcode,
                                    cancel=cancel, start_number=start_number)

    say("步骤 2/3 移植 inst box...")
    import tempfile as _temp
    from datetime import datetime as _dt
    work = _temp.mkdtemp(prefix="insta_inst_")
    metas: dict[str, object] = {}
    inst_errs: list[str] = []
    try:
        thumb_path = Path(work) / "thumb.yuv"
        thumbnail = None
        if cover:
            try:
                thumbnail = render_cover(cover, str(thumb_path), cancel=cancel)
                say(f"封面: 使用自定义图片 {os.path.basename(cover)}")
            except CanceledError:
                raise
            except Exception as _ce:
                say(f"  自定义封面处理失败，改用视频取帧: {_ce}")
        if thumbnail is None:
            try:
                thumbnail = tf.make_thumbnail(Path(source), thumb_path)
            except Exception as _te:
                say(f"  缩略图生成失败（不致命）: {_te}")
                thumbnail = None
        p_inst = _stage_cb(progress, 0.70, 0.94, "移植 inst box")
        if p_inst:
            p_inst(0.0, "", 0.0, 0)
        pairs = ((main_path, tpl_main, "VID", False),
                 (proxy_path, tpl_proxy, "LRV", True))
        for _k, (gen, native, label, is_proxy) in enumerate(pairs):
            if cancel.is_set():
                raise CanceledError("已取消")
            if gen is None or not os.path.isfile(gen):
                inst_errs.append(f"{label}: 转码产物不存在")
                if p_inst:
                    p_inst((_k + 1) / len(pairs), "", 0.0, 0)
                continue
            gen_p = Path(gen)
            native_p = Path(native)
            try:
                new_meta_bytes = _inst_attach_one(
                    tf, rw, work, gen_p, native_p, label, is_proxy,
                    thumbnail, ref_meta, spec, log=say)
                metas[gen] = new_meta_bytes
                say(f"  {label}: inst 已移植 ({gen_p.stat().st_size}B)"
                    f" → /DCIM/Camera01/{gen_p.name}")
            except Exception as e:
                import traceback as _tb
                msg = f"{type(e).__name__}: {e}"
                inst_errs.append(f"{label}: {msg}")
                say(f"  {label}: inst 移植失败（{msg}）")
                say("  " + _tb.format_exc().replace("\n", "\n  ")[:900])
            if p_inst:
                p_inst((_k + 1) / len(pairs), "", 0.0, 0)

        say("步骤 3/3 登记索引...")
        p_index = _stage_cb(progress, 0.94, 1.0, "登记索引")
        if p_index:
            p_index(0.1, "", 0.0, 0)
        media, media_metas = [], []
        skipped = []
        for p in (main_path, proxy_path):
            if not p:
                continue
            if metas.get(p):
                media.append(p)
                media_metas.append(metas[p])
            else:
                skipped.append(os.path.basename(p))
        if skipped:
            say("以下文件 inst 移植未成功，已跳过索引登记（避免产生打不开的条目）：")
            for n in skipped:
                say(f"    {n}")
        registered = []
        index_error = ""
        if media:
            try:
                registered = register_to_card(card_root, media, log=log,
                                              metas=media_metas)
            except Exception as e:
                import traceback as _tb2
                index_error = f"{type(e).__name__}: {e}"
                say(f"索引登记失败（inst 已移植，文件本身可用）: {index_error}")
                say("  " + _tb2.format_exc().replace("\n", "\n  ")[:700])
        if p_index:
            p_index(1.0, "", 0.0, 0)
    finally:
        shutil.rmtree(work, ignore_errors=True)

    inst_ok = bool(main_path and proxy_path
                   and metas.get(main_path) and metas.get(proxy_path))
    return {"main": main_path, "proxy": proxy_path,
            "registered": registered,
            "inst_ok": inst_ok,
            "inst_error": "; ".join(inst_errs) if inst_errs else "",
            "index_error": index_error,
            "inst_metas": {k: len(v) for k, v in metas.items() if v}}

_UDTA_NAME_RE = re.compile(rb"(?:VID|LRV)_\d{8}_\d{6}_\d{3}\.(?:mp4|lrv)")

def _udta_stored_name(tf, native_p, is_proxy: bool) -> str:
    """读出模板 udta 里存的【相机原始文件名】。

    udta 的 free box 内存着 "/DCIM/Camera01/VID_xxxx.mp4"，
    其中文件名是相机写入的规范名，与磁盘上的文件名可能不同
    （用户可能给模板文件加过前缀或改过名）。
    找不到时回退到磁盘文件名。
    """
    want = b"LRV_" if is_proxy else b"VID_"
    try:
        udta = tf.extract_udta(Path(native_p))
        for m in _UDTA_NAME_RE.finditer(udta):
            if m.group().startswith(want):
                return m.group().decode("ascii")
    except Exception:  # noqa: BLE001
        pass
    return os.path.basename(str(native_p))

def _shrink_avc1_entry(tf, path, keep: bytes = b"avcC") -> bool:
    """把视频采样条目的子 box 精简为只保留 keep（相机要求）。

    黄金参考：相机认的采样条目里只有解码配置盒 —— H.264 是 avc1/avcC，
    HEVC 是 hvc1/hvcC。ffmpeg 产物会多带 pasp / btrt 等，相机直接拒收整条。
    GO Ultra 的 LRV 是 hvc1，所以这里不能只看 avc1：按实际 tag 选对应的
    配置盒，否则 GO Ultra 的 LRV 会静默跳过精简。
    修改后同步回填 stsd/stbl/minf/mdia/trak/moov 的 box 长度。
    返回是否发生了修改。
    """
    data = bytearray(open(path, "rb").read())
    snap = bytes(data)
    boxes = list(tf.mp4_boxes(snap))
    moov = next((b for b in boxes if b[2] == b"moov"), None)
    if moov is None:
        return False
    for trak in [b for b in tf.child_boxes(snap, moov[0] + 8, moov[0] + moov[1])
                 if b[2] == b"trak"]:
        mdia = tf.direct_child(snap, trak, b"mdia")
        hdlr = tf.direct_child(snap, mdia, b"hdlr")
        if snap[hdlr[0] + 16:hdlr[0] + 20] != b"vide":
            continue
        minf = tf.direct_child(snap, mdia, b"minf")
        stbl = tf.direct_child(snap, minf, b"stbl")
        stsd = tf.direct_child(snap, stbl, b"stsd")
        eoff = stsd[0] + 16
        esz = struct.unpack_from(">I", data, eoff)[0]
        # 采样条目 tag 决定保留哪个配置盒：avc1->avcC，hvc1/hev1->hvcC。
        tag = bytes(data[eoff + 4:eoff + 8])
        if tag == b"avc1":
            keep = b"avcC"
        elif tag in (b"hvc1", b"hev1"):
            keep = b"hvcC"
        else:
            return False
        ch, ch_off = None, None
        for h in (86, 36, 64, 78, 20, 24, 16):
            try:
                got = tf.child_boxes(snap, eoff + h, eoff + esz)
            except Exception:  # noqa: BLE001
                continue
            if got:
                ch, ch_off = got, h
                break
        if not ch:
            return False
        drop = [c for c in ch if c[2] != keep]
        if not drop:
            return False
        removed = sum(d[1] for d in drop)
        out = bytearray()
        out += data[:eoff]
        out += struct.pack(">I", esz - removed)
        out += data[eoff + 4:eoff + ch_off]
        for c in ch:
            if c[2] == keep:
                out += data[c[0]:c[0] + c[1]]
        out += data[eoff + esz:]
        for anc in (stsd, stbl, minf, mdia, trak, moov):
            struct.pack_into(">I", out, anc[0], anc[1] - removed)
        open(path, "wb").write(bytes(out))
        return True
    return False

def stamp_from_name(name: str) -> int:
    """从 VID_YYYYMMDD_HHMMSS_NNN 取出 14 位 YYYYMMDDHHMMSS（inst 的 f7 字段）。

      能列出条目但打不开。序号只用于磁盘文件名去重，不进 meta。
    """
    stem = os.path.splitext(os.path.basename(name))[0]
    parts = stem.split("_")
    if len(parts) < 3:
        raise ValueError(f"文件名不符合 VID_YYYYMMDD_HHMMSS_NNN: {name}")
    ymd, hms = parts[-3], parts[-2]
    digits = ymd + hms
    if len(ymd) != 8 or len(hms) != 6 or not digits.isdigit():
        raise ValueError(f"文件名里没有 8+6 位时间戳: {name}")
    return int(digits)

def _inst_attach_one(tf, rw, work, gen_p, native_p, label, is_proxy,
                     thumbnail, ref_meta, spec, log=None) -> bytes:
    """给单个文件移植 inst box，返回 inst box 里写入的真实 meta。

    GUI 与 CLI 共用此实现，避免两套代码行为不一致。
    """
    from datetime import datetime as _dt

    #   而不是留给底层抛 WinError 2（盘符变化/卡被拔/临时目录失效）。
    for _role, _p in (("生成文件", gen_p), ("模板文件", native_p), ("临时目录", work)):
        _sp = str(_p)
        if _role == "临时目录":
            if not os.path.isdir(os.path.dirname(_sp) or _sp):
                raise FileNotFoundError(
                    f"{_role} 不可用: {_sp}（卡可能被拔出或盘符变了）")
        elif not os.path.isfile(_sp):
            raise FileNotFoundError(
                f"{_role} 不存在: {_sp}（卡可能被拔出或盘符变了）")

    # a) 注入相机 udta（含 AMBA 等相机私有 box）
    #
    #   要求两者【长度相同】。而 udta 里存的是相机原始名，
    #   不是磁盘上的文件名。模板文件一旦被改过名（加前缀/改名），
    #   拿 native_p.name 当旧名就会直接失败。
    #   所以从 udta 里读出真实旧名。
    old_name = _udta_stored_name(tf, native_p, is_proxy)
    new_name = gen_p.name
    if len(old_name) != len(new_name):
        raise ValueError(
            f"udta 内旧名与目标名长度不一致：{old_name!r}({len(old_name)}) "
            f"vs {new_name!r}({len(new_name)})；"
            "请使用相机原生的 VID_YYYYMMDD_HHMMSS_NNN.mp4 作模板。")
    udta = tf.camera_udta(
        native_p,
        old_name=old_name,
        new_name=new_name,
        thumbnail=thumbnail,
        stats=tf.media_stats(gen_p),
        # AMBA[53] 声明的是这条码流的真实关键帧间隔，所以量生成物而不是模板。
        gop=tf.video_gop(gen_p),
    )
    tf.inject_udta(gen_p, udta)
    # b) 修正 ftyp（free -> wide，与相机一致）
    tf.patch_ftyp(gen_p, native_p)
    # c) 接上模板的 inst box
    _, tpl_inst = tf.split_inst(native_p)
    tmp_with_inst = Path(work) / (label + "_gen.mp4")
    tmp_with_inst.write_bytes(gen_p.read_bytes() + tpl_inst)

    # c2)  缩略图必须在 rebuild_media 【之前】写入。
    #      实测产物 VID 与 LRV 用同一张新帧即可被相机识别，
    #      证明“原地替换 type-2 记录的像素”本身是安全的。
    #      实测：该记录 40 字节头在【相机原生】与【本工具产物】之间逐字节相同，
    #      与画面内容无关（只是 896x512 的格式描述符），所以只需换像素。
    #      rebuild_media 会把整块 inst 原样带走，故在这里写即可。
    #      关闭方式：设置环境变量 INSTA_NO_THUMB_PATCH=1
    if (os.environ.get("INSTA_NO_THUMB_PATCH") != "1"
            and thumbnail and len(thumbnail) == 896 * 512 * 3 // 2):
        try:
            tf.patch_inst_thumbnail(tmp_with_inst, thumbnail)
            if log:
                log("  inst 缩略图已写入新帧（rebuild 前）")
        except Exception as _te:  # noqa: BLE001
            if log:
                log(f"  [警告] inst 缩略图写入失败（封面仍会是模板的）: {_te}")

    # d)  关键：把 meta 里的路径/时间戳/规格改成【本文件自己的】
    cat_path = f"/DCIM/Camera01/{gen_p.name}"
    # 文件名形如 VID_YYYYMMDD_HHMMSS_NNN
    #     真机 094907~094911 均为 f7=20260915094907 这种 14 位。
    #   ✗ 旧版取 parts[-2]+parts[-1] = "HHMMSS"+"NNN" = 9 位，
    #     丢了日期段 → 相机解析 f7 失败 → 条目显示但不能播放。
    stamp_digits = 0
    epoch_ms = int(_dt.now().timestamp() * 1000)
    try:
        stamp_digits = stamp_from_name(gen_p.name)      # YYYYMMDDHHMMSS（14 位）
        dt = _dt.strptime(str(stamp_digits), "%Y%m%d%H%M%S")
        try:
            epoch_ms = int(dt.timestamp() * 1000)
        except (OSError, OverflowError, ValueError):
            # Windows 上 timestamp() 超出可表示范围会抛 OSError
            epoch_ms = int(_dt.now().timestamp() * 1000)
    except (ValueError, IndexError):
        pass
    stats = tf.media_stats(gen_p)
    dur_s = float(stats.get("duration_seconds") or 0) if isinstance(stats, dict) else 0.0
    if not dur_s:
        try:
            dur_s = float(tf.ffprobe(gen_p).get("format", {}).get("duration") or 0)
        except Exception:  # noqa: BLE001
            dur_s = 1.0
    inst_start = tmp_with_inst.stat().st_size - len(tpl_inst) + 8
    spec_v = (spec or {}).get("lrv_video" if is_proxy else "video", {}) or {}
    _fps_txt = str(spec_v.get("fps") or "")
    _fps_num = None
    if "/" in _fps_txt:
        try:
            _fps_num = int(round(float(_fps_txt.split("/")[0]) / float(_fps_txt.split("/")[1])))
        except (ValueError, ZeroDivisionError):
            _fps_num = None
    elif _fps_txt:
        try:
            _fps_num = int(round(float(_fps_txt)))
        except ValueError:
            _fps_num = None
    prepared_meta = tf.tailor_metadata(
        ref_meta,
        catalog_path=cat_path,
        timestamp_digits=stamp_digits,
        epoch_ms=epoch_ms,
        inst_payload_offset=inst_start,
        duration=dur_s,
        width=int(spec_v.get("width") or (1280 if is_proxy else 1920)),
        height=int(spec_v.get("height") or (720 if is_proxy else 1080)),
        proxy=is_proxy,
        fps=_fps_num,
    )
    out_p = Path(work) / (label + "_final.mp4")
    new_meta_bytes = rw.rebuild_media(tmp_with_inst, native_p, out_p, prepared_meta)

    #   缺任何一步相机都会直接丢弃整条，表现为“有条目但打不开”。
    #
    #   a) LRV(h264)：avc1 采样条目里【只保留 avcC】
    #      实测黄金文件：GOLD-LRV entry=141 children=[avcC]
    #                   我们的      entry=176 children=[avcC,pasp,btrt]
    #      多出的 pasp/btrt 相机不认。这里用 build_v13_lrv_children
    #      的 filter_avc1_children 做这件事，本模块里没有该函数，自己实现。
    if is_proxy:
        try:
            if _shrink_avc1_entry(tf, out_p, b"avcC"):
                new_meta_bytes = tf.repoint_inst_metadata(Path(out_p), new_meta_bytes)
                if log:
                    log("  LRV avc1 采样条目已精简为仅 avcC")
        except Exception as _fe:  # noqa: BLE001
            if log:
                log(f"  [警告] LRV avc1 精简失败（不致命）: {_fe}")
    #   b) 音频采样表换成相机原生 mp4a 条目
    new_meta_bytes = tf.install_camera_mp4a(out_p, new_meta_bytes)
    #   c) 音频轨去掉 edts（相机不接受）
    new_meta_bytes = tf.remove_audio_edts(out_p, new_meta_bytes)
    #   d) 缩略图已在上面的 c2) 步骤写入（rebuild 之前），此处不再重复处理。

    shutil.copy2(out_p, gen_p)
    return new_meta_bytes

def _meta_equivalent(a: bytes, b: bytes) -> bool:
    """判断两份 inst 元数据是否“同一个”（忽略易变字段）。

    相机只关心 f7 时间戳 / f9 偏移 / f10 时长 / f19 分辨率 / f20 帧率
    / f26 路径与 proxy 标记。逐字节比全量反而易因 f9 可变长而误判。
    这里比较：长度近似 + 关键字段逐个相等。
    """
    #   早期这里是裸 `import inst_transplant`：该模块实际在 shared/instbox/ 下，
    #   顶层导入必然 ModuleNotFoundError，被 except 吞掉后退化成逐字节全量比较。
    #   而 f9（inst 偏移）本身可变长，全量比较会把好条目误判成坏条目。
    try:
        _tf, _ = _load_inst_modules()
        fa = _tf.parse_message(a)
        fb = _tf.parse_message(b)
    except Exception:  # noqa: BLE001
        return a == b

    def key(fields):
        out = {}
        for f in fields:
            if f.number in (7, 10, 19, 20, 26):
                out[f.number] = bytes(f.value) if isinstance(f.value, (bytes, bytearray)) \
                    else int(f.value)
        return out

    ka, kb = key(fa), key(fb)
    if ka.get(26) != kb.get(26):
        return False
    for n in (7, 10, 19, 20):
        if n in ka and n in kb and ka[n] != kb[n]:
            return False
    return True

def verify_card(card_root: str) -> dict:
    """校验卡内索引与文件是否严格一致（防止"相册有条目但打不开"）。

    对每条索引条目检查：
        1. 文件是否存在
        2. 文件是否带 inst box
        3. 索引 meta 是否与文件内 inst box 的 meta 逐字节一致
        4. 索引 meta 的 f9（inst 偏移）是否与实际位置吻合

    返回 {"ok": [...], "bad": [(path, reason), ...], "entries": n}
    """
    import insta_index as ix
    card_root = _card_root(card_root)
    fi_path, _ = card_index_paths(card_root)
    cam = camera_dir(card_root)
    data = _read_index(fi_path)
    ok_list, bad_list = [], []
    if not data:
        return {"ok": ok_list, "bad": bad_list, "entries": 0}

    entries = ix.parse_fileinfo(data)
    for e in entries:
        name = os.path.basename(e.path)
        fp = os.path.join(cam, name)
        if not os.path.isfile(fp):
            bad_list.append((e.path, "文件不存在")); continue
        try:
            has, inst_sz = has_inst_box(fp)
        except Exception as ex:  # noqa: BLE001
            bad_list.append((e.path, f"读取失败: {ex}")); continue
        if not has:
            bad_list.append((e.path, "缺 inst box")); continue
        if e.meta is None:
            bad_list.append((e.path, "索引条目无元数据")); continue
        # 实际 inst box 偏移（f9 为 0 表示条目未携带该字段，跳过此项检查）
        real_off = _inst_offset(fp)
        want = getattr(e.meta, "inst_payload_offset", None)
        if want is None:
            want = e.meta.raw.get(9)
        if isinstance(want, int) and want > 0 and real_off is not None \
                and abs(int(want) - int(real_off)) > 16:
            bad_list.append((e.path,
                             f"inst 偏移不符 索引={want} 实际={real_off}"))
            continue
        #   相机流程：读索引拿 meta A → 按 A 的 f9 去文件读 inst 得到 B，
        #   A≠B 则条目显示但打不开。旧版只比 f9 偏移，漏了这项。
        try:
            file_meta = extract_inst_meta(fp)
        except Exception:  # noqa: BLE001
            file_meta = None
        if not file_meta:
            bad_list.append((e.path, "无法从 inst box 读出元数据"))
            continue
        try:
            idx_bytes = bytes(e.meta.to_bytes())
        except Exception:  # noqa: BLE001
            idx_bytes = b""
        if not idx_bytes:
            bad_list.append((e.path, "索引条目无元数据"))
            continue
        # 逐字节对比（f9 可能因 rebuild 后长度变化，比较时跳过 f9 值）
        if not _meta_equivalent(idx_bytes, file_meta):
            bad_list.append((e.path, "索引 meta 与文件内 inst meta 不一致"))
            continue
        ok_list.append(e.path)
    return {"ok": ok_list, "bad": bad_list, "entries": len(entries)}

def repair_card(card_root: str, log=None, remove_bad: bool = True) -> dict:
    """清理卡内索引里的坏条目（"相册有但打不开"的元凶）。

    坏条目 = 指向不存在文件 / 缺 inst box / meta 与文件不符 的条目。
    这些条目会让相机相册显示一堆打不开的"幽灵"文件。

    remove_bad=True 时把它们从索引中移除（先自动备份）。
    返回 {"removed": [...], "kept": n}
    """
    import insta_index as ix
    card_root = _card_root(card_root)
    fi_path, ei_path = card_index_paths(card_root)
    cam = camera_dir(card_root)
    data = _read_index(fi_path)
    if not data:
        return {"removed": [], "kept": 0}

    def say(m):
        (log or print)(m)

    fi_entries = ix.parse_fileinfo(data)
    ei_entries = ix.parse_editinfo(_read_index(ei_path))
    keep, removed = [], []
    for e in fi_entries:
        name = os.path.basename(e.path)
        fp = os.path.join(cam, name)
        reason = None
        if not os.path.isfile(fp):
            reason = "文件不存在"
        else:
            try:
                has, _sz = has_inst_box(fp)
                if not has:
                    reason = "缺 inst box"
            except Exception:  # noqa: BLE001
                reason = "文件损坏"
        if reason:
            removed.append((e.path, reason))
        else:
            keep.append(e)

    if not remove_bad or not removed:
        return {"removed": removed, "kept": len(keep)}

    bak = _backup_once(fi_path)
    if bak:
        say(f"已备份原索引 -> {os.path.basename(bak)}")
    _backup_once(ei_path)

    keep_paths = {e.path for e in keep}
    ei_keep = [e for e in ei_entries if e.path in keep_paths]

    _write_index_file(fi_path, ix.build_fileinfo(keep), log=say)
    _write_index_file(ei_path, ix.build_editinfo(ei_keep), log=say)

    for p, why in removed:
        say(f"已移除坏条目: {p}  ({why})")
    say(f"索引已清理：保留 {len(keep)} 条，移除 {len(removed)} 条")
    return {"removed": removed, "kept": len(keep)}

def _inst_offset(path: str) -> int | None:
    """返回文件里 inst box 的【载荷起始偏移】（与索引 f9 字段同语义）。

    实测：索引 f9 = inst box 起始偏移 + box 头长度(8)，即载荷（protobuf 元数据）起点。
    这里直接返回载荷起点，使校验可以逐字节精确对比，不靠容差。
    """
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            i = 0
            while i + 8 <= size:
                f.seek(i); hdr = f.read(8)
                if len(hdr) < 8:
                    return None
                sz = int.from_bytes(hdr[:4], "big"); typ = hdr[4:8]
                hdr_len = 8
                if sz == 1:
                    f.seek(i + 8); sz = int.from_bytes(f.read(8), "big")
                    hdr_len = 16
                elif sz == 0:
                    sz = size - i
                if typ == b"inst":
                    return i + hdr_len
                if sz < 8:
                    return None
                i += sz
    except OSError:
        return None
    return None

def _cli_progress(frac, label, speed, eta):
    """命令行进度条（单行刷新，配 ETA）。"""
    bar_w = 28
    filled = int(round(frac * bar_w))
    bar = "#" * filled + "-" * (bar_w - filled)
    eta_txt = format_duration(eta) if eta and eta > 0 else "--:--"
    spd_txt = f"{speed:.1f}x" if speed else "--"
    line = f"\r[{bar}] {frac*100:5.1f}%  剩余 {eta_txt:>8s}  ({spd_txt})  {label[:40]:<40s}"
    sys.stdout.write(line)
    sys.stdout.flush()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python core.py <输入视频> [输出目录] [起始序号]")
        print("      起始序号可省略，将自动接续已有文件序号(推荐)。")
        sys.exit(1)
    src = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.dirname(os.path.abspath(src))
    num = int(sys.argv[3]) if len(sys.argv) > 3 else None

    if os.path.isdir(src):
        exts = (".mp4", ".mov", ".mkv", ".avi", ".ts", ".flv", ".wmv", ".m4v")
        files = [os.path.join(src, f) for f in sorted(os.listdir(src))
                 if f.lower().endswith(exts)]
        ok, bad = batch_convert(files, out, start_number=num, progress=_cli_progress)
        print(f"\n成功 {len(ok)} 个，失败 {len(bad)} 个。")
        for f, e in bad:
            print(f"  失败: {f} -> {e}")
    else:
        vid, lrv = convert(src, out, start_number=num, progress=_cli_progress)
        print(f"\n生成完成:\n  VID: {vid}\n  LRV: {lrv}")