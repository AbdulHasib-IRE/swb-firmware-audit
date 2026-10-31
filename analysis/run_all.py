"""Regenerate every number reported in the analysis from the firmware model.

Usage:  python3 analysis/run_all.py      (writes CSV files and summary.json to results/)

Standard library only. Runtime: a few seconds.
"""

import csv
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fwmodel as fw  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results")
os.makedirs(OUT, exist_ok=True)
S = {}


def write(name, header, rows):
    with open(os.path.join(OUT, name), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


# ---------------------------------------------------------------- 1 volume
STEP = 0.001
grid = [round(i * STEP, 3) for i in range(0, int(20 / STEP) + 1)]
rows, errs = [], []
for d in grid:
    v = fw.volume_fw_from_distance(d)
    lin = fw.volume_linear(d) if 5 <= d <= 17 else None
    e = (v - lin) if (v is not None and lin is not None) else None
    if e is not None:
        errs.append((e, d))
    rows.append([d, "" if v is None else v, "" if lin is None else round(lin, 4),
                 "" if e is None else round(e, 4)])
write("volume_transfer.csv", ["distance_cm", "firmware_ml", "linear_ml", "difference_ml"], rows)
levels = sorted({r[1] for r in rows if r[1] != ""})
S["volume_levels_ml"] = levels
S["volume_n_levels"] = len(levels)
S["volume_diff_min_ml"] = round(min(errs)[0], 4)
S["volume_diff_max_ml"] = round(max(errs)[0], 4)
S["volume_diff_max_at_cm"] = max(errs)[1]
S["volume_step_ml"] = round(800 / 12, 4)
S["volume_one_us_step_ml"] = round(800 / 12 / fw.US_ROUNDTRIP_CM, 4)

# echo-time domain: every possible reported echo time
trans = []
for uS in range(0, fw.MAX_DISTANCE_CM * fw.US_ROUNDTRIP_CM + 1):
    v, t = fw.volume_step(uS, prev_volume=400)
    trans.append([uS, round(uS / fw.US_ROUNDTRIP_CM, 4), v, "" if t is None else t])
write("volume_by_echo_time.csv", ["echo_us", "distance_cm", "final_g_volume_ml",
                                  "transient_line137_ml"], trans)
S["volume_transient_max_ml"] = max(r[3] for r in trans if r[3] != "")
S["volume_no_echo_keeps_previous"] = trans[0][2] == 400
echo_err = [(fw.volume_step(u, 0)[0] - fw.volume_linear(u / fw.US_ROUNDTRIP_CM), u)
            for u in range(5 * fw.US_ROUNDTRIP_CM, 17 * fw.US_ROUNDTRIP_CM + 1)]
S["volume_diff_max_echo_grid_ml"] = round(max(echo_err)[0], 3)
S["volume_diff_max_echo_us"] = max(echo_err)[1]
S["volume_diff_min_echo_grid_ml"] = round(min(echo_err)[0], 3)
S["volume_diff_mean_ml"] = round(sum(e for e, _ in errs) / len(errs), 2)
S["volume_diff_mean_echo_grid_ml"] = round(sum(e for e, _ in echo_err) / len(echo_err), 2)

# ------------------------------------------------------- 2 thermal chain
S["c57_m_s"] = round(fw.C57, 2)
T0 = None
for k in range(0, 100001):
    T = k / 1000.0
    if fw.sound_speed(T) >= fw.C57:
        T0 = T
        break
S["zero_bias_temperature_C"] = round(T0, 1)

dgrid = [round(5 + i * STEP, 3) for i in range(0, int(12 / STEP) + 1)]
trow, ptrow = [], []
for k in range(0, 91):
    T = k * 0.5
    c = fw.sound_speed(T)
    E = []
    for d in dgrid:
        uS = fw.echo_us(d, c)
        v, _ = fw.volume_step(uS, prev_volume=0)
        E.append(v - fw.volume_linear(d))
    bias = {d: -800 / 12 * d * (fw.C57 / c - 1) for d in (5, 11, 17)}
    chain = {}
    for d in (5, 11, 17):
        uS = fw.echo_us(d, c)
        chain[d] = fw.volume_step(uS, 0)[0] - fw.volume_linear(d)
    trow.append([T, round(min(E), 2), round(max(E), 2), round(sum(E) / len(E), 2),
                 round(bias[5], 2), round(bias[11], 2), round(bias[17], 2),
                 round(chain[5], 2), round(chain[11], 2), round(chain[17], 2)])
write("volume_thermal_chain.csv",
      ["air_temp_C", "chain_err_min_ml", "chain_err_max_ml", "chain_err_mean_ml",
       "continuous_bias_5cm_ml", "continuous_bias_11cm_ml", "continuous_bias_17cm_ml",
       "chain_err_5cm_ml", "chain_err_11cm_ml", "chain_err_17cm_ml"], trow)
byT = {r[0]: r for r in trow}
for T in (0.0, 20.0, 33.0, 40.0):
    r = byT[T]
    S[f"thermal_{int(T)}C"] = {"chain_min": r[1], "chain_max": r[2], "chain_mean": r[3],
                               "bias_5": r[4], "bias_11": r[5], "bias_17": r[6],
                               "chain_5": r[7], "chain_11": r[8], "chain_17": r[9]}
S["thermal_0_40C_bounds"] = [min(r[1] for r in trow if r[0] <= 40), max(r[2] for r in trow if r[0] <= 40)]
# distance computed for a true 11 cm at 20 C
S["computed_distance_11cm_20C"] = round(11 * fw.C57 / fw.sound_speed(20), 3)
S["linear_volume_11cm_20C"] = round(fw.volume_linear(11 * fw.C57 / fw.sound_speed(20)), 1)
# temperature range over which an exactly whole-cm surface is reported without error
S["chain_err_ranges"] = {str(T): [byT[T][1], byT[T][2]] for T in (0.0, 10.0, 20.0, 25.0, 30.0, 33.0, 35.0, 40.0)}

# ------------------------------------------------------------ 3 turbidity
trows = []
for avg in range(0, 4096):
    n = fw.ntu_from_avg(avg)
    raw = fw.arduino_map(avg, 1500, 3000, 300, 0)
    trows.append([avg, raw, n, fw.status(False, n), fw.status(True, n)])
write("turbidity_transfer.csv", ["avg_count", "map_output_before_constrain", "ntu_reported",
                                 "status_reminder_off", "status_reminder_on"], trows)
S["ntu_max_reported"] = max(r[2] for r in trows)
S["ntu_at_count0"] = trows[0][2]
S["ntu_zero_from_count"] = min(r[0] for r in trows if r[2] == 0 and all(x[2] == 0 for x in trows[r[0]:]))
S["safe_min_count_reminder_off"] = min(r[0] for r in trows if r[3] == "SAFE")
S["ntu_distinct_values"] = len({r[2] for r in trows})
S["ntu_output_increment"] = 1
S["ntu_nominal_slope_per_count"] = -300 / 1500
runs = {}
prev, start = trows[0][2], 0
for r in trows[1:]:
    if r[2] != prev:
        runs.setdefault(r[0] - start, 0)
        runs[r[0] - start] += 1
        if r[0] - start != 5:
            S.setdefault("ntu_irregular_runs", []).append([start, r[0] - 1, prev])
        prev, start = r[2], r[0]
S["ntu_counts_per_output_unit"] = runs
S["ntu_map_min_before_constrain"] = min(r[1] for r in trows)

# ---------------------------------------------------------- 4 decision table
dt = []
for a in (False, True):
    for avg in range(0, 4096):
        n = fw.ntu_from_avg(avg)
        dt.append([int(a), avg, n, fw.status(a, n)])
write("decision_table_full.csv", ["reminder_flag_a", "avg_count", "ntu", "status"], dt)
summary = []
for a in (0, 1):
    seg, cur = [], None
    for r in (x for x in dt if x[0] == a):
        key = r[3]
        if cur is None or key != cur[0]:
            cur = [key, r[1], r[1], r[2], r[2]]
            seg.append(cur)
        else:
            cur[2] = r[1]
            cur[3] = max(cur[3], r[2]) if False else cur[3]
            cur[4] = r[2]
    for s in seg:
        summary.append([a, s[1], s[2], s[3], s[4], s[0]])
write("decision_table_summary.csv",
      ["reminder_flag_a", "count_from", "count_to", "ntu_at_from", "ntu_at_to", "status"], summary)
S["decision_table"] = summary

# ---------------------------------------------------------------- 5 timing
t = {
    "t_conv_max_ms": 750,          # DS18B20 12-bit maximum; DallasTemperature 4.0.4 MAX_CONVERSION_TIMEOUT
    "adc_delays": 10,              # vTaskDelay after every read, lines 60-63, including the last
    "adc_delay_ms": 10,
    "sensor_task_delay_ms": 500,
    "firebase_delay_ms": 5000,
    "firebase_requests_per_cycle": 6,
    "fb_socket_connection_timeout_ms_default": 10000,   # Firebase-ESP-Client 4.4.17 FB_Const.h
    "fb_server_response_timeout_ms_default": 10000,
}
t["sensor_budget_ms"] = t["t_conv_max_ms"] + t["adc_delays"] * t["adc_delay_ms"] + t["sensor_task_delay_ms"]
t["sensor_budget_ratio_to_500"] = round(t["sensor_budget_ms"] / 500, 2)
t["per_request_timeout_ms"] = t["fb_socket_connection_timeout_ms_default"] + t["fb_server_response_timeout_ms_default"]
t["degraded_cycle_command_delay_ms"] = t["firebase_delay_ms"] + 6 * t["per_request_timeout_ms"]
S["timing"] = t
write("timing_budget.csv", ["quantity", "value"], [[k, v] for k, v in t.items()])

# ---------------------------------------------------------------- 6 energy
# Datasheet values (see README for sources); items marked 'assumed' are not datasheet-derived.
loads = [
    ["ESP32 module, modem-sleep at 240 MHz (upper value)", 68, "Espressif ESP32 datasheet v5.3, Table 4-2", "low"],
    ["ESP32 module, Wi-Fi RX continuous", 112, "ESP32-WROOM-32E datasheet v2.1, Table 16", "high"],
    ["ESP32 module, Wi-Fi TX 802.11b 19.5 dBm (average)", 239, "ESP32-WROOM-32E datasheet v2.1, Table 16", "high, 10% duty assumed"],
    ["HC-SR04 working current", 15, "HC-SR04 module datasheet", "both"],
    ["Turbidity module (SEN0189-type) operating current, max", 40, "DFRobot SEN0189 documentation", "both"],
    ["DS18B20 active current, max", 1.5, "DS18B20 datasheet", "both"],
    ["OLED module", 20, "assumed (not datasheet-derived)", "both"],
    ["Development-board overhead (power LED, USB-UART idle)", 10, "assumed (not datasheet-derived)", "both"],
]
fixed = 15 + 40 + 1.5 + 20 + 10
esp_low = 68
esp_high = 0.9 * 112 + 0.1 * 239
V5, VBAT, ETA = 5.0, 3.7, 0.85
res = {}
for name, esp in (("low", esp_low), ("high", esp_high)):
    i5 = esp + fixed
    p5 = V5 * i5 / 1000
    ibat = p5 / (ETA * VBAT) * 1000
    res[name] = {"I_5V_mA": round(i5, 1), "P_5V_W": round(p5, 3), "I_cell_mA": round(ibat, 1),
                 "hours_per_1000mAh": round(1000 / ibat, 2)}
S["energy"] = {"assumptions": {"rail_V": V5, "cell_V": VBAT, "boost_efficiency": ETA,
                               "esp_low_mA": esp_low, "esp_high_mA": round(esp_high, 1),
                               "excluded": "buzzer and LED (event-driven; LED current undefined without a series resistor)"},
               **res}
write("energy_budget_inputs.csv", ["load", "current_mA", "source", "scenario"], loads)
write("energy_budget_results.csv", ["scenario", "I_5V_mA", "P_5V_W", "I_cell_mA", "hours_per_1000mAh"],
      [[k, v["I_5V_mA"], v["P_5V_W"], v["I_cell_mA"], v["hours_per_1000mAh"]] for k, v in res.items()])

# ------------------------------------------------------ 7 shared variables
shared = [
    ["g_temp", "float", "taskReadSensors (core 1, prio 2), line 56", "taskUpdateDisplay, taskFirebase (core 1, prio 1)",
     "aligned 32-bit store; readers cannot preempt the writer", "stale value only"],
    ["g_ntu", "int", "taskReadSensors (core 1, prio 2), lines 64-65", "taskUpdateDisplay, taskFirebase (core 1, prio 1)",
     "two writes (map, then constrain) without blocking in between", "unconstrained transient not observable by lower-priority readers on the same core"],
    ["g_waterStatus", "String (heap)", "taskReadSensors (core 1, prio 2), lines 69-71", "taskUpdateDisplay line 124, taskFirebase line 85",
     "reassignment may reallocate the buffer while a preempted reader is copying it", "possible corrupted or invalid read"],
    ["g_volume", "int", "taskUltrasonic (core 0, prio 2), lines 137 and 143", "taskUpdateDisplay, taskFirebase (core 1)",
     "two writes on another core; readers run in parallel", "transient value above 800 ml observable (up to 1133 ml)"],
    ["g_dist", "float", "taskUltrasonic, line 136", "none", "single task", "none"],
    ["a", "bool", "taskFirebase (core 1, prio 1), line 93", "taskReadSensors line 69", "single byte", "status lags the command by up to one sensing period"],
    ["Bottle/* record", "4 database fields", "taskFirebase, lines 82-85 (four separate requests)", "dashboard",
     "no snapshot, no timestamp, return values ignored", "fields may come from different acquisitions; failed writes leave older values unmarked"],
]
write("shared_variables.csv", ["variable", "type", "writer", "readers", "mechanism", "consequence"], shared)

with open(os.path.join(OUT, "summary.json"), "w") as f:
    json.dump(S, f, indent=2)
print(json.dumps(S, indent=1)[:6000])
