package com.duofreedom.instatools.ui

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * 协议同意状态的判定逻辑（纯函数部分）。
 *
 * 真实读写依赖 Context，这里把判定规则抽成可测的纯函数，
 * 保证「协议版本升级后必须重新征求同意」这条规则不会被改坏。
 */
class ConsentLogicTest {

    /** 与 Consent.agreed() 相同的判定规则（对文件内容的解析）。 */
    private fun parseAgreed(content: String, policyVersion: String): Boolean =
        content.contains("\"agreed\":true") &&
            content.contains("\"policy_version\":\"$policyVersion\"")

    private fun makeContent(agreed: Boolean, version: String) =
        "{\"agreed\":$agreed,\"policy_version\":\"$version\"," +
            "\"accepted_at\":1799999999999}"

    @Test
    fun freshInstallHasNoConsentFile() {
        // 空内容（未写过文件）→ 未同意
        assertFalse(parseAgreed("", "1.0"))
    }

    @Test
    fun agreedOnceIsRemembered() {
        val content = makeContent(true, "1.0")
        assertTrue(parseAgreed(content, "1.0"))
    }

    @Test
    fun declinedStateIsNotAgreed() {
        val content = makeContent(false, "1.0")
        assertFalse(parseAgreed(content, "1.0"))
    }

    @Test
    fun policyVersionChangeRequiresReconsent() {
        // 协议内容改了（版本 1.0 → 2.0），旧的同意记录必须失效
        val old = makeContent(true, "1.0")
        assertFalse(parseAgreed(old, "2.0"))
        assertTrue(parseAgreed(old, "1.0"))
    }

    @Test
    fun policyVersionIsStable() {
        // 当前版本号不应随意变动（改动会让已同意的用户重新弹窗）
        assertEquals("1.0", Consent.POLICY_VERSION)
    }
}
