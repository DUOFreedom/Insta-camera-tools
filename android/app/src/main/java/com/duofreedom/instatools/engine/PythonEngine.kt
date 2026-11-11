package com.duofreedom.instatools.engine

import android.content.Context
import com.chaquo.python.PyObject
import com.duofreedom.instatools.R
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

    fun onProgress(frac: Double, text: String) {
        fraction = frac.toFloat().coerceIn(0f, 1f)
        if (text.isNotBlank()) label = text
    }

    fun onLog(line: String) {
        lastLog = line
    }
}

/**
 * Python 核心自检结果。
 *
 * why 拆成 ok + text：界面既要按成败配色/分支，又要把说明文字展示给用户。
 *   如果把两者混在一个字符串里，只能靠文案前缀判断成败——一翻译就失效。
 */
data class CoreStatus(val ok: Boolean, val text: String)

/**
 * 更新检查回调接口。
 */
interface UpdateCheckListener {
    fun onUpdateAvailable(tag: String, url: String)
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

    /**
     * 交给 Python 侧的语言标签（"zh" / "en"）。
     *
     * why 读资源配置而不是 `Locale.getDefault()`：Android 13+ 的「按应用语言」
     *   只改 Activity 的 resources 配置，进程默认 locale 仍是系统值；用户把本
     *   应用单独设成英文时，只有这里能拿到他实际看到的语言。
     */
    fun langTag(ctx: Context): String =
        if (ctx.resources.configuration.locales[0].language == "zh") "zh" else "en"

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
            // Python 侧文案（进度标签/自检说明/失败原因）按这里的语言出。
            //   进度回调 label、self_check 说明都是 Python 产出的字符串，
            //   不跟着 Kotlin 的资源走，必须显式告诉它。
            bridge.callAttr("set_lang", langTag(ctx))
            initialized = true
            true
        } catch (t: Throwable) {
            initError = "${t.javaClass.simpleName}: ${t.message}"
            false
        }
    }

    fun status(ctx: Context): CoreStatus {
        if (!requireInit(ctx)) {
            return CoreStatus(
                ok = false,
                text = ctx.getString(R.string.python_core_unavailable, initError)
            )
        }
        // 把真实异常暴露出来：真机上只显示「不可用」没法定位
        return try {
            val bridge = Python.getInstance().getModule("android_bridge")
            // 自检说明由 Python 拼接（含编码器名与版本号），语言要现取现传：
            //   进程存活着的时候用户可能切过语言，init 时设的那次已经过期了。
            bridge.callAttr("set_lang", langTag(ctx))
            val arr = bridge.callAttr("self_check")?.asList()
            val ok = arr?.getOrNull(0)?.toBoolean() ?: false
            val msg = arr?.getOrNull(1)?.toString().orEmpty()
            if (ok) CoreStatus(true, ctx.getString(R.string.python_core_ready, msg))
            else CoreStatus(false, ctx.getString(R.string.python_core_error, msg))
        } catch (t: Throwable) {
            CoreStatus(
                ok = false,
                text = ctx.getString(
                    R.string.python_self_check_failed,
                    "${t.javaClass.simpleName}: ${t.message}"
                )
            )
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
     *
     * cancel 由 [newCancelEvent] 创建；调用 [cancelEventSet] 置位后，
     * 正在跑的 ffmpeg 子进程会被 kill，本函数返回 canceled=true 的 JSON。
     */
    fun runImport(
        ctx: Context,
        source: File,
        mirrorRoot: File,
        callback: ImportCallback,
        preferHardware: Boolean = false,
        cancel: PyObject? = null,
        templateNames: Pair<String, String>? = null
    ): JSONObject {
        if (!requireInit(ctx)) {
            throw RuntimeException(ctx.getString(R.string.python_core_init_failed, initError))
        }
        val bridge = Python.getInstance().getModule("android_bridge")
        val raw = bridge.callAttr(
            "run_import",
            source.absolutePath,
            mirrorRoot.absolutePath,
            callback,
            null,                 // cover
            preferHardware,       // prefer_hardware
            cancel,               // cancel（threading.Event 或 None）
            // Chaquopy 把 Kotlin 数组转成 Python list；Python 侧按二元序列解包，
            //   不要求是 tuple。
            templateNames?.let { arrayOf(it.first, it.second) },  // template_names
            langTag(ctx)                                         // lang
        )?.toString() ?: throw RuntimeException(ctx.getString(R.string.python_no_result))
        return JSONObject(raw)
    }

    /** 创建一个取消事件（Python threading.Event），交给 runImport 使用。 */
    fun newCancelEvent(ctx: Context): PyObject? = try {
        if (!requireInit(ctx)) null
        else Python.getInstance().getModule("android_bridge").callAttr("new_cancel_event")
    } catch (_: Throwable) {
        null
    }

    /**
     * 置位取消事件。线程安全（Python Event.set 本身可跨线程调用）。
     * 返回 false 表示事件为空或置位失败——调用方应继续等待，不要假定已取消。
     */
    fun cancelEventSet(ev: PyObject?): Boolean {
        if (ev == null) return false
        return try {
            ev.callAttr("set")
            true
        } catch (_: Throwable) {
            false
        }
    }

    fun logTail(ctx: Context): String = try {
        if (!requireInit(ctx)) "" else {
            Python.getInstance().getModule("android_bridge")
                .callAttr("read_log_tail", 60)?.toString().orEmpty()
        }
    } catch (_: Throwable) {
        ""
    }

    /**
     * 启动后台更新检查（GitHub latest release）。
     * 有新版本时回调 listener.onUpdateAvailable(tag, url)。
     * 静默失败：网络超时、限流、JSON 异常等不抛异常、不打扰用户。
     */
    fun checkUpdate(ctx: Context, listener: UpdateCheckListener) {
        if (!requireInit(ctx)) return
        val bridge = Python.getInstance().getModule("android_bridge")
        // Python 侧会在后台线程跑完后回调 Kotlin 的 listener
        bridge.callAttr("check_update", UpdateCheckListenerWrapper(listener))
    }

    /** 将 Kotlin listener 包装成 Python 可调用的对象。 */
    private class UpdateCheckListenerWrapper(private val listener: UpdateCheckListener) {
        @Suppress("unused")
        fun onUpdate(tag: String, url: String) {
            listener.onUpdateAvailable(tag, url)
        }
    }

    /**
     * 忽略某版本（写入 Python 内存，进程重启失效；
     * 若需持久化由 Kotlin 落 SharedPreferences 再传回此处）。
     */
    fun ignoreUpdate(ctx: Context, tag: String) {
        if (!requireInit(ctx)) return
        val bridge = Python.getInstance().getModule("android_bridge")
        bridge.callAttr("ignore_update", tag)
    }
}
