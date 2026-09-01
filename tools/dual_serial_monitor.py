#!/usr/bin/env python3
"""
dual_serial_monitor.py

Opens BOTH ESP32 USB serial ports simultaneously and prints their output to one
console, prefixed so you can tell them apart:

    [TX]  -> transmitter (COM4)   LoRa GPS transmitter
    [RX]  -> receiver    (COM10)  LoRa receiver / ACK

Default ports/baud:
    COM4 (transmitter) at 115200
    COM10 (receiver)   at 115200

Usage:
    python tools/dual_serial_monitor.py
    python tools/dual_serial_monitor.py --tx COM4 --rx COM10 --baud 115200
    python tools/dual_serial_monitor.py --log         # also save to timestamped log

Install dependency (once):
    pip install pyserial

IMPORTANT: Close this monitor before flashing a board. You cannot flash while
the same COM port is open by another application.
"""

import argparse
import datetime
import sys
import threading
import time

try:
    import serial
except ImportError:
    sys.stderr.write("pyserial is not installed. Run: pip install pyserial\n")
    sys.exit(1)


def read_loop(ser, prefix, stop):
    """Continuously read lines from one serial port and print them prefixed."""
    try:
        while not stop.is_set():
            line = ser.read_until(b"\n")
            if not line:
                continue
            text = line.decode("utf-8", errors="replace").rstrip("\r\n")
            ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
            print("[%s] %s  %s" % (ts, prefix, text), flush=True)
    except serial.SerialException as exc:
        print("[%s] port error: %s" % (prefix, exc), flush=True)
    finally:
        try:
            ser.close()
        except Exception:
            pass


def open_port(port, baud):
    try:

        s = serial.Serial(port, baud, timeout=0.1)
        print("Opened %s @ %d" % (port, baud), flush=True)
        return s
    except Exception as exc:
        print("ERROR: could not open %s: %s" % (port, exc), flush=True)
        return None


def main():
    ap = argparse.ArgumentParser(description="Dual COM-port monitor for ESP32 LoRa GPS telemetry")
    ap.add_argument("--tx", default="COM4", help="transmitter serial port (default COM4)")
    ap.add_argument("--rx", default="COM10", help="receiver serial port (default COM10)")
    ap.add_argument("--baud", type=int, default=115200, help="baud rate (default 115200)")
    ap.add_argument("--log", action="store_true", help="also write combined output to a timestamped log file")
    args = ap.parse_args()
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(errors='replace')
        sys.stderr.reconfigure(errors='replace')

    tx_ser = open_port(args.tx, args.baud)
    rx_ser = open_port(args.rx, args.baud)

    if tx_ser is None and rx_ser is None:
        sys.exit("Both ports failed to open. Nothing to monitor.")

    logf = None
    if args.log:
        name = "telemetry_%s.log" % datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        logf = open(name, "w", encoding="utf-8")
        print("Logging to %s" % name, flush=True)

    stop = threading.Event()
    threads = []
    # patch stdout print to also log? Simpler: a wrapper writer.
    if logf is not None:
        orig_print = builtins_print = print

        def tee(*objs, **kwargs):
            text = " ".join(str(o) for o in objs)
            orig_print(*objs, **kwargs)
            logf.write(text + "\n")
            logf.flush()

        globals()["print"] = tee

    if tx_ser is not None:
        t = threading.Thread(target=read_loop, args=(tx_ser, "[TX]", stop), daemon=True)
        t.start()
        threads.append(t)
    if rx_ser is not None:
        t = threading.Thread(target=read_loop, args=(rx_ser, "[RX]", stop), daemon=True)
        t.start()
        threads.append(t)

    print("Monitoring. Press Ctrl+C to stop.", flush=True)
    try:
        while True:
            time.sleep(0.2)
    except KeyboardInterrupt:
        print("\nStopping...", flush=True)
        stop.set()
        if tx_ser is not None:
            tx_ser.close()
        if rx_ser is not None:
            rx_ser.close()
        for t in threads:
            t.join(timeout=1.0)
    finally:
        if logf is not None:
            logf.close()
    print("Monitor closed. Reopen before each flash; close before flashing.")


if __name__ == "__main__":
    main()
