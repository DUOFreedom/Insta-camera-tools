package com.duofreedom.instaace.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable

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

@Composable
fun InstaAceTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    content: @Composable () -> Unit
) {
    MaterialTheme(
        colorScheme = if (darkTheme) DarkColors else LightColors,
        content = content
    )
}
