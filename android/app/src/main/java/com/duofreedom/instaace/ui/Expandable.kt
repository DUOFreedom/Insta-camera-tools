package com.duofreedom.instaace.ui

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.expandVertically
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.shrinkVertically
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.ExpandMore
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.duofreedom.instaace.ui.theme.Motion

/**
 * 可展开分组。
 *
 * 动效全部走弹簧：
 * - 内容高度用 [expandVertically] / [shrinkVertically] + [Motion.spatialDefault]
 * - 内容透明度用 [fadeIn] / [fadeOut] + [Motion.effectsDefault]
 * - 箭头旋转用 [animateFloatAsState] + [Motion.spatialFast]
 *
 * 选择 `AnimatedVisibility` 而不是 `animateContentSize`，是因为后者需要
 * 在测量阶段反复触发布局，长列表里会造成频繁重排；前者只动画高度插值。
 */
@Composable
fun ExpandableSection(
    title: String,
    subtitle: String? = null,
    initiallyExpanded: Boolean = false,
    modifier: Modifier = Modifier,
    content: @Composable ColumnScope.() -> Unit
) {
    var expanded by rememberSaveable { mutableStateOf(initiallyExpanded) }
    val arrowAngle by animateFloatAsState(
        targetValue = if (expanded) 180f else 0f,
        animationSpec = Motion.spatialFast(),
        label = "arrow"
    )

    Column(modifier.fillMaxWidth()) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .clickable { expanded = !expanded }
                .padding(vertical = 12.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Column(Modifier.weight(1f)) {
                Text(
                    title,
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.SemiBold
                )
                if (subtitle != null) {
                    Text(
                        subtitle,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }
            Spacer(Modifier.size(8.dp))
            Icon(
                Icons.Rounded.ExpandMore,
                contentDescription = if (expanded) "收起" else "展开",
                modifier = Modifier
                    .size(20.dp)
                    .rotate(arrowAngle),
                tint = MaterialTheme.colorScheme.onSurfaceVariant
            )
        }

        AnimatedVisibility(
            visible = expanded,
            enter = expandVertically(animationSpec = Motion.spatialDefault()) +
                fadeIn(animationSpec = Motion.effectsDefault()),
            exit = shrinkVertically(animationSpec = Motion.spatialDefault()) +
                fadeOut(animationSpec = Motion.effectsDefault())
        ) {
            Column(
                Modifier
                    .fillMaxWidth()
                    .padding(bottom = 8.dp)
            ) {
                content()
            }
        }
    }
}

/**
 * 一次性展开的卡片详情（点击卡片主体切换）。
 *
 * 与 [ExpandableSection] 的区别：这个没有标题栏的固定结构，
 * 用于卡片内部「点一下展开更多说明」。
 */
@Composable
fun ExpandableDetail(
    collapsed: @Composable () -> Unit,
    modifier: Modifier = Modifier,
    initiallyExpanded: Boolean = false,
    expanded: @Composable ColumnScope.() -> Unit
) {
    var open by remember { mutableStateOf(initiallyExpanded) }
    Column(
        modifier
            .fillMaxWidth()
            .clickable { open = !open }
    ) {
        collapsed()
        AnimatedVisibility(
            visible = open,
            enter = expandVertically(animationSpec = Motion.spatialDefault()) +
                fadeIn(animationSpec = Motion.effectsDefault()),
            exit = shrinkVertically(animationSpec = Motion.spatialDefault()) +
                fadeOut(animationSpec = Motion.effectsDefault())
        ) {
            Column(Modifier.fillMaxWidth()) { expanded() }
        }
    }
}
