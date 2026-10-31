"""Compare the Python model with a native C compilation of the same firmware expressions.

Usage: python3 c_check/crosscheck.py   (needs gcc)   Exit code 0 when every case agrees.
"""
import os, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "analysis"))
import fwmodel as fw  # noqa: E402

exe = os.path.join(tempfile.mkdtemp(), "fwcheck")
subprocess.check_call(["gcc", "-std=c99", "-O0", "-o", exe, os.path.join(HERE, "fwcheck.c")])
lines = subprocess.check_output([exe], text=True).splitlines()
bad = n = 0
for ln in lines:
    p = ln.split(",")
    n += 1
    if p[0] == "T":
        avg, a, tr, ntu, st = int(p[1]), int(p[2]), int(p[3]), int(p[4]), p[5]
        py_ntu, py_tr = fw.ntu_from_sum(avg * 10)
        ok = (py_ntu, py_tr, fw.status(bool(a), py_ntu)) == (ntu, tr, st)
    else:
        uS, vol, tr = int(p[1]), int(p[2]), int(p[3])
        pv, pt = fw.volume_step(uS, 400)
        ok = (pv, -1 if pt is None else pt) == (vol, tr)
    if not ok:
        bad += 1
        if bad < 10:
            print("MISMATCH", ln)
print(f"{n} cases compared, {bad} mismatches")
sys.exit(1 if bad else 0)
