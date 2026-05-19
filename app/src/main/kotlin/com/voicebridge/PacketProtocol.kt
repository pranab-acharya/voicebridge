package com.voicebridge

import java.nio.ByteBuffer
import java.nio.ByteOrder

object PacketProtocol {
    // "VBRG"
    private val MAGIC = byteArrayOf(0x56, 0x42, 0x52, 0x47.toByte())

    const val TYPE_AUDIO_FRAME: Byte = 0x01
    const val TYPE_CALL_START:  Byte = 0x02
    const val TYPE_CALL_END:    Byte = 0x03
    const val TYPE_HEARTBEAT:   Byte = 0x04
    const val TYPE_CONTROL:     Byte = 0x05
    const val TYPE_METADATA:    Byte = 0x06

    // Header: MAGIC(4) + TYPE(1) + SEQ_ID(4) + LENGTH(4) = 13 bytes
    fun buildPacket(type: Byte, seqId: Int, payload: ByteArray): ByteArray {
        val buf = ByteBuffer.allocate(13 + payload.size).order(ByteOrder.BIG_ENDIAN)
        buf.put(MAGIC)
        buf.put(type)
        buf.putInt(seqId)
        buf.putInt(payload.size)
        buf.put(payload)
        return buf.array()
    }

    fun buildHeartbeat(seqId: Int): ByteArray =
        buildPacket(TYPE_HEARTBEAT, seqId, ByteArray(0))

    fun buildCallStart(seqId: Int, phoneNumber: String): ByteArray =
        buildPacket(TYPE_CALL_START, seqId, phoneNumber.toByteArray(Charsets.UTF_8))

    fun buildCallEnd(seqId: Int): ByteArray =
        buildPacket(TYPE_CALL_END, seqId, ByteArray(0))

    fun parseControlPacket(data: ByteArray): ControlCommand? {
        if (data.size < 13) return null
        val buf = ByteBuffer.wrap(data).order(ByteOrder.BIG_ENDIAN)
        val magic = ByteArray(4).also { buf.get(it) }
        if (!magic.contentEquals(MAGIC)) return null
        if (buf.get() != TYPE_CONTROL) return null
        buf.getInt()  // seqId — ignored for commands
        val length = buf.getInt()
        if (length <= 0 || length > data.size - 13) return null
        val payload = ByteArray(length).also { buf.get(it) }
        return ControlCommand.fromBytes(payload)
    }
}

sealed class ControlCommand {
    data class Dial(val number: String) : ControlCommand()
    object Hangup : ControlCommand()

    companion object {
        // payload[0]: 0x01 = dial, 0x02 = hangup
        fun fromBytes(bytes: ByteArray): ControlCommand? {
            if (bytes.isEmpty()) return null
            return when (bytes[0].toInt()) {
                0x01 -> Dial(String(bytes, 1, bytes.size - 1, Charsets.UTF_8))
                0x02 -> Hangup
                else -> null
            }
        }
    }
}
