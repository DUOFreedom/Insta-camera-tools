package com.duofreedom.instaace.engine

import android.content.Context
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import org.json.JSONObject
import java.io.File

/**
 * 回调给 Python 侧使用（Chaquopy 允许 Python 直接调用 Java 对象的方法）。
 * 方法签名要稳定：Python 传 float/str。
 */
class ImportCallback {
    @Volatile var fraction: Float = 0f
    @Volatile var label: String = ""
    @Volatile var lastLog: String = ""
    @Volatile var lastLogAt: Long = 0L

    fun onProgress(frac: Double, text: String) {
        fraction = frac.toFloat().coerceIn(0f, 1f)
        if (text.isNotBlank()) label = text
    }

    fun onLog(line: String) {
        lastLog = line
        lastLogAt = System.currentTimeMillis()
    }
}

/**
 * 嵌入式 CPython（Chaquopy）桥。
 *
 * 复用桌面端已经验证过的 `insta_core.py`（转码 + inst 移植 + 索引登记），
 * 避免在 Kotlin 里重写 2000+ 行二进制处理逻辑。
 */
object PythonEngine {

    @Volatile private var initialized = false
    @Volatile private var initError: String = ""
    @Volatile var coreVersion: String = ""

    private fun requireInit(ctx: Context): Boolean {
        if (initialized) return true
        if (initError.isNotBlank()) return false
        return try {
            if (!Python.isStarted()) {
                Python.start(AndroidPlatform(ctx.applicationContext))
            }
            val bridge = Python.getInstance().getModule("android_bridge")
            val ffmpeg = Engine.ffmpeg(ctx).absolutePath
            val ffprobe = Engine.ffprobe(ctx).absolutePath
            val cache = File(ctx.cacheDir, "python").apply { mkdirs() }
            coreVersion = bridge.callAttr("init", ffmpeg, ffprobe, cache.absolutePath)
                ?.toString().orEmpty()
            initialized = true
            true
        } catch (t: Throwable) {
            initError = "${t.javaClass.simpleName}: ${t.message}"
            false
        }
    }

    fun status(ctx: Context): String {
        if (!requireInit(ctx)) return "Python 核心不可用：$initError"
        // 把真实异常暴露出来：真机上只显示「不可用」没法定位
        return try {
            val bridge = Python.getInstance().getModule("android_bridge")
            val arr = bridge.callAttr("self_check")?.asList()
            val ok = arr?.getOrNull(0)?.toBoolean() ?: false
            val msg = arr?.getOrNull(1)?.toString().orEmpty()
            if (ok) "Python 核心就绪（$msg）" else "Python 核心异常：$msg"
        } catch (t: Throwable) {
            "Python 自检失败：${t.javaClass.simpleName}: ${t.message}"
        }
    }

    @Suppress("unused")
    private fun statusVerbose(ctx: Context): String {
        if (!requireInit(ctx)) return "init 失败：$initError"
        return try {
            val bridge = Python.getInstance().getModule("android_bridge")
            val arr = bridge.callAttr("self_check")?.asList()
            val ok = arr?.getOrNull(0)?.toBoolean() ?: false
            val msg = arr?.getOrNull(1)?.toString().orEmpty()
            if (ok) "Python 核心就绪（$msg）" else "Python 核心异常：$msg"
        } catch (t: Throwable) {
            "Python 自检失败：${t.message}"
        }
    }

    /** 诊断信息：把初始化异常与最近一次日志一起给出，便于真机排查。 */
    fun diagnostics(ctx: Context): String {
        val sb = StringBuilder()
        sb.append("initError=").append(initError.ifBlank { "(无)" }).append('\n')
        sb.append("coreVersion=").append(coreVersion.ifBlank { "(未初始化)" }).append('\n')
        sb.append("logTail=\n").append(logTail(ctx).takeLast(800))
        return sb.toString()
    }

    /**
     * 在镜像卡目录上执行完整导入。
     * 返回 Python 侧 JSON（ok / main / proxy / inst_ok / inst_error / index_error）。
     *
     * preferHardware = true 时走 MediaCodec 硬件编码（快），
     * 但其关键帧间隔受 MediaFormat 限制只能 1 秒，相机可能不识别；
     * false 时走 libx265/libx264 软件编码（与桌面端一致，最稳）。
     */
    fun runImport(
        ctx: Context,
        source: File,
        mirrorRoot: File,
        callback: ImportCallback,
        preferHardware: Boolean = false
    ): JSONObject {
        if (!requireInit(ctx)) {
            throw RuntimeException("Python 核心初始化失败：$initError")
        }
        val bridge = Python.getInstance().getModule("android_bridge")
        val raw = bridge.callAttr(
            "run_import",
            source.absolutePath,
            mirrorRoot.absolutePath,
            callback,
            null,                 // cover
            preferHardware        // prefer_hardware
        )?.toString() ?: throw RuntimeException("Python 未返回结果")
        return JSONObject(raw)
    }

    fun logTail(ctx: Context): String = try {
        if (!requireInit(ctx)) "" else {
            Python.getInstance().getModule("android_bridge")
                .callAttr("read_log_tail", 60)?.toString().orEmpty()
        }
    } catch (_: Throwable) {
        ""
    }
}
