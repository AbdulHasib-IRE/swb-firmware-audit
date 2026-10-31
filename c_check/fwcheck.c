/* Native cross-check of the firmware arithmetic.
 * The expressions below are copied from firmware/smart_bottle.ino (lines cited) and
 * from long map() in the Arduino-ESP32 core (cores/esp32/WMath.cpp, tags 2.0.17/3.0.7).
 * 'long' is 32-bit on the ESP32, so it is replaced by int32_t here.
 * Build:  gcc -std=c99 -O0 -o fwcheck c_check/fwcheck.c      Run: ./fwcheck > c_out.csv
 */
#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>

#define US_ROUNDTRIP_CM 57
#define constrain(amt, low, high) ((amt) < (low) ? (low) : ((amt) > (high) ? (high) : (amt)))

static int32_t map(int32_t x, int32_t in_min, int32_t in_max, int32_t out_min, int32_t out_max) {
  const int32_t run = in_max - in_min;
  if (run == 0) return -1;
  const int32_t rise = out_max - out_min;
  const int32_t delta = x - in_min;
  return (delta * rise) / run + out_min;
}

int main(void) {
  /* turbidity: lines 59-71 */
  for (int32_t avg = 0; avg < 4096; avg++) {
    int32_t turbRaw = avg * 10;               /* any sum with this average */
    int g_ntu = map(turbRaw / 10, 1500, 3000, 300, 0);
    int transient = g_ntu;
    g_ntu = constrain(g_ntu, 0, 800);
    for (int a = 0; a <= 1; a++) {
      const char *st;
      if (a == true) st = "Drink Time";
      else if (g_ntu >= 10) st = "UNSAFE";
      else st = "SAFE";
      printf("T,%d,%d,%d,%d,%s\n", (int)avg, a, transient, g_ntu, st);
    }
  }
  /* volume: lines 132-143, previous value 400 */
  for (unsigned int uS = 0; uS <= 30 * US_ROUNDTRIP_CM; uS++) {
    int g_volume = 400, transient = -1;
    float g_dist = 0;
    float currentDist = (float)uS / US_ROUNDTRIP_CM;
    if (currentDist > 0 && currentDist <= 17) {
      g_dist = currentDist;
      g_volume = map(g_dist, 17, 5, 0, 800);
      transient = g_volume;
    } else if (currentDist > 17) {
      g_volume = 0;
    }
    g_volume = constrain(g_volume, 0, 800);
    printf("V,%u,%d,%d\n", uS, g_volume, transient);
  }
  return 0;
}
