package com.duofreedom.instaace.engine

import java.io.ByteArrayOutputStream

/**
 * 影石相机索引（DCIM 下的 .list）的最小 protobuf 实现。
 *
 * 设计要点：meta 以【原始字节】保存，只在需要时按字段号读写。
 * 这样解析→回写是字节级幂等的，不会因为未知字段丢失导致相机不认索引
 * （桌面端 insta_index.py 用同样的策略）。
 */
object Index {

    // ---------------------------------------------------------------- 原语
    private class Field(val num: Int, val wire: Int, val value: ByteArray, val uint: Long)

    private fun readVarint(b: ByteArray, start: Int): Pair<Long, Int> {
        var result = 0L
        var shift = 0
        var i = start
        while (true) {
            val x = b[i].toInt() and 0xFF
            i++
            result = result or ((x and 0x7F).toLong() shl shift)
            if (x and 0x80 == 0) break
            shift += 7
        }
        return result to i
    }

    private fun writeVarint(value: Long): ByteArray {
        var v = value
        val out = ByteArrayOutputStream()
        while (true) {
            val b = (v and 0x7F).toInt()
            v = v ushr 7
            if (v != 0L) out.write(b or 0x80) else {
                out.write(b)
                break
            }
        }
        return out.toByteArray()
    }

    private fun parseFields(buf: ByteArray): List<Field> {
        val out = ArrayList<Field>()
        var i = 0
        while (i < buf.size) {
            val (key, i1) = readVarint(buf, i)
            i = i1
            val num = (key ushr 3).toInt()
            when ((key and 7L).toInt()) {
                0 -> {
                    val (v, i2) = readVarint(buf, i)
                    i = i2
                    out.add(Field(num, 0, ByteArray(0), v))
                }
                2 -> {
                    val (len, i2) = readVarint(buf, i)
                    i = i2
                    val n = len.toInt()
                    out.add(Field(num, 2, buf.copyOfRange(i, i + n), 0))
                    i += n
                }
                1 -> {
                    out.add(Field(num, 1, buf.copyOfRange(i, i + 8), 0))
                    i += 8
                }
                5 -> {
                    out.add(Field(num, 5, buf.copyOfRange(i, i + 4), 0))
                    i += 4
                }
                else -> throw IllegalArgumentException("unsupported wire type at field $num")
            }
        }
        return out
    }

    private fun encodeFields(fields: List<Field>): ByteArray {
        val out = ByteArrayOutputStream()
        for (f in fields) {
            out.write(writeVarint(((f.num.toLong() shl 3) or f.wire.toLong())))
            when (f.wire) {
                0 -> out.write(writeVarint(f.uint))
                2 -> {
                    out.write(writeVarint(f.value.size.toLong()))
                    out.write(f.value)
                }
                else -> out.write(f.value)
            }
        }
        return out.toByteArray()
    }

    private fun encStr(num: Int, s: String): ByteArray {
        val b = s.toByteArray(Charsets.UTF_8)
        return writeVarint(((num.toLong() shl 3) or 2L)) + writeVarint(b.size.toLong()) + b
    }

    private fun encBytes(num: Int, b: ByteArray): ByteArray =
        writeVarint(((num.toLong() shl 3) or 2L)) + writeVarint(b.size.toLong()) + b

    private operator fun ByteArray.plus(o: ByteArray): ByteArray {
        val r = ByteArray(size + o.size)
        System.arraycopy(this, 0, r, 0, size)
        System.arraycopy(o, 0, r, size, o.size)
        return r
    }

    // ---------------------------------------------------------------- 字段读写
    fun fieldStr(meta: ByteArray, num: Int): String? =
        parseFields(meta).firstOrNull { it.num == num && it.wire == 2 }
            ?.value?.toString(Charsets.UTF_8)

    fun fieldUint(meta: ByteArray, num: Int): Long? =
        parseFields(meta).firstOrNull { it.num == num && it.wire == 0 }?.uint

    fun fieldDouble(meta: ByteArray, num: Int): Double? {
        val f = parseFields(meta).firstOrNull { it.num == num && it.wire == 1 } ?: return null
        var bits = 0L
        for (k in 0 until 8) bits = bits or ((f.value[k].toLong() and 0xFF) shl (8 * k))
        return Double.fromBits(bits)
    }

    /** 替换/追加一个 LEN 字段，其余字段原样保留（顺序不变）。 */
    fun withStr(meta: ByteArray, num: Int, value: String): ByteArray {
        val payload = value.toByteArray(Charsets.UTF_8)
        val fields = parseFields(meta).toMutableList()
        val idx = fields.indexOfFirst { it.num == num }
        val nf = Field(num, 2, payload, 0)
        if (idx >= 0) fields[idx] = nf else fields.add(nf)
        return encodeFields(fields)
    }

    /** 替换/追加一个 varint 字段。 */
    fun withUint(meta: ByteArray, num: Int, value: Long): ByteArray {
        val fields = parseFields(meta).toMutableList()
        val idx = fields.indexOfFirst { it.num == num }
        val nf = Field(num, 0, ByteArray(0), value)
        if (idx >= 0) fields[idx] = nf else fields.add(nf)
        return encodeFields(fields)
    }

    // ---------------------------------------------------------------- 条目
    data class FileEntry(val path: String, val meta: ByteArray)

    data class EditEntry(val path: String, val flag: ByteArray)

    fun parseFileInfo(data: ByteArray): List<FileEntry> =
        parseFields(data).filter { it.num == 1 && it.wire == 2 }.map { top ->
            var path = ""
            var meta = ByteArray(0)
            for (f in parseFields(top.value)) {
                when {
                    f.num == 1 && f.wire == 2 -> path = f.value.toString(Charsets.UTF_8)
                    f.num == 2 && f.wire == 2 -> meta = f.value
                }
            }
            FileEntry(path, meta)
        }

    fun buildFileInfo(entries: List<FileEntry>): ByteArray {
        val out = ByteArrayOutputStream()
        for (e in entries) {
            val body = encStr(1, e.path) + encBytes(2, e.meta)
            out.write(encBytes(1, body))
        }
        return out.toByteArray()
    }

    fun parseEditInfo(data: ByteArray): List<EditEntry> =
        parseFields(data).filter { it.num == 1 && it.wire == 2 }.map { top ->
            var path = ""
            var flag = ByteArray(0)
            for (f in parseFields(top.value)) {
                when {
                    f.num == 1 && f.wire == 2 -> path = f.value.toString(Charsets.UTF_8)
                    f.num == 2 && f.wire == 2 -> flag = f.value
                }
            }
            EditEntry(path, flag)
        }

    fun buildEditInfo(entries: List<EditEntry>): ByteArray {
        val out = ByteArrayOutputStream()
        for (e in entries) {
            val body = encStr(1, e.path) + encBytes(2, e.flag)
            out.write(encBytes(1, body))
        }
        return out.toByteArray()
    }

    /**
     * 登记一条媒体（幂等：同 path 先删再加，最后按 path 排序）。
     * 与桌面端 register_media 行为一致。
     */
    fun register(
        fileInfo: ByteArray,
        editInfo: ByteArray,
        path: String,
        meta: ByteArray,
        editFlag: ByteArray = byteArrayOf(0x08, 0x01),
    ): Pair<ByteArray, ByteArray> {
        val fi = parseFileInfo(fileInfo).filter { it.path != path }.toMutableList()
        fi.add(FileEntry(path, meta))
        fi.sortBy { it.path }

        val ei = parseEditInfo(editInfo).filter { it.path != path }.toMutableList()
        ei.add(EditEntry(path, editFlag))
        ei.sortBy { it.path }

        return buildFileInfo(fi) to buildEditInfo(ei)
    }
}
