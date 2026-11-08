package com.duofreedom.instaace.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.ExperimentalMaterial3ExpressiveApi
import androidx.compose.material3.MaterialExpressiveTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.MotionScheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

private val DarkColors = darkColorScheme(
    primary = Brand,
    onPrimary = BrandDark,
    primaryContainer = BrandContainer,
    onPrimaryContainer = OnBrandContainer,
    secondary = Brand,
    onSecondary = BrandDark,
    background = Ink,
    onBackground = Color0E1620,
    surface = Ink,
    onSurface = Color0E1620,
    surfaceVariant = SurfaceVariant,
    onSurfaceVariant = OnSurfaceVariantLight,
    error = ErrorRed,
    outline = Color0E1620
)

private val LightColors = lightColorScheme(
    primary = Brand,
    onPrimary = Color0E1620,
    primaryContainer = ColorE3F0FF,
    onPrimaryContainer = BrandDark,
    background = ColorF6F8FC,
    onBackground = Ink,
    surface = ColorF6F8FC,
    onSurface = Ink,
    surfaceVariant = ColorE6EAF2,
    onSurfaceVariant = Color4A5262,
    error = ErrorRed
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
fun InstaAceTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    content: @Composable () -> Unit
) {
    MaterialExpressiveTheme(
        colorScheme = if (darkTheme) DarkColors else LightColors,
        motionScheme = MotionScheme.expressive(),
        content = content
    )
}

/** 供不依赖主题的场合取当前配色（例如 Canvas 绘制）。 */
@Composable
fun currentScheme() = MaterialTheme.colorScheme

/** 主题里的强调色常量，避免在界面层散落 hex。 */
object Accent {
    val brand: Color get() = Brand
    val error: Color get() = ErrorRed
}
