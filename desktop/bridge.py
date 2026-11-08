import os
import threading

from PySide6.QtCore import Property, QObject, Signal, Slot

import core

VIDEO_EXTS = (".mp4", ".mov", ".mkv", ".avi", ".ts", ".flv", ".wmv", ".m4v")


class Bridge(QObject):
    """QML 与转码核心之间的桥。耗时操作在后台线程，UI 只走信号。"""

    busyChanged = Signal()
    statusChanged = Signal()
    progressChanged = Signal()
    filesChanged = Signal()
    sampleChanged = Signal()
    errorChanged = Signal()
    ffmpegMissingChanged = Signal()
    ffmpegProgressChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._busy = False
        self._status = "就绪。添加视频后点击「开始转换」。"
        self._progress = 0.0
        self._eta = "剩余 --:--"
        self._files: list[str] = []
        self._sample = ""
        self._spec = None
        self._error = ""
        self._cancel = threading.Event()
        self._worker: threading.Thread | None = None
        self._ffmpeg_missing = False
        self._ffmpeg_downloading = False
        self._ffmpeg_progress = 0.0

    @Property(bool, notify=busyChanged)
    def busy(self) -> bool:
        return self._busy

    @Property(str, notify=statusChanged)
    def status(self) -> str:
        return self._status

    @Property(float, notify=progressChanged)
    def progress(self) -> float:
        return self._progress

    @Property(str, notify=progressChanged)
    def eta(self) -> str:
        return self._eta

    @Property("QVariantList", notify=filesChanged)
    def files(self):
        return list(self._files)

    @Property(str, notify=sampleChanged)
    def sample(self) -> str:
        return self._sample

    @Property(str, notify=errorChanged)
    def lastError(self) -> str:
        return self._error

    @Property(bool, notify=ffmpegMissingChanged)
    def ffmpegMissing(self) -> bool:
        return self._ffmpeg_missing

    @Property(bool, notify=ffmpegMissingChanged)
    def ffmpegDownloading(self) -> bool:
        return self._ffmpeg_downloading

    @Property(float, notify=ffmpegProgressChanged)
    def ffmpegProgress(self) -> float:
        return self._ffmpeg_progress

    def _set_status(self, text: str) -> None:
        self._status = str(text)
        self.statusChanged.emit()

    def _set_error(self, text: str) -> None:
        self._error = str(text)
        self.errorChanged.emit()

    @Slot(result=str)
    def ffmpegState(self) -> str:
        ok, msg = core.ffmpeg_available()
        self._ffmpeg_missing = not ok
        self.ffmpegMissingChanged.emit()
        return "ok" if ok else str(msg)

    @Slot()
    def downloadFfmpeg(self) -> None:
        if self._ffmpeg_downloading:
            return
        self._ffmpeg_downloading = True
        self._ffmpeg_progress = 0.0
        self.ffmpegMissingChanged.emit()
        self.ffmpegProgressChanged.emit()
        self._set_status("正在下载 ffmpeg，请稍候…")
        threading.Thread(target=self._download_ffmpeg, daemon=True).start()

    def _download_ffmpeg(self) -> None:
        def stage(frac, msg):
            self._ffmpeg_progress = max(0.0, min(1.0, float(frac or 0.0)))
            self.ffmpegProgressChanged.emit()
            self._set_status(str(msg or "下载中…"))
        try:
            ok, msg = core.download_and_install_ffmpeg(stage)
        except Exception as exc:
            ok, msg = False, str(exc)
        self._ffmpeg_downloading = False
        self._ffmpeg_progress = 1.0 if ok else 0.0
        self.ffmpegMissingChanged.emit()
        self.ffmpegProgressChanged.emit()
        if ok:
            self._ffmpeg_missing = False
            self.ffmpegMissingChanged.emit()
            self._set_status("ffmpeg 安装完成，可开始转换")
        else:
            self._set_error("ffmpeg 下载失败：%s" % msg)

    @Slot(str)
    def setStatusHint(self, text: str) -> None:
        self._set_status(text)

    @Slot(str)
    def setSample(self, path: str) -> None:
        self._set_error("")
        if not isinstance(path, str) or not os.path.isfile(path):
            self._set_error("样本文件不存在")
            return
        self._set_status("正在分析样本结构…")
        try:
            folder = os.path.dirname(path)
            stem = os.path.splitext(os.path.basename(path))[0]
            if stem.upper().startswith("LRV_"):
                main = os.path.join(folder, stem.replace("LRV_", "VID_", 1) + ".mp4")
                spec = core.analyze_native(main if os.path.isfile(main) else path)
                spec["lrv_video"] = core.analyze_native(path).get("video", {})
            else:
                spec = core.analyze_native(path)
                lrv = os.path.join(folder, stem.replace("VID_", "LRV_", 1) + ".lrv")
                if os.path.isfile(lrv):
                    try:
                        spec["lrv_video"] = core.analyze_native(lrv).get("video", {})
                    except Exception:
                        pass
        except Exception as exc:
            self._spec = None
            self._sample = ""
            self.sampleChanged.emit()
            self._set_error("样本分析失败：%s" % exc)
            return

        self._spec = spec
        self._sample = path
        self.sampleChanged.emit()
        video = spec.get("video", {}) or {}
        self._set_status("样本已读取：%sx%s @%s" % (
            video.get("width", "?"), video.get("height", "?"), video.get("fps", "?")))

    @Slot("QVariantList")
    def addFiles(self, paths) -> None:
        if self._busy:
            return
        added = 0
        for raw in paths or []:
            if not isinstance(raw, str):
                continue
            path = os.path.normpath(raw)
            if path in self._files or not os.path.isfile(path):
                continue
            if not path.lower().endswith(VIDEO_EXTS):
                continue
            self._files.append(path)
            added += 1
        if added:
            self.filesChanged.emit()
            self._set_status("已添加 %d 个视频，共 %d 个" % (added, len(self._files)))

    @Slot(str)
    def addFolder(self, folder: str) -> None:
        if self._busy:
            return
        if not isinstance(folder, str) or not os.path.isdir(folder):
            self._set_error("文件夹不存在")
            return
        try:
            names = sorted(os.listdir(folder))
        except OSError as exc:
            self._set_error("读取文件夹失败：%s" % exc)
            return
        self.addFiles([os.path.join(folder, n) for n in names if n.lower().endswith(VIDEO_EXTS)])

    @Slot()
    def clearFiles(self) -> None:
        if self._busy or not self._files:
            return
        self._files.clear()
        self.filesChanged.emit()
        self._set_status("列表已清空")

    @staticmethod
    def _encoder_tuple(label: str):
        text = (label or "").strip()
        if "AMD" in text:
            return ("hevc_amf", "h264_amf", "AMD")
        if "NVIDIA" in text:
            return ("hevc_nvenc", "h264_nvenc", "NVIDIA")
        if "Intel" in text:
            return ("hevc_qsv", "h264_qsv", "Intel")
        return ("", "", "software")

    @Slot(str, bool, bool, str)
    def start(self, output_dir: str, do_index: bool, auto_seq: bool, encoder_label: str) -> None:
        if self._busy:
            return
        self._set_error("")
        if not self._files:
            self._set_error("请先添加要转换的视频")
            return
        out = (output_dir or "").strip()
        if not out:
            self._set_error("请先选择输出目录")
            return
        try:
            os.makedirs(out, exist_ok=True)
        except OSError as exc:
            self._set_error("无法创建输出目录：%s" % exc)
            return
        if not os.access(out, os.W_OK):
            self._set_error("输出目录不可写：%s" % out)
            return
        ok, msg = core.ffmpeg_available()
        if not ok:
            self._set_error("ffmpeg 不可用：%s" % msg)
            return

        self._busy = True
        self._progress = 0.0
        self._eta = "剩余 --:--"
        self.busyChanged.emit()
        self.progressChanged.emit()
        self._cancel.clear()

        encoder = self._encoder_tuple(encoder_label)
        files = list(self._files)
        self._worker = threading.Thread(
            target=self._run,
            args=(files, out, bool(do_index), bool(auto_seq), encoder),
            daemon=True,
        )
        self._worker.start()

    @Slot()
    def cancel(self) -> None:
        if not self._busy:
            return
        self._cancel.set()
        self._set_status("正在取消…")

    def _run(self, files, out, do_index, auto_seq, encoder) -> None:
        ok_count = 0
        fail_count = 0
        #   auto_seq=True（默认）：交给 core 扫目录自动接续下一个序号；
        #   auto_seq=False：从 000 起编号，每成功一个文件 +1，
        #   避免旧文件把序号顶到高位（此前该开关收下后从未使用）。
        next_start = None if auto_seq else 0
        try:
            core.set_awake(True)
            card_ok = core.is_camera_card(out)
            use_inst = do_index and card_ok
            if do_index and not card_ok:
                # 用户勾了「登记索引」但输出目录不是相机卡结构：不阻断，
                # 只降级为纯转码，但要显式告知并写日志，避免用户以为
                # 已经登记成功（此前是静默降级）。
                core.append_log(
                    "[warn] 输出目录不是影石相机卡结构，跳过 inst 移植与索引登记：%s" % out)
                self._set_status("输出目录不是相机卡结构，改为仅转码")
            template = None
            if use_inst:
                try:
                    template = core.find_native_template(out)
                except Exception:
                    template = None
                if template is None:
                    use_inst = False
                    self._set_status("卡内未找到真机原片，改为仅转码")

            total = max(1, len(files))
            for index, src in enumerate(files):
                if self._cancel.is_set():
                    break
                name = os.path.basename(src)
                self._set_status("[%d/%d] %s" % (index + 1, total, name))

                def on_progress(frac, label, speed, eta, _i=index):
                    self._progress = min(1.0, (_i + float(frac or 0)) / total)
                    self._eta = "剩余 %s" % core.format_duration(eta) if eta and eta > 0 else "剩余 --:--"
                    self.progressChanged.emit()

                try:
                    if use_inst and template is not None:
                        result = core.import_with_inst(
                            src, out, template=template, encoder=encoder,
                            spec=self._spec, progress=on_progress,
                            cancel=self._cancel, log=self._set_status,
                            start_number=next_start,
                        )
                        if not result.get("inst_ok"):
                            raise RuntimeError(result.get("inst_error") or "inst 移植失败")
                    else:
                        core.convert(
                            src, out, encoder=encoder, spec=self._spec,
                            progress=on_progress, cancel=self._cancel,
                            log=self._set_status, start_number=next_start,
                        )
                    ok_count += 1
                    if next_start is not None:
                        next_start += 1
                except core.CanceledError:
                    break
                except Exception as exc:
                    fail_count += 1
                    self._set_status("[失败] %s：%s" % (name, exc))

            if self._cancel.is_set():
                self._set_status("已取消：成功 %d，失败 %d" % (ok_count, fail_count))
            elif fail_count:
                self._set_status("完成：成功 %d，失败 %d" % (ok_count, fail_count))
            else:
                self._progress = 1.0
                self._eta = "完成"
                self.progressChanged.emit()
                self._set_status("完成：成功 %d" % ok_count)
        except Exception as exc:
            self._set_error("转换异常：%s" % exc)
        finally:
            try:
                core.set_awake(False)
            except Exception:
                pass
            self._busy = False
            self.busyChanged.emit()
