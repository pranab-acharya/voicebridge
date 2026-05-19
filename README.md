# VoiceBridge

Android app that captures phone call audio and streams it over USB to a laptop for real-time, local speech-to-text transcription — zero cloud, zero deployment.

[![Build VoiceBridge APK](https://github.com/pranab-acharya/voicebridge/actions/workflows/build.yml/badge.svg)](https://github.com/pranab-acharya/voicebridge/actions/workflows/build.yml)

---

## What it does

```
Phone call audio
       │
       ▼
VOICE_COMMUNICATION AudioRecord (16kHz mono)
       │
       ▼
Lock-free ring buffer (C, 32 slots × 320 samples)
       │
       ▼
Opus encoder via JNI (16kbps, DTX, complexity 3)
       │
       ▼
Custom binary packet stream over AOAv2 USB
       │
       ▼
Laptop daemon → local Whisper STT → ATS text field
```

- Detects when a call starts using `READ_PHONE_STATE`
- Captures audio from the `VOICE_COMMUNICATION` source (echo-cancelled, far-end suppressed)
- Encodes with Opus in a C JNI hot path — target < 12 MB RAM, < 4% CPU
- Streams encoded audio over USB to a laptop daemon using Android Open Accessory v2 (AOAv2)
- Laptop daemon (separate repo) runs Whisper STT locally and delivers transcript
- Recruiter can also trigger a call from the laptop via ADB or the AOAv2 control channel

---

## Architecture

### Thread model

| Thread | Role |
|---|---|
| `AudioCaptureThread` | Reads 320-sample frames from `AudioRecord` into the ring buffer |
| `OpusEncoderThread` | Drains the ring buffer, Opus-encodes each frame, pushes to encoded queue |
| `UsbWriteThread` | Pops encoded frames from the queue, wraps in packets, writes to USB |

### Packet protocol

Every packet sent over USB uses this binary layout:

```
┌─────────┬──────┬─────────┬─────────┬─────────────┐
│ MAGIC   │ TYPE │ SEQ_ID  │ LENGTH  │ PAYLOAD     │
│ 4 bytes │ 1 B  │ 4 bytes │ 4 bytes │ LENGTH bytes│
└─────────┴──────┴─────────┴─────────┴─────────────┘
  "VBRG"           big-endian uint32
```

| Type | Value | Direction | Description |
|---|---|---|---|
| `AUDIO_FRAME` | `0x01` | phone → laptop | Opus-encoded audio frame |
| `CALL_START`  | `0x02` | phone → laptop | Call began; payload = phone number (UTF-8) |
| `CALL_END`    | `0x03` | phone → laptop | Call ended |
| `HEARTBEAT`   | `0x04` | phone → laptop | Keep-alive every 2 s |
| `CONTROL`     | `0x05` | laptop → phone | Dial / hangup command |
| `METADATA`    | `0x06` | phone → laptop | Reserved for future use |

### Native layer (C/C++ via JNI)

| File | Purpose |
|---|---|
| `ring_buffer.h` | Lock-free SPSC ring buffer using `std::atomic<uint32_t>` |
| `opus_jni.cpp` | JNI bridge — init/destroy encoder, ring buffer read/write, encode frame |

Opus settings: 16 kHz · mono · VOIP mode · 16 kbps · DTX on · complexity 3

---

## Getting the APK

Every push to `main` builds a debug APK via GitHub Actions — no Android Studio needed.

1. Go to [Actions → Build VoiceBridge APK](https://github.com/pranab-acharya/voicebridge/actions/workflows/build.yml)
2. Click the latest successful run
3. Download the `voicebridge-debug-<run#>` artifact

---

## Permissions

| Permission | Why |
|---|---|
| `RECORD_AUDIO` | Capture call audio |
| `READ_PHONE_STATE` | Detect call start / end |
| `CALL_PHONE` | Dial from laptop command |
| `ANSWER_PHONE_CALLS` | Answer / end calls |
| `FOREGROUND_SERVICE` + `FOREGROUND_SERVICE_MICROPHONE` | Keep service alive with mic |
| `RECEIVE_BOOT_COMPLETED` | Auto-start after reboot |
| `REQUEST_IGNORE_BATTERY_OPTIMIZATIONS` | Prevent OS from killing the service |
| `WAKE_LOCK` | Keep CPU alive during a call |

---

## USB accessory setup (AOAv2)

The phone acts as the USB device; the laptop acts as the AOAv2 accessory. The laptop daemon must identify itself during the AOA handshake with:

```
manufacturer = "VoiceBridge"
model        = "LaptopDaemon"
version      = "1.0"
```

When the cable is connected the app launches automatically via the `USB_ACCESSORY_ATTACHED` intent filter.

---

## Edge cases handled

| Scenario | Handling |
|---|---|
| Battery optimisation kills service | Request exemption on first launch; `START_STICKY` + `BootReceiver` |
| Another app steals `AudioRecord` | Detect `ERROR_DEAD_OBJECT`; service stops and `START_STICKY` restarts it |
| USB disconnected mid-call | `UsbWriteThread` detects `IOException`, clears stream, retries `connectToAccessory()` every second |
| Call waiting / hold | `CallStateReceiver` pauses capture on `RINGING` while `OFFHOOK` |
| Ring buffer overflow | Frame is dropped and logged; encoder thread is never blocked |

---

## Build setup

| Component | Version |
|---|---|
| Android NDK | 26.3.11579264 |
| CMake | 3.22.1 |
| libopus | v1.3.1 (fetched from GitHub via CMake FetchContent) |
| Gradle | 8.7 |
| AGP | 8.3.2 |
| Kotlin | 1.9.23 |
| Min SDK | 26 (Android 8.0) |
| Target SDK | 34 (Android 14) |
| ABI targets | arm64-v8a · armeabi-v7a · x86_64 |

---

## Project structure

```
voicebridge/
├── app/
│   ├── CMakeLists.txt                  # Native build; fetches libopus
│   └── src/main/
│       ├── cpp/
│       │   ├── ring_buffer.h           # Lock-free SPSC ring buffer
│       │   └── opus_jni.cpp            # JNI bridge
│       ├── kotlin/com/voicebridge/
│       │   ├── MainActivity.kt         # Permission requests + service start
│       │   ├── VoiceBridgeService.kt   # Foreground service orchestrator
│       │   ├── AudioCaptureThread.kt   # AudioRecord → ring buffer
│       │   ├── OpusEncoderThread.kt    # Ring buffer → encoded queue
│       │   ├── UsbWriteThread.kt       # Encoded queue → USB
│       │   ├── UsbAccessoryManager.kt  # AOAv2 open/close + control reader
│       │   ├── CallStateReceiver.kt    # Phone state broadcast receiver
│       │   ├── BootReceiver.kt         # Auto-start on boot
│       │   ├── PacketProtocol.kt       # Packet build / parse
│       │   └── NativeBridge.kt         # JNI declarations
│       ├── res/
│       │   └── xml/usb_accessory_filter.xml
│       └── AndroidManifest.xml
└── .github/workflows/build.yml         # CI: builds debug APK, uploads artifact
```

---

## Roadmap

- [ ] Laptop daemon (Python): AOAv2 USB host → Opus decode → Whisper STT → ATS injection
- [ ] Voice activity detection to suppress hold music
- [ ] Release APK signing workflow
- [ ] ADB fallback transport (no AOAv2 driver needed on laptop)
