# Firmware-level audit of an ESP32 smart water bottle: source, model and results

This repository contains the computational material behind an analytical audit of an
ESP32-based smart water bottle. It lets every number in the analysis be regenerated
from the analysed firmware.

**No physical measurement data exist.** The study is analytical: every result is derived
from the firmware source, the documented behaviour of its libraries and published
component characteristics. The repository therefore contains code and computed results only.

## Contents

| Path | What it is |
|---|---|
| `firmware/smart_bottle.ino` | The analysed 215-line firmware. Lines 16-19 (Wi-Fi and Firebase credentials) are replaced by placeholders; every other line is unchanged, so line numbers match the analysis. |
| `analysis/fwmodel.py` | Reimplementation of the firmware arithmetic and decision logic, each function citing the firmware lines it reproduces. 32-bit C integer semantics. |
| `analysis/run_all.py` | Regenerates all results in `results/`. |
| `c_check/fwcheck.c`, `c_check/crosscheck.py` | Native C compilation of the same firmware expressions, compared case by case with the Python model (9,903 cases). |
| `tests/test_model.py` | 19 executable checks: model checks of the arithmetic and source checks of the control flow behind each failure mode. |
| `results/` | Computed outputs (CSV) and `summary.json` with every reported number. |

## How to reproduce

Requirements: Python 3.8 or later (standard library only); `gcc` for the optional C cross-check.

```
python3 analysis/run_all.py       # writes results/*.csv and results/summary.json  (about 1 s)
python3 tests/test_model.py       # 19/19 checks should pass
python3 c_check/crosscheck.py     # "9903 cases compared, 0 mismatches"
```

## Evaluated domains

* Volume: distances 0-20 cm in 0.001 cm steps, and every echo time a 30 cm `MAX_DISTANCE` allows
  (0-1710 us, including the no-echo value 0). Air temperature 0-45 C in 0.5 C steps for the
  speed-of-sound chain (dry-air model c = 331.3 sqrt(1 + T/273.15) m/s; echo time modelled as whole
  microseconds; NewPing timing overheads not modelled).
* Turbidity: every averaged 12-bit count 0-4095, with the reminder flag both false and true
  (8,192 decision cases).
* Timing and energy: symbolic budgets with the constants listed in `results/timing_budget.csv` and
  `results/energy_budget_inputs.csv`. Energy inputs marked "assumed" are not datasheet-derived.

## Software environment

The Arduino-ESP32 core and library versions used to build the original prototype **were not
recorded**. The behaviours the analysis depends on were checked against these tagged releases:

| Component | Behaviour relied on | Version checked |
|---|---|---|
| Arduino-ESP32 core, `cores/esp32/WMath.cpp` | `long map()` = `(x - in_min) * (out_max - out_min) / (in_max - in_min) + out_min`, C integer division | 2.0.17 and 3.0.7 (identical) |
| Arduino-ESP32 core, `esp32-hal-adc.c` | default attenuation 11 dB, default 12-bit width | 3.0.7 |
| DallasTemperature | `DEVICE_DISCONNECTED_C = -127`; `requestTemperatures()` blocks until conversion completes, at most `MAX_CONVERSION_TIMEOUT = 750` ms when externally powered | 4.0.4 |
| Firebase Arduino Client Library for ESP8266 and ESP32 (Mobizt) | blocking requests; default socket-connection and server-response timeouts of 10 s each | 4.4.17 (final release; library now deprecated by its author) |
| NewPing | `US_ROUNDTRIP_CM = 57`, `NO_ECHO = 0` | default value; parameter in `fwmodel.py` |

Adafruit SSD1306/GFX and OneWire are used by the firmware but no result depends on their internals.
The web dashboard source code was not part of the analysed material and is not included.

## Hardware identification

| Item | What can be stated |
|---|---|
| Controller | ESP32 development board with ESP-WROOM-32 module, USB-C, 30-pin header (visible in photographs); exact board revision not recorded |
| Charger | single-cell Li-ion charger board marked CA-033M, micro-USB input (visible); protection configuration not verified |
| Boost converter | MT3608-type module with 22 uH inductor and trimmer (visible); output setting not recorded (schematic labels the rail +5 V) |
| Cell | 18650 Li-ion; label illegible; capacity not recorded |
| Switch | rocker switch between charger output and converter input (visible; not drawn in the schematic) |
| Display | 0.96 in 128x64 I2C OLED, 4-pin GND/VDD/SCK/SDA (visible) |
| Turbidity | analogue turbidity probe with adapter board; the wiring illustration depicts a SEN0189-type adapter; exact module not confirmed |
| Others | HC-SR04 ultrasonic ranger, DS18B20 probe, 5 mm blue LED, buzzer (type not recorded) |

## License

MIT (see `LICENSE`). The firmware placeholders must be replaced with your own credentials to build it.
