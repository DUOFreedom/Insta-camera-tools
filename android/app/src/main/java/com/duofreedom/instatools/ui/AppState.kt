package com.duofreedom.instatools.ui

import android.content.Context
import android.net.Uri
import android.provider.OpenableColumns
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import androidx.compose.runtime.setValue
import androidx.documentfile.provider.DocumentFile
import com.chaquo.python.PyObject
import com.duofreedom.instatools.R
import com.duofreedom.instatools.engine.CoreStatus
import com.duofreedom.instatools.engine.ImportCallback
import com.duofreedom.instatools.engine.Index
import com.duofreedom.instatools.engine.Engine
import com.duofreedom.instatools.engine.PythonEngine
import com.duofreedom.instatools.engine.CardMirror
import com.duofreedom.instatools.engine.SafeCard
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/** 队列里的一条待转换视频。 */
data class QueueItem(
    val uri: Uri,
    val name: String,
    val size: Long
)

/** 单条导入结果（用于界面展示）。 */
data class ImportResult(
    val name: String,
    val ok: Boolean,
    val main: String,
    val proxy: String,
    val detail: String
)

/**
 * 导入阶段的语义分类。
 *
 * why 单独存在：界面需要按「成功 / 失败 / 已取消」做分支（卡片配色、
 *   Snackbar 文案、错误区是否出现）。一旦直接对本地化后的文案做前缀判断，
 *   切到英文就会命中不了——语言一变，分支就坏。因此文案只负责显示，
 *   判断一律看这个语言无关的枚举。
 */
enum class StageKind {
    /** 空闲：还没开始，或上一次导入已被清空。 */
    Idle,

    /** 导入进行中。 */
    Running,

    /** 已请求取消，正在等 Python 侧收尾。 */
    Canceling,

    /** 已取消。 */
    Canceled,

    /** 全部完成。 */
    Done,

    /** 部分完成（有失败条目）。 */
    Partial,

    /** 失败。 */
    Failed
}

/**
 * 界面状态、存储卡扫描与完整导入调度。
 *
 * 导入流程（与桌面端一致，只是把 CPU 侧交给内嵌的 CPython）：
 *   选定卡 → 建卡镜像（模板对 + 索引）→ 逐条：拷贝源文件 → 转码 → inst 移植 → 登记索引
 *   → 把新增媒体与更新后的索引写回卡 → 重新扫描确认。
 *
 * 文案：所有用户可见文字都从资源取（跟随系统语言），所以必须持有 Context。
 *   这里存的是 applicationContext：AppState 的生命周期由 Composable 的
 *   `remember` + `DisposableEffect` 管理，用应用级 Context 可以避免误持有
 *   Activity 造成泄漏，getString 的结果完全一样。
 */
class AppState(context: Context) {

    private val app: Context = context.applicationContext

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)

    /** 取一条本地化文案。占位符顺序与数量在 values/ 与 values-zh/ 中必须一致。 */
    private fun s(id: Int, vararg args: Any): String = app.getString(id, *args)

    companion object {
        /** 编码器选项的稳定标识：与显示文案解耦，切换语言不会改变判断结果。 */
        const val ENCODER_AUTO = "auto"
        const val ENCODER_HW = "hardware"

        /**
         * 机型预设的稳定标识，必须与 Python 侧 `CAMERA_PRESETS` 的键一致。
         *
         * auto      = 卡里有真机原片就按它量出参数（默认，与旧行为完全相同）
         * ace_pro_2 = 按 Ace Pro 2 的预设参数生成
         * go_ultra  = 按 GO Ultra 的预设参数生成
         */
        const val MODEL_AUTO = "auto"
        const val MODEL_ACE_PRO_2 = "ace_pro_2"
        const val MODEL_GO_ULTRA = "go_ultra"
    }

    /** 释放内部协程作用域。调用后不应再使用本实例。 */
    fun close() {
        scope.cancel()
    }

    var cardUri by mutableStateOf<Uri?>(null)
        private set
    var cardLabel by mutableStateOf(app.getString(R.string.card_none_selected))
    var scanning by mutableStateOf(false)
        private set

    var dcimFound by mutableStateOf(false)
        private set
    var camDirFound by mutableStateOf(false)
        private set
    var indexFound by mutableStateOf(false)
        private set
    var indexCount by mutableStateOf(0)
        private set
    var indexEmptyMeta by mutableStateOf(0)
        private set
    var indexError by mutableStateOf("")
        private set
    var vidCount by mutableStateOf(0)
        private set
    var lrvCount by mutableStateOf(0)
        private set
    var templateName by mutableStateOf("")
        private set

    /** 成对的原片数量：相机识别必须有至少一对真机 VID+LRV 作模板。 */
    val templatePairs: Int get() = minOf(vidCount, lrvCount)

    val queue = mutableStateListOf<QueueItem>()

    /** 编码器选择，取值 [ENCODER_AUTO] 或 [ENCODER_HW]。 */
    var encoder by mutableStateOf(ENCODER_AUTO)

    /**
     * 机型预设，取值 [MODEL_AUTO] / [MODEL_ACE_PRO_2] / [MODEL_GO_ULTRA]。
     *
     * 选 auto 时参数从卡里的真机原片量出来（与旧版本行为完全一致）；
     * 选定机型则改用该机型的预设参数，不看卡里有什么。
     * 注意：`.inst` 移植仍然需要一对真机原片当模板，这里只影响编码参数。
     */
    var modelOverride by mutableStateOf(MODEL_AUTO)

    var registerIndex by mutableStateOf(true)

    var progress by mutableStateOf(0f)

    /** 阶段文案（已按当前语言本地化，只用于显示）。 */
    var stage by mutableStateOf(app.getString(R.string.status_idle))
        private set

    /** [stage] 的语义分类：界面分支只看它，不看文案。 */
    var stageKind by mutableStateOf(StageKind.Idle)
        private set

    /** 失败详情（不含「失败：」前缀），失败态卡片展示用。 */
    var stageError by mutableStateOf("")
        private set

    /**
     * 同时更新阶段文案与语义分类，避免两者写漏一个。
     */
    private fun setStage(kind: StageKind, text: String, error: String = "") {
        stageKind = kind
        stage = text
        stageError = error
    }

    var running by mutableStateOf(false)
        private set
    var canceling by mutableStateOf(false)
        private set

    /** 本次导入的取消事件（Python threading.Event），导入结束即清空。 */
    @Volatile
    private var cancelEvent: PyObject? = null

    /** 已请求取消：队列循环据此停止派发下一条。 */
    @Volatile
    private var cancelRequested: Boolean = false

    /**
     * 请求取消当前导入。
     *
     * 前置条件：无（未在导入时调用是安全的空操作）。
     * 后置条件：正在跑的 ffmpeg 子进程被 kill；队列剩余条目不再开始；
     *   半成品不写回相机卡。
     * 不变量：本函数不阻塞——标志立即置上，真正去置位 Python Event 的
     *   动作丢到 IO 线程。Chaquopy 的 callAttr 要抢 GIL，而导入线程可能
     *   正卡在纯 Python 的 moov 重写循环里；在 UI 线程上直接等 GIL 会掉帧。
     */
    fun cancelImport() {
        // 先把标志置上：running 早于事件创建就已为 true，按钮在这一小段
        //   窗口里是可点的，此时 cancelEvent 还是 null。只置标志不置事件也
        //   足够——队列循环每条开始前都查它，第一条都还没派发就直接收尾。
        cancelRequested = true
        canceling = true
        setStage(StageKind.Canceling, s(R.string.action_canceling))
        val ev = cancelEvent ?: return
        scope.launch(Dispatchers.IO) {
            if (!PythonEngine.cancelEventSet(ev)) {
                // 置位失败（核心已回收等）：把 UI 从「正在取消」放开，
                //   否则用户会一直盯着一个不会变的按钮。
                withContext(Dispatchers.Main) {
                    canceling = false
                    cancelRequested = false
                    setStage(StageKind.Running, s(R.string.status_cancel_failed))
                }
            }
        }
    }
    var logLine by mutableStateOf("")
    var outputSummary by mutableStateOf("")
    val results = mutableStateListOf<ImportResult>()

    /** Python 核心自检结果；null 表示尚未检测。 */
    var pythonStatus by mutableStateOf<CoreStatus?>(null)
        private set

    fun checkPython(ctx: Context) {
        pythonStatus = CoreStatus(ok = false, text = s(R.string.status_detecting))
        scope.launch {
            val status = withContext(Dispatchers.IO) { PythonEngine.status(ctx) }
            pythonStatus = status
        }
    }

    /**
     * 扫描卡结构并解析索引。
     *
     * IO 部分必须离开主线程：`DocumentFile.fromTreeUri` / `listFiles()` 每次都要
     * 走 ContentResolver 往返，索引还要整块读进来解 protobuf。卡里几百个文件时
     * 这些调用足以触发 ANR，而且同步执行时 `scanning` 根本来不及渲染。
     * 结果回到调用线程再写状态——Compose 的状态只能在主线程改。
     */
    suspend fun scanCard(ctx: Context, tree: Uri) {
        scanning = true
        cardUri = tree
        try {
            val scan = withContext(Dispatchers.IO) { readCard(ctx, tree) }
            cardLabel = scan.label
            dcimFound = scan.dcim
            camDirFound = scan.cam
            vidCount = scan.vids
            lrvCount = scan.lrvs
            templateName = scan.template
            indexFound = scan.indexFound
            indexCount = scan.indexCount
            indexEmptyMeta = scan.indexEmptyMeta
            indexError = scan.indexError
        } finally {
            // 无论成功、失败还是被取消，都不能让界面一直停在「扫描中」。
            scanning = false
        }
    }

    private class CardScan(
        val label: String,
        val dcim: Boolean,
        val cam: Boolean,
        val vids: Int,
        val lrvs: Int,
        val template: String,
        val indexFound: Boolean,
        val indexCount: Int,
        val indexEmptyMeta: Int,
        val indexError: String
    )

    private fun readCard(ctx: Context, tree: Uri): CardScan {
        var label = tree.lastPathSegment ?: s(R.string.label_storage_card)
        var dcim = false
        var camOk = false
        var vids = 0
        var lrvs = 0
        var template = ""
        var indexFound = false
        var indexCount = 0
        var emptyMeta = 0
        var indexError = ""
        try {
            val root = DocumentFile.fromTreeUri(ctx, tree)
            label = root?.name?.takeIf { it.isNotBlank() } ?: label

            val dcimDir = root?.findFile("DCIM")
            dcim = dcimDir?.isDirectory == true

            val camDir = dcimDir?.findFile("Camera01")
            camOk = camDir?.isDirectory == true

            val files = camDir?.listFiles() ?: emptyArray()
            vids = files.count { it.isFile && it.name?.startsWith("VID_") == true }
            lrvs = files.count { it.isFile && it.name?.startsWith("LRV_") == true }

            val pair = camDir?.let { SafeCard.findTemplatePair(it) }
            template = pair?.let { "${it.first.name} + ${it.second.name}" } ?: ""

            val idxFile = dcimDir?.findFile("fileinfo_list.list")
            indexFound = idxFile != null
            if (idxFile != null) {
                try {
                    ctx.contentResolver.openInputStream(idxFile.uri)?.use { ins ->
                        val entries = Index.parseFileInfo(ins.readBytes())
                        indexCount = entries.size
                        // 空 meta 的条目在相机里显示成 0KB 且打不开，单独计数。
                        emptyMeta = entries.count { it.meta.isEmpty() }
                    }
                } catch (e: Exception) {
                    indexError = e.message ?: s(R.string.index_read_failed_short)
                }
            }
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            label = s(R.string.card_read_failed, e.message ?: "")
        }
        return CardScan(
            label = label,
            dcim = dcim,
            cam = camOk,
            vids = vids,
            lrvs = lrvs,
            template = template,
            indexFound = indexFound,
            indexCount = indexCount,
            indexEmptyMeta = emptyMeta,
            indexError = indexError
        )
    }

    fun addVideos(ctx: Context, uris: List<Uri>) {
        uris.forEach { uri ->
            if (queue.any { it.uri == uri }) return@forEach
            var name = uri.lastPathSegment ?: s(R.string.file_fallback_video_name)
            var size = 0L
            try {
                ctx.contentResolver.query(
                    uri,
                    arrayOf(OpenableColumns.DISPLAY_NAME, OpenableColumns.SIZE),
                    null, null, null
                )?.use { c ->
                    if (c.moveToFirst()) {
                        val ni = c.getColumnIndex(OpenableColumns.DISPLAY_NAME)
                        val si = c.getColumnIndex(OpenableColumns.SIZE)
                        if (ni >= 0) c.getString(ni)?.let { name = it }
                        if (si >= 0 && !c.isNull(si)) size = c.getLong(si)
                    }
                }
            } catch (_: Exception) {
                // 拿不到元数据不影响入队，界面退化为显示文件名
            }
            queue.add(QueueItem(uri, name, size))
        }
    }

    fun remove(item: QueueItem) {
        queue.remove(item)
    }

    fun clearQueue() {
        queue.clear()
        progress = 0f
        setStage(StageKind.Idle, s(R.string.status_idle))
        outputSummary = ""
        results.clear()
    }

    /**
     * 执行完整导入：转码 + inst 移植 + 索引登记 + 写回卡。
     */
    /**
     * 执行导入。
     *
     * 前置条件：queue 非空、cardUri 已授权、ffmpeg 可执行。
     * 后置条件：results 填入每条结果；running 复位为 false。
     * 不变量：本函数在主线程调度，所有 Compose 状态写入都在主线程；
     *   只有文件 IO / Python 调用被 withContext(Dispatchers.IO) 包裹。
     */
    suspend fun startImport(ctx: Context) {
        if (running) return
        if (queue.isEmpty()) {
            setStage(StageKind.Idle, s(R.string.status_queue_empty))
            return
        }
        val tree = cardUri
        if (tree == null) {
            setStage(StageKind.Idle, s(R.string.status_no_card))
            return
        }
        if (!Engine.available(ctx)) {
            setStage(StageKind.Idle, s(R.string.status_engine_unavailable))
            logLine = Engine.versionLine(ctx)
            return
        }

        running = true
        canceling = false
        cancelRequested = false
        setStage(StageKind.Running, s(R.string.status_preparing))
        progress = 0f
        results.clear()
        outputSummary = ""

        // 机型与编码器在开跑时定下来：跑的过程中改设置不该让后半批换参数。
        val model = modelOverride
        val hw = encoder == ENCODER_HW

        val jobDir = File(ctx.cacheDir, "job").apply { mkdirs() }
        val stageDir = File(ctx.cacheDir, "stage").apply { mkdirs() }
        val cb = ImportCallback()
        var ticker: Job? = null

        try {
            // 取消事件必须早于任何耗时操作创建，否则用户在「准备卡镜像」
            //   阶段点取消会没有东西可置位，按钮看起来失灵。
            val ev = withContext(Dispatchers.IO) { PythonEngine.newCancelEvent(ctx) }
            if (ev == null) throw RuntimeException(s(R.string.error_no_cancel_event))
            cancelEvent = ev

            val card = withContext(Dispatchers.IO) {
                SafeCard.open(ctx, tree)
            } ?: throw RuntimeException(s(R.string.error_card_incomplete))

            val pyStatus = withContext(Dispatchers.IO) { PythonEngine.status(ctx) }
            if (!pyStatus.ok) throw RuntimeException(pyStatus.text)

            setStage(StageKind.Running, s(R.string.status_preparing_mirror))
            val mirror = CardMirror(ctx, card, jobDir)
            val mirrorOk = withContext(Dispatchers.IO) { mirror.build() }
            if (!mirrorOk) throw RuntimeException(s(R.string.error_mirror_failed))

            val items = queue.toList()
            for (i in items.indices) {
                val item = items[i]
                // 取消后不再开始下一条：否则用户点了取消，剩下的每一条
                //   仍要转码几分钟，取消等于没生效。
                if (cancelRequested) break

                val base = i.toFloat() / items.size
                setStage(
                    StageKind.Running,
                    s(R.string.status_item_read, i + 1, items.size)
                )
                progress = base

                val safeName = item.name.replace(Regex("[^A-Za-z0-9._-]"), "_")
                    .ifBlank { "input_$i.mp4" }
                val staged = File(stageDir, "${i}_$safeName")
                if (item.size > 0 && item.size * 3 > stageDir.usableSpace) {
                    throw RuntimeException(
                        s(
                            R.string.error_cache_space,
                            human(item.size),
                            human(stageDir.usableSpace)
                        )
                    )
                }
                val copied = withContext(Dispatchers.IO) {
                    ctx.contentResolver.openInputStream(item.uri)?.use { ins ->
                        staged.outputStream().use { out -> ins.copyTo(out, 1 shl 20) }
                        true
                    } ?: false
                }
                if (!copied) throw RuntimeException(s(R.string.error_cannot_read, item.name))

                cb.fraction = 0f
                cb.label = s(R.string.stage_label_transcode)
                // 进度轮询跑在 IO 协程里，每次写状态都切回主线程。
                val tick = scope.launch(Dispatchers.IO) {
                    while (isActive) {
                        val f = ((i + cb.fraction) / items.size).coerceIn(0f, 1f)
                        val lbl = cb.label
                        withContext(Dispatchers.Main) {
                            progress = f
                            // 取消中不要用进度文字盖掉「正在取消…」：
                            //   否则点完取消 250ms 后又变回「第 1/2 条 · 转码」，
                            //   看起来像按钮没生效。
                            if (lbl.isNotBlank() && !canceling) {
                                setStage(
                                    StageKind.Running,
                                    s(R.string.status_item_stage, i + 1, items.size, lbl)
                                )
                            }
                        }
                        delay(250)
                    }
                }
                ticker = tick

                val json = try {
                    withContext(Dispatchers.IO) {
                        PythonEngine.runImport(
                            ctx, staged, mirror.root, cb,
                            preferHardware = hw,
                            cancel = cancelEvent,
                            // 明确告诉核心用哪一对文件当模板。镜像目录里除了
                            //   刚拷进来的真机原片，还可能躺着上一轮的产物，
                            //   而它们同样带 inst box —— 让核心自己按字典序猜
                            //   会选中错的，产出的东西相机不认且不报错。
                            templateNames = card.templateVid.name?.let { vid ->
                                card.templateLrv.name?.let { lrv -> vid to lrv }
                            },
                            modelOverride = model
                        )
                    }
                } finally {
                    tick.cancel()
                    ticker = null
                    logLine = cb.lastLog
                    withContext(Dispatchers.IO) { staged.delete() }
                }

                if (json.optBoolean("canceled")) {
                    // 这一条被中断，没有完整产物：不记入 results，直接收尾。
                    cancelRequested = true
                    break
                }

                val ok = json.optBoolean("ok")
                results.add(
                    ImportResult(
                        name = item.name,
                        ok = ok && json.optBoolean("inst_ok"),
                        main = json.optString("main"),
                        proxy = json.optString("proxy"),
                        detail = if (ok) {
                            val errs = listOfNotNull(
                                json.optString("inst_error").takeIf { it.isNotBlank() },
                                json.optString("index_error").takeIf { it.isNotBlank() }
                            )
                            if (errs.isEmpty()) s(R.string.result_inst_ok)
                            else errs.joinToString(" / ")
                        } else json.optString("error")
                    )
                )
                progress = ((i + 1).toFloat() / items.size).coerceIn(0f, 1f)
            }

            val canceled = cancelRequested
            // 已经转换并登记好的条目是完整产物，取消不该把它们一起丢掉；
            //   正在转的那条只留在镜像里（jobDir），不会写回卡。
            val media = results.filter { it.ok }
                .flatMap { listOf(it.main, it.proxy) }
                .filter { it.isNotBlank() }

            val (writeOk, writeErr) = if (media.isEmpty()) {
                true to ""
            } else {
                setStage(
                    StageKind.Running,
                    if (canceled) s(R.string.status_canceled_writeback)
                    else s(R.string.status_writeback)
                )
                withContext(Dispatchers.IO) { mirror.writeBack(media) }
            }

            outputSummary = results.joinToString("\n") {
                val mark = if (it.ok) "✓" else "✗"
                "$mark ${it.main.ifBlank { it.name }}  ${it.detail}"
            } + when {
                !writeOk -> "\n" + s(R.string.summary_writeback_failed, writeErr)
                media.isEmpty() ->
                    if (canceled) "\n" + s(R.string.summary_canceled_nothing) else ""
                else -> "\n" + s(R.string.summary_written, media.size)
            }

            when {
                canceled && media.isEmpty() ->
                    setStage(StageKind.Canceled, s(R.string.status_canceled))
                canceled -> setStage(
                    StageKind.Canceled,
                    s(R.string.status_canceled_partial, results.count { it.ok })
                )
                results.all { it.ok } && writeOk ->
                    setStage(StageKind.Done, s(R.string.status_all_done))
                else -> setStage(StageKind.Partial, s(R.string.status_partial))
            }
            if (!canceled) progress = 1f

            scanCard(ctx, tree)
        } catch (t: Throwable) {
            val detail = t.message?.lineSequence()?.firstOrNull() ?: t.javaClass.simpleName
            setStage(StageKind.Failed, s(R.string.status_failed, detail), detail)
            logLine = t.message ?: t.toString()
        } finally {
            ticker?.cancel()
            stageDir.listFiles()?.forEach { it.delete() }
            cancelEvent = null
            cancelRequested = false
            canceling = false
            running = false
        }
    }

    private fun human(bytes: Long): String = when {
        bytes <= 0 -> s(R.string.size_unknown)
        bytes >= 1L shl 30 -> "%.2f GB".format(bytes / 1073741824.0)
        bytes >= 1L shl 20 -> "%.1f MB".format(bytes / 1048576.0)
        bytes >= 1L shl 10 -> "%.0f KB".format(bytes / 1024.0)
        else -> "$bytes B"
    }
}
