# Debugging on real hardware

## Identifying the two USB-C ports

```bash
ioreg -p IOUSB -w0 -l 2>/dev/null | grep -iE '"USB Vendor Name"|"USB Product Name"'
```

- `"USB Vendor Name" = "Espressif"`, `"USB Product Name" = "USB JTAG_serial debug unit"`
  → the ESP32-C6's **native USB** (built-in USB-Serial-JTAG). Good for
  **flashing**. Console output does *not* reliably go here (see below).
- `"USB Product Name" = "USB Single Serial"` (WCH vendor id `0x1A86`)
  → **CH343** external UART bridge. This is where the running app's console
  actually goes (`CONFIG_ESP_CONSOLE_UART_DEFAULT=y` = UART0, wired to
  CH343). Use this for **monitoring**.

Both currently enumerate as `/dev/cu.usbmodemXXXX` on macOS (not
`wchusbserial*` — modern macOS has a built-in CDC-ACM driver, no WCH kernel
extension needed), so `ioreg` is the only reliable way to tell them apart;
don't assume from the device path alone.

## Flashing

`tos.py flash` (TuyaOpen's `tyutool_cli` wrapper) could not complete its
auto-reset-into-bootloader handshake over the native USB port on this board,
even with a manual BOOT+RESET. Plain `esptool.py` works immediately, no
button-pressing needed:

```bash
esptool.py --chip esp32c6 --port /dev/cu.usbmodemXXXX --baud 460800 \
  --before default_reset --after hard_reset write_flash -z \
  --flash_mode dio --flash_size 8MB --flash_freq 40m \
  0x0 dist/ph4_tuyaopen_esp32bridge_1.0.0/ph4_tuyaopen_esp32bridge_QIO_1.0.0.bin
```

Reflashing does **not** erase WiFi credentials or Tuya activation/binding
state — see "Does reflashing lose pairing?" below.

## Monitoring: avoid the serial-buffer-backlog trap

ESP-IDF's default WiFi driver logging (`wifi:(phy)...`, `wifi:(opr)...`,
etc.) is extremely verbose — hundreds of lines per second during
association. A short, scripted serial capture (e.g. a Python loop reading
for N seconds) can fall behind this flood and end up reading **stale
backlog** rather than live output, especially right after a fresh
connection where the OS's serial receive buffer may already hold minutes of
un-drained data. Symptom: captured timestamps stay low (e.g. stuck under
10s) even after a long capture window, or app_main's startup banner
(`=== ph4_tuyaopen_esp32bridge ===`) appears more than once in a single
capture when the device only booted once.

Reliable approach for a scripted one-shot capture:

```python
import serial, time
ser = serial.Serial('/dev/cu.usbmodemXXXX', 115200, timeout=0.5)
# Hard reset via RTS (same sequence esptool uses) so timestamps start at 0
ser.dtr = False
ser.rts = True
time.sleep(0.1)
ser.rts = False
time.sleep(0.1)
ser.reset_input_buffer()   # drop anything stale that arrived before this
buf = bytearray()
end = time.time() + 30
while time.time() < end:
    data = ser.read(4096)  # raw block reads, not readline() -- keeps up better
    if data:
        buf.extend(data)
ser.close()
```

Then grep the saved buffer for the relevant tagged lines instead of trying
to filter live:

```bash
grep -a -n "ha_mqtt.c\|tuya_cloud.c\|app_main.c\|config.c\|dp_bridge.c" capture.log \
  | grep -v "queue free spaces\|thread_create\|Thread:.*Exec Start"
```

For interactive human monitoring, `tos.py monitor -p /dev/cu.usbmodemXXXX`
doesn't have this problem — it's only scripted short-window captures that
get outrun by the log volume.

If you can reach the MQTT broker directly from your dev machine, checking
MQTT traffic directly is more reliable than the serial log for confirming
HA-side connectivity:

```bash
mosquitto_sub -h 10.0.1.103 -p 1883 -t 'ph4/bridge01/#' -v
```

## Decoding a crash (`Guru Meditation Error`)

A crash produces a register dump ending in `Rebooting...`. The important
fields are `MEPC` (crash PC) and `RA` (return address) — decode them
against the *exact* ELF that was flashed (rebuilding first invalidates old
addresses):

```bash
TOOL=tuyaopen/platform/ESP32/.espressif/tools/riscv32-esp-elf/esp-14.2.0_20241119/riscv32-esp-elf/bin/riscv32-esp-elf-addr2line
ELF=tuyaopen/platform/ESP32/tuya_open_sdk/build/tuya_open_sdk.elf
"$TOOL" -pfiaC -e "$ELF" 0x<MEPC> 0x<RA> 0x<other stack addresses of interest>
```

`riscv32-esp-elf-addr2line` isn't on `PATH` even after `source
tuyaopen/export.sh` — use the full path above (find it again with `find
tuyaopen -iname '*addr2line*'` if the toolchain version changes).

### Worked example: the HA MQTT NULL-`strlen` crash (2026-09-28)

Symptom: device rebooted in a loop, every ~11s, right after `ha_mqtt`
connected to Tuya cloud and started its own connect thread. No obvious
cause in our own log lines — the crash printed a raw register dump with no
symbol names.

```
Guru Meditation Error: Core  0 panic'ed (Load access fault). Exception was unhandled.
MEPC    : 0x40031c8a  RA      : 0x4200af7a  ...  A0 : 0x00000000
```

Decoded:
```
0x40031c8a: ?? ??:0                                    # inside a libc function (strlen)
0x4200af7a: mqtt_client_connect at .../libmqtt/src/mqtt_client_wrapper.c:208
0x42008b7a: ha_mqtt_thread at src/ha_mqtt.c:127
0x42011818: __WrapRunFunc at .../tal_system/src/tal_thread.c:254
```

`A0 = 0x00000000` (the crash argument register) plus a crash inside an
unresolved libc frame called from `mqtt_client_connect` was the giveaway:
TuyaOpen's own `mqtt_client_wrapper.c` calls
`strlen(context->config.username)` / `strlen(context->config.password)`
**unconditionally**, with no NULL check. `ha_mqtt.c` had been passing `NULL`
for both fields when no MQTT user/pass was configured (the natural way to
say "no auth" for most MQTT clients) — that's exactly what `strlen(NULL)`
crashed on. Fix: pass empty strings instead of NULL (`strlen("") == 0` is
safe) — see `src/ha_mqtt.c`'s `mcfg.username`/`mcfg.password`. This is a
real bug in the vendored SDK, but the fix lives entirely in our own file
(the API contract of `mqtt_client_config_t` just isn't NULL-safe the way
you'd expect), so no `docs/tuyaopen-sdk-patches/` entry was needed.

## Does reflashing lose pairing?

No, as long as the flash write only spans the bootloader/partition-table/
app region (offsets `0x0`–`0x6d0fff` for the current 8MB partition table —
check `tuya_open_sdk/partitions.csv` if that ever changes). WiFi
credentials and Tuya activation/binding state live in the `tuya`
(`0x7C0000`, Tuya's own custom partition subtype `0xAA`) and `factory_nvs`
(`0x7FC000`) partitions, both well past where a normal app reflash writes.
Confirmed empirically across multiple reflashes in this project: the device
reconnects to WiFi and hits `TUYA_EVENT_BINDED_NOTIFY`/
`TUYA_EVENT_MQTT_CONNECTED` immediately on boot, with no AP-pairing-mode
re-entry (which is what a genuinely wiped/factory-reset device does
instead).
