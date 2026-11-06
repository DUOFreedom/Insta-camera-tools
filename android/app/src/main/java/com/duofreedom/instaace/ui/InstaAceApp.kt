@file:OptIn(ExperimentalMaterial3Api::class)

package com.duofreedom.instaace.ui

import android.content.Intent
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.PlaylistPlay
import androidx.compose.material.icons.rounded.Add
import androidx.compose.material.icons.rounded.CheckCircle
import androidx.compose.material.icons.rounded.DeleteOutline
import androidx.compose.material.icons.rounded.ErrorOutline
import androidx.compose.material.icons.rounded.Info
import androidx.compose.material.icons.rounded.Movie
import androidx.compose.material.icons.rounded.PlayArrow
import androidx.compose.material.icons.rounded.SdCard
import androidx.compose.material.icons.rounded.Settings
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.AssistChip
import androidx.compose.material3.AssistChipDefaults
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CenterAlignedTopAppBar
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.ListItem
import androidx.compose.material3.ListItemDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.OutlinedCard
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SegmentedButton
import androidx.compose.material3.SegmentedButtonDefaults
import androidx.compose.material3.SingleChoiceSegmentedButtonRow
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.duofreedom.instaace.engine.Engine
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

private val TABS = listOf("存储卡", "队列", "设置")

@Composable
fun InstaAceApp() {
    val ctx = LocalContext.current
    var docName by remember { mutableStateOf<String?>(null) }
    val state = remember { AppState() }
    val snackbar = remember { SnackbarHostState() }
    val scope = rememberCoroutineScope()
    var tab by rememberSaveable { mutableIntStateOf(0) }

    // 首次启动强制同意协议：未同意前不进入主界面
    var consented by remember {
        mutableStateOf(Consent.agreed(ctx))
    }

    // 未同意时，系统返回键不能把应用退到后台「绕过」协议弹窗。
    //   BackHandler 优先于系统默认返回处理，因此能拦住。
    BackHandler(enabled = !consented) { /* 拦截：必须先同意协议 */ }

    if (!consented) {
        ConsentGate(
            onOpenFullPolicy = { docName = it },
            onAgree = {
                Consent.setAgreed(ctx)
                consented = true
            },
            onDecline = {
                // 不同意即退出应用（Activity.finish 会结束当前任务）
                (ctx as? android.app.Activity)?.finish()
            }
        )
    }

    val cardPicker = rememberLauncherForActivityResult(
        ActivityResultContracts.OpenDocumentTree()
    ) { uri ->
        if (uri != null) {
            try {
                ctx.contentResolver.takePersistableUriPermission(
                    uri,
                    Intent.FLAG_GRANT_READ_URI_PERMISSION or
                        Intent.FLAG_GRANT_WRITE_URI_PERMISSION
                )
            } catch (_: SecurityException) {
                // 只读授权也能扫描，写回阶段再提示
            }
            state.scanCard(ctx, uri)
        }
    }

    val videoPicker = rememberLauncherForActivityResult(
        ActivityResultContracts.OpenMultipleDocuments()
    ) { uris ->
        if (!uris.isNullOrEmpty()) state.addVideos(ctx, uris)
    }

    if (consented) Scaffold(
        topBar = {
            CenterAlignedTopAppBar(
                title = {
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Text("InstaAce 导入器", fontWeight = FontWeight.SemiBold)
                        Text(
                            "影石 Ace Pro 2 · 素材导入",
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                },
                colors = TopAppBarDefaults.centerAlignedTopAppBarColors(
                    containerColor = MaterialTheme.colorScheme.background
                )
            )
        },
        bottomBar = {
            NavigationBar {
                TABS.forEachIndexed { i, title ->
                    NavigationBarItem(
                        selected = tab == i,
                        onClick = { tab = i },
                        icon = {
                            Icon(
                                imageVector = when (i) {
                                    0 -> Icons.Rounded.SdCard
                                    1 -> Icons.AutoMirrored.Rounded.PlaylistPlay
                                    else -> Icons.Rounded.Settings
                                },
                                contentDescription = null
                            )
                        },
                        label = { Text(title) }
                    )
                }
            }
        },
        snackbarHost = { SnackbarHost(snackbar) },
        containerColor = MaterialTheme.colorScheme.background
    ) { inner ->
        when (tab) {
            0 -> CardScreen(
                state,
                onPick = { cardPicker.launch(null) },
                modifier = Modifier.padding(inner)
            )
            1 -> QueueScreen(
                state = state,
                onPick = { videoPicker.launch(arrayOf("video/*")) },
                onStart = {
                    scope.launch {
                        state.startImport(ctx)
                        snackbar.showSnackbar(
                            when {
                                state.stage.startsWith("失败") || state.stage.startsWith("部分完成") ->
                                    state.stage
                                else -> "导入完成：已写回相机卡，拔卡插回相机查看"
                            }
                        )
                    }
                },
                modifier = Modifier.padding(inner)
            )
            else -> SettingsScreen(state, onOpenDoc = { docName = it }, modifier = Modifier.padding(inner))
        }
    }

    // 文档弹窗：直接从 assets 读，不依赖任何外部应用
    if (docName != null) {
        val name = docName!!
        val docText = remember(name) {
            runCatching {
                ctx.assets.open("docs/$name").bufferedReader().use { it.readText() }
            }.getOrElse { "无法读取文档：$name\n${it.message}" }
        }
        AlertDialog(
            onDismissRequest = { docName = null },
            title = { Text(name.removeSuffix(".md")) },
            text = {
                Text(
                    docText,
                    style = MaterialTheme.typography.bodySmall,
                    modifier = Modifier.verticalScroll(rememberScrollState())
                )
            },
            confirmButton = {
                TextButton(onClick = { docName = null }) { Text("关闭") }
            }
        )
    }
}

/* ------------------------------------------------------------------ 存储卡 */

@Composable
private fun CardScreen(state: AppState, onPick: () -> Unit, modifier: Modifier = Modifier) {
    LazyColumn(
        modifier = modifier.fillMaxSize().padding(horizontal = 16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        item { Spacer(Modifier.height(4.dp)) }

        item {
            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(
                    containerColor = MaterialTheme.colorScheme.primaryContainer
                )
            ) {
                Column(Modifier.padding(20.dp)) {
                    Text(
                        "选择相机存储卡",
                        style = MaterialTheme.typography.titleLarge,
                        color = MaterialTheme.colorScheme.onPrimaryContainer
                    )
                    Spacer(Modifier.height(6.dp))
                    Text(
                        state.cardLabel,
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onPrimaryContainer.copy(alpha = 0.8f)
                    )
                    Spacer(Modifier.height(16.dp))
                    FilledTonalButton(onClick = onPick) {
                        Icon(
                            Icons.Rounded.SdCard,
                            contentDescription = null,
                            modifier = Modifier.size(18.dp)
                        )
                        Spacer(Modifier.size(8.dp))
                        Text(if (state.cardUri == null) "选择存储卡" else "重新选择")
                    }
                }
            }
        }

        item {
            Text(
                "三层识别前置条件",
                style = MaterialTheme.typography.titleMedium,
                modifier = Modifier.padding(top = 8.dp)
            )
        }

        item {
            OutlinedCard(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        StatusChip(state.dcimFound, "DCIM 结构")
                        StatusChip(state.camDirFound, "Camera01")
                    }
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        StatusChip(state.indexFound, "索引文件")
                        StatusChip(state.templatePairs > 0, "真机模板")
                    }
                    if (state.templateName.isNotBlank()) {
                        Text(
                            "模板：${state.templateName}",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                    HorizontalDivider(Modifier.padding(vertical = 4.dp))
                    Text(
                        "VID ${state.vidCount} 个 · LRV ${state.lrvCount} 个 · 可作模板 ${state.templatePairs} 对",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    if (state.camDirFound && state.templatePairs == 0) {
                        Text(
                            "卡里缺一对相机原生录制的 VID_/LRV_，缺它无法生成可识别的文件。先用相机录一小段。",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.error
                        )
                    }
                    if (state.indexCount > 0 || state.indexError.isNotBlank() || state.indexEmptyMeta > 0) {
                        val bad = state.indexError.isNotBlank() || state.indexEmptyMeta > 0
                        Text(
                            when {
                                state.indexError.isNotBlank() -> "索引读取失败：${state.indexError}"
                                state.indexEmptyMeta > 0 ->
                                    "索引 ${state.indexCount} 条，其中 ${state.indexEmptyMeta} 条 meta 为空——相机会显示 0KB 且打不开"
                                else -> "索引 ${state.indexCount} 条，全部带 meta"
                            },
                            style = MaterialTheme.typography.bodySmall,
                            color = if (bad) MaterialTheme.colorScheme.error
                            else MaterialTheme.colorScheme.primary
                        )
                    }
                }
            }
        }

        item {
            Text(
                "手机通过 USB-C 读卡器挂载相机卡；导入时会在这里的三层条件都满足后" +
                    "执行：转码 → inst box 移植 → 索引登记 → 写回 DCIM\\Camera01。",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(top = 4.dp, bottom = 16.dp)
            )
        }
    }
}

@Composable
private fun StatusChip(ok: Boolean, label: String) {
    val tint = if (ok) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.error
    AssistChip(
        onClick = {},
        label = { Text("$label ${if (ok) "✓" else "✕"}") },
        leadingIcon = {
            Icon(
                imageVector = if (ok) Icons.Rounded.CheckCircle else Icons.Rounded.ErrorOutline,
                contentDescription = null,
                modifier = Modifier.size(16.dp),
                tint = tint
            )
        },
        colors = AssistChipDefaults.assistChipColors(labelColor = tint)
    )
}

/* -------------------------------------------------------------------- 队列 */

@Composable
private fun QueueScreen(
    state: AppState,
    onPick: () -> Unit,
    onStart: () -> Unit,
    modifier: Modifier = Modifier
) {
    Column(modifier.fillMaxSize().padding(horizontal = 16.dp)) {
        Row(
            Modifier.fillMaxWidth().padding(top = 12.dp, bottom = 8.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text(
                "待导入（${state.queue.size}）",
                style = MaterialTheme.typography.titleMedium,
                modifier = Modifier.weight(1f)
            )
            FilledTonalButton(onClick = onPick, enabled = !state.running) {
                Icon(Icons.Rounded.Add, contentDescription = null, modifier = Modifier.size(18.dp))
                Spacer(Modifier.size(6.dp))
                Text("添加视频")
            }
        }

        if (state.queue.isEmpty()) {
            EmptyState(Modifier.weight(1f))
        } else {
            LazyColumn(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                items(state.queue, key = { it.uri.toString() }) { item ->
                    ListItem(
                        leadingContent = {
                            Icon(
                                Icons.Rounded.Movie,
                                contentDescription = null,
                                tint = MaterialTheme.colorScheme.primary
                            )
                        },
                        headlineContent = {
                            Text(item.name, maxLines = 1, overflow = TextOverflow.Ellipsis)
                        },
                        supportingContent = { Text(humanSize(item.size)) },
                        trailingContent = {
                            IconButton(
                                onClick = { state.remove(item) },
                                enabled = !state.running
                            ) {
                                Icon(Icons.Rounded.DeleteOutline, contentDescription = "移除")
                            }
                        },
                        colors = ListItemDefaults.colors(
                            containerColor = MaterialTheme.colorScheme.surfaceVariant
                                .copy(alpha = 0.35f)
                        )
                    )
                }
            }
        }

        Column(Modifier.fillMaxWidth().padding(vertical = 12.dp)) {
            Row(Modifier.fillMaxWidth()) {
                Text(
                    state.stage,
                    style = MaterialTheme.typography.labelMedium,
                    modifier = Modifier.weight(1f)
                )
                Text(
                    "${(state.progress * 100).toInt()}%",
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
            Spacer(Modifier.height(6.dp))
            LinearProgressIndicator(
                progress = { state.progress },
                modifier = Modifier.fillMaxWidth().height(8.dp)
            )
            if (state.logLine.isNotBlank()) {
                Spacer(Modifier.height(8.dp))
                Text(
                    state.logLine,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    maxLines = 3,
                    overflow = TextOverflow.Ellipsis
                )
            }
            if (state.outputSummary.isNotBlank()) {
                Spacer(Modifier.height(8.dp))
                OutlinedCard(Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(12.dp)) {
                        Text("导入明细", style = MaterialTheme.typography.labelMedium)
                        Spacer(Modifier.height(4.dp))
                        Text(
                            state.outputSummary,
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                }
            }
            Spacer(Modifier.height(12.dp))
            Button(
                onClick = onStart,
                enabled = state.queue.isNotEmpty() && !state.running && state.cardUri != null,
                modifier = Modifier.fillMaxWidth().height(52.dp)
            ) {
                Icon(Icons.Rounded.PlayArrow, contentDescription = null)
                Spacer(Modifier.size(8.dp))
                Text(
                    when {
                        state.running -> "导入中…"
                        state.cardUri == null -> "请先选择存储卡"
                        else -> "开始导入"
                    }
                )
            }
        }
    }
}

@Composable
private fun EmptyState(modifier: Modifier = Modifier) {
    Column(
        modifier.fillMaxWidth(),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center
    ) {
        Icon(
            Icons.Rounded.Movie,
            contentDescription = null,
            modifier = Modifier.size(48.dp),
            tint = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.5f)
        )
        Spacer(Modifier.height(12.dp))
        Text(
            "还没有添加视频\n支持从「文件」里多选，或从相册选",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
    }
}

/* -------------------------------------------------------------------- 设置 */

@Composable
private fun SettingsScreen(state: AppState, onOpenDoc: (String) -> Unit, modifier: Modifier = Modifier) {
    Column(
        modifier.fillMaxSize().padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        Card(Modifier.fillMaxWidth()) {
            Column(Modifier.padding(16.dp)) {
                Text("编码器", style = MaterialTheme.typography.titleSmall)
                Spacer(Modifier.height(10.dp))
                SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
                    listOf("自动", "硬件").forEachIndexed { i, label ->
                        SegmentedButton(
                            selected = state.encoder == label,
                            onClick = { state.encoder = label },
                            shape = SegmentedButtonDefaults.itemShape(index = i, count = 2),
                            label = { Text(label) }
                        )
                    }
                }
                Spacer(Modifier.height(8.dp))
                Text(
                    "自动 = 软件编码（libx265 + libx264，与桌面端一致，相机识别最稳）。\n" +
                        "硬件 = MediaCodec 硬件编码，速度快很多，但关键帧间隔受系统限制只能 1 秒" +
                        "（相机要求 16 帧），若导入后相机不显示缩略图或无法识别，请切回「自动」。",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        }

        Card(Modifier.fillMaxWidth()) {
            ListItem(
                headlineContent = { Text("登记相机索引") },
                supportingContent = { Text("写入 DCIM 下的 fileinfo / editinfo，相册才会出现") },
                trailingContent = {
                    Switch(
                        checked = state.registerIndex,
                        onCheckedChange = { state.registerIndex = it }
                    )
                }
            )
        }

        Card(Modifier.fillMaxWidth()) {
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(
                        Icons.Rounded.Info,
                        contentDescription = null,
                        modifier = Modifier.size(18.dp),
                        tint = MaterialTheme.colorScheme.primary
                    )
                    Spacer(Modifier.size(8.dp))
                    Text("关于", style = MaterialTheme.typography.titleSmall)
                }
                Text("版本 0.7.1 · 预览版", style = MaterialTheme.typography.bodyMedium)

                val ctx = LocalContext.current
                var engineLine by remember { mutableStateOf("检测中…") }
                LaunchedEffect(Unit) {
                    engineLine = withContext(Dispatchers.IO) { Engine.versionLine(ctx) }
                }
                Text(
                    "ffmpeg：$engineLine",
                    style = MaterialTheme.typography.bodySmall,
                    color = if (engineLine.startsWith("ffmpeg version"))
                        MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.error
                )

                if (state.pythonStatus == "未检测") {
                    LaunchedEffect(Unit) { state.checkPython(ctx) }
                }
                Text(
                    "导入核心：${state.pythonStatus}",
                    style = MaterialTheme.typography.bodySmall,
                    color = if (state.pythonStatus.startsWith("Python 核心就绪"))
                        MaterialTheme.colorScheme.primary
                    else MaterialTheme.colorScheme.onSurfaceVariant
                )

                Text(
                    "已内置：选卡扫描与索引体检、aarch64 ffmpeg 7.1、" +
                        "内嵌 CPython 运行桌面端已验证的导入核心" +
                        "（转码 → inst box 移植 → 索引登记 → 写回相机卡）。",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
                HorizontalDivider(Modifier.padding(vertical = 4.dp))
                Text("作者：B站@铎DUOFreedom", style = MaterialTheme.typography.bodySmall)
                Text(
                    "GPL-3.0 · 与桌面端同源",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )

                // 隐私与许可：应用内可直接查阅全文（随包 assets/docs/ 里的 Markdown）
                HorizontalDivider(Modifier.padding(vertical = 4.dp))
                Row(
                    Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    FilledTonalButton(onClick = { onOpenDoc("使用协议与隐私政策.md") }) {
                        Text("使用协议与隐私", style = MaterialTheme.typography.labelMedium)
                    }
                    FilledTonalButton(onClick = { onOpenDoc("开源合规声明.md") }) {
                        Text("开源合规声明", style = MaterialTheme.typography.labelMedium)
                    }
                }
                Spacer(Modifier.height(4.dp))
                Text(
                    "权限：仅 1 项 AndroidX 自定义签名权限；无危险权限、无网络权限。" +
                        "存储访问通过系统目录选择器按需授权，随时可撤销。",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        }
    }
}

/* -------------------------------------------------------------------- 工具 */

private fun humanSize(bytes: Long): String = when {
    bytes <= 0 -> "大小未知"
    bytes >= 1L shl 30 -> String.format("%.2f GB", bytes / 1073741824.0)
    bytes >= 1L shl 20 -> String.format("%.1f MB", bytes / 1048576.0)
    bytes >= 1L shl 10 -> String.format("%.0f KB", bytes / 1024.0)
    else -> "$bytes B"
}
