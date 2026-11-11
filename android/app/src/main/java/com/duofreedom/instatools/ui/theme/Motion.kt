package com.duofreedom.instatools.ui.theme

import androidx.compose.animation.core.SpringSpec
import androidx.compose.animation.core.spring

/**
 * 动效令牌。
 *
 * M3 Expressive 的动效基于弹簧物理，而不是固定时长的插值曲线：
 * 动画目标可以随时被打断，中断后从当前速度继续，不会出现"半路跳变"。
 *
 * Expressive 的令牌分两类：
 * - **Spatial**（位移/尺寸/旋转）刚度更小、回弹更明显，用于展开、收起、页面切换
 * - **Effects**（透明度/颜色）刚度更大、几乎不回弹，用于淡入淡出与颜色过渡
 *
 * 这里的常量与 `ExpressiveMotionTokens` 对齐：
 * ```
 * spatial  fast    damping 0.8  stiffness 380
 * spatial  default damping 0.8  stiffness 380
 * spatial  slow    damping 0.8  stiffness 350
 * effects  fast    damping 1.0  stiffness 3800
 * effects  default damping 1.0  stiffness 1600
 * effects  slow    damping 1.0  stiffness 800
 * ```
 * 不从 `MotionScheme` 直接取，是因为该 API 在部分 material3 版本上是
 * experimental 且签名不稳定；这里给出等价常量，保证一处改、全应用生效。
 */
object Motion {

    /** 阻尼比：位移类 0.8（有轻微回弹），效果类 1.0（不过冲）。 */
    private const val SPATIAL_DAMPING = 0.8f
    private const val EFFECTS_DAMPING = 1.0f

    private const val SPATIAL_FAST_STIFFNESS = 380f
    private const val SPATIAL_DEFAULT_STIFFNESS = 380f
    private const val SPATIAL_SLOW_STIFFNESS = 350f

    private const val EFFECTS_FAST_STIFFNESS = 3800f
    private const val EFFECTS_DEFAULT_STIFFNESS = 1600f

    /** 位移：快速。用于按压反馈、图标微动。 */
    fun <T> spatialFast(): SpringSpec<T> =
        spring(dampingRatio = SPATIAL_DAMPING, stiffness = SPATIAL_FAST_STIFFNESS)

    /** 位移：默认。用于卡片展开/收起、行内高度变化。 */
    fun <T> spatialDefault(): SpringSpec<T> =
        spring(dampingRatio = SPATIAL_DAMPING, stiffness = SPATIAL_DEFAULT_STIFFNESS)

    /** 位移：慢速。用于整页切换、大块区域入场。 */
    fun <T> spatialSlow(): SpringSpec<T> =
        spring(dampingRatio = SPATIAL_DAMPING, stiffness = SPATIAL_SLOW_STIFFNESS)

    /** 效果：快速。用于按下态、选中态。 */
    fun <T> effectsFast(): SpringSpec<T> =
        spring(dampingRatio = EFFECTS_DAMPING, stiffness = EFFECTS_FAST_STIFFNESS)

    /** 效果：默认。用于淡入淡出、颜色过渡。 */
    fun <T> effectsDefault(): SpringSpec<T> =
        spring(dampingRatio = EFFECTS_DAMPING, stiffness = EFFECTS_DEFAULT_STIFFNESS)
}
