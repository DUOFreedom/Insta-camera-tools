package com.duofreedom.instaace.engine

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * 索引层回归测试：用真机导出的 12 个 .list 样本验证字节级幂等。
 *
 * 为什么必须字节级：相机读索引时，任何未知字段丢失都会让条目“看得见但打不开”。
 */
class IndexTest {

    private fun samples(): List<String> {
        val dir = java.io.File("src/test/resources/samples")
        return dir.listFiles()?.filter { it.isFile }?.sortedBy { it.name }?.map { it.name } ?: emptyList()
    }

    private fun bytes(name: String): ByteArray =
        java.io.File("src/test/resources/samples/$name").readBytes()

    @Test
    fun samplesArePresent() {
        assertTrue("样本缺失，测试将失去意义", samples().size >= 10)
    }

    @Test
    fun everySampleRoundTripsByteForByte() {
        val failures = ArrayList<String>()
        for (name in samples()) {
            val data = bytes(name)
            val rebuilt = if (name.contains("fileinfo")) {
                Index.buildFileInfo(Index.parseFileInfo(data))
            } else {
                Index.buildEditInfo(Index.parseEditInfo(data))
            }
            if (!rebuilt.contentEquals(data)) {
                failures.add("$name: ${data.size}B vs ${rebuilt.size}B")
            }
        }
        assertTrue("以下样本往返不一致: $failures", failures.isEmpty())
    }

    @Test
    fun realFileInfoParsesSixEntries() {
        val entries = Index.parseFileInfo(bytes("fileinfo_list.list"))
        assertEquals(6, entries.size)
        assertTrue(entries.all { it.path.startsWith("/DCIM/Camera01/") })
        // 样本里确实存在 meta 为空的 LRV 条目：这就是相机显示 0KB 的成因。
        //   这里把现象写成断言，防止将来又把 LRV 登进索引。
        assertTrue("至少 4 条带 meta", entries.count { it.meta.isNotEmpty() } >= 4)
        assertTrue("存在空 meta 条目（LRV 污染）", entries.any { it.meta.isEmpty() })
    }

    @Test
    fun registerIsIdempotent() {
        val fi0 = bytes("fileinfo_list.list")
        val ei0 = bytes(".editinfo_list.list")
        val meta = Index.parseFileInfo(fi0).first().meta
        val path = "/DCIM/Camera01/VID_20260101_000000_999.mp4"

        val (fi1, ei1) = Index.register(fi0, ei0, path, meta)
        val (fi2, ei2) = Index.register(fi1, ei1, path, meta)

        assertArrayEquals("重复登记不应改变 fileinfo", fi1, fi2)
        assertArrayEquals("重复登记不应改变 editinfo", ei1, ei2)
        assertEquals(1, Index.parseFileInfo(fi1).count { it.path == path })
    }

    @Test
    fun registerKeepsExistingEntries() {
        val fi0 = bytes("fileinfo_list.list")
        val before = Index.parseFileInfo(fi0).map { it.path }.toSet()
        val meta = Index.parseFileInfo(fi0).first().meta

        val (fi1, _) = Index.register(fi0, ByteArray(0), "/DCIM/Camera01/VID_20260101_000000_998.mp4", meta)
        val after = Index.parseFileInfo(fi1).map { it.path }.toSet()

        assertTrue("原有条目不能丢", after.containsAll(before))
        assertEquals(before.size + 1, after.size)
    }

    @Test
    fun settingTimestampTouchesOnlyThatField() {
        val meta = Index.parseFileInfo(bytes("fileinfo_list.list")).first().meta
        val old = Index.fieldUint(meta, 7)
        assertNotNull("样本里应存在 f7", old)

        val patched = Index.withUint(meta, 7, 20261016104229L)
        assertEquals(20261016104229L, Index.fieldUint(patched, 7))
        assertEquals("其它字段必须原样保留", meta.size, patched.size)
    }

    @Test
    fun pathStringSurvivesRoundTrip() {
        val fi = Index.parseFileInfo(bytes("fileinfo_list.list"))
        val rebuilt = Index.buildFileInfo(fi)
        val again = Index.parseFileInfo(rebuilt)
        assertEquals(fi.map { it.path }, again.map { it.path })
        assertArrayEquals(fi[0].meta, again[0].meta)
    }
}
