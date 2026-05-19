"""
VoiceBridge binary packet protocol.

Wire format (big-endian):
  MAGIC   4 B  "VBRG"
  TYPE    1 B
  SEQ_ID  4 B  uint32
  LENGTH  4 B  uint32  — payload byte count
  PAYLOAD LENGTH B
"""
import struct
from dataclasses import dataclass
from typing import Optional

MAGIC       = b"VBRG"
HEADER_SIZE = 13  # 4+1+4+4

TYPE_AUDIO_FRAME = 0x01
TYPE_CALL_START  = 0x02
TYPE_CALL_END    = 0x03
TYPE_HEARTBEAT   = 0x04
TYPE_CONTROL     = 0x05
TYPE_METADATA    = 0x06

TYPE_NAMES = {
    TYPE_AUDIO_FRAME: "AUDIO_FRAME",
    TYPE_CALL_START:  "CALL_START",
    TYPE_CALL_END:    "CALL_END",
    TYPE_HEARTBEAT:   "HEARTBEAT",
    TYPE_CONTROL:     "CONTROL",
    TYPE_METADATA:    "METADATA",
}

# Control sub-commands (laptop → phone)
CTRL_DIAL   = 0x01
CTRL_HANGUP = 0x02


@dataclass
class Packet:
    type:    int
    seq_id:  int
    payload: bytes

    @property
    def type_name(self) -> str:
        return TYPE_NAMES.get(self.type, f"UNKNOWN(0x{self.type:02x})")


def parse_packet(data: bytes) -> Optional[Packet]:
    if len(data) < HEADER_SIZE or data[:4] != MAGIC:
        return None
    pkt_type = data[4]
    seq_id   = struct.unpack_from(">I", data, 5)[0]
    length   = struct.unpack_from(">I", data, 9)[0]
    if len(data) < HEADER_SIZE + length:
        return None
    return Packet(type=pkt_type, seq_id=seq_id,
                  payload=data[HEADER_SIZE: HEADER_SIZE + length])


def build_packet(pkt_type: int, seq_id: int, payload: bytes = b"") -> bytes:
    return MAGIC + bytes([pkt_type]) + struct.pack(">II", seq_id, len(payload)) + payload


def build_dial(seq_id: int, number: str) -> bytes:
    return build_packet(TYPE_CONTROL, seq_id,
                        bytes([CTRL_DIAL]) + number.encode("utf-8"))


def build_hangup(seq_id: int) -> bytes:
    return build_packet(TYPE_CONTROL, seq_id, bytes([CTRL_HANGUP]))
