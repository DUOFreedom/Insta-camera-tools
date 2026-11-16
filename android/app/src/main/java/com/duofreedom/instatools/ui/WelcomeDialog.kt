package com.duofreedom.instatools.ui

import android.content.Context
import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Description
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import com.duofreedom.instatools.R
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

private const val REPO_URL = "https://github.com/DUOFreedom/Insta-camera-tools"
private const val REPO_API = "https://api.github.com/repos/DUOFreedom/Insta-camera-tools"

/**
 * 首次启动的三页欢迎窗：使用协议 / 使用须知 / 作者主页。
 *
 * why 三页而不是一个弹窗：桌面端就是这个流程，协议和须知读起来是两件事，
 *   挤进一个 AlertDialog 只会让人直接点同意。
 * why 不可关闭：协议页是合规要求，必须过；后两页已经同意过，所以可以退。
 */
@Composable
fun WelcomeGate(onAgree: () -> Unit, onDecline: () -> Unit) {
    val ctx = LocalContext.current
    var page by rememberSaveable { mutableStateOf(0) }
    var checked by rememberSaveable { mutableStateOf(false) }
    var showPolicy by remember { mutableStateOf(false) }
    var stars by remember { mutableStateOf<Int?>(null) }
    var starLoading by remember { mutableStateOf(false) }

    LaunchedEffect(page) {
        if (page == 2 && !starLoading && stars == null) {
            starLoading = true
            stars = fetchStarCount()
            starLoading = false
        }
    }

    val titles = intArrayOf(
        R.string.welcome_title_legal,
        R.string.welcome_title_notice,
        R.string.welcome_title_author,
    )
    val hints = intArrayOf(
        R.string.welcome_hint_legal,
        R.string.welcome_hint_notice,
        R.string.welcome_hint_author,
    )

    Dialog(
        onDismissRequest = { /* 未过协议页之前不给关 */ },
        properties = DialogProperties(
            dismissOnBackPress = false,
            dismissOnClickOutside = false,
            usePlatformDefaultWidth = false,
        ),
    ) {
        Surface(
            shape = RoundedCornerShape(16.dp),
            color = MaterialTheme.colorScheme.surface,
            modifier = Modifier
                .padding(20.dp)
                .widthIn(max = 460.dp)
                .heightIn(max = 620.dp),
        ) {
            Column(Modifier.padding(start = 20.dp, end = 20.dp, top = 18.dp, bottom = 14.dp)) {
                Text(
                    stringResource(titles[page]),
                    style = MaterialTheme.typography.titleLarge,
                    fontWeight = FontWeight.SemiBold,
                )
                Spacer(Modifier.height(4.dp))
                Text(
                    stringResource(R.string.welcome_step, page + 1, stringResource(hints[page])),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                Spacer(Modifier.height(14.dp))
                Column(
                    Modifier
                        .weight(1f, fill = false)
                        .verticalScroll(rememberScrollState()),
                    verticalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    when (page) {
                        0 -> PageLegal()
                        1 -> PageNotices()
                        else -> PageAuthor(stars = stars, loading = starLoading)
                    }
                }
                Spacer(Modifier.height(14.dp))
                HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
                Spacer(Modifier.height(10.dp))
                Dots(page)
                Spacer(Modifier.height(10.dp))
                Row(
                    Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    if (page == 0) {
                        FooterLegal(
                            checked = checked,
                            onChecked = { checked = it },
                            onOpenPolicy = { showPolicy = true },
                            onDecline = onDecline,
                            onAgree = { page = 1 },
                        )
                    } else {
                        FooterRest(
                            page = page,
                            onPrev = { page -= 1 },
                            onNext = { page += 1 },
                            onSkip = onAgree,
                            onStar = {
                                openUrl(ctx, REPO_URL)
                                onAgree()
                            },
                        )
                    }
                }
            }
        }
    }

    if (showPolicy) FullPolicyDialog(onClose = { showPolicy = false })
}

@Composable
private fun PageLegal() {
    for (res in intArrayOf(
        R.string.legal_p1,
        R.string.legal_p2,
        R.string.legal_p3,
        R.string.legal_p4,
        R.string.legal_p5,
    )) {
        Text(
            stringResource(res),
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            lineHeight = 22.sp,
        )
    }
}

@Composable
private fun PageNotices() {
    for (res in intArrayOf(
        R.string.notice_p1,
        R.string.notice_p2,
        R.string.notice_p3,
        R.string.notice_p4,
        R.string.notice_p5,
        R.string.notice_p6,
    )) {
        Text(
            stringResource(res),
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            lineHeight = 22.sp,
        )
    }
}

@Composable
private fun PageAuthor(stars: Int?, loading: Boolean) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        // 头像本身已经裁成圆形，这里只负责把它摆上去。
        Image(
            painter = painterResource(R.drawable.welcome_avatar),
            contentDescription = null,
            contentScale = ContentScale.Crop,
            modifier = Modifier
                .size(48.dp)
                .clip(CircleShape)
                .background(MaterialTheme.colorScheme.primaryContainer),
        )
        Spacer(Modifier.size(12.dp))
        Column {
            Text(
                "DUOFreedom",
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.SemiBold,
            )
            Text(
                stringResource(R.string.author_subtitle),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
    Text(
        stringResource(R.string.author_body),
        style = MaterialTheme.typography.bodyMedium,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
        lineHeight = 22.sp,
    )
    Text(
        stringResource(R.string.author_bili),
        style = MaterialTheme.typography.bodyMedium,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
        lineHeight = 22.sp,
    )
    Text(
        stringResource(R.string.author_qq),
        style = MaterialTheme.typography.bodyMedium,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
        lineHeight = 22.sp,
    )
    Text(
        stringResource(R.string.author_future),
        style = MaterialTheme.typography.bodyMedium,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
        lineHeight = 22.sp,
    )
    Text(
        when {
            loading -> stringResource(R.string.author_star_loading)
            stars != null && stars > 0 -> stringResource(R.string.author_star_ok, stars)
            else -> stringResource(R.string.author_star_unknown)
        },
        style = MaterialTheme.typography.bodySmall,
        color = if (stars != null && stars > 0) {
            MaterialTheme.colorScheme.primary
        } else {
            MaterialTheme.colorScheme.onSurfaceVariant
        },
    )
}

@Composable
private fun Dots(page: Int) {
    Row(horizontalArrangement = Arrangement.spacedBy(6.dp), modifier = Modifier.fillMaxWidth()) {
        for (i in 0..2) {
            val current = i == page
            Spacer(
                Modifier
                    .size(width = if (current) 16.dp else 6.dp, height = 6.dp)
                    .clip(RoundedCornerShape(3.dp))
                    .background(
                        if (current) {
                            MaterialTheme.colorScheme.primary
                        } else {
                            MaterialTheme.colorScheme.outlineVariant
                        }
                    ),
            )
        }
    }
}

@Composable
private fun androidx.compose.foundation.layout.RowScope.FooterLegal(
    checked: Boolean,
    onChecked: (Boolean) -> Unit,
    onOpenPolicy: () -> Unit,
    onDecline: () -> Unit,
    onAgree: () -> Unit,
) {
    Checkbox(checked = checked, onCheckedChange = onChecked)
    Text(
        stringResource(R.string.consent_checkbox),
        style = MaterialTheme.typography.bodySmall,
        modifier = Modifier.weight(1f),
    )
    TextButton(onClick = onOpenPolicy) {
        Icon(Icons.Rounded.Description, contentDescription = null, modifier = Modifier.size(16.dp))
        Spacer(Modifier.size(4.dp))
        Text(stringResource(R.string.consent_view_full), style = MaterialTheme.typography.labelSmall)
    }
    TextButton(onClick = onDecline) {
        Text(stringResource(R.string.consent_decline), style = MaterialTheme.typography.labelSmall)
    }
    Button(enabled = checked, onClick = onAgree) {
        Text(stringResource(R.string.consent_agree_continue))
    }
}

@Composable
private fun androidx.compose.foundation.layout.RowScope.FooterRest(
    page: Int,
    onPrev: () -> Unit,
    onNext: () -> Unit,
    onSkip: () -> Unit,
    onStar: () -> Unit,
) {
    TextButton(onClick = onPrev) { Text(stringResource(R.string.welcome_prev)) }
    Spacer(Modifier.weight(1f))
    if (page < 2) {
        Button(onClick = onNext) { Text(stringResource(R.string.welcome_next)) }
    } else {
        TextButton(onClick = onSkip) { Text(stringResource(R.string.welcome_skip)) }
        Button(onClick = onStar) { Text(stringResource(R.string.welcome_star)) }
    }
}

@Composable
private fun FullPolicyDialog(onClose: () -> Unit) {
    val ctx = LocalContext.current
    val text = remember {
        runCatching {
            ctx.assets.open("docs/privacy-policy.md").bufferedReader().use { it.readText() }
        }.getOrElse { ctx.getString(R.string.consent_read_failed, it.message ?: "") }
    }
    AlertDialog(
        onDismissRequest = onClose,
        title = { Text(stringResource(R.string.doc_privacy_title)) },
        text = {
            Text(
                text,
                fontSize = 12.sp,
                modifier = Modifier
                    .heightIn(max = 460.dp)
                    .verticalScroll(rememberScrollState()),
            )
        },
        confirmButton = {
            TextButton(onClick = onClose) { Text(stringResource(R.string.action_back)) }
        },
    )
}

private suspend fun fetchStarCount(): Int? = withContext(Dispatchers.IO) {
    var conn: HttpURLConnection? = null
    try {
        conn = URL(REPO_API).openConnection() as HttpURLConnection
        conn.connectTimeout = 6000
        conn.readTimeout = 6000
        conn.setRequestProperty("User-Agent", "instatoolsAndroid")
        conn.setRequestProperty("Accept", "application/vnd.github+json")
        if (conn.responseCode != HttpURLConnection.HTTP_OK) return@withContext null
        val body = conn.inputStream.bufferedReader().use { it.readText() }
        JSONObject(body).optInt("stargazers_count", 0).takeIf { it > 0 }
    } catch (_: Exception) {
        // 读不到就不显示数字，不影响使用。
        null
    } finally {
        conn?.disconnect()
    }
}

private fun openUrl(ctx: Context, url: String): Boolean = try {
    ctx.startActivity(
        Intent(Intent.ACTION_VIEW, Uri.parse(url)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
    )
    true
} catch (_: Exception) {
    false
}
