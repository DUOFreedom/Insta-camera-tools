package com.duofreedom.instaace.ui

import android.content.Context
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Check
import androidx.compose.material.icons.rounded.Description
import androidx.compose.material.icons.rounded.PrivacyTip
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Checkbox
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import java.io.File

/**
 * 协议同意状态。
 *
 * why: 首次启动必须强制用户阅读并同意《使用协议与隐私政策》才能使用，
 *   这是合规要求，也是自我保护（避免用户误以为「装上就能随便改卡」）。
 *
 * 存储位置：应用私有目录 `files/instaace_consent.json`（用户卸载即清除）。
 * 记录了同意的协议版本号：协议内容变更后需要重新征求同意。
 */
object Consent {

    private const val FILE = "instaace_consent.json"
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

/**
 * 首次启动的强制协议弹窗。
 *
 * - 未同意时不可关闭（点返回键 / 点击外部都无效）
 * - 必须勾选「我已阅读并同意」才能点「同意并继续」
 * - 「不同意」则退出应用
 * - 提供「查看完整协议」入口，读的是随包 assets/docs/ 下的原文
 */
@Composable
fun ConsentGate(
    onOpenFullPolicy: (String) -> Unit,
    onAgree: () -> Unit,
    onDecline: () -> Unit
) {
    val ctx = LocalContext.current
    var checked by rememberSaveable { mutableStateOf(false) }
    var showFull by remember { mutableStateOf(false) }

    // 协议全文：随包 assets/docs/privacy-policy.md（ASCII 文件名，避免 AAPT 编码问题）
    val policyText = remember {
        runCatching {
            ctx.assets.open("docs/privacy-policy.md")
                .bufferedReader().use { it.readText() }
        }.getOrElse { "无法读取协议全文：${it.message}" }
    }

    AlertDialog(
        onDismissRequest = { /* 未同意前不允许关闭 */ },
        title = {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(
                    Icons.Rounded.PrivacyTip,
                    contentDescription = null,
                    tint = MaterialTheme.colorScheme.primary,
                    modifier = Modifier.size(22.dp)
                )
                Spacer(Modifier.size(8.dp))
                Text("使用协议与隐私政策", fontWeight = FontWeight.SemiBold)
            }
        },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState())) {
                Text(
                    "本应用的转码与索引处理全部在你的手机上本地完成，" +
                        "不收集、不上传任何数据。",
                    style = MaterialTheme.typography.bodyMedium
                )
                Spacer(Modifier.height(10.dp))
                Text(
                    "开始使用前，请阅读并同意《使用协议与隐私政策》。" +
                        "要点：\n" +
                        "· 不申请任何危险权限\n" +
                        "· 唯一的联网行为是启动时查一次新版本（不下载、不上传）\n" +
                        "· 存储访问需你在系统目录选择器中亲自授权，随时可撤销\n" +
                        "· 导入会改写相机卡的索引文件，导入前建议备份 DCIM 目录\n" +
                        "· 请确保你对导入的视频内容拥有合法权利",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
                Spacer(Modifier.height(12.dp))
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Checkbox(checked = checked, onCheckedChange = { checked = it })
                    Spacer(Modifier.size(4.dp))
                    Text(
                        "我已阅读并同意《使用协议与隐私政策》",
                        style = MaterialTheme.typography.bodyMedium
                    )
                }
                Spacer(Modifier.height(4.dp))
                TextButton(onClick = { showFull = true }) {
                    Icon(
                        Icons.Rounded.Description,
                        contentDescription = null,
                        modifier = Modifier.size(16.dp)
                    )
                    Spacer(Modifier.size(6.dp))
                    Text("查看完整协议原文", style = MaterialTheme.typography.labelLarge)
                }
            }
        },
        confirmButton = {
            TextButton(
                enabled = checked,
                onClick = { onAgree() }
            ) {
                Icon(Icons.Rounded.Check, contentDescription = null, modifier = Modifier.size(16.dp))
                Spacer(Modifier.size(4.dp))
                Text("同意并继续")
            }
        },
        dismissButton = {
            TextButton(onClick = { onDecline() }) { Text("不同意，退出") }
        }
    )

    // 完整协议原文
    if (showFull) {
        AlertDialog(
            onDismissRequest = { showFull = false },
            title = { Text("使用协议与隐私政策") },
            text = {
                Text(
                    policyText,
                    fontSize = 12.sp,
                    modifier = Modifier
                        .heightIn(max = 460.dp)
                        .verticalScroll(rememberScrollState())
                )
            },
            confirmButton = {
                TextButton(onClick = { showFull = false }) { Text("返回") }
            }
        )
    }
}
