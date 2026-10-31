"""Reimplementation of the arithmetic and decision logic of firmware/smart_bottle.ino.

Every function names the firmware line(s) it reproduces. Integer semantics follow
C/C++ on the ESP32 (32-bit `long`, division truncating toward zero), as used by
`long map(long, long, long, long, long)` in the Arduino-ESP32 core
(cores/esp32/WMath.cpp, identical in tags 2.0.17 and 3.0.7):

    return (x - in_min) * (out_max - out_min) / (in_max - in_min) + out_min;

Only the Python standard library is used.
"""

import math

INT32_MIN, INT32_MAX = -2**31, 2**31 - 1

# Constants taken verbatim from the firmware
US_ROUNDTRIP_CM = 57      # NewPing default; line 133 divides by it
MAX_DISTANCE_CM = 30      # line 25; beyond this NewPing returns NO_ECHO = 0
VOL_IN_MIN, VOL_IN_MAX, VOL_OUT_MIN, VOL_OUT_MAX = 17, 5, 0, 800   # line 137
NTU_IN_MIN, NTU_IN_MAX, NTU_OUT_MIN, NTU_OUT_MAX = 1500, 3000, 300, 0  # line 64
NTU_UNSAFE_AT = 10        # line 70
DEVICE_DISCONNECTED_C = -127.0  # DallasTemperature 4.0.4, DallasTemperature.h


def _i32(v):
    """Assert that an intermediate value fits a 32-bit signed long."""
    assert INT32_MIN <= v <= INT32_MAX, v
    return v


def c_div(n, d):
    """C integer division: quotient truncated toward zero."""
    q = abs(n) // abs(d)
    return q if (n >= 0) == (d > 0) else -q


def c_trunc(x):
    """Implicit float -> long conversion in C (truncation toward zero)."""
    return int(math.trunc(x))


def arduino_map(x, in_min, in_max, out_min, out_max):
    """WMath.cpp map() with 32-bit long arithmetic."""
    run = in_max - in_min
    if run == 0:
        return -1
    rise = out_max - out_min
    delta = x - in_min
    return _i32(c_div(_i32(delta * rise), run) + out_min)


def constrain(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


# ---------------------------------------------------------------- volume
def echo_us(d_cm, c_ms):
    """Round-trip echo time reported for a surface at d_cm with sound speed c_ms.

    Modelled as whole microseconds (NewPing returns an unsigned int in us);
    NO_ECHO (0) is returned beyond MAX_DISTANCE_CM. Library timing overheads
    (PING_OVERHEAD) and polling granularity are not modelled.
    """
    t = 2.0 * d_cm / 100.0 / c_ms * 1e6
    if t > MAX_DISTANCE_CM * US_ROUNDTRIP_CM:
        return 0
    return int(math.floor(t + 1e-9))


def volume_step(uS, prev_volume):
    """One iteration of taskUltrasonic (lines 132-143).

    Returns (final g_volume, transient value written at line 137 or None).
    The transient is the value a reader on the other core can observe between
    line 137 and line 143.
    """
    current = float(uS) / US_ROUNDTRIP_CM                     # line 133
    transient = None
    if 0 < current <= 17:                                     # line 135
        g_volume = arduino_map(c_trunc(current), 17, 5, 0, 800)  # line 137
        transient = g_volume
    elif current > 17:                                        # line 138
        g_volume = 0                                          # line 139
    else:                                                     # current == 0
        g_volume = prev_volume                                # line 141 comment
    g_volume = constrain(g_volume, 0, 800)                    # line 143
    return g_volume, transient


def volume_fw_from_distance(d_cm):
    """Firmware volume for an already computed distance d (no echo-time step)."""
    if d_cm <= 0:
        return None
    if d_cm > 17:
        return 0
    return constrain(arduino_map(c_trunc(d_cm), 17, 5, 0, 800), 0, 800)


def volume_linear(d_cm):
    """Continuous model encoded by the constants: 800 (17 - d) / 12."""
    return 800.0 * (17.0 - d_cm) / 12.0


def sound_speed(T_c):
    """Dry-air speed of sound, m/s."""
    return 331.3 * math.sqrt(1.0 + T_c / 273.15)


C57 = 2.0 / 100.0 / (US_ROUNDTRIP_CM * 1e-6)   # 350.877 m/s assumed by 57 us/cm


# ------------------------------------------------------------- turbidity
def ntu_from_sum(turb_raw_sum):
    """Lines 59-65: average of ten reads, map, constrain."""
    avg = c_div(turb_raw_sum, 10)                            # long / int
    ntu = arduino_map(avg, 1500, 3000, 300, 0)               # line 64
    transient = ntu
    return constrain(ntu, 0, 800), transient                 # line 65


def ntu_from_avg(avg):
    return constrain(arduino_map(avg, 1500, 3000, 300, 0), 0, 800)


def status(a, ntu):
    """Lines 69-71."""
    if a:
        return "Drink Time"
    if ntu >= NTU_UNSAFE_AT:
        return "UNSAFE"
    return "SAFE"


def temp_label(t):
    """Lines 109-111 (display task)."""
    if t < 20:
        return "COLD"
    if t <= 35:
        return "NORMAL"
    return "HOT"
