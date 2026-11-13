package com.duofreedom.instatools.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.ExperimentalMaterial3ExpressiveApi
import androidx.compose.material3.MaterialExpressiveTheme
import androidx.compose.material3.MotionScheme
import androidx.compose.material3.Shapes
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp

/**
 * 浅色方案：蓝白。
 *
 * 角色必须写全。M3 里 Card 取 surfaceContainerLow、NavigationBar 取
 * surfaceContainer、Chip 取 outlineVariant、Switch 未选中轨道取 surfaceVariant
 * ——这些角色不赋值就会落到基线紫，整屏冷色调里混进紫色元素。
 */
private val LightColors = lightColorScheme(
    primary = BluePrimary,
    onPrimary = BlueOnPrimary,
    primaryContainer = BlueContainer,
    onPrimaryContainer = BlueOnContainer,
    secondary = BlueSecondary,
    onSecondary = BlueOnSecondary,
    secondaryContainer = BlueSecondaryContainer,
    onSecondaryContainer = BlueOnSecondaryContainer,
    tertiary = BlueTertiary,
    onTertiary = BlueOnTertiary,
    tertiaryContainer = BlueTertiaryContainer,
    onTertiaryContainer = BlueOnTertiaryContainer,
    background = CanvasLight,
    onBackground = InkLight,
    surface = SurfaceLight,
    onSurface = InkLight,
    surfaceVariant = SurfaceVariantLight,
    onSurfaceVariant = OnSurfaceVariantLight,
    surfaceTint = BluePrimary,
    surfaceBright = SurfaceLight,
    surfaceDim = SurfaceHighestLight,
    surfaceContainerLowest = SurfaceLowestLight,
    surfaceContainerLow = SurfaceLowLight,
    surfaceContainer = SurfaceContainerLight,
    surfaceContainerHigh = SurfaceHighLight,
    surfaceContainerHighest = SurfaceHighestLight,
    outline = OutlineLight,
    outlineVariant = OutlineVariantLight,
    error = ErrorLight,
    onError = OnErrorLight,
    errorContainer = ErrorContainerLight,
    onErrorContainer = OnErrorContainerLight,
    inverseSurface = Color(0xFF22303F),
    inverseOnSurface = Color(0xFFEEF3FA),
    inversePrimary = BluePrimaryDark,
    scrim = Color(0xFF000000)
)

/**
 * 深色方案。
 *
 * 旧版把 background/surface 设成深海军蓝（#0A0E15），onSurface 却写成了
 * #0E1620 —— 同样是近黑的深色，正文在深色背景上读不出来。这里按
 * 「深底浅字」重新配对。
 */
private val DarkColors = darkColorScheme(
    primary = BluePrimaryDark,
    onPrimary = BlueOnPrimaryDark,
    primaryContainer = BlueContainerDark,
    onPrimaryContainer = BlueOnContainerDark,
    secondary = BlueSecondaryDark,
    onSecondary = BlueOnSecondaryDark,
    secondaryContainer = BlueSecondaryContainerDark,
    onSecondaryContainer = BlueOnSecondaryContainerDark,
    tertiary = BlueTertiaryDark,
    onTertiary = BlueOnTertiaryDark,
    tertiaryContainer = BlueTertiaryContainerDark,
    onTertiaryContainer = BlueOnTertiaryContainerDark,
    background = CanvasDark,
    onBackground = InkDark,
    surface = SurfaceDark,
    onSurface = InkDark,
    surfaceVariant = SurfaceVariantDark,
    onSurfaceVariant = OnSurfaceVariantDark,
    surfaceTint = BluePrimaryDark,
    surfaceBright = SurfaceHighestDark,
    surfaceDim = CanvasDark,
    surfaceContainerLowest = SurfaceLowestDark,
    surfaceContainerLow = SurfaceLowDark,
    surfaceContainer = SurfaceContainerDark,
    surfaceContainerHigh = SurfaceHighDark,
    surfaceContainerHighest = SurfaceHighestDark,
    outline = OutlineDark,
    outlineVariant = OutlineVariantDark,
    error = ErrorDark,
    onError = OnErrorDark,
    errorContainer = ErrorContainerDark,
    onErrorContainer = OnErrorContainerDark,
    inverseSurface = Color(0xFFE4ECF7),
    inverseOnSurface = Color(0xFF16222F),
    inversePrimary = BluePrimary,
    scrim = Color(0xFF000000)
)

/**
 * 圆角。
 *
 * M3 Expressive 的形状比 M3 更圆：卡片用 large(22) 而不是默认的 12，
 * 与首页主卡、操作卡的视觉重量才对得上。界面上任何需要圆角的地方
 * 走 MaterialTheme.shapes，不写字面量。
 */
private val AppShapes = Shapes(
    extraSmall = RoundedCornerShape(8.dp),
    small = RoundedCornerShape(12.dp),
    medium = RoundedCornerShape(16.dp),
    large = RoundedCornerShape(22.dp),
    extraLarge = RoundedCornerShape(28.dp)
)

/**
 * 应用主题。
 *
 * 使用 Material 3 Expressive 主题，挂载 [MotionScheme.expressive] 弹簧引擎：
 * 组件的展开/收起、页面切换、点击反馈全部由弹簧物理驱动（阻尼比与刚度
 * 来自 ExpressiveMotionTokens），而不是线性插值，因此动画有轻微回弹、
 * 快速连续操作时不会互相截断。
 */
@OptIn(ExperimentalMaterial3ExpressiveApi::class)
@Composable
fun instatoolsTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    content: @Composable () -> Unit
) {
    MaterialExpressiveTheme(
        colorScheme = if (darkTheme) DarkColors else LightColors,
        motionScheme = MotionScheme.expressive(),
        shapes = AppShapes,
        content = content
    )
}

// 此前的 `currentScheme()` 与 `Accent` 对象没有任何调用点，且 `Accent` 的
// getter 直接读 MaterialTheme（非 @Composable 上下文编译不过）。配色一律从
// MaterialTheme.colorScheme 取，删掉这两个入口。
