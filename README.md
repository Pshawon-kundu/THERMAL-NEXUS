# ESP32 LoRa GPS Telemetry

A reliable point-to-point telemetry link between two ESP32 DevKit V1 boards using
Ra-02 (SX1278) LoRa modules and a u-blox NEO-M8N GPS on the transmitter.

```
 transmitter (LoRa TX)  ----LoRa---->  receiver (LoRa RX)  -> USB serial on PC
 NEO-M8N GPS -> Serial2                       |
     |                                         +--- sends ACK back to TX
     +-- sends GPS telemetry packet        ACK carries the receiver-measured RSSI/SNR
```

- Transmitter ESP32 on **COM4**
- Receiver ESP32 on **COM10**
- Both USB debug serials at **115200 baud**

## Hardware wiring (both boards identical for LoRa)

Ra-02 SX1278 <-> ESP32 DevKit V1 (all boards):

| SX1278   | ESP32       |
|----------|-------------|
| VCC      | 3V3         |
| GND      | GND         |
| MOSI     | GPIO23      |
| MISO     | GPIO19      |
| SCK      | GPIO18      |
| NSS/CS   | GPIO5 (`LORA_SS`)  |
| RST      | GPIO14 (`LORA_RST`)|
| DIO0     | GPIO2  (`LORA_DIO0`)|

> SPI pins are the ESP32 default **VSPI** (MOSI=23, MISO=19, SCK=18) and must not be changed.

NEO-M8N GPS <-> Transmitter ESP32:

| GPS  | ESP32      |
|------|------------|
| TX   | GPIO16 (`Serial2` RX) |
| RX   | GPIO17 (`Serial2` TX) |

- GPS UART `GPS_BAUD = 9600` (easily changeable constant at the top of the
  transmitter code; the NEO-M8N can later be re-configured to 115200).

## LoRa configuration

Both transmitter and receiver use IDENTICAL settings (defined near the top of
each `main.cpp`):

| Parameter      | Value     |
|----------------|-----------|
| Frequency      | 433 MHz (`433E6`) |
| Spreading Factor | 7        |
| Bandwidth      | 125 kHz   |
| Coding Rate    | 4/5 (`setCodingRate4(5)`) |
| TX power       | 17 dBm (not maximized; SX1278 PA_BOOST) |
| Preamble       | 8 symbols  |
| Sync word      | 0x12 (LoRa default) |
| CRC            | enabled   |

## Packet protocol

Compact comma-separated, shared by both ends (see `common/include/packet_format.h`).

**GPS telemetry packet (TX -> RX)**
```
GPS,<seq>,<valid>,<lat>,<lng>,<date>,<time>,<sats>,<hdop>
GPS,105,1,23.780573,90.407113,2026-08-10,06:35:20,11,0.92
```
- `seq`   ? sequence number (increments each transmitted packet)
- `valid` ? `1` if GPS has a fix, `0` = **NO FIX** (coordinates then marked invalid, not claimed valid)
- `lat/lng` ? signed decimal degrees, 6 decimals
- `date` ? UTC `YYYY-MM-DD` (`0000-00-00` when unavailable)
- `time` ? UTC `HH:MM:SS`  (`00:00:00` when unavailable)
- `sats` ? number of satellites
- `hdop` ? HDOP

**ACK packet (RX -> TX)**
```
ACK,<seq>,<rxRssi>,<rxSnr>,<rxQuality>
ACK,105,-72,8.25,91
```
- `seq`       ? sequence being acknowledged
- `rxRssi`    ? telemetry packet RSSI measured **by the receiver** (dBm)
- `rxSnr`     ? telemetry packet SNR measured **by the receiver** (dB)
- `rxQuality` ? receiver-computed signal quality (0-100 %)

Parsing is defensive: malformed packets are rejected and never crash the firmware.

## Signal diagnostics

- **RSSI** (dBm) and **SNR** (dB) are receive-side measurements. The receiver
  measures them for each telemetry packet; the transmitter measures them for each
  ACK packet. There is no transmitter-RSSI for the outgoing telemetry packet.
- **Signal quality %** is a clearly described USER-FRIENDLY HEURISTIC, NOT an
  absolute RF measurement. See `common/src/signal_quality.cpp`:
  - RSSI normalized -120 dBm (poor) ... -40 dBm (excellent)
  - SNR  normalized  -20 dB   (poor) ... +10 dB  (excellent)
  - result = 0.6 * RSSI score + 0.4 * SNR score, clamped 0-100.

Quality categories (centralized in `signal_quality.h/.cpp`):

| Score   | Category  |
|---------|-----------|
| 90-100  | Excellent |
| 75-89   | Very Good |
| 60-74   | Good      |
| 40-59   | Fair      |
| 20-39   | Weak      |
| 0-19    | Very Weak |

## Statistics

**Receiver** (via sequence-number gaps):
- packets received, last sequence, estimated lost packets, total expected,
  packet reception rate %.

**Transmitter**:
- packets sent, ACKs received, ACK timeouts, ACK success %.

Sequence gap example: receiving seq 10, 11, then 14 -> packets 12, 13 estimated lost.

## Project layout

```
.
??? common/                       # shared library (both projects)
?   ??? library.json
?   ??? include/
?   ?   ??? packet_format.h       # packet protocol
?   ?   ??? signal_quality.h      # quality heuristic thresholds
?   ??? src/
?       ??? packet_format.cpp
?       ??? signal_quality.cpp
??? transmitter/                  # PlatformIO project -> COM4
?   ??? platformio.ini
?   ??? src/main.cpp
??? receiver/                     # PlatformIO project -> COM10
?   ??? platformio.ini
?   ??? src/main.cpp
??? tools/
?   ??? dual_serial_monitor.py    # PC dual COM-port monitor
??? README.md
```

## Build / flash

Requires [PlatformIO Core](https://platformio.org). Libraries (Sandeep Mistry
`LoRa`, Mikal Hart `TinyGPSPlus`) and the shared `common` library are pulled in
automatically.

```powershell
# Build
cd transmitter ; pio run
cd ..\receiver ; pio run

# Flash (close any serial monitor on the port first!)
cd transmitter ; pio run -t upload    # -> COM4
cd ..\receiver   ; pio run -t upload  # -> COM10
```

`upload_port`/`monitor_port` are preset to COM4 / COM10 in each `platformio.ini`.

## PC dual serial monitor

`tools/dual_serial_monitor.py` opens COM4 (transmitter) and COM10 (receiver)
together, prefixes lines with `[TX]`/`[RX]`, adds timestamps, and can log to a
file. This lets you see both ends of the link on one terminal.

```powershell
pip install pyserial
python tools/dual_serial_monitor.py            # defaults COM4 / COM10 @ 115200
python tools/dual_serial_monitor.py --log      # also write timestamped log file
```

> **Important:** Close the serial monitor before flashing. You cannot upload to
> a COM port while another application has it open. Reopen the monitor after
> flashing.

## Operation notes

- The transmitter always sends telemetry (even with no GPS fix) with
  `GPS Status : NO FIX`, so LoRa can be verified before a satellite fix.
- GPS parsing is non-blocking (`millis()`-based transmit schedule); the GPS UART
  is consumed continuously.
- If LoRa init fails the firmware clearly reports `[LORA] INITIALIZATION FAILED`
  and does not pretend to transmit.
- GPS startup diagnostics distinguish "no serial data" (wiring/baud problem) from
  "waiting for satellite fix" (not a LoRa problem).

## RF diagnostic mode (raw LoRa link test)

Both firmware files contain a compile-time mode switch for isolating the RF link
from GPS / parsing / ACK while debugging.

Switch at the top of each `src/main.cpp`:

```cpp
// MODE SWITCH
#define RF_DIAGNOSTIC_MODE 1     // comment this line to restore telemetry mode
```

- `RF_DIAGNOSTIC_MODE` defined  -> raw RF ping test (no GPS, no parsing, no ACK)
- `RF_DIAGNOSTIC_MODE` undefined-> normal GPS telemetry + ACK

Per-device role and payload prefix (also near the top, only used in RF diag mode):

```cpp
#define RF_IS_SENDER 1    // 1 = transmit "<prefix>,<seq>", 0 = receive raw packets
#define DIAG_PREFIX "PING" // e.g. "PING" (forward), "PING-RX" (reverse test)
```

The RF diag parameters default to the original telemetry config (433 MHz, SF7,
BW125 kHz, CR4/5, 17 dBm, preamble 8, sync 0x12, CRC on) so a diagnostic run is
comparable to the real link. To try the robust SF10 setting, change `DIAG_SF`
to 10 (and optionally `DIAG_TX_POWER` to 10-14) in BOTH files.

On boot, each device prints its actual SX1278 register config (chip version,
frequency, SF, BW, coding rate, TX power, preamble, sync word, CRC) so the two
radios can be compared that they are identical.

Expected output in RF diag mode:
```
[RF-TEST TX] seq=5 payload="PING,5" beginPacket=1 endPacket=1   (sender)
[RF-TEST RX] bytes=6 payload="PING,5" RSSI=-36 dBm SNR=9.50 dB  (receiver)
```

To switch roles for a reverse-direction test, swap `RF_IS_SENDER` between the two
files, choose the payload prefix, and reflash.

> Raw RF link (forward direction, original SF7 config) was verified PASS on
> 2026-08-10: COM4 transmitted PING,5..13, COM10 received each matching payload
> with RSSI/SNR.
