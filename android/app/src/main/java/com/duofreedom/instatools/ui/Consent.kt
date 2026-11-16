package com.duofreedom.instatools.ui

import android.content.Context
import java.io.File

/**
 * 协议同意状态。
 *
 * why: 首次启动必须强制用户阅读并同意《使用协议与隐私政策》才能使用，
 *   这是合规要求，也是自我保护（避免用户误以为「装上就能随便改卡」）。
 *
 * 存储位置：应用私有目录 `files/instatools_consent.json`（用户卸载即清除）。
 * 记录了同意的协议版本号：协议内容变更后需要重新征求同意。
 */
object Consent {

    private const val FILE = "instatools_consent.json"
    private const val KEY_AGREED = "agreed"
    private const val KEY_VERSION = "policy_version"

    /** 当前协议版本。**修改协议内容后必须 +1**，应用会重新征求同意。 */
    const val POLICY_VERSION = "1.0"

    private fun file(ctx: Context) = File(ctx.filesDir, FILE)

    /** 是否已同意当前版本的协议。 */
    fun agreed(ctx: Context): Boolean {
        return try {
            val f = file(ctx)
            if (!f.isFile) return false
            val text = f.readText()
            text.contains("\"$KEY_AGREED\":true") &&
                text.contains("\"$KEY_VERSION\":\"$POLICY_VERSION\"")
        } catch (_: Exception) {
            false
        }
    }

    /** 记录同意。 */
    fun setAgreed(ctx: Context) {
        try {
            file(ctx).writeText(
                "{\"$KEY_AGREED\":true,\"$KEY_VERSION\":\"$POLICY_VERSION\"," +
                    "\"accepted_at\":${System.currentTimeMillis()}}"
            )
        } catch (_: Exception) {
            // 写不进去也不影响使用，只是下次还会再问
        }
    }
}
