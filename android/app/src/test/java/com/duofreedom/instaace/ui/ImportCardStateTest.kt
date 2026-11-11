package com.duofreedom.instatools.ui

import org.junit.Assert.assertEquals
import org.junit.Test

/**
 * 导入操作卡的状态推导。
 *
 * 渲染没法在无设备环境下测，但「哪个状态压过哪个」是纯逻辑，值得钉住：
 * 导入中点取消时界面必须仍显示 Loading（不能跳回 Ready 让按钮重新可点），
 * 而失败文案的判定依赖 stage 前缀「失败」—— 这两条改坏了，用户看到的是
 * 一个点了没反应或者失败后还能再点的按钮。
 */
class ImportCardStateTest {

    @Test
    fun runningWinsOverEverything() {
        // 导入中即使队列为空、卡已选、上一条是失败，也必须显示 Loading
        assertEquals(
            ImportCardState.Loading,
            cardStateFor(running = true, queueEmpty = true, noCard = true, stage = "失败：x")
        )
    }

    @Test
    fun emptyQueueBeforeCardCheck() {
        // 没有视频时提示「先添加视频」，比「请先选择存储卡」更贴合用户下一步
        assertEquals(
            ImportCardState.Empty,
            cardStateFor(running = false, queueEmpty = true, noCard = true, stage = "")
        )
    }

    @Test
    fun noCardIsDisabled() {
        assertEquals(
            ImportCardState.Disabled,
            cardStateFor(running = false, queueEmpty = false, noCard = true, stage = "")
        )
    }

    @Test
    fun failureStageIsError() {
        assertEquals(
            ImportCardState.Error,
            cardStateFor(
                running = false, queueEmpty = false, noCard = false,
                stage = "失败：缓存空间不足"
            )
        )
    }

    @Test
    fun readyWhenEverythingIsInPlace() {
        assertEquals(
            ImportCardState.Ready,
            cardStateFor(
                running = false, queueEmpty = false, noCard = false,
                stage = "全部完成"
            )
        )
    }

    @Test
    fun canceledStageIsNotError() {
        // 「已取消」不是失败：按钮应该回到可开始，而不是变成「重新导入」
        assertEquals(
            ImportCardState.Ready,
            cardStateFor(
                running = false, queueEmpty = false, noCard = false,
                stage = "已取消（已完成的 1 条已写回卡）"
            )
        )
    }
}
