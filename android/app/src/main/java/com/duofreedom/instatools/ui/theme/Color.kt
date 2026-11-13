package com.duofreedom.instatools.ui.theme

import androidx.compose.ui.graphics.Color

/**
 * 蓝白色板。
 *
 * 设计约束：只用 Material 3 Expressive 的角色（primary / surfaceContainer …），
 * 界面层不出现裸 hex，换主题只改这里和 [Theme] 里的两套 ColorScheme。
 *
 * 为什么要把每个角色都写死：`lightColorScheme()` 未赋值的角色会落到 M3
 * 基线色（紫 #6750A4 一族）。此前只给了 primary/background/surface 等少数
 * 几个角色，于是 Card（surfaceContainerLow）、NavigationBar（surfaceContainer）、
 * Chip、Switch 的轨道全部取到基线紫，蓝底上突兀地冒出紫色元素——这就是
 * 「配色不协调」的根因。角色补齐后整屏才是一条冷色。
 */


/** 品牌蓝：填充按钮底、选中态、链接。白字对比度 5.9:1。 */
val BluePrimary = Color(0xFF0B5FD0)
val BlueOnPrimary = Color(0xFFFFFFFF)

/** 淡蓝容器：首页主卡、导航选中指示器。 */
val BlueContainer = Color(0xFFD9E8FF)
val BlueOnContainer = Color(0xFF001B3D)

val BlueSecondary = Color(0xFF4A6785)
val BlueOnSecondary = Color(0xFFFFFFFF)
val BlueSecondaryContainer = Color(0xFFD7E4F6)
val BlueOnSecondaryContainer = Color(0xFF0A1D33)

val BlueTertiary = Color(0xFF4B6EA8)
val BlueOnTertiary = Color(0xFFFFFFFF)
val BlueTertiaryContainer = Color(0xFFDCE6F8)
val BlueOnTertiaryContainer = Color(0xFF0B1E38)

val CanvasLight = Color(0xFFEEF3FA)
val InkLight = Color(0xFF0B1B2B)

val SurfaceLight = Color(0xFFFFFFFF)
val SurfaceLowestLight = Color(0xFFFFFFFF)
val SurfaceLowLight = Color(0xFFFFFFFF)
val SurfaceContainerLight = Color(0xFFF6F9FE)
val SurfaceHighLight = Color(0xFFE8EFF8)
val SurfaceHighestLight = Color(0xFFDDE7F4)

val SurfaceVariantLight = Color(0xFFE2E8F2)
val OnSurfaceVariantLight = Color(0xFF47536B)

val OutlineLight = Color(0xFF7A879C)
val OutlineVariantLight = Color(0xFFC9D4E4)

val ErrorLight = Color(0xFFBA1A1A)
val OnErrorLight = Color(0xFFFFFFFF)
val ErrorContainerLight = Color(0xFFFFDAD6)
val OnErrorContainerLight = Color(0xFF410002)


val BluePrimaryDark = Color(0xFFA6C8FF)
val BlueOnPrimaryDark = Color(0xFF00315B)
val BlueContainerDark = Color(0xFF0E4A8F)
val BlueOnContainerDark = Color(0xFFD9E8FF)

val BlueSecondaryDark = Color(0xFFB3C8E3)
val BlueOnSecondaryDark = Color(0xFF1E3248)
val BlueSecondaryContainerDark = Color(0xFF344B63)
val BlueOnSecondaryContainerDark = Color(0xFFD3E2F7)

val BlueTertiaryDark = Color(0xFFAEC7EC)
val BlueOnTertiaryDark = Color(0xFF11294A)
val BlueTertiaryContainerDark = Color(0xFF2B4368)
val BlueOnTertiaryContainerDark = Color(0xFFDAE5FA)

val CanvasDark = Color(0xFF0B1420)
val InkDark = Color(0xFFE4ECF7)

val SurfaceDark = Color(0xFF0F1A28)
val SurfaceLowestDark = Color(0xFF070D16)
val SurfaceLowDark = Color(0xFF121D2C)
val SurfaceContainerDark = Color(0xFF16222F)
val SurfaceHighDark = Color(0xFF1D2A3A)
val SurfaceHighestDark = Color(0xFF253345)

val SurfaceVariantDark = Color(0xFF2A3949)
val OnSurfaceVariantDark = Color(0xFFBFCCDE)

val OutlineDark = Color(0xFF8B97AB)
val OutlineVariantDark = Color(0xFF3A4759)

val ErrorDark = Color(0xFFFFB4AB)
val OnErrorDark = Color(0xFF690005)
val ErrorContainerDark = Color(0xFF93000A)
val OnErrorContainerDark = Color(0xFFFFDAD6)

// 此前界面层与 ImportActionCard 直接引用了这几个名字，保留同义常量，
// 避免为改名去动一排无关文件。

val Brand = BluePrimary
val BrandDark = BlueOnPrimary
val ErrorRed = ErrorLight
val Color0E1620 = InkLight
val Color4A5262 = OnSurfaceVariantLight
val ColorE3F0FF = BlueContainer
val ColorE6EAF2 = SurfaceVariantLight
val ColorF6F8FC = CanvasLight
