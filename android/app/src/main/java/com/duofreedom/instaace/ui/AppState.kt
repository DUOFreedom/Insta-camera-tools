package com.duofreedom.instaace.ui

import android.content.Context
import android.net.Uri
import android.provider.OpenableColumns
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
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
import com.duofreedom.instaace.engine.ImportCallback
import com.duofreedom.instaace.engine.Index
import com.duofreedom.instaace.engine.Engine
import com.duofreedom.instaace.engine.PythonEngine
import com.duofreedom.instaace.engine.CardMirror
import com.duofreedom.instaace.engine.SafeCard
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
 * 界面状态、存储卡扫描与完整导入调度。
 *
 * 导入流程（与桌面端一致，只是把 CPU 侧交给内嵌的 CPython）：
 *   选定卡 → 建卡镜像（模板对 + 索引）→ 逐条：拷贝源文件 → 转码 → inst 移植 → 登记索引
 *   → 把新增媒体与更新后的索引写回卡 → 重新扫描确认。
 */
class AppState {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)

    /** 释放内部协程作用域。调用后不应再使用本实例。 */
    fun close() {
        scope.cancel()
    }

    var cardUri by mutableStateOf<Uri?>(null)
        private set
    var cardLabel by mutableStateOf("未选择存储卡")
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

    var encoder by mutableStateOf("自动")
    var registerIndex by mutableStateOf(true)

    var progress by mutableStateOf(0f)
    var stage by mutableStateOf("待开始")

    var running by mutableStateOf(false)
        private set
    var logLine by mutableStateOf("")
    var outputSummary by mutableStateOf("")
    val results = mutableStateListOf<ImportResult>()

    var pythonStatus by mutableStateOf("未检测")
        private set

    fun checkPython(ctx: Context) {
        pythonStatus = "检测中…"
        scope.launch {
            val status = withContext(Dispatchers.IO) { PythonEngine.status(ctx) }
            pythonStatus = status
        }
    }

    fun scanCard(ctx: Context, tree: Uri) {
        cardUri = tree
        scanning = true
        try {
            val root = DocumentFile.fromTreeUri(ctx, tree)
            cardLabel = root?.name?.takeIf { it.isNotBlank() }
                ?: tree.lastPathSegment ?: "存储卡"

            val dcim = root?.findFile("DCIM")
            dcimFound = dcim?.isDirectory == true

            val cam = dcim?.findFile("Camera01")
            camDirFound = cam?.isDirectory == true

            val files = cam?.listFiles() ?: emptyArray()
            vidCount = files.count { it.isFile && it.name?.startsWith("VID_") == true }
            lrvCount = files.count { it.isFile && it.name?.startsWith("LRV_") == true }

            val pair = cam?.let { SafeCard.findTemplatePair(it) }
            templateName = pair?.let { "${it.first.name} + ${it.second.name}" } ?: ""

            indexFound = dcim?.findFile("fileinfo_list.list") != null

            // 真正解析索引：条目数 + 空 meta 条目（相机把它们显示成 0KB 且打不开）
            indexCount = 0
            indexEmptyMeta = 0
            indexError = ""
            val idxFile = dcim?.findFile("fileinfo_list.list")
            if (idxFile != null) {
                try {
                    ctx.contentResolver.openInputStream(idxFile.uri)?.use { ins ->
                        val entries = Index.parseFileInfo(ins.readBytes())
                        indexCount = entries.size
                        indexEmptyMeta = entries.count { it.meta.isEmpty() }
                    }
                } catch (e: Exception) {
                    indexError = e.message ?: "索引读取失败"
                }
            }
        } catch (e: Exception) {
            cardLabel = "读取失败：${e.message}"
            dcimFound = false
            camDirFound = false
            indexFound = false
            vidCount = 0
            lrvCount = 0
            indexCount = 0
            indexEmptyMeta = 0
            templateName = ""
        } finally {
            scanning = false
        }
    }

    fun addVideos(ctx: Context, uris: List<Uri>) {
        uris.forEach { uri ->
            if (queue.any { it.uri == uri }) return@forEach
            var name = uri.lastPathSegment ?: "视频"
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
        stage = "待开始"
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
            stage = "队列为空"
            return
        }
        val tree = cardUri
        if (tree == null) {
            stage = "请先选择相机存储卡"
            return
        }
        if (!Engine.available(ctx)) {
            stage = "引擎不可用：找不到可执行的 libffmpeg.so"
            logLine = Engine.versionLine(ctx)
            return
        }

        running = true
        stage = "准备中…"
        progress = 0f
        results.clear()
        outputSummary = ""

        val jobDir = File(ctx.cacheDir, "job").apply { mkdirs() }
        val stageDir = File(ctx.cacheDir, "stage").apply { mkdirs() }
        val cb = ImportCallback()
        var ticker: Job? = null

        try {
            val card = withContext(Dispatchers.IO) {
                SafeCard.open(ctx, tree)
            } ?: throw RuntimeException("卡结构不完整：需要 DCIM/Camera01 与一对真机 VID_/LRV_ 原片")

            val pyStatus = withContext(Dispatchers.IO) { PythonEngine.status(ctx) }
            if (!pyStatus.startsWith("Python 核心就绪")) throw RuntimeException(pyStatus)

            stage = "准备卡镜像（模板 + 索引）…"
            val mirror = CardMirror(ctx, card, jobDir)
            val mirrorOk = withContext(Dispatchers.IO) { mirror.build() }
            if (!mirrorOk) throw RuntimeException("卡镜像构建失败：模板或索引拷贝不出来")

            val items = queue.toList()
            items.forEachIndexed { i, item ->
                val base = i.toFloat() / items.size
                stage = "第 ${i + 1}/${items.size} 条：读取源文件"
                progress = base

                val safeName = item.name.replace(Regex("[^A-Za-z0-9._-]"), "_")
                    .ifBlank { "input_$i.mp4" }
                val staged = File(stageDir, "${i}_$safeName")
                if (item.size > 0 && item.size * 3 > stageDir.usableSpace) {
                    throw RuntimeException(
                        "缓存空间不足：源 ${human(item.size)}，可用 ${human(stageDir.usableSpace)}"
                    )
                }
                val copied = withContext(Dispatchers.IO) {
                    ctx.contentResolver.openInputStream(item.uri)?.use { ins ->
                        staged.outputStream().use { out -> ins.copyTo(out, 1 shl 20) }
                        true
                    } ?: false
                }
                if (!copied) throw RuntimeException("无法读取：${item.name}")

                cb.fraction = 0f
                cb.label = "转码"
                // 进度轮询跑在 IO 协程里，每次写状态都切回主线程。
                val tick = scope.launch(Dispatchers.IO) {
                    while (isActive) {
                        val f = ((i + cb.fraction) / items.size).coerceIn(0f, 1f)
                        val lbl = cb.label
                        withContext(Dispatchers.Main) {
                            progress = f
                            if (lbl.isNotBlank()) stage = "第 ${i + 1}/${items.size} 条 · $lbl"
                        }
                        delay(250)
                    }
                }
                ticker = tick

                val json = try {
                    withContext(Dispatchers.IO) {
                        PythonEngine.runImport(
                            ctx, staged, mirror.root, cb,
                            preferHardware = (encoder == "硬件")
                        )
                    }
                } finally {
                    tick.cancel()
                    ticker = null
                    logLine = cb.lastLog
                    withContext(Dispatchers.IO) { staged.delete() }
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
                            if (errs.isEmpty()) "inst 已移植 · 索引已登记" else errs.joinToString(" / ")
                        } else json.optString("error")
                    )
                )
                progress = ((i + 1).toFloat() / items.size).coerceIn(0f, 1f)
            }

            stage = "写回相机卡…"
            val media = results.filter { it.ok }
                .flatMap { listOf(it.main, it.proxy) }
                .filter { it.isNotBlank() }
            val (writeOk, writeErr) = mirror.writeBack(media)
            outputSummary = results.joinToString("\n") {
                val mark = if (it.ok) "✓" else "✗"
                "$mark ${it.main.ifBlank { it.name }}  ${it.detail}"
            } + if (writeOk) "\n已写回相机卡（${media.size} 个文件 + 索引）"
            else "\n写回失败：$writeErr"

            stage = if (results.all { it.ok } && writeOk) "全部完成"
            else "部分完成（见下方明细）"
            progress = 1f

            scanCard(ctx, tree)
        } catch (t: Throwable) {
            stage = "失败：${t.message?.lineSequence()?.firstOrNull() ?: t.javaClass.simpleName}"
            logLine = t.message ?: t.toString()
        } finally {
            ticker?.cancel()
            stageDir.listFiles()?.forEach { it.delete() }
            running = false
        }
    }

    private fun human(bytes: Long): String = when {
        bytes <= 0 -> "未知"
        bytes >= 1L shl 30 -> "%.2f GB".format(bytes / 1073741824.0)
        bytes >= 1L shl 20 -> "%.1f MB".format(bytes / 1048576.0)
        bytes >= 1L shl 10 -> "%.0f KB".format(bytes / 1024.0)
        else -> "$bytes B"
    }
}
