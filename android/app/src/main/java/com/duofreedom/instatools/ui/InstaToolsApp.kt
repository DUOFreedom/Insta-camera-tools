@file:OptIn(ExperimentalMaterial3Api::class)

package com.duofreedom.instatools.ui

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
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.PaddingValues
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
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.PlaylistPlay
import androidx.compose.material.icons.rounded.Add
import androidx.compose.material.icons.rounded.CheckCircle
import androidx.compose.material.icons.rounded.Code
import androidx.compose.material.icons.rounded.DeleteOutline
import androidx.compose.material.icons.rounded.ErrorOutline
import androidx.compose.material.icons.rounded.Info
import androidx.compose.material.icons.rounded.Movie
import androidx.compose.material.icons.rounded.SdCard
import androidx.compose.material.icons.rounded.Settings
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CenterAlignedTopAppBar
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.ListItem
import androidx.compose.material3.ListItemDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.RadioButton
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
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.duofreedom.instatools.BuildConfig
import com.duofreedom.instatools.R
import com.duofreedom.instatools.engine.Engine
import com.duofreedom.instatools.engine.PythonEngine
import com.duofreedom.instatools.engine.UpdateCheckListener
import com.duofreedom.instatools.ui.theme.Motion
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/** 底部导航的标题资源，顺序与图标一一对应。 */
private val TAB_TITLES = listOf(R.string.tab_card, R.string.tab_queue, R.string.tab_settings)
private const val SOURCE_URL = "https://github.com/DUOFreedom/Insta-camera-tools"
private const val PREFS_UPDATE = "update_prefs"
private const val KEY_IGNORED_TAG = "ignored_update_tag"

/** 界面统一间距，全部取 8dp 的整数倍，避免各处手写魔数。 */
private object Gaps {
    val x1 = 8.dp
    val x2 = 16.dp
    val x3 = 24.dp
}

@Composable
fun instatoolsApp() {
    val ctx = LocalContext.current
    var docName by remember { mutableStateOf<String?>(null) }
    var docTitle by remember { mutableStateOf<String>("") }
    val state = remember { AppState(ctx) }
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
            onOpenFullPolicy = {
                docName = "privacy-policy.md"
                docTitle = ctx.getString(R.string.doc_privacy_title)
            },
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
            scope.launch { state.scanCard(ctx, uri) }
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
            title = { Text(stringResource(R.string.update_available_title)) },
            text = {
                Text(
                    stringResource(
                        R.string.update_available_body,
                        currentTag,
                        BuildConfig.VERSION_NAME
                    )
                )
            },
            confirmButton = {
                TextButton(
                    onClick = {
                        val opened = currentUrl.isNotBlank() && openUrl(ctx, currentUrl)
                        if (!opened) {
                            scope.launch {
                                snackbar.showSnackbar(
                                    if (currentUrl.isBlank()) ctx.getString(R.string.update_no_url)
                                    else ctx.getString(R.string.no_browser)
                                )
                            }
                        }
                        updateTag = null
                    }
                ) { Text(stringResource(R.string.update_go_download)) }
            },
            dismissButton = {
                Row {
                    TextButton(onClick = { updateTag = null }) {
                        Text(stringResource(R.string.update_later))
                    }
                    Spacer(Modifier.size(4.dp))
                    TextButton(
                        onClick = {
                            prefs.edit().putString(KEY_IGNORED_TAG, currentTag).apply()
                            PythonEngine.ignoreUpdate(ctx, currentTag)
                            updateTag = null
                        }
                    ) { Text(stringResource(R.string.update_ignore)) }
                }
            }
        )
    }

    if (consented) Scaffold(
        topBar = {
            CenterAlignedTopAppBar(
                title = {
                    Text(
                        stringResource(R.string.app_name),
                        fontWeight = FontWeight.SemiBold
                    )
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.surface,
                    titleContentColor = MaterialTheme.colorScheme.onSurface
                )
            )
        },
        bottomBar = {
            NavigationBar(
                containerColor = MaterialTheme.colorScheme.surface,
                contentColor = MaterialTheme.colorScheme.primary,
                tonalElevation = 0.dp
            ) {
                TAB_TITLES.forEachIndexed { i, titleRes ->
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
                        label = { Text(stringResource(titleRes)) },
                        colors = NavigationBarItemDefaults.colors(
                            selectedIconColor = MaterialTheme.colorScheme.onPrimaryContainer,
                            selectedTextColor = MaterialTheme.colorScheme.primary,
                            indicatorColor = MaterialTheme.colorScheme.primaryContainer,
                            unselectedIconColor = MaterialTheme.colorScheme.onSurfaceVariant,
                            unselectedTextColor = MaterialTheme.colorScheme.onSurfaceVariant
                        )
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
                            // 分支只看语言无关的 StageKind，不看本地化文案：
                            //   否则切到英文后前缀匹配全部失效。
                            snackbar.showSnackbar(
                                when (state.stageKind) {
                                    StageKind.Canceled,
                                    StageKind.Failed,
                                    StageKind.Partial -> state.stage
                                    else -> ctx.getString(R.string.import_done_snackbar)
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
            }.getOrElse {
                ctx.getString(R.string.doc_read_failed, name, it.message ?: "")
            }
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
                TextButton(onClick = { docName = null }) {
                    Text(stringResource(R.string.action_close))
                }
            }
        )
    }
}


@Composable
private fun CardScreen(state: AppState, onPick: () -> Unit, modifier: Modifier = Modifier) {
    LazyColumn(
        modifier = modifier.fillMaxSize(),
        contentPadding = PaddingValues(
            start = Gaps.x2,
            end = Gaps.x2,
            top = Gaps.x1,
            bottom = Gaps.x2
        ),
        verticalArrangement = Arrangement.spacedBy(Gaps.x2)
    ) {
        item { CardHero(state, onPick) }

        item {
            Text(
                stringResource(R.string.preflight_title),
                style = MaterialTheme.typography.titleMedium,
                color = MaterialTheme.colorScheme.onSurface,
                modifier = Modifier.padding(start = Gaps.x1, top = Gaps.x1)
            )
        }

        item { PreflightCard(state) }

        item {
            Text(
                stringResource(R.string.card_how_it_works),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(horizontal = Gaps.x1)
            )
        }
    }
}

/** 首页主卡片：整块深蓝底 + 白字 + 白色主按钮，是这一屏唯一的强调色块。 */
@Composable
private fun CardHero(state: AppState, onPick: () -> Unit) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = MaterialTheme.shapes.extraLarge,
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.primary,
            contentColor = MaterialTheme.colorScheme.onPrimary
        )
    ) {
        Column(
            Modifier.padding(Gaps.x3),
            verticalArrangement = Arrangement.spacedBy(Gaps.x1)
        ) {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(Gaps.x1)
            ) {
                Box(
                    Modifier
                        .size(40.dp)
                        .clip(CircleShape)
                        .background(MaterialTheme.colorScheme.onPrimary.copy(alpha = 0.16f)),
                    contentAlignment = Alignment.Center
                ) {
                    Icon(
                        Icons.Rounded.SdCard,
                        contentDescription = null,
                        modifier = Modifier.size(22.dp),
                        tint = MaterialTheme.colorScheme.onPrimary
                    )
                }
                Text(
                    stringResource(R.string.card_section_title),
                    style = MaterialTheme.typography.titleLarge,
                    fontWeight = FontWeight.SemiBold
                )
            }
            Text(
                state.cardLabel,
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onPrimary.copy(alpha = 0.85f)
            )
            Spacer(Modifier.height(Gaps.x1))
            Button(
                onClick = onPick,
                colors = ButtonDefaults.buttonColors(
                    containerColor = MaterialTheme.colorScheme.onPrimary,
                    contentColor = MaterialTheme.colorScheme.primary
                )
            ) {
                Text(
                    stringResource(
                        if (state.cardUri == null) R.string.pick_card
                        else R.string.pick_card_again
                    )
                )
            }
        }
    }
}

/** 预检卡片：2×2 网格 + 结论行；白底卡片衬在浅蓝背景上。 */
@Composable
private fun PreflightCard(state: AppState) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = MaterialTheme.shapes.large,
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surface,
            contentColor = MaterialTheme.colorScheme.onSurface
        )
    ) {
        Column(
            Modifier.padding(Gaps.x3),
            verticalArrangement = Arrangement.spacedBy(Gaps.x1)
        ) {
            Row(horizontalArrangement = Arrangement.spacedBy(Gaps.x1)) {
                PreflightItem(
                    state.dcimFound,
                    stringResource(R.string.preflight_dcim),
                    Modifier.weight(1f)
                )
                PreflightItem(state.camDirFound, "Camera01", Modifier.weight(1f))
            }
            Row(horizontalArrangement = Arrangement.spacedBy(Gaps.x1)) {
                PreflightItem(
                    state.indexFound,
                    stringResource(R.string.preflight_index),
                    Modifier.weight(1f)
                )
                PreflightItem(
                    state.templatePairs > 0,
                    stringResource(R.string.preflight_template),
                    Modifier.weight(1f)
                )
            }
            if (state.templateName.isNotBlank()) {
                Text(
                    stringResource(R.string.preflight_template_name, state.templateName),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
            HorizontalDivider(
                Modifier.padding(vertical = Gaps.x1),
                color = MaterialTheme.colorScheme.outlineVariant
            )
            Text(
                stringResource(
                    R.string.preflight_counts,
                    state.vidCount,
                    state.lrvCount,
                    state.templatePairs
                ),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
            if (state.camDirFound && state.templatePairs == 0) {
                Text(
                    stringResource(R.string.preflight_need_template),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.error
                )
            }
            if (state.indexCount > 0 || state.indexError.isNotBlank() || state.indexEmptyMeta > 0) {
                val bad = state.indexError.isNotBlank() || state.indexEmptyMeta > 0
                Text(
                    when {
                        state.indexError.isNotBlank() -> stringResource(
                            R.string.preflight_index_error, state.indexError
                        )

                        state.indexEmptyMeta > 0 -> stringResource(
                            R.string.preflight_index_empty_meta,
                            state.indexCount,
                            state.indexEmptyMeta
                        )

                        else -> stringResource(
                            R.string.preflight_index_all_meta, state.indexCount
                        )
                    },
                    style = MaterialTheme.typography.bodySmall,
                    color = if (bad) MaterialTheme.colorScheme.error
                    else MaterialTheme.colorScheme.primary
                )
            }
        }
    }
}

/** 单项预检：对勾或叉号 + 文案，失败时整项转成错误色，扫一眼就能看出缺哪一步。 */
@Composable
private fun PreflightItem(ok: Boolean, label: String, modifier: Modifier = Modifier) {
    val tint = if (ok) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.error
    Row(
        modifier,
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(4.dp)
    ) {
        Icon(
            imageVector = if (ok) Icons.Rounded.CheckCircle else Icons.Rounded.ErrorOutline,
            contentDescription = null,
            modifier = Modifier.size(18.dp),
            tint = tint
        )
        Text(
            label,
            style = MaterialTheme.typography.bodyMedium,
            color = if (ok) MaterialTheme.colorScheme.onSurface else tint,
            maxLines = 2,
            overflow = TextOverflow.Ellipsis
        )
    }
}

@Composable
private fun QueueScreen(
    state: AppState,
    onPick: () -> Unit,
    onStart: () -> Unit,
    onCancel: () -> Unit,
    modifier: Modifier = Modifier
) {
    val ctx = LocalContext.current
    Column(modifier.fillMaxSize().padding(horizontal = Gaps.x2)) {
        Row(
            Modifier.fillMaxWidth().padding(top = Gaps.x1, bottom = Gaps.x1),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text(
                stringResource(R.string.queue_pending_count, state.queue.size),
                style = MaterialTheme.typography.titleMedium,
                modifier = Modifier.weight(1f)
            )
            FilledTonalButton(onClick = onPick, enabled = !state.running) {
                Icon(Icons.Rounded.Add, contentDescription = null, modifier = Modifier.size(18.dp))
                Spacer(Modifier.size(6.dp))
                Text(stringResource(R.string.add_videos))
            }
        }

        if (state.queue.isEmpty()) {
            EmptyState(Modifier.weight(1f))
        } else {
            LazyColumn(
                Modifier.weight(1f),
                contentPadding = PaddingValues(bottom = Gaps.x1),
                verticalArrangement = Arrangement.spacedBy(Gaps.x1)
            ) {
                items(state.queue, key = { it.uri.toString() }) { item ->
                    ListItem(
                        // animateItem 只在增删/重排时生效，不改布局尺寸，也不触发整表重组。
                        modifier = Modifier
                            .animateItem()
                            .clip(MaterialTheme.shapes.large),
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
                        supportingContent = { Text(humanSize(ctx, item.size)) },
                        trailingContent = {
                            IconButton(
                                onClick = { state.remove(item) },
                                enabled = !state.running
                            ) {
                                Icon(
                                    Icons.Rounded.DeleteOutline,
                                    contentDescription = stringResource(R.string.action_remove)
                                )
                            }
                        },
                        colors = ListItemDefaults.colors(
                            containerColor = MaterialTheme.colorScheme.surface,
                            headlineColor = MaterialTheme.colorScheme.onSurface,
                            supportingColor = MaterialTheme.colorScheme.onSurfaceVariant,
                            leadingIconColor = MaterialTheme.colorScheme.primary,
                            trailingIconColor = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    )
                }
            }
        }

        if (state.outputSummary.isNotBlank()) {
            Card(
                Modifier.fillMaxWidth().padding(bottom = Gaps.x1),
                shape = MaterialTheme.shapes.large,
                colors = CardDefaults.cardColors(
                    containerColor = MaterialTheme.colorScheme.surface
                )
            ) {
                Column(Modifier.padding(Gaps.x2), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text(
                        stringResource(R.string.import_summary_title),
                        style = MaterialTheme.typography.labelMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    Text(
                        state.outputSummary,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }
        }
        ImportActionCard(
            // 数据态优先级：导入中 > 空队列 > 未选卡 > 上一条失败 > 可开始
            state = cardStateFor(
                running = state.running,
                queueEmpty = state.queue.isEmpty(),
                noCard = state.cardUri == null,
                kind = state.stageKind
            ),
            stage = state.stage,
            progress = state.progress,
            logLine = state.logLine,
            errorText = state.stageError,
            canceling = state.canceling,
            onStart = onStart,
            onCancel = onCancel,
            modifier = Modifier.padding(bottom = Gaps.x1)
        )
    }
}

@Composable
private fun EmptyState(modifier: Modifier = Modifier) {
    Column(
        modifier.fillMaxWidth(),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center
    ) {
        Box(
            Modifier
                .size(80.dp)
                .clip(CircleShape)
                .background(MaterialTheme.colorScheme.primaryContainer),
            contentAlignment = Alignment.Center
        ) {
            Icon(
                Icons.Rounded.Movie,
                contentDescription = null,
                modifier = Modifier.size(36.dp),
                tint = MaterialTheme.colorScheme.onPrimaryContainer
            )
        }
        Spacer(Modifier.height(Gaps.x2))
        Text(
            stringResource(R.string.empty_queue),
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
            .padding(horizontal = Gaps.x2, vertical = Gaps.x1),
        verticalArrangement = Arrangement.spacedBy(Gaps.x1)
    ) {
        // 机型预设：与桌面端「输出与选项」里的同名下拉对应。
        //   auto = 跟随卡里的真机原片（旧行为），选定机型 = 用该机型的预设参数。
        Card(
            Modifier.fillMaxWidth(),
            shape = MaterialTheme.shapes.large,
            colors = CardDefaults.cardColors(
                containerColor = MaterialTheme.colorScheme.surface
            )
        ) {
            Column(Modifier.padding(Gaps.x2)) {
                Text(
                    stringResource(R.string.settings_model_title),
                    style = MaterialTheme.typography.titleSmall
                )
                Spacer(Modifier.height(6.dp))
                Text(
                    stringResource(R.string.settings_model_desc),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
                Spacer(Modifier.height(8.dp))
                val models = listOf(
                    AppState.MODEL_AUTO to R.string.model_auto,
                    AppState.MODEL_ACE_PRO_2 to R.string.model_ace_pro_2,
                    AppState.MODEL_GO_ULTRA to R.string.model_go_ultra
                )
                models.forEach { (code, labelRes) ->
                    Row(
                        Modifier
                            .fillMaxWidth()
                            .clickable { state.modelOverride = code }
                            .padding(vertical = 4.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        // 整行可点，命中区域比单独点圆钮大得多。
                        RadioButton(
                            selected = state.modelOverride == code,
                            onClick = { state.modelOverride = code }
                        )
                        Text(
                            stringResource(labelRes),
                            style = MaterialTheme.typography.bodyMedium
                        )
                    }
                }
                Spacer(Modifier.height(4.dp))
                Text(
                    stringResource(R.string.settings_model_hint),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        }

        Card(
            Modifier.fillMaxWidth(),
            shape = MaterialTheme.shapes.large,
            colors = CardDefaults.cardColors(
                containerColor = MaterialTheme.colorScheme.surface
            )
        ) {
            Column(Modifier.padding(Gaps.x2)) {
                Text(
                    stringResource(R.string.settings_encoder_title),
                    style = MaterialTheme.typography.titleSmall
                )
                Spacer(Modifier.height(Gaps.x1))
                val encoders = listOf(
                    AppState.ENCODER_AUTO to R.string.encoder_auto,
                    AppState.ENCODER_HW to R.string.encoder_hardware
                )
                SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
                    encoders.forEachIndexed { i, (code, labelRes) ->
                        SegmentedButton(
                            selected = state.encoder == code,
                            onClick = { state.encoder = code },
                            shape = SegmentedButtonDefaults.itemShape(
                                index = i, count = encoders.size
                            ),
                            label = { Text(stringResource(labelRes)) }
                        )
                    }
                }
                Spacer(Modifier.height(8.dp))
                ExpandableSection(
                    title = stringResource(R.string.settings_encoder_diff_title),
                    subtitle = if (state.encoder == AppState.ENCODER_HW) {
                        stringResource(R.string.settings_encoder_current_hw)
                    } else {
                        stringResource(R.string.settings_encoder_current_auto)
                    }
                ) {
                    Text(
                        stringResource(R.string.settings_encoder_diff_body),
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }
        }

        Card(
            Modifier.fillMaxWidth(),
            shape = MaterialTheme.shapes.large,
            colors = CardDefaults.cardColors(
                containerColor = MaterialTheme.colorScheme.surface
            )
        ) {
            ListItem(
                headlineContent = { Text(stringResource(R.string.settings_register_index)) },
                supportingContent = {
                    Text(stringResource(R.string.settings_register_index_desc))
                },
                trailingContent = {
                    Switch(
                        checked = state.registerIndex,
                        onCheckedChange = { state.registerIndex = it }
                    )
                }
            )
        }

        Card(
            Modifier.fillMaxWidth(),
            shape = MaterialTheme.shapes.large,
            colors = CardDefaults.cardColors(
                containerColor = MaterialTheme.colorScheme.surface
            )
        ) {
            Column(
                Modifier.padding(Gaps.x2),
                verticalArrangement = Arrangement.spacedBy(Gaps.x1)
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(
                        Icons.Rounded.Info,
                        contentDescription = null,
                        modifier = Modifier.size(18.dp),
                        tint = MaterialTheme.colorScheme.primary
                    )
                    Spacer(Modifier.size(8.dp))
                    Text(
                        stringResource(R.string.settings_about),
                        style = MaterialTheme.typography.titleSmall
                    )
                }
                Text(
                    stringResource(R.string.settings_version, BuildConfig.VERSION_NAME),
                    style = MaterialTheme.typography.bodyMedium
                )

                val ctx = LocalContext.current
                var engineLine by remember { mutableStateOf("…") }
                LaunchedEffect(Unit) {
                    engineLine = withContext(Dispatchers.IO) { Engine.versionLine(ctx) }
                }
                Text(
                    stringResource(R.string.settings_ffmpeg, engineLine),
                    style = MaterialTheme.typography.bodySmall,
                    color = if (engineLine.startsWith("ffmpeg version"))
                        MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.error
                )

                val py = state.pythonStatus
                if (py == null) {
                    LaunchedEffect(Unit) { state.checkPython(ctx) }
                }
                Text(
                    stringResource(
                        R.string.settings_import_core,
                        py?.text ?: stringResource(R.string.status_not_checked)
                    ),
                    style = MaterialTheme.typography.bodySmall,
                    color = if (py?.ok == true)
                        MaterialTheme.colorScheme.primary
                    else MaterialTheme.colorScheme.onSurfaceVariant
                )

                Text(
                    stringResource(R.string.settings_built_in),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
                HorizontalDivider(Modifier.padding(vertical = 4.dp))

                // 开发者与源码入口
                Text(
                    stringResource(R.string.settings_developer),
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
                Spacer(Modifier.height(4.dp))
                Text(
                    stringResource(R.string.settings_developer_bili),
                    style = MaterialTheme.typography.bodyMedium
                )
                Spacer(Modifier.height(2.dp))
                Text(
                    "GitHub  ·  DUOFreedom",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
                Spacer(Modifier.height(8.dp))
                Text(
                    stringResource(R.string.settings_source_code),
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
                Spacer(Modifier.height(4.dp))
                Text(
                    "github.com/DUOFreedom/Insta-camera-tools",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.primary,
                    modifier = Modifier.clickable {
                        if (!openUrl(ctx, SOURCE_URL)) {
                            onMessage(ctx.getString(R.string.no_browser))
                        }
                    }
                )
                Spacer(Modifier.height(6.dp))
                OutlinedButton(
                    onClick = {
                        if (!openUrl(ctx, SOURCE_URL)) {
                            onMessage(ctx.getString(R.string.no_browser))
                        }
                    },
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Icon(
                        Icons.Rounded.Code,
                        contentDescription = null,
                        modifier = Modifier.size(16.dp)
                    )
                    Spacer(Modifier.size(6.dp))
                    Text(stringResource(R.string.settings_open_repo))
                }
                Spacer(Modifier.height(8.dp))
                Text(
                    stringResource(R.string.settings_license),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )

                // 隐私与许可：应用内可直接查阅全文（随包 assets/docs/ 里的 Markdown）
                HorizontalDivider(Modifier.padding(vertical = 4.dp))
                Row(
                    Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    FilledTonalButton(
                        onClick = {
                            onOpenDoc(
                                "privacy-policy.md",
                                ctx.getString(R.string.doc_privacy_title)
                            )
                        }
                    ) {
                        Text(
                            stringResource(R.string.settings_open_privacy),
                            style = MaterialTheme.typography.labelMedium
                        )
                    }
                    FilledTonalButton(
                        onClick = {
                            onOpenDoc(
                                "open-source-notices.md",
                                ctx.getString(R.string.doc_notices_title)
                            )
                        }
                    ) {
                        Text(
                            stringResource(R.string.settings_open_notices),
                            style = MaterialTheme.typography.labelMedium
                        )
                    }
                }
                Spacer(Modifier.height(4.dp))
                Text(
                    stringResource(R.string.settings_permissions),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        }
    }
}


private fun humanSize(ctx: Context, bytes: Long): String = when {
    bytes <= 0 -> ctx.getString(R.string.size_unknown_full)
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
