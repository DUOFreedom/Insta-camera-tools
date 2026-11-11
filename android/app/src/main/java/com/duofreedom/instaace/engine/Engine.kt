package com.duofreedom.instatools.engine

import android.content.Context
import java.io.File

/**
 * 随包携带的 ffmpeg / ffprobe 引擎。
 *
 * why: Android 10+ 禁止从应用数据目录执行二进制，但允许从
 * `nativeLibraryDir`（安装时由系统解压并 chmod +x 的 lib 目录）执行。
 * 因此把它们以 `libffmpeg.so` / `libffprobe.so` 命名放进 jniLibs，
 * 运行时按该路径调用；manifest 侧配合 `useLegacyPackaging = true` 保证解压。
 */
object Engine {

    fun ffmpeg(ctx: Context): File = File(ctx.applicationInfo.nativeLibraryDir, "libffmpeg.so")

    fun ffprobe(ctx: Context): File = File(ctx.applicationInfo.nativeLibraryDir, "libffprobe.so")

    fun available(ctx: Context): Boolean = ffmpeg(ctx).canExecute()

    /** 跑一次 `-version`，返回首行；失败返回错误描述。 */
    fun versionLine(ctx: Context): String {
        val bin = ffmpeg(ctx)
        if (!bin.exists()) return "引擎缺失：${bin.name}"
        return try {
            val p = ProcessBuilder(bin.absolutePath, "-version")
                .redirectErrorStream(true)
                .start()
            val out = p.inputStream.bufferedReader().readText()
            p.waitFor()
            out.lineSequence().firstOrNull { it.startsWith("ffmpeg version") }
                ?: out.lineSequence().firstOrNull().orEmpty().ifBlank { "无输出" }
        } catch (e: Exception) {
            "启动失败：${e.javaClass.simpleName} ${e.message ?: ""}"
        }
    }
}
