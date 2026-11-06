package com.duofreedom.instaace.engine

import android.content.Context
import android.net.Uri
import android.provider.DocumentsContract
import android.provider.OpenableColumns
import androidx.documentfile.provider.DocumentFile
import java.io.File

/** 相机卡上导入所需的目录与文件视图。 */
data class CardLayout(
    val tree: Uri,
    val dcim: DocumentFile,
    val cam: DocumentFile,
    val fileInfo: DocumentFile?,
    val editInfo: DocumentFile?,
    val templateVid: DocumentFile,
    val templateLrv: DocumentFile
)

/**
 * SAF（存储访问框架）读写封装。
 *
 * 桌面端能直接 `open(path, "r+b")`，Android 必须通过 ContentResolver；
 * 这里统一处理“媒体文件拷贝 + 索引文件原地覆盖 + 精确文件名创建”。
 */
object SafeCard {

    fun open(ctx: Context, tree: Uri): CardLayout? {
        val root = DocumentFile.fromTreeUri(ctx, tree) ?: return null
        val dcim = root.findFile("DCIM") ?: return null
        if (!dcim.isDirectory) return null
        val cam = dcim.findFile("Camera01") ?: return null
        if (!cam.isDirectory) return null
        val pair = findTemplatePair(cam) ?: return null
        return CardLayout(
            tree = tree,
            dcim = dcim,
            cam = cam,
            fileInfo = dcim.findFile("fileinfo_list.list"),
            editInfo = dcim.findFile(".editinfo_list.list"),
            templateVid = pair.first,
            templateLrv = pair.second
        )
    }

    /** 找一对真机原片：VID_xxx.mp4 ↔ LRV_xxx.lrv。 */
    fun findTemplatePair(cam: DocumentFile): Pair<DocumentFile, DocumentFile>? {
        val vids = LinkedHashMap<String, DocumentFile>()
        val lrvs = LinkedHashMap<String, DocumentFile>()
        for (f in cam.listFiles()) {
            val n = f.name ?: continue
            val up = n.uppercase()
            val vi = up.indexOf("VID_")
            val li = up.indexOf("LRV_")
            if (up.endsWith(".MP4") && vi >= 0) {
                vids[n.substring(vi).lowercase()] = f
            } else if (up.endsWith(".LRV") && li >= 0) {
                lrvs[n.substring(li).lowercase()] = f
            }
        }
        // 取名字最大（通常也是最新）的一对，优先有对应 LRV 的 VID
        for (key in vids.keys.sortedDescending()) {
            val stem = key.removeSuffix(".mp4")
            val lk = "lrv_" + stem.removePrefix("vid_") + ".lrv"
            val lrv = lrvs[lk] ?: continue
            return vids[key]!! to lrv
        }
        return null
    }

    fun copyToLocal(ctx: Context, file: DocumentFile, dst: File): Boolean = try {
        dst.parentFile?.mkdirs()
        ctx.contentResolver.openInputStream(file.uri)?.use { input ->
            dst.outputStream().use { out -> input.copyTo(out, 1 shl 20) }
        }
        dst.exists() && dst.length() > 0
    } catch (_: Exception) {
        false
    }

    private fun mimeFor(name: String): String = when {
        name.lowercase().endsWith(".mp4") -> "video/mp4"
        else -> "application/octet-stream"
    }

    /**
     * 把本地文件写入 SAF 文档，已存在则覆盖，不存在则按精确文件名创建。
     * 返回写入后的字节数；失败返回 -1。
     */
    fun writeDocument(
        ctx: Context,
        parent: DocumentFile,
        displayName: String,
        src: File
    ): Long {
        val mime = mimeFor(displayName)
        val targetUri: Uri = parent.findFile(displayName)?.uri
            ?: DocumentsContract.createDocument(
                ctx.contentResolver, parent.uri, mime, displayName
            ) ?: return -1L

        return try {
            ctx.contentResolver.openOutputStream(targetUri, "wt")?.use { out ->
                src.inputStream().use { input -> input.copyTo(out, 1 shl 20) }
            } ?: return -1L
            readableSize(ctx, targetUri)
        } catch (_: Exception) {
            -1L
        }
    }

    /** 覆盖写索引文件（内容较小，直接写 byte[]）。 */
    fun writeSmallFile(
        ctx: Context,
        parent: DocumentFile,
        displayName: String,
        bytes: ByteArray
    ): Boolean {
        return try {
            val targetUri: Uri = parent.findFile(displayName)?.uri
                ?: DocumentsContract.createDocument(
                    ctx.contentResolver, parent.uri, mimeFor(displayName), displayName
                ) ?: return false
            ctx.contentResolver.openOutputStream(targetUri, "wt")?.use { it.write(bytes) }
                ?: return false
            true
        } catch (_: Exception) {
            false
        }
    }

    fun readableSize(ctx: Context, uri: Uri): Long = try {
        ctx.contentResolver.query(
            uri, arrayOf(OpenableColumns.SIZE), null, null, null
        )?.use { c -> if (c.moveToFirst() && !c.isNull(0)) c.getLong(0) else -1L }
            ?: -1L
    } catch (_: Exception) {
        -1L
    }
}

/**
 * 导入用的“卡镜像”：把模板对 + 索引复制到应用私有目录，
 * 让桌面端 Python 核心在普通目录上完整跑一遍，再把结果写回。
 */
class CardMirror(
    private val ctx: Context,
    private val card: CardLayout,
    private val jobDir: File
) {
    val root = File(jobDir, "card")
    val dcimDir = File(root, "DCIM")
    val camDir = File(dcimDir, "Camera01")

    fun build(): Boolean {
        camDir.mkdirs()
        dcimDir.mkdirs()
        card.fileInfo?.let { SafeCard.copyToLocal(ctx, it, File(dcimDir, "fileinfo_list.list")) }
        card.editInfo?.let { SafeCard.copyToLocal(ctx, it, File(dcimDir, ".editinfo_list.list")) }
        if (!SafeCard.copyToLocal(ctx, card.templateVid, File(camDir, card.templateVid.name!!))) {
            return false
        }
        if (!SafeCard.copyToLocal(ctx, card.templateLrv, File(camDir, card.templateLrv.name!!))) {
            return false
        }
        return true
    }

    /** 把新增媒体与更新后的索引写回真实相机卡。 */
    fun writeBack(mediaNames: List<String>): Pair<Boolean, String> {
        val errors = mutableListOf<String>()

        for (name in mediaNames) {
            val src = File(camDir, name)
            if (!src.isFile) continue
            val written = SafeCard.writeDocument(ctx, card.cam, name, src)
            if (written < 0) errors += "写入失败: $name"
        }

        for (idx in listOf("fileinfo_list.list", ".editinfo_list.list")) {
            val src = File(dcimDir, idx)
            if (!src.isFile) continue
            val bytes = src.readBytes()
            if (!SafeCard.writeSmallFile(ctx, card.dcim, idx, bytes)) {
                errors += "索引写入失败: $idx"
            }
        }
        return errors.isEmpty() to errors.joinToString("; ")
    }
}
