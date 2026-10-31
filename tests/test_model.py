"""Executable checks for every code-path claim of the analysis.

Run:  python3 tests/test_model.py      (exit code 0 when all checks pass)

Two kinds of check are used:
  * model checks evaluate the reimplemented arithmetic and decision logic;
  * source checks read firmware/smart_bottle.ino and assert the control-flow
    facts (loop structure, absence of timeouts or return-value checks) on which
    a claim rests, citing the line numbers.
None of these checks exercises hardware; they establish what the code does.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "analysis"))
import fwmodel as fw  # noqa: E402

SRC = open(os.path.join(HERE, "..", "firmware", "smart_bottle.ino"), encoding="utf-8").read().split("\n")


def line(n):
    return SRC[n - 1].strip()


CHECKS = []


def check(fn):
    CHECKS.append(fn)
    return fn


# ------------------------------------------------------------------ volume
@check
def volume_has_13_levels():
    levels = {fw.volume_fw_from_distance(i / 1000) for i in range(1, 20001)}
    assert sorted(levels) == [0, 66, 133, 200, 266, 333, 400, 466, 533, 600, 666, 733, 800], levels


@check
def volume_difference_bounds():
    diffs = [fw.volume_fw_from_distance(i / 1000) - fw.volume_linear(i / 1000) for i in range(5000, 17001)]
    assert min(diffs) >= -2 / 3 - 1e-9 and max(diffs) < 800 / 12


@check
def no_echo_keeps_previous_volume():           # FM5, lines 132-143
    assert fw.volume_step(0, prev_volume=533)[0] == 533


@check
def transient_volume_above_800_observable():   # FM10, lines 137 and 143
    finals, transients = zip(*(fw.volume_step(u, 0) for u in range(1, 5 * 57)))
    assert max(finals) == 800 and max(t for t in transients if t is not None) == 1133
    assert line(137).startswith("g_volume = map(") and line(143).startswith("g_volume = constrain(")


@check
def thermal_example_11cm_20C():
    c = fw.sound_speed(20.0)
    d_c = fw.echo_us(11.0, c) / 57
    assert abs(11 * fw.C57 / c - 11.246) < 5e-4
    assert fw.volume_step(fw.echo_us(11.0, c), 0)[0] == 400
    assert abs(fw.volume_linear(11 * fw.C57 / c) - 383.6) < 0.05
    assert 11.2 < d_c < 11.3


@check
def above_33C_reading_jumps_one_step():
    c = fw.sound_speed(40.0)
    assert fw.volume_step(fw.echo_us(11.0, c), 0)[0] == 466   # true 400 ml


# --------------------------------------------------------------- turbidity
@check
def turbidity_transfer_endpoints():
    assert fw.ntu_from_avg(0) == 600 and fw.ntu_from_avg(1500) == 300 and fw.ntu_from_avg(3000) == 0
    assert max(fw.ntu_from_avg(a) for a in range(4096)) == 600   # 800 cap unreachable


@check
def turbidity_output_increment_is_one_unit():
    vals = [fw.ntu_from_avg(a) for a in range(4096)]
    steps = {abs(vals[i + 1] - vals[i]) for i in range(4095)}
    assert steps == {0, 1}


@check
def decision_table_reminder_off():          # Eq. (7), lines 69-71
    for avg in range(4096):
        st = fw.status(False, fw.ntu_from_avg(avg))
        assert st == ("SAFE" if avg >= 2955 else "UNSAFE"), (avg, st)


@check
def decision_table_reminder_on_masks_quality():   # FM8
    assert {fw.status(True, fw.ntu_from_avg(a)) for a in range(4096)} == {"Drink Time"}


@check
def full_scale_reads_safe():                # FM6, conditional on the input reaching full scale
    assert fw.status(False, fw.ntu_from_avg(4095)) == "SAFE"


@check
def zero_volt_reads_unsafe():               # FM7
    assert fw.ntu_from_avg(0) == 600 and fw.status(False, 600) == "UNSAFE"


@check
def averaging_is_ten_reads_with_ten_delays():   # Eq. (8), lines 60-63
    assert line(60) == "for (int i = 0; i < 10; i++) {"
    assert line(61).startswith("turbRaw += analogRead(TURB_PIN);")
    assert line(62).startswith("vTaskDelay(pdMS_TO_TICKS(10));")   # inside the loop: after every read
    assert line(63) == "}"


# ------------------------------------------------------------- temperature
@check
def disconnected_probe_displayed_cold_and_uploaded():   # FM4
    assert fw.temp_label(fw.DEVICE_DISCONNECTED_C) == "COLD"
    assert line(56) == "g_temp = tempSensor.getTempCByIndex(0);"          # no validity test
    assert 'setFloat(&fbdo, "Bottle/Temperature", g_temp)' in line(82)


# ------------------------------------------------------------ start-up/cloud
@check
def startup_blocks_without_wifi_or_time():   # FM1, FM2
    assert line(169) == "while (WiFi.status() != WL_CONNECTED) {"
    assert line(178).startswith("while (time(nullptr) < 1000000000L) {")
    for a, b in ((169, 172), (178, 181)):
        body = " ".join(line(i) for i in range(a + 1, b))
        assert not re.search(r"\b(break|return|millis|timeout)\b", body), body
    # sensing tasks are created only after both loops (lines 200-209)
    assert all("xTaskCreatePinnedToCore" in line(n) for n in (200, 203, 206, 209))


@check
def wifi_loss_skips_cycle_silently():   # FM3
    assert line(80) == "if (Firebase.ready() && WiFi.status() == WL_CONNECTED) {"
    assert line(95) == "}" and line(96).startswith("vTaskDelay")   # no else branch, no indication


@check
def telemetry_is_four_unchecked_requests():   # FM11
    for n, key in ((82, "Temperature"), (83, "Turbidity"), (84, "Volume"), (85, "Status")):
        assert line(n).startswith("Firebase.RTDB.set") and f'"Bottle/{key}"' in line(n)
        assert not line(n).startswith("if")       # return value ignored


@check
def command_applied_only_after_successful_read():   # FM9
    assert line(91).startswith('if (Firebase.RTDB.getBool(&fbdo, "Bottle/BuzzerStatus"))')
    assert line(92) == "digitalWrite(BUZZER_PIN, fbdo.boolData() ? LOW : HIGH);"   # active-low drive
    assert line(96) == "vTaskDelay(pdMS_TO_TICKS(5000));"


@check
def no_mutex_on_shared_string():   # FM10
    joined = "\n".join(SRC)
    assert "String g_waterStatus" in joined
    assert not re.search(r"xSemaphore|portENTER_CRITICAL|xQueue", joined)


if __name__ == "__main__":
    failed = 0
    for fn in CHECKS:
        try:
            fn()
            print("PASS", fn.__name__)
        except AssertionError as e:
            failed += 1
            print("FAIL", fn.__name__, e)
    print(f"{len(CHECKS) - failed}/{len(CHECKS)} checks passed")
    sys.exit(1 if failed else 0)
