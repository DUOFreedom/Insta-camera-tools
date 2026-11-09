package com.duofreedom.instaace.ui

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.spring
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.scaleIn
import androidx.compose.animation.scaleOut
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Close
import androidx.compose.material.icons.rounded.ErrorOutline
import androidx.compose.material.icons.rounded.PlayArrow
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import com.duofreedom.instaace.ui.theme.InstaAceTheme
import kotlinx.coroutines.delay

/**
 * 导入操作卡：把「队列为空 / 未选卡 / 可开始 / 导入中 / 失败」五种数据状态
 * 收进一张卡片，外加按下反馈构成第六态。
 *
 * 与 [com.duofreedom.instaace.ui.theme.Motion] 的关系：项目主题用 Expressive
 * 阻尼 0.8 / 刚度 380（位移）与 1.0 / 1600（效果）；本组件按设计稿要求改为
 * 0.75 / 400 与 1.0 / 500 —— 位移回弹更明显一点，效果更快收尾。差异只在本
 * 组件内，不动全局令牌。
 */
enum class ImportCardState {
    /** 队列里一个视频都没有。 */
    Empty,

    /** 有视频但还没选存储卡，主按钮不可点。 */
    Disabled,

    /** 可开始导入。 */
    Ready,

    /** 导入进行中（含「正在取消」）。 */
    Loading,

    /** 上一次导入失败。 */
    Error
}

private object Space {
    val s1 = 8.dp
    val s2 = 16.dp
}

/** 位移/缩放的弹簧：阻尼 0.75 略带回弹，刚度 400 收得干脆。 */
private val SpatialSpring = spring<Float>(dampingRatio = 0.75f, stiffness = 400f)

/** 透明度/颜色的弹簧：阻尼 1.0 不过冲，刚度 500 比位移更快落定。 */
private val EffectsSpring = spring<Float>(dampingRatio = 1f, stiffness = 500f)

/** 子元素错峰间隔。40ms 落在 30–50ms 区间中间。 */
private const val STAGGER_MS = 40L

@Composable
fun ImportActionCard(
    state: ImportCardState,
    stage: String,
    progress: Float,
    logLine: String,
    errorText: String,
    canceling: Boolean,
    onStart: () -> Unit,
    onCancel: () -> Unit,
    modifier: Modifier = Modifier
) {
    // 进度条不直接吃 progress：导入时进度每 250ms 才刷新一次，
    //   直接赋值会一跳一跳；弹簧补间把它拉成连续移动。
    //   用 effects 弹簧而不是 spatial，因为过冲会把进度条顶过 1.0。
    val animatedProgress by animateFloatAsState(
        targetValue = progress.coerceIn(0f, 1f),
        animationSpec = EffectsSpring,
        label = "cardProgress"
    )

    Card(
        modifier = modifier.fillMaxWidth(),
        shape = MaterialTheme.shapes.extraLarge,
        colors = CardDefaults.cardColors(
            containerColor = when (state) {
                ImportCardState.Error -> MaterialTheme.colorScheme.errorContainer
                else -> MaterialTheme.colorScheme.surfaceVariant
            }
        )
    ) {
        Column(Modifier.padding(Space.s2), verticalArrangement = Arrangement.spacedBy(Space.s1)) {

            // ── empty：队列为空。占位由调用方的列表区负责（大图标 + 引导文案），
            //    这里只把主按钮标成「先添加视频」并禁用，避免同一句话出现两次。
            // ──────────────────────────────────────────────────────────

            // ── loading：进度 + 阶段文字 + 实时日志，逐项错峰入场 ────────
            StaggeredIn(index = 0, visible = state == ImportCardState.Loading) {
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        stage,
                        style = MaterialTheme.typography.labelMedium,
                        modifier = Modifier.weight(1f),
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis
                    )
                    Text(
                        "${(animatedProgress * 100).toInt()}%",
                        style = MaterialTheme.typography.labelMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }
            StaggeredIn(index = 1, visible = state == ImportCardState.Loading) {
                LinearProgressIndicator(
                    progress = { animatedProgress },
                    modifier = Modifier.fillMaxWidth().height(Space.s1)
                )
            }
            StaggeredIn(index = 2, visible = state == ImportCardState.Loading && logLine.isNotBlank()) {
                Text(
                    logLine,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    maxLines = 3,
                    overflow = TextOverflow.Ellipsis
                )
            }

            // ── error：错误文案区 + 主按钮变成「重新导入」────────────────
            StaggeredIn(index = 0, visible = state == ImportCardState.Error) {
                Row(verticalAlignment = Alignment.Top) {
                    Icon(
                        Icons.Rounded.ErrorOutline,
                        contentDescription = null,
                        modifier = Modifier.size(Space.s2),
                        tint = MaterialTheme.colorScheme.onErrorContainer
                    )
                    Spacer(Modifier.size(Space.s1))
                    Text(
                        errorText.ifBlank { "导入失败，详情见下方日志" },
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onErrorContainer
                    )
                }
            }

            Spacer(Modifier.height(Space.s1))

            // ── default / pressed / disabled / loading 共用这一颗主按钮 ──
            PrimaryAction(
                state = state,
                canceling = canceling,
                onStart = onStart,
                onCancel = onCancel
            )
        }
    }
}

@Composable
private fun PrimaryAction(
    state: ImportCardState,
    canceling: Boolean,
    onStart: () -> Unit,
    onCancel: () -> Unit
) {
    // 按下态：Animatable 只负责一个缩放标量，animateTo 走空间弹簧。
    //   不用 indicator 的默认 ripple 缩放，因为那颗是 tween。
    val interaction = remember { MutableInteractionSource() }
    val pressed by interaction.collectIsPressedAsState()
    val pressScale = remember { Animatable(1f) }

    LaunchedEffect(pressed) {
        pressScale.animateTo(
            targetValue = if (pressed) 0.96f else 1f,
            animationSpec = SpatialSpring
        )
    }

    // 缩放只走 graphicsLayer，且值在 lambda 里读 —— 不触发重组，只在绘制阶段生效。
    val scaleModifier = Modifier.graphicsLayer {
        scaleX = pressScale.value
        scaleY = pressScale.value
    }

    val loading = state == ImportCardState.Loading
    // disabled：没选卡，或有视频但状态不允许开始
    val enabled = when (state) {
        ImportCardState.Ready -> true
        ImportCardState.Error -> true
        ImportCardState.Loading -> !canceling
        ImportCardState.Disabled, ImportCardState.Empty -> false
    }

    if (loading) {
        OutlinedButton(
            onClick = onCancel,
            enabled = enabled,
            interactionSource = interaction,
            modifier = scaleModifier.fillMaxWidth().height(52.dp),
            shape = RoundedCornerShape(percent = 50)
        ) {
            Icon(Icons.Rounded.Close, contentDescription = null, modifier = Modifier.size(Space.s2))
            Spacer(Modifier.size(Space.s1))
            Text(if (canceling) "正在取消…" else "取消导入")
        }
    } else {
        Button(
            onClick = onStart,
            enabled = enabled,
            interactionSource = interaction,
            modifier = scaleModifier.fillMaxWidth().height(52.dp),
            shape = RoundedCornerShape(percent = 50),
            colors = ButtonDefaults.buttonColors(
                containerColor = if (state == ImportCardState.Error) {
                    MaterialTheme.colorScheme.error
                } else {
                    MaterialTheme.colorScheme.primary
                }
            )
        ) {
            Icon(
                if (state == ImportCardState.Error) Icons.Rounded.ErrorOutline else Icons.Rounded.PlayArrow,
                contentDescription = null
            )
            Spacer(Modifier.size(Space.s1))
            Text(
                when (state) {
                    ImportCardState.Empty -> "先添加视频"
                    ImportCardState.Disabled -> "请先选择存储卡"
                    ImportCardState.Error -> "重新导入"
                    else -> "开始导入"
                }
            )
        }
    }
}

/**
 * 错峰入场：每个子项按 index 延后 [STAGGER_MS] 再打开 AnimatedVisibility。
 *
 * 用「延迟后再切 visible」而不是给 tween 加 delayMillis —— 后者是固定时长动画，
 * 与「全部动画走弹簧」的约束冲突。
 */
@Composable
private fun StaggeredIn(
    index: Int,
    visible: Boolean,
    content: @Composable () -> Unit
) {
    var shown by remember { mutableStateOf(false) }

    LaunchedEffect(visible) {
        if (visible) {
            delay(index * STAGGER_MS)
            shown = true
        } else {
            shown = false
        }
    }

    AnimatedVisibility(
        visible = shown,
        enter = fadeIn(animationSpec = EffectsSpring) +
            scaleIn(animationSpec = EffectsSpring, initialScale = 0.92f),
        exit = fadeOut(animationSpec = EffectsSpring) +
            scaleOut(animationSpec = EffectsSpring, targetScale = 0.92f)
    ) {
        content()
    }
}

// ── 预览：五个数据态各一张 ────────────────────────────────────────────

@Preview(name = "空状态", showBackground = true)
@Composable
private fun PreviewEmpty() {
    InstaAceTheme {
        ImportActionCard(
            state = ImportCardState.Empty,
            stage = "", progress = 0f, logLine = "", errorText = "", canceling = false,
            onStart = {}, onCancel = {}
        )
    }
}

@Preview(name = "未选卡", showBackground = true)
@Composable
private fun PreviewDisabled() {
    InstaAceTheme {
        ImportActionCard(
            state = ImportCardState.Disabled,
            stage = "", progress = 0f, logLine = "", errorText = "", canceling = false,
            onStart = {}, onCancel = {}
        )
    }
}

@Preview(name = "可开始", showBackground = true)
@Composable
private fun PreviewReady() {
    InstaAceTheme {
        ImportActionCard(
            state = ImportCardState.Ready,
            stage = "", progress = 0f, logLine = "", errorText = "", canceling = false,
            onStart = {}, onCancel = {}
        )
    }
}

@Preview(name = "导入中", showBackground = true)
@Composable
private fun PreviewLoading() {
    InstaAceTheme {
        ImportActionCard(
            state = ImportCardState.Loading,
            stage = "第 2/3 条 · 编码 VID",
            progress = 0.42f,
            logLine = "frame= 812 fps= 58 q=28.0 size= 12288kB time=00:00:14.00",
            errorText = "",
            canceling = false,
            onStart = {}, onCancel = {}
        )
    }
}

@Preview(name = "失败", showBackground = true)
@Composable
private fun PreviewError() {
    InstaAceTheme {
        ImportActionCard(
            state = ImportCardState.Error,
            stage = "",
            progress = 0f,
            logLine = "",
            errorText = "卡结构不完整：需要 DCIM/Camera01 与一对真机 VID_/LRV_ 原片",
            canceling = false,
            onStart = {}, onCancel = {}
        )
    }
}

@Preview(name = "深色 · 导入中", showBackground = true)
@Composable
private fun PreviewLoadingDark() {
    InstaAceTheme(darkTheme = true) {
        ImportActionCard(
            state = ImportCardState.Loading,
            stage = "第 1/2 条 · 移植 inst box",
            progress = 0.78f,
            logLine = "[移植] VID_20261109_183000_000.mp4",
            errorText = "",
            canceling = true,
            onStart = {}, onCancel = {}
        )
    }
}
