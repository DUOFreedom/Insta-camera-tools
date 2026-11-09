@file:OptIn(ExperimentalMaterial3Api::class)

package com.duofreedom.instaace.ui

import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.content.SharedPreferences
import android.os.Handler
import android.os.Looper
import android.net.Uri
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.slideOutHorizontally
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.clickable
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
import androidx.compose.material.icons.rounded.Close
import androidx.compose.material.icons.rounded.Code
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
import androidx.compose.material3.OutlinedButton
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
import androidx.compose.runtime.DisposableEffect
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
import com.duofreedom.instaace.BuildConfig
import com.duofreedom.instaace.engine.Engine
import com.duofreedom.instaace.engine.PythonEngine
import com.duofreedom.instaace.engine.UpdateCheckListener
import com.duofreedom.instaace.ui.theme.Motion
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

private val TABS = listOf("存储卡", "队列", "设置")
private const val SOURCE_URL = "https://github.com/DUOFreedom/Insta-camera-tools"
private const val PREFS_UPDATE = "update_prefs"
private const val KEY_IGNORED_TAG = "ignored_update_tag"

@Composable
fun InstaAceApp() {
    val ctx = LocalContext.current
    var docName by remember { mutableStateOf<String?>(null) }
    var docTitle by remember { mutableStateOf<String>("") }
    val state = remember { AppState() }
    // AppState 内部持有 CoroutineScope，离开组合时必须取消，否则协程泄漏。
    DisposableEffect(state) {
        onDispose { state.close() }
    }
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
            onOpenFullPolicy = { docName = "privacy-policy.md"; docTitle = "使用协议与隐私政策" },
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

    // 更新检查：启动后台检查 GitHub latest release
    var updateTag by remember { mutableStateOf<String?>(null) }
    var updateUrl by remember { mutableStateOf<String?>(null) }
    val prefs = remember { ctx.getSharedPreferences(PREFS_UPDATE, 0) }
    val mainHandler = remember { Handler(Looper.getMainLooper()) }

    LaunchedEffect(Unit) {
        val ignored = prefs.getString(KEY_IGNORED_TAG, "") ?: ""
        if (ignored.isNotBlank()) {
            PythonEngine.ignoreUpdate(ctx, ignored)
        }
        PythonEngine.checkUpdate(ctx, object : UpdateCheckListener {
            // Python 在后台线程回调，Compose 的 mutableStateOf 必须在主线程写，
            //   否则快照系统会丢写或抛 IllegalStateException。
            override fun onUpdateAvailable(tag: String, url: String) {
                mainHandler.post {
                    updateTag = tag
                    updateUrl = url
                }
            }
        })
    }

    val pendingTag = updateTag
    if (consented && pendingTag != null) {
        val currentTag = pendingTag
        val currentUrl = updateUrl ?: ""
        AlertDialog(
            onDismissRequest = { updateTag = null },
            title = { Text("发现新版本") },
            text = {
                Text("最新版本为 $currentTag，当前版本为 ${BuildConfig.VERSION_NAME}。")
            },
            confirmButton = {
                TextButton(
                    onClick = {
                        val opened = currentUrl.isNotBlank() && openUrl(ctx, currentUrl)
                        if (!opened) {
                            scope.launch {
                                snackbar.showSnackbar(
                                    if (currentUrl.isBlank()) "下载地址缺失，请到 GitHub Releases 页面查看"
                                    else "没有可用的浏览器"
                                )
                            }
                        }
                        updateTag = null
                    }
                ) { Text("前往下载") }
            },
            dismissButton = {
                Row {
                    TextButton(onClick = { updateTag = null }) { Text("稍后") }
                    Spacer(Modifier.size(4.dp))
                    TextButton(
                        onClick = {
                            prefs.edit().putString(KEY_IGNORED_TAG, currentTag).apply()
                            PythonEngine.ignoreUpdate(ctx, currentTag)
                            updateTag = null
                        }
                    ) { Text("忽略此版本") }
                }
            }
        )
    }

    if (consented) Scaffold(
        topBar = {
            CenterAlignedTopAppBar(
                title = {
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Text("影石相机工具", fontWeight = FontWeight.SemiBold)
                        Text(
                            "影石 Ace Pro 2 · 素材导入",
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
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
        // 页面切换：位移 + 淡入淡出，全部走弹簧；方向由序号差决定
        AnimatedContent(
            targetState = tab,
            transitionSpec = {
                val dir = if (targetState >= initialState) 1 else -1
                (slideInHorizontally(
                    animationSpec = Motion.spatialSlow(),
                    initialOffsetX = { w -> dir * w / 6 }
                ) + fadeIn(animationSpec = Motion.effectsDefault()))
                    .togetherWith(
                        slideOutHorizontally(
                            animationSpec = Motion.spatialFast(),
                            targetOffsetX = { w -> -dir * w / 6 }
                        ) + fadeOut(animationSpec = Motion.effectsFast())
                    )
            },
            label = "tab",
            modifier = Modifier.padding(inner)
        ) { current ->
            when (current) {
                0 -> CardScreen(
                    state,
                    onPick = { cardPicker.launch(null) }
                )
                1 -> QueueScreen(
                    state = state,
                    onPick = { videoPicker.launch(arrayOf("video/*")) },
                    onStart = {
                        scope.launch {
                            state.startImport(ctx)
                            snackbar.showSnackbar(
                                when {
                                    state.stage.startsWith("已取消") -> state.stage
                                    state.stage.startsWith("失败") || state.stage.startsWith("部分完成") ->
                                        state.stage
                                    else -> "导入完成：已写回相机卡，拔卡插回相机查看"
                                }
                            )
                        }
                    },
                    onCancel = { state.cancelImport() }
                )
                else -> SettingsScreen(
                    state,
                    onOpenDoc = { file: String, title: String ->
                        docName = file
                        docTitle = title
                    },
                    onMessage = { msg -> scope.launch { snackbar.showSnackbar(msg) } }
                )
            }
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
            title = { Text(docTitle) },
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


@Composable
private fun QueueScreen(
    state: AppState,
    onPick: () -> Unit,
    onStart: () -> Unit,
    onCancel: () -> Unit,
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
            // 导入中把「开始」换成「取消」：否则用户只能杀掉 App 才能停下，
            //   而杀进程会留下半截暂存文件和一个正在跑的 ffmpeg 子进程。
            if (state.running) {
                OutlinedButton(
                    onClick = onCancel,
                    enabled = !state.canceling,
                    modifier = Modifier.fillMaxWidth().height(52.dp)
                ) {
                    Icon(Icons.Rounded.Close, contentDescription = null)
                    Spacer(Modifier.size(8.dp))
                    Text(if (state.canceling) "正在取消…" else "取消导入")
                }
            } else {
                Button(
                    onClick = onStart,
                    enabled = state.queue.isNotEmpty() && state.cardUri != null,
                    modifier = Modifier.fillMaxWidth().height(52.dp)
                ) {
                    Icon(Icons.Rounded.PlayArrow, contentDescription = null)
                    Spacer(Modifier.size(8.dp))
                    Text(if (state.cardUri == null) "请先选择存储卡" else "开始导入")
                }
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


@Composable
private fun SettingsScreen(
    state: AppState,
    onOpenDoc: (file: String, title: String) -> Unit,
    onMessage: (String) -> Unit,
    modifier: Modifier = Modifier
) {
    // 设置项越加越多，小屏必然超过一屏；不给 verticalScroll 的话
    // 底部内容会被裁掉且无法查看。
    Column(
        modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
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
                ExpandableSection(
                    title = "两种编码器的区别",
                    subtitle = if (state.encoder == "硬件") "当前：硬件（快，但关键帧间隔受限）"
                    else "当前：自动（软件编码，识别最稳）"
                ) {
                    Text(
                        "自动 = 软件编码（libx265 + libx264，与桌面端一致，相机识别最稳）。\n" +
                            "硬件 = MediaCodec 硬件编码，速度快很多，但关键帧间隔受系统限制只能 1 秒" +
                            "（相机要求 16 帧），若导入后相机不显示缩略图或无法识别，请切回「自动」。",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
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
                Text("版本 1.2.0", style = MaterialTheme.typography.bodyMedium)

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

                // 开发者与源码入口
                Text(
                    "开发者",
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
                Spacer(Modifier.height(4.dp))
                Text("B站 @铎DUOFreedom", style = MaterialTheme.typography.bodyMedium)
                Spacer(Modifier.height(2.dp))
                Text(
                    "GitHub  ·  DUOFreedom",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
                Spacer(Modifier.height(8.dp))
                Text(
                    "源代码",
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
                Spacer(Modifier.height(4.dp))
                Text(
                    "github.com/DUOFreedom/Insta-camera-tools",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.primary,
                    modifier = Modifier.clickable {
                        if (!openUrl(ctx, SOURCE_URL)) onMessage("没有可用的浏览器")
                    }
                )
                Spacer(Modifier.height(6.dp))
                OutlinedButton(
                    onClick = {
                        if (!openUrl(ctx, SOURCE_URL)) onMessage("没有可用的浏览器")
                    },
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Icon(
                        Icons.Rounded.Code,
                        contentDescription = null,
                        modifier = Modifier.size(16.dp)
                    )
                    Spacer(Modifier.size(6.dp))
                    Text("在浏览器中打开源代码仓库")
                }
                Spacer(Modifier.height(8.dp))
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
                    FilledTonalButton(onClick = { onOpenDoc("privacy-policy.md", "使用协议与隐私政策") }) {
                        Text("使用协议与隐私", style = MaterialTheme.typography.labelMedium)
                    }
                    FilledTonalButton(onClick = { onOpenDoc("open-source-notices.md", "开源合规声明") }) {
                        Text("开源合规声明", style = MaterialTheme.typography.labelMedium)
                    }
                }
                Spacer(Modifier.height(4.dp))
                Text(
                    "权限：无危险权限。仅申请 INTERNET 用于启动时检查新版本" +
                        "（单次 GET，不下载、不上传、无遥测）；" +
                        "存储访问通过系统目录选择器按需授权，随时可撤销。",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        }
    }
}


private fun humanSize(bytes: Long): String = when {
    bytes <= 0 -> "大小未知"
    bytes >= 1L shl 30 -> String.format("%.2f GB", bytes / 1073741824.0)
    bytes >= 1L shl 20 -> String.format("%.1f MB", bytes / 1048576.0)
    bytes >= 1L shl 10 -> String.format("%.0f KB", bytes / 1024.0)
    else -> "$bytes B"
}

/** 用系统浏览器打开链接。返回 false 表示设备上没有能处理 VIEW 的 Activity。 */
private fun openUrl(ctx: Context, url: String): Boolean = try {
    ctx.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)))
    true
} catch (_: ActivityNotFoundException) {
    false
}
