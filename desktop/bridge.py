import os
import threading

from PySide6.QtCore import Property, QObject, QUrl, Signal, Slot

import core
import i18n

VIDEO_EXTS = (".mp4", ".mov", ".mkv", ".avi", ".ts", ".flv", ".wmv", ".m4v")
#   自动找样本时比「可选输入」多认几种：真机原片是 VID_*.mp4 + LRV_*.lrv，
#   有些机型还有 .insv/.ins。LRV 也在内是因为 setSample 支持从 LRV 反推 VID，
#   卡里只剩代理轨时还能用；但 VID 优先，见 autoDetectSample。
SAMPLE_EXTS = VIDEO_EXTS + (".lrv", ".insv", ".ins")


def _now() -> str:
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _tf(fmt: str, *args) -> str:
    """先翻译模板再套参数。

    文案表里的键是带 %s/%d 的原始模板，所以必须在格式化之前查表。先套参数
    再查表就永远查不到，英文界面会漏成中文。
    """
    text = i18n.t(fmt)
    return text % args if args else text


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
    coversChanged = Signal()
    verifyChanged = Signal()
    resumeChanged = Signal()
    locatedChanged = Signal()
    hwChanged = Signal()
    specChanged = Signal()
    seqChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._busy = False
        self._status = i18n.t("就绪。添加视频后点击「开始转换」。")
        self._progress = 0.0
        self._eta = i18n.t("剩余 --:--")
        self._files: list[str] = []
        self._sample = ""
        self._spec = None
        #   样本对的文件名：转码产物落在卡里之后，卡上会同时有真机原片和
        #   上一轮的产物，两者都带 inst box。让核心按字典序猜模板会挑错，
        #   所以把用户实际选中的这一对名字记下来，转码时按名字取模板。
        self._spec_pair: tuple[str, str] | None = None
        self._error = ""
        self._cancel = threading.Event()
        self._worker: threading.Thread | None = None
        self._ffmpeg_missing = False
        self._ffmpeg_downloading = False
        self._ffmpeg_progress = 0.0
        #   ffmpeg 是从哪儿来的：missing / env / system / portable。界面上
        #   要告诉用户「你系统里已经有」，不然他会以为自己没装。
        self._ffmpeg_source = "missing"
        #   本次安装的目标范围：global（系统目录，需管理员）/ portable。
        self._ffmpeg_scope = "portable"
        #   每个源视频一张封面图（键是 normpath）。加文件时按同名图自动配对，
        #   用户也可以手动指定；未指定时核心自己从视频第 10 秒取帧。
        self._covers: dict[str, str] = {}
        self._verify = ""
        self._verify_bad = 0
        self._verifying = False
        #   断点续跑：_resume_remain 是上次没跑完的源文件（绝对路径）。
        #   _resume_only 由界面上的勾选决定 —— 用户看到「上次还有 3 条没跑完」
        #   后可以选只跑这 3 条，也可以全部重跑。
        self._resume_remain: list[str] = []
        self._resume_done = 0
        self._resume_only = True
        self._located = ""
        self._hw = ""
        self._hw_checked = False
        self._seq_text = ""
        self._model_override = "auto"  # "auto" / "ace_pro_2" / "go_ultra"

    @Property(bool, notify=busyChanged)
    def busy(self) -> bool:
        return self._busy

    #   产品名与界面语言都只在启动时判定一次：系统界面语言不会在程序运行期间
    #   改变，做成可变属性只会让 QML 里出现一堆拿不到更新的绑定。
    @Property(str, constant=True)
    def appName(self) -> str:
        """英文 locale 是 instatools，中文 locale 是影石相机工具。"""
        return i18n.app_name()

    @Property(str, constant=True)
    def lang(self) -> str:
        return i18n.lang()

    @Slot(str, result=str)
    def tr(self, text: str) -> str:
        """QML 里的界面文案统一走这里。中文原样返回，英文查表。"""
        return i18n.t(text)

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

    @Property(str, notify=ffmpegMissingChanged)
    def ffmpegSource(self) -> str:
        return self._ffmpeg_source

    @Property(str, notify=ffmpegMissingChanged)
    def ffmpegScope(self) -> str:
        return self._ffmpeg_scope

    @Property("QVariantMap", notify=coversChanged)
    def covers(self):
        return dict(self._covers)

    @Property(str, notify=coversChanged)
    def coverImage(self) -> str:
        """给界面预览用的封面图地址；多条视频或未指定时为空。

        返回的是 file:// URL 而不是裸路径：QML 的 Image.source 只认 URL，
        直接给 `C:/a.jpg` 会解析成相对路径，加载状态是 Error 但没有任何
        报错，界面上就是一块空白（实测 Image.status == 2）。

        QML 侧别自己拼 `bridge.covers[bridge.files[0]]`：covers 的键是
        normpath，路径分隔符与大小写都和 files 里那份不一定逐字相同。
        """
        if len(self._files) != 1:
            return ""
        path = self._covers.get(os.path.normpath(self._files[0]))
        if not path:
            return ""
        return QUrl.fromLocalFile(path).toString()

    @Property(str, notify=coversChanged)
    def coverSummary(self) -> str:
        """给界面显示的一句话封面状态。"""
        if not self._files:
            return i18n.t("自动（源视频第 10 秒）")
        if len(self._files) > 1:
            n = sum(1 for f in self._files if os.path.normpath(f) in self._covers)
            return _tf("同名图自动配对（已配 %d/%d）", n, len(self._files))
        cur = self._covers.get(os.path.normpath(self._files[0]))
        if cur:
            return "%s → %s" % (os.path.basename(self._files[0]), os.path.basename(cur))
        return i18n.t("自动（源视频第 10 秒）")

    @Property(str, notify=verifyChanged)
    def verifyResult(self) -> str:
        return self._verify

    @Property(bool, notify=verifyChanged)
    def verifying(self) -> bool:
        return self._verifying

    @Property(bool, notify=verifyChanged)
    def verifyHasBad(self) -> bool:
        return self._verify_bad > 0

    @Property(str, notify=locatedChanged)
    def locatedDir(self) -> str:
        """最近一次「定位 SD 卡」找到的目录；界面把它灌进输出目录。"""
        return self._located

    @Property(str, notify=hwChanged)
    def hardwareEncoder(self) -> str:
        """探测到的硬件编码器名（"未检测到" / "NVIDIA" / …）。

        经典版启动后在后台探一次，把下拉框首项标注成「自动 (软件编码)」并
        提示可选哪个硬件加速。QML 版此前列表写死五项，用户不知道自己机器
        有没有硬件可用，选了也用不了。
        """
        return self._hw

    @Property(str, notify=specChanged)
    def specSummary(self) -> str:
        """样本结构摘要：主视频/预览的分辨率帧率编码、色域、音频轨数。

        经典版用 `_summarize_spec` 把它摊在界面上。没有它，用户只能看
        「样本已读取」四个字，分不清是解析成功还是拿到了一份空结构。
        """
        spec = self._spec
        if not spec:
            return ""
        v = spec.get("video", {}) or {}
        lv = spec.get("lrv_video", {}) or {}
        audio = spec.get("audio_tracks", []) or []
        lines = [_tf("主视频: %sx%s @%s %s lvl%s",
                     v.get("width", "?"), v.get("height", "?"), v.get("fps", "?"),
                     v.get("codec", "?"), v.get("level", "?"))]
        if lv:
            lines.append(_tf("预览: %sx%s @%s %s",
                             lv.get("width", "?"), lv.get("height", "?"),
                             lv.get("fps", "?"), lv.get("codec", "?")))
        lines.append(_tf("色域: %s",
                         "full-range(PC)" if v.get("color_range") == "pc"
                         else v.get("color_range", "?")))
        lines.append(_tf("音频 %d 轨", len(audio)))
        return chr(10).join(lines)

    @Property(str, notify=seqChanged)
    def nextSequence(self) -> str:
        """输出目录里下一个可用序号（「自动接续序号」开着时才有意义）。"""
        return self._seq_text

    @Property(str, notify=seqChanged)
    def modelOverride(self) -> str:
        """当前选择的机型预设："auto" / "ace_pro_2" / "go_ultra"。"""
        return self._model_override

    @Slot(str)
    def setModelOverride(self, value: str) -> None:
        val = str(value or "auto")
        if val not in ("auto", "ace_pro_2", "go_ultra"):
            self._set_error(i18n.t("未知机型预设: %s") % val)
            return
        if val == self._model_override:
            return
        self._model_override = val
        self.seqChanged.emit()  # 复用 seqChanged 通知

    @Property(bool, notify=resumeChanged)
    def resumeOnly(self) -> bool:
        return self._resume_only

    @Property(str, notify=resumeChanged)
    def resumeSummary(self) -> str:
        if not self._resume_remain:
            return ""
        return _tf("上次这个输出目录已完成 %d 条，还有 %d 条没跑完。",
                   self._resume_done, len(self._resume_remain))

    def _set_status(self, text: str) -> None:
        #   统一在这里过一遍文案表：核心层把 log 直接接到 _set_status 上，
        #   逐条改调用点容易漏，集中在出口拦截才是闭合的。
        self._status = i18n.t(str(text))
        self.statusChanged.emit()

    def _set_error(self, text: str) -> None:
        self._error = i18n.t(str(text))
        self.errorChanged.emit()

    @Slot(QUrl, result=str)
    def localPath(self, url: QUrl) -> str:
        """把 QML 的 file:// URL 还原成本地路径。

        不能用 selectedFile.toString().replace("file:///", "")：toString()
        会把 # % [ ] ^ ` { } 这些在 Windows 上合法的字符转成 %XX，
        替换完路径就不存在了；UNC 路径 file://server/share 只有两个斜杠，
        连前缀都剥不掉。toLocalFile() 两种情况都对。
        """
        return url.toLocalFile()

    @Slot(int, result=bool)
    def waitWorker(self, timeout_ms: int = 20000) -> bool:
        """等后台线程收尾（关窗前调用）。返回线程是否已退出。"""
        w = self._worker
        if w is None or not w.is_alive():
            return True
        w.join(timeout=max(0, int(timeout_ms)) / 1000.0)
        return not w.is_alive()

    @Slot()
    def checkFfmpeg(self) -> None:
        """启动时探一次 ffmpeg。经典版是启动就自动下载，QML 版此前连探都
        没探 —— ffmpeg 缺失时用户只会看到「ffmpeg 不可用：…」，界面上
        没有任何补救入口。"""
        ok, msg = core.ffmpeg_available()
        self._ffmpeg_missing = not ok
        self._ffmpeg_source = core.ffmpeg_source()
        self.ffmpegMissingChanged.emit()
        if not ok:
            self._set_status(
                "ffmpeg 未就绪：%s。可以装到系统目录（需管理员权限），"
                "也可以只装到程序目录。" % msg)
        elif self._ffmpeg_source == "system":
            self._set_status(i18n.t("已使用系统已安装的 ffmpeg：%s") % msg)

    @Slot(result=str)
    def ffmpegState(self) -> str:
        ok, msg = core.ffmpeg_available()
        self._ffmpeg_missing = not ok
        self._ffmpeg_source = core.ffmpeg_source()
        self.ffmpegMissingChanged.emit()
        if not ok:
            return str(msg)
        return "ok:%s" % self._ffmpeg_source

    @Slot()
    def downloadFfmpeg(self) -> None:
        """兼容旧入口：默认装到程序目录。"""
        self.installFfmpeg("portable")

    @Slot(str)
    def installFfmpeg(self, scope: str) -> None:
        """下载并安装 ffmpeg。scope 为 "global"（系统目录，需管理员）或
        "portable"（程序目录）。

        下载与安装分两步：先下到临时目录，再按 scope 落盘。这样选「装到系统」
        时 UAC 弹窗只覆盖最后那次复制，用户拒绝也不会白下 200 MB。
        """
        if self._ffmpeg_downloading:
            return
        target = "global" if str(scope or "").lower() == "global" else "portable"
        self._ffmpeg_downloading = True
        self._ffmpeg_scope = target
        self._ffmpeg_progress = 0.0
        self.ffmpegMissingChanged.emit()
        self.ffmpegProgressChanged.emit()
        self._set_status("正在下载 ffmpeg，请稍候…")
        threading.Thread(target=self._download_ffmpeg, args=(target,),
                         daemon=True).start()

    def _download_ffmpeg(self, scope: str = "portable") -> None:
        def stage(frac, msg):
            self._ffmpeg_progress = max(0.0, min(1.0, float(frac or 0.0)))
            self.ffmpegProgressChanged.emit()
            self._set_status(str(msg or "下载中…"))
        try:
            ok, msg = core.install_ffmpeg(scope, stage)
        except Exception as exc:  # noqa: BLE001
            ok, msg = False, str(exc)
        self._ffmpeg_downloading = False
        self._ffmpeg_progress = 1.0 if ok else 0.0
        self.ffmpegMissingChanged.emit()
        self.ffmpegProgressChanged.emit()
        if ok:
            self._ffmpeg_missing = False
            self._ffmpeg_source = core.ffmpeg_source()
            self.ffmpegMissingChanged.emit()
            #   刚装好 ffmpeg 时硬件探测还没跑过（启动那次因为找不到 ffmpeg
            #   直接返回「未检测到」）。不重探的话用户装了 ffmpeg 也看不到
            #   自己机器有硬件编码器，白等一个永远不出现的提示。
            self._hw_checked = False
            self.detectHardware()
            self._set_status("ffmpeg 安装完成，可开始转换")
        else:
            self._set_error(i18n.t("ffmpeg 安装失败：%s") % msg)

    @Slot()
    def clearError(self) -> None:
        """用户关掉错误提示后必须真的清掉。

        lastError 是粘性的：出错一次后，文件区会一直显示错误态，直到下一次
        点「开始转换」才被清 —— 中间用户改完路径、加好文件，界面还是红的。
        """
        self._set_error("")

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
            pair = None
            if stem.upper().startswith("LRV_"):
                main = os.path.join(folder, stem.replace("LRV_", "VID_", 1) + ".mp4")
                spec = core.analyze_native(main if os.path.isfile(main) else path)
                spec["lrv_video"] = core.analyze_native(path).get("video", {})
                if os.path.isfile(main):
                    pair = (os.path.basename(main), os.path.basename(path))
            else:
                spec = core.analyze_native(path)
                lrv = os.path.join(folder, stem.replace("VID_", "LRV_", 1) + ".lrv")
                if os.path.isfile(lrv):
                    try:
                        spec["lrv_video"] = core.analyze_native(lrv).get("video", {})
                    except Exception:
                        pass
                    pair = (os.path.basename(path), os.path.basename(lrv))
        except Exception as exc:
            self._spec = None
            self._spec_pair = None
            self._sample = ""
            self.sampleChanged.emit()
            self.specChanged.emit()
            self._set_error(i18n.t("样本分析失败：%s") % exc)
            return

        self._spec = spec
        self._spec_pair = pair
        self._sample = path
        self.sampleChanged.emit()
        #   specSummary 是另一个 Property，得单独通知；漏了这一行界面上
        #   「样本已读取」会亮而结构摘要一直是空的。
        self.specChanged.emit()
        video = spec.get("video", {}) or {}
        self._set_status(i18n.t("样本已读取：%sx%s @%s") % (
            video.get("width", "?"), video.get("height", "?"), video.get("fps", "?")))

    @Slot(str)
    def autoDetectSample(self, output_dir: str, sync_for_test: bool = False) -> None:
        """自动从输出目录（或常见 SD 卡 DCIM）里找一个原生录制视频当样本。

        经典版界面有「自动从存储卡分析」按钮，QML 版此前只弹一句「请手动
        选择」—— 这个退化被当成功能缺失写进了 README。现在补上：
        先看用户选的输出目录及其父目录，再扫 D 到 I 盘的 DCIM，
        找到第一个 VID_*/LRV_* 就交给 setSample 走正常分析流程。

        sync_for_test=True 时同步执行（仅供测试），否则后台线程跑，避免扫盘卡死 UI。
        """
        self._set_status("正在扫描存储卡…")
        if sync_for_test or self._running_in_test():
            self._auto_detect_worker(output_dir)
        else:
            threading.Thread(target=self._auto_detect_worker, args=(output_dir,), daemon=True).start()

    def _auto_detect_worker(self, output_dir: str) -> None:
        cands: list[str] = []
        out = (output_dir or "").strip()
        if out and os.path.isdir(out):
            cands.append(out)
            cands.append(os.path.dirname(out))
        for drive in "DEFGHIJ":
            root = "%s:\\" % drive
            if not os.path.isdir(root):
                continue
            for sub in ("DCIM", os.path.join("DCIM", "Camera01"),
                        os.path.join("DCIM", "100MEDIA")):
                cands.append(os.path.join(root, sub))

        seen: set[str] = set()
        for folder in cands:
            if folder in seen or not os.path.isdir(folder):
                continue
            seen.add(folder)
            try:
                names = sorted(os.listdir(folder))
            except OSError:
                continue
            #   同一对里 VID_ 是主轨、LRV_ 是代理轨。按字母序 LRV 排在前面，
            #   直接取第一个会把代理轨当样本 —— 它的分辨率/帧率/GOP 都与主轨
            #   不同，照它生成的规格是错的。所以 VID_ 优先，都没有才用 LRV_。
            for prefix in ("VID", "LRV"):
                for name in names:
                    upper = name.upper()
                    if not upper.startswith(prefix):
                        continue
                    #   upper 是大写，SAMPLE_EXTS 是小写 —— endswith 区分大小写，
                    #   直接比会一个都匹配不上（自动分析永远报「没找到」）。
                    if not upper.lower().endswith(SAMPLE_EXTS):
                        continue
                    path = os.path.join(folder, name)
                    self.setSample(path)
                    return
        # 未找到
        self._on_auto_detect_not_found()

    def _running_in_test(self) -> bool:
        """检测是否在测试环境（无 QApplication 实例）。"""
        try:
            from PySide6.QtWidgets import QApplication
            return QApplication.instance() is None
        except Exception:
            return True

    @Slot(str)
    def _on_auto_detect_found(self, path: str) -> None:
        self.setSample(path)

    @Slot()
    def _on_auto_detect_not_found(self) -> None:
        self._set_error(
            "未在存储卡中自动找到原生录制视频。请确认已插入存有原生录制视频的 "
            "SD 卡，再点「选择原生录制视频」手动指定。")

    @Slot(str)
    def checkResume(self, output_dir: str) -> None:
        """看看这个输出目录上次跑到哪了。界面在目录或文件列表变化时调用。"""
        out = (output_dir or "").strip()
        remain: list[str] = []
        done = 0
        if out and os.path.isdir(out) and self._files:
            try:
                job = core.load_job(out)
            except Exception:  # noqa: BLE001
                job = None
            if job:
                done_src = {os.path.normpath(str(it.get("src", "")))
                            for it in (job.get("items") or [])
                            if it.get("status") == "done"}
                cur = {os.path.normpath(f): f for f in self._files}
                #   只统计「这次列表里也有」的：换了一批文件时旧记录无意义。
                done = len(done_src & set(cur))
                remain = [cur[k] for k in cur if k not in done_src]
                if not (done and remain):
                    remain = []
        if remain == self._resume_remain and done == self._resume_done:
            return
        self._resume_remain = remain
        self._resume_done = done
        self.resumeChanged.emit()

    @Slot(bool)
    def setResumeOnly(self, value: bool) -> None:
        if bool(value) == self._resume_only:
            return
        self._resume_only = bool(value)
        self.resumeChanged.emit()

    @Slot(str)
    def pickCover(self, image_path: str) -> None:
        """给当前视频指定一张封面图。

        多视频时不猜「这张图配哪个视频」：猜错会让 A 视频用上 B 的封面，
        而且很难发现。同名图（a.mp4 + a.jpg）在添加时已经自动配对了。
        """
        self._set_error("")
        if not self._files:
            self._set_error("请先添加要转换的视频")
            return
        if not isinstance(image_path, str) or not os.path.isfile(image_path):
            self._set_error("封面图片不存在")
            return
        if not image_path.lower().endswith(core.SIDECAR_IMG_EXTS):
            self._set_error(i18n.t("封面只支持 %s") % " / ".join(core.SIDECAR_IMG_EXTS))
            return
        if len(self._files) != 1:
            self._set_error(
                "自选封面仅支持单个视频。多视频请把封面图命名成与视频同名，"
                "放在同一文件夹（a.mp4 + a.jpg），添加时会自动配对。")
            return
        self._covers[os.path.normpath(self._files[0])] = os.path.normpath(image_path)
        self.coversChanged.emit()
        self._set_status(i18n.t("封面已指定：%s → %s") % (
            os.path.basename(self._files[0]), os.path.basename(image_path)))

    @Slot()
    def clearCovers(self) -> None:
        """恢复自动：丢掉手动指定的，重新按同名图配对。"""
        self._covers.clear()
        for f in self._files:
            side = core.default_cover_for(f)
            if side:
                self._covers[os.path.normpath(f)] = side
        self.coversChanged.emit()
        self._set_status("封面已恢复自动")

    @Slot()
    def detectHardware(self) -> None:
        """后台探一次硬件编码器。探测本身要真编一次，几百毫秒起，不能卡 UI。"""
        if self._hw_checked:
            return
        self._hw_checked = True

        def run() -> None:
            try:
                ok, _ = core.ffmpeg_available()
                hw = core.detect_hw_encoder() if ok else None
            except Exception:  # noqa: BLE001
                hw = None
            if hw and len(hw) == 3:
                self._hw = str(hw[2])
            else:
                self._hw = i18n.t("未检测到")
            self.hwChanged.emit()

        threading.Thread(target=run, daemon=True).start()

    @Slot(str, bool)
    def refreshSequence(self, output_dir: str, auto_seq: bool) -> None:
        """更新「下一序号」提示。

        经典版在输出目录或开关变化时算一次，显示「自动续接，下一序号 003」。
        没有它，用户不知道这次会从几号开始，容易和卡里已有文件撞号。
        """
        out = (output_dir or "").strip()
        if not auto_seq:
            text = i18n.t("从 000 开始")
        elif out and os.path.isdir(out):
            try:
                text = _tf("自动续接，下一序号 %03d", core.next_seq(out))
            except Exception:  # noqa: BLE001
                text = i18n.t("自动")
        elif out:
            text = i18n.t("目录不存在")
        else:
            text = i18n.t("设置输出目录后显示下一序号")
        if text != self._seq_text:
            self._seq_text = text
            self.seqChanged.emit()

    @Slot()
    def locateCard(self) -> None:
        """自动定位存储卡并填进输出目录（经典版叫「定位 SD 卡」）。

        用户插上卡后要知道往哪写，自己翻资源管理器找 DCIM 很麻烦。
        """
        found = ""
        for drive in "DEFGHIJ":
            root = "%s:" % drive
            if not os.path.isdir(root + os.sep):
                continue
            for sub in (("DCIM", "Camera01"), ("DCIM", "100MEDIA"), ("DCIM",)):
                p = os.path.join(root + os.sep, *sub)
                if os.path.isdir(p):
                    found = p
                    break
            if found:
                break
        if not found:
            self._set_error("未在 D 到 I 盘找到 DCIM 目录，请手动选择输出目录")
            return
        self._located = found
        self.locatedChanged.emit()
        self._set_status(i18n.t("已定位到 %s") % found)

    @Slot(str)
    def verifyCard(self, card_root: str) -> None:
        """校验卡内索引与文件是否一致（后台线程，卡里几百条时要跑几秒）。"""
        if self._verifying:
            return
        root = (card_root or "").strip()
        if not root or not os.path.isdir(root):
            self._set_error("请先选择存储卡目录（DCIM 或 DCIM\\Camera01）")
            return
        self._verifying = True
        self._verify = i18n.t("正在校验索引…")
        self._verify_bad = 0
        self.verifyChanged.emit()
        threading.Thread(target=self._verify_worker, args=(root,), daemon=False).start()

    def _verify_worker(self, root: str) -> None:
        try:
            res = core.verify_card(root)
        except Exception as exc:  # noqa: BLE001
            self._verifying = False
            self._verify = _tf("校验失败：%s", exc)
            self._verify_bad = 0
            self.verifyChanged.emit()
            self._set_error(self._verify)
            return
        ok_list = res.get("ok") or []
        bad_list = res.get("bad") or []
        lines = [_tf("共 %d 条索引：正常 %d，异常 %d",
                     res.get("entries") or 0, len(ok_list), len(bad_list))]
        for path, why in bad_list[:15]:
            lines.append("  • %s — %s" % (os.path.basename(str(path)), why))
        if len(bad_list) > 15:
            lines.append(_tf("  … 另有 %d 条", len(bad_list) - 15))
        self._verify = "\n".join(lines)
        self._verify_bad = len(bad_list)
        self._verifying = False
        self.verifyChanged.emit()
        self._set_status(lines[0])
        try:
            core.append_log("[verify] %s\n%s" % (root, self._verify))
        except Exception:  # noqa: BLE001
            pass

    @Slot(str, result=str)
    def repairCard(self, card_root: str) -> str:
        """移除索引里的坏条目（相册有条目但打不开的元凶）。先自动备份。"""
        root = (card_root or "").strip()
        if not root or not os.path.isdir(root):
            self._set_error("请先选择存储卡目录")
            return ""
        try:
            res = core.repair_card(root, log=self._set_status)
        except Exception as exc:  # noqa: BLE001
            self._set_error(i18n.t("清理失败：%s") % exc)
            return ""
        msg = _tf("保留 %d 条，移除 %d 条。请重新插卡让相机刷新相册。",
                  res.get("kept") or 0, len(res.get("removed") or []))
        self._verify = msg
        self._verify_bad = 0
        self.verifyChanged.emit()
        self._set_status(msg)
        try:
            core.append_log("[repair] %s\n%s" % (root, msg))
        except Exception:  # noqa: BLE001
            pass
        return msg

    @Slot("QVariantList")
    def addPaths(self, paths) -> None:
        """拖拽入口：文件直接加，文件夹展开一层。

        QML 的 DropArea 给的是 url 列表，可能混着文件与文件夹。经典版
        `_paths_from_mime` 就是这么处理的；只收文件的话，用户把整个
        DCIM 文件夹拖进来会毫无反应。
        """
        files: list[str] = []
        for raw in paths or []:
            if not isinstance(raw, str):
                continue
            path = os.path.normpath(raw)
            if os.path.isdir(path):
                try:
                    names = sorted(os.listdir(path))
                except OSError:
                    continue
                files.extend(os.path.join(path, n) for n in names
                             if n.lower().endswith(VIDEO_EXTS))
            elif os.path.isfile(path) and path.lower().endswith(VIDEO_EXTS):
                #   扩展名要自己判：addFiles 会再过滤一遍，但那样「拖进一个
                #   txt」就变成静默无反应，连提示都没有。
                files.append(path)
        if not files:
            self._set_error("拖入的内容里没有可识别的视频文件")
            return
        before = len(self._files)
        self.addFiles(files)
        added = len(self._files) - before
        if added:
            self._set_status(i18n.t("已拖入 %d 个视频，共 %d 个") % (added, len(self._files)))

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
            #   同名 jpg/png 自动配对：相机原片旁边常放一张同名图作封面，
            #   以前只有经典版读它，QML 版一律走「视频第 10 秒」。
            side = core.default_cover_for(path)
            if side:
                self._covers[os.path.normpath(path)] = side
            added += 1
        if added:
            self.filesChanged.emit()
            self.coversChanged.emit()
            self._set_status(i18n.t("已添加 %d 个视频，共 %d 个") % (added, len(self._files)))

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
            self._set_error(i18n.t("读取文件夹失败：%s") % exc)
            return
        self.addFiles([os.path.join(folder, n) for n in names if n.lower().endswith(VIDEO_EXTS)])

    @Slot(str)
    def removeFile(self, path: str) -> None:
        """从列表里去掉一个视频。

        经典版有「移除选中」，QML 版只能「清空」—— 加错一个文件就得全删
        重加，批量拖几十个时很难受。
        """
        if self._busy:
            return
        key = os.path.normpath(str(path or ""))
        for i, f in enumerate(self._files):
            if os.path.normpath(f) == key:
                del self._files[i]
                self._covers.pop(key, None)
                self.filesChanged.emit()
                self.coversChanged.emit()
                self._set_status(i18n.t("已移除 %s，剩余 %d 个") % (
                    os.path.basename(f), len(self._files)))
                return
        self._set_error("列表里没有这个文件")

    @Slot()
    def clearFiles(self) -> None:
        if self._busy or not self._files:
            return
        self._files.clear()
        self._covers.clear()
        self.filesChanged.emit()
        self.coversChanged.emit()
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
            self._set_error(i18n.t("无法创建输出目录：%s") % exc)
            return
        if not os.access(out, os.W_OK):
            self._set_error(i18n.t("输出目录不可写：%s") % out)
            return
        ok, msg = core.ffmpeg_available()
        if not ok:
            self._set_error(i18n.t("ffmpeg 不可用：%s") % msg)
            return

        #   开工前体检：把「跑到最后才失败」的问题提前到 1 秒内。
        #   经典版界面在 start() 里做过这一步，QML 版此前完全跳过 ——
        #   选错目录、卡里没有真机原片、剩余空间不足，都要等转码跑完
        #   才在状态栏冒一行字，用户以为成功了。
        try:
            chk = core.preflight(out, self._files, do_index=bool(do_index),
                                 template_names=self._spec_pair)
        except Exception as exc:  # noqa: BLE001
            chk = {"blocking": [], "warnings": [], "preflightError": str(exc)}
        blocking = [str(x) for x in (chk.get("blocking") or [])]
        if blocking:
            self._set_error("开始前检查未通过：" + "；".join(blocking))
            return
        for warning in (chk.get("warnings") or []):
            core.append_log("[warn] %s" % warning)

        #   断点续跑：先看这个目录上次跑到哪了。用户勾了「只跑未完成」
        #   就跳过已完成的那几条 —— 重跑一条要几分钟，跳过是真省时间。
        self.checkResume(out)
        files = list(self._files)
        if self._resume_only and self._resume_remain:
            files = list(self._resume_remain)
            core.append_log("[resume] 只跑未完成的 %d 条（已完成 %d 条）" % (
                len(files), self._resume_done))

        self._busy = True
        self._progress = 0.0
        self._eta = i18n.t("剩余 --:--")
        self.busyChanged.emit()
        self.progressChanged.emit()
        self._cancel.clear()

        encoder = self._encoder_tuple(encoder_label)
        #   非 daemon：daemon 线程在进程退出时被直接丢弃，ffmpeg 会变成
        #   孤儿进程继续往卡里写，set_awake(False) 也不会执行。
        self._worker = threading.Thread(
            target=self._run,
            args=(files, out, bool(do_index), bool(auto_seq), encoder),
            daemon=False,
        )
        self._worker.start()

    @Slot()
    def cancel(self) -> None:
        if not self._busy:
            return
        self._cancel.set()
        self._set_status("正在取消…")

    @staticmethod
    def _job_item(job: dict, src: str) -> dict:
        """按源文件路径取 job 条目（合并后索引与 files 不再一一对应）。"""
        key = os.path.normpath(src)
        for it in job.get("items") or []:
            if os.path.normpath(str(it.get("src") or "")) == key:
                return it
        item = {"src": src, "status": "pending"}
        job.setdefault("items", []).append(item)
        return item

    def _run(self, files, out, do_index, auto_seq, encoder) -> None:
        ok_count = 0
        fail_count = 0
        #   续跑时 files 只是「未完成的那几条」，直接覆盖会把已完成记录
        #   抹掉 —— 再取消一次就全白跑了。所以先继承旧记录，再合并本次列表。
        try:
            old_job = core.load_job(out) or {}
        except Exception:  # noqa: BLE001
            old_job = {}
        merged: dict[str, dict] = {}
        for it in (old_job.get("items") or []):
            src = str(it.get("src") or "")
            if src:
                merged[os.path.normpath(src)] = dict(it)
        for f in files:
            key = os.path.normpath(f)
            merged[key] = {"src": f, "status": "pending"}
        job = {"dest": out, "updated": _now(), "items": list(merged.values())}
        #   本次只跑 files 里的这些，其余条目沿用旧状态（done/failed 不动）。

        def save_job() -> None:
            #   断点续跑靠这个文件。存不下来不影响本次转换，只是下次
            #   无法跳过已完成的 —— 提示一句就够，不该中断任务。
            try:
                core.save_job(out, job)
            except OSError as exc:
                self._set_status(i18n.t("断点续跑进度保存失败: %s") % exc)

        save_job()
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
                #   用户选过样本就按名字取，别让核心按字典序猜 —— 卡里可能
                #   躺着上一轮的产物，它们同样带 inst box，猜中产物的后果是
                #   moov 骨架/帧率/分辨率全来自产物，相机不认且不报错。
                try:
                    if self._spec_pair:
                        template = core.template_from_names(
                            out, self._spec_pair[0], self._spec_pair[1])
                    if template is None:
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
                self._set_status(i18n.t("[%d/%d] %s") % (index + 1, total, name))
                item_cover = self._covers.get(os.path.normpath(src))
                self._job_item(job, src)["status"] = "running"
                save_job()

                def on_progress(frac, label, speed, eta, _i=index):
                    self._progress = min(1.0, (_i + float(frac or 0)) / total)
                    self._eta = (i18n.t("剩余 %s") % core.format_duration(eta)
                                  if eta and eta > 0 else i18n.t("剩余 --:--"))
                    self.progressChanged.emit()

                try:
                    if use_inst and template is not None:
                        result = core.import_with_inst(
                            src, out, template=template, encoder=encoder,
                            spec=self._spec, progress=on_progress,
                            cancel=self._cancel, log=self._set_status,
                            start_number=next_start,
                            template_names=self._spec_pair,
                            cover=item_cover,
                            model_override=self._model_override,
                        )
                        if not result.get("inst_ok"):
                            raise RuntimeError(result.get("inst_error") or i18n.t("inst 移植失败"))
                    else:
                        core.convert(
                            src, out, encoder=encoder, spec=self._spec,
                            progress=on_progress, cancel=self._cancel,
                            log=self._set_status, start_number=next_start,
                            model_override=self._model_override,
                        )
                    ok_count += 1
                    _item = self._job_item(job, src)
                    _item["status"] = "done"
                    _item.pop("err", None)
                    if next_start is not None:
                        next_start += 1
                except core.CanceledError:
                    #   取消不是失败：保持 running，下次进来还要跑它。
                    break
                except Exception as exc:
                    fail_count += 1
                    _item = self._job_item(job, src)
                    _item["status"] = "failed"
                    _item["err"] = str(exc)
                    self._set_status(i18n.t("[失败] %s：%s") % (name, exc))
                job["updated"] = _now()
                save_job()

            if self._cancel.is_set():
                self._set_status(i18n.t("已取消：成功 %d，失败 %d") % (ok_count, fail_count))
            elif fail_count:
                self._set_status(i18n.t("完成：成功 %d，失败 %d") % (ok_count, fail_count))
            else:
                self._progress = 1.0
                self._eta = i18n.t("完成")
                self.progressChanged.emit()
                self._set_status(i18n.t("完成：成功 %d") % ok_count)
        except Exception as exc:
            self._set_error(i18n.t("转换异常：%s") % exc)
        finally:
            try:
                core.set_awake(False)
            except Exception:
                pass
            self._busy = False
            self.busyChanged.emit()
