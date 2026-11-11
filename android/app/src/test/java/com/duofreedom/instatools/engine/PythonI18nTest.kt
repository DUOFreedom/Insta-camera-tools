package com.duofreedom.instatools.engine

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Before
import org.junit.Test
import java.io.File
import java.util.concurrent.TimeUnit

/**
 * Python 侧文案的双语回归。
 *
 * 为什么要有这层测试：Kotlin 界面文案走 resources 切语言，但进度标签、
 * 自检说明、失败原因全是 Python 拼好再回传给界面的字符串。一旦漏译，
 * 英文界面里就会夹出「编码 VID」这类中文，而编译器、lint、aapt2 全都
 * 看不见——只有真跑一遍 Python 才能发现。
 *
 * 这里不打包 APK、不启动安卓，直接用主机的 Python 3.11 跑
 * `src/main/python` 下的真实模块（i18n / insta_core 只依赖标准库，
 * 能被独立 import），因此可以在 `gradle test` 里几分钟内跑完。
 * 没有解释器时用 Assume 跳过（与 IndexTest 的样本缺失处理一致），
 * 不让干净检出直接红掉。
 */
class PythonI18nTest {

    private val pythonDir = "src/main/python"

    /** 中日韩字符 + 全角标点：英文文案里出现任何一个都算漏译。 */
    private val cjk = Regex("[\\u3000-\\u303f\\u3400-\\u4dbf\\u4e00-\\u9fff\\uff00-\\uffef]")

    /**
     * 找解释器：优先用 Chaquopy 那个（构建命令本来就要配它），
     * 其次尝试 PATH 上的 python3/python。
     */
    private fun pythonBinary(): String? {
        val fromEnv = System.getenv("CHAQUOPY_PYTHON")
        if (!fromEnv.isNullOrBlank() && File(fromEnv).isFile) return fromEnv
        for (candidate in listOf("python3", "python")) {
            try {
                val p = ProcessBuilder(candidate, "-c", "print(1)")
                    .redirectErrorStream(true)
                    .start()
                p.inputStream.readBytes()
                if (p.waitFor(15, TimeUnit.SECONDS) && p.exitValue() == 0) return candidate
            } catch (_: Exception) {
                // 换下一个候选
            }
        }
        return null
    }

    @Before
    fun requirePython() {
        assumeTrue(
            "跳过：找不到 Python 3.11 解释器（设 CHAQUOPY_PYTHON 或把 python 加进 PATH）",
            pythonBinary() != null,
        )
    }

    /**
     * 跑一段脚本并返回 stdout。
     *
     * 为什么要落成临时文件而不是 `python -c`：Windows 上 CreateProcess 的
     * 参数引用规则会把脚本里的双引号吃掉，`re.compile(r"...")` 到达
     * Python 时已变成 `re.compile(r[...])`，直接 SyntaxError。
     * 写文件既躲开这层转义，也方便失败时人工复现。
     *
     * 工作目录是 app 模块目录（与 IndexTest 用相对样本路径的前提一致），
     * 所以脚本里可以直接 `sys.path.insert(0, "src/main/python")`。
     */
    private fun py(script: String): String {
        val file = File.createTempFile("insta_i18n_", ".py")
        try {
            file.writeText(script, Charsets.UTF_8)
            val pb = ProcessBuilder(pythonBinary()!!, file.absolutePath)
            pb.directory(File("").absoluteFile)
            pb.redirectErrorStream(true)
            pb.environment()["PYTHONIOENCODING"] = "utf-8"
            val process = pb.start()
            val out = process.inputStream.bufferedReader(Charsets.UTF_8).readText()
            assertTrue("python 脚本执行超时：\n$out", process.waitFor(120, TimeUnit.SECONDS))
            assertEquals("python 脚本非零退出：\n$out", 0, process.exitValue())
            return out
        } finally {
            file.delete()
        }
    }

    /** 英文文案表里不能有任何中文——否则不过是把中文搬了个地方。 */
    @Test
    fun englishTableHasNoChinese() {
        val out = py(
            """
            import re, sys
            sys.path.insert(0, "$pythonDir")
            import i18n
            cjk = re.compile(r"[\u3000-\u303f\u4e00-\u9fff\uff00-\uffef]")
            bad = sorted(k for k, v in i18n.EN_TEXT.items() if cjk.search(v))
            print("COUNT", len(i18n.EN_TEXT))
            print("BAD|" + "|".join(bad))
            """.trimIndent(),
        )
        val lines = out.trim().lines()
        val count = lines[0].removePrefix("COUNT").trim().toInt()
        assertTrue("英文文案表不该是空的（现在 $count 条）", count >= 15)
        val bad = lines[1].removePrefix("BAD|").trim()
        assertEquals("以下键的英文译文里还残留中文: $bad", "", bad)
    }

    /** 源码里每一处 `i18n.t("…")` 的字面量都必须能在表里查到（含多行拼接的首段）。 */
    @Test
    fun everyTranslatedLiteralHasEnglishText() {
        val out = py(
            """
            import pathlib, re, sys
            sys.path.insert(0, "$pythonDir")
            import i18n
            i18n.set_lang("en")
            keys = set()
            for name in ("android_bridge.py", "insta_core.py"):
                src = pathlib.Path("$pythonDir", name).read_text(encoding="utf-8")
                keys |= set(re.findall(r'i18n\.t\(\s*"([^"\\\n]+)"', src))
            def covered(k):
                # 多行消息在源码里被拆成多段字面量，正则只抓得到第一段，
                # 因此"是某个键的前缀"也算覆盖。
                return k in i18n.EN_TEXT or any(full.startswith(k) for full in i18n.EN_TEXT)
            missing = sorted(k for k in keys if not covered(k))
            print("COUNT", len(keys))
            print("MISSING|" + "|".join(missing))
            """.trimIndent(),
        )
        val lines = out.trim().lines()
        val count = lines[0].removePrefix("COUNT").trim().toInt()
        assertTrue("没扫到 i18n.t(...) 调用，测试失去意义（$count 处）", count >= 15)
        val missing = lines[1].removePrefix("MISSING|").trim()
        assertEquals("以下文案没有英文译文，英文界面会漏出中文: $missing", "", missing)
    }

    /**
     * 真跑一遍进度回调链路：`_stage_cb` 负责把「阶段名 · 条目名」拼成
     * 界面显示的进度文案，是 Python 产出用户可见文案最密集的地方。
     */
    @Test
    fun progressLabelsFollowLanguage() {
        val out = py(
            """
            import sys
            sys.path.insert(0, "$pythonDir")
            import i18n, insta_core
            def labels(lang):
                i18n.set_lang(lang)
                got = []
                cb = insta_core._stage_cb(lambda f, t, s, e: got.append(t), 0.0, 0.70, i18n.t("转码"))
                cb(0.5, i18n.t("VID (主视频)"), 1.0, 3)
                cb2 = insta_core._stage_cb(lambda f, t, s, e: got.append(t), 0.70, 0.94, i18n.t("移植 inst box"))
                cb2(0.0, i18n.t("LRV (低清预览)"), 0.0, 0)
                return got
            en = labels("en")
            i18n.set_lang("en")
            canceled = str(insta_core.CanceledError(i18n.t("已取消")))
            zh = labels("zh")
            print("EN|" + "|".join(en))
            print("ZH|" + "|".join(zh))
            print("CANCEL|" + canceled)
            """.trimIndent(),
        )
        val lines = out.trim().lines()
        val en = lines[0].removePrefix("EN|").split("|")
        val zh = lines[1].removePrefix("ZH|").split("|")
        val canceled = lines[2].removePrefix("CANCEL|")

        assertEquals("英文进度文案应有 2 条: $en", 2, en.size)
        en.forEach { assertFalse("英文进度文案里出现中文：$it", cjk.containsMatchIn(it)) }
        assertTrue("阶段名没翻译：${en[0]}", en[0].contains("Transcoding"))
        assertTrue("条目名没翻译：${en[0]}", en[0].contains("main video"))
        assertTrue("阶段名没翻译：${en[1]}", en[1].contains("inst box"))
        assertTrue("条目名没翻译：${en[1]}", en[1].contains("low-res preview"))
        // 中文用户那边必须还是中文（别把兜底英文兜反了）
        assertTrue("中文环境下进度文案应保持中文：$zh", zh.any { cjk.containsMatchIn(it) })
        assertEquals("取消文案没翻译", "Canceled", canceled.trim())
    }

    /**
     * 失败原因走的是**边界翻译**：异常在中途 raise 时还是中文原文，只是在
     * 写进 JSON / 组装 inst_error 时套一次 `i18n.t(str(e))`。那时字符串里
     * 参数早就填好了（`输入文件不存在: /x.mp4`），只能靠 `_templates()`
     * 把 `%s` 当通配符反查回中文模板。这条链路一旦断，界面上的失败明细
     * 就是一段中文——而这正是英文用户最需要看懂的地方。
     */
    @Test
    fun formattedErrorMessagesTranslate() {
        val out = py(
            """
            import re, sys
            sys.path.insert(0, "$pythonDir")
            import i18n
            CJK = re.compile(r"[\u3000-\u303f\u3400-\u4dbf\u4e00-\u9fff\uff00-\uffef]")
            # 这些是「已经填好参数」的中文正文，模拟 raise 现场拼出来的样子。
            SAMPLES = [
                "输入文件不存在: /sdcard/DCIM/Camera01/VID_20240101_120000_001.mp4",
                "输出目录不可写: /sdcard/DCIM/Camera01",
                "未在样文件中找到视频流",
                "ffprobe 读取失败: /card/VID_1.mp4",
                "ffmpeg 退出码非 0: Invalid data found when processing input",
                "VID_1.mp4 无音频流",
                "找不到 ffmpeg（已找: 环境变量 FFMPEG_PATH、/data/app/bin:/system/bin、PATH）；"
                "请把 ffmpeg 放到程序同目录的 bin 下。",
                "文件名不符合 VID_YYYYMMDD_HHMMSS_NNN: IMG_0001.mp4",
                "stbl 里既没有 stco 也没有 co64，文件结构异常",
                "MCRC box 长度异常: 12",
                "Camera01 缺少 VID_*.mp4 模板",
                "模板文件 不存在: /card/DCIM/Camera01/VID_1.mp4（卡可能被拔出或盘符变了）",
                "udta 内旧名与目标名长度不一致：'VID_20240101_120000_001.mp4'(19) vs "
                "'VID_20240102_130000_002.mp4'(18)；请使用相机原生的 VID_YYYYMMDD_HHMMSS_NNN.mp4 作模板。",
                "无法写入索引 camera01.index：权限被拒。\n"
                "    路径: /card/DCIM/Camera01/camera01.index\n"
                "    请确认：1) 卡的写保护开关没打开；"
                "2) 文件没被其他程序（相机软件/杀软）占用；"
                "3) 以管理员身份运行本程序。",
                "VID (主视频): 转码产物不存在",
            ]
            i18n.set_lang("en")
            bad = []
            for s in SAMPLES:
                got = i18n.t(s)
                if CJK.search(got) or got == s:
                    bad.append(s.replace("\n", "\\n") + "  =>  " + got.replace("\n", "\\n"))
            # 占位符数量必须与译文一致，否则 % formatting 会崩或吞参数
            mismatch = [k for k, v in i18n.EN_TEXT.items()
                        if len(re.findall(r"%[sd]", k)) != len(re.findall(r"%[sd]", v))]
            print("N", len(SAMPLES))
            print("BADCNT", len(bad))
            for item in bad:
                print("BADITEM|" + item)
            print("MISMATCH|" + "|".join(mismatch))
            """.trimIndent(),
        )
        val lines = out.trim().lines()
        val total = lines.first { it.startsWith("N ") }.removePrefix("N ").trim().toInt()
        val badCount = lines.first { it.startsWith("BADCNT ") }.removePrefix("BADCNT ").trim().toInt()
        val badItems = lines.filter { it.startsWith("BADITEM|") }
            .joinToString("\n") { it.removePrefix("BADITEM|") }
        val mismatch = lines.first { it.startsWith("MISMATCH|") }.removePrefix("MISMATCH|").trim()

        assertEquals("样本数不对，测试失去意义", 15, total)
        assertEquals("以下失败文案没翻成英文（界面会漏出中文）:\n$badItems", 0, badCount)
        assertEquals("以下键中英文占位符数量不一致: $mismatch", "", mismatch)
    }
}
