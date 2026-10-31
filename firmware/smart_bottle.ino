#include <Arduino.h>
#include <WiFi.h>
#include <Firebase_ESP_Client.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <NewPing.h>

// Required for Firebase
#include "addons/TokenHelper.h"
#include "addons/RTDBHelper.h"

// --- CREDENTIALS ---
#define WIFI_SSID "YOUR_WIFI_SSID"
#define WIFI_PASSWORD "YOUR_WIFI_PASSWORD"
#define API_KEY "YOUR_FIREBASE_WEB_API_KEY"
#define DATABASE_URL "YOUR_FIREBASE_RTDB_URL"

// --- PIN DEFINITIONS ---
#define TURB_PIN 34
#define ONE_WIRE_BUS 17 //temp
#define SONAR_PIN 16 //Ultrasonic
#define MAX_DISTANCE 30 
#define OLED_SDA 21
#define OLED_SCL 22
#define LED_PIN 25
#define BUZZER_PIN 2

// --- OBJECTS ---
OneWire oneWire(ONE_WIRE_BUS);
DallasTemperature tempSensor(&oneWire);
NewPing sonar(SONAR_PIN, SONAR_PIN, MAX_DISTANCE);
Adafruit_SSD1306 display(128, 64, &Wire, -1);

FirebaseData fbdo;
FirebaseAuth auth;
FirebaseConfig config;

// --- GLOBALS ---
float g_temp = 0, g_dist = 0;
int g_volume = 0;
int g_ntu = 0;
String g_waterStatus = "SAFE";
bool a;

/* ============================================================
   TASKS
============================================================ */

void taskReadSensors(void *pvParameters) {
  for (;;) {
    // 1. Temperature
    tempSensor.requestTemperatures();
    g_temp = tempSensor.getTempCByIndex(0);

    // 2. Turbidity (averaged)
    long turbRaw = 0;
    for (int i = 0; i < 10; i++) {
      turbRaw += analogRead(TURB_PIN);
      vTaskDelay(pdMS_TO_TICKS(10));
    }
    g_ntu = map(turbRaw / 10, 1500, 3000, 300, 0);
    g_ntu = constrain(g_ntu, 0, 800);

    // 3. Update Status (now volume is updated independently)
    
    if(a == true)g_waterStatus = "Drink Time";
    else if (g_ntu >= 10) g_waterStatus = "UNSAFE";
    else g_waterStatus = "SAFE";

    vTaskDelay(pdMS_TO_TICKS(500));  // temp & turbidity every 500ms
  }
}


void taskFirebase(void *pvParameters) {
  for (;;) {
    if (Firebase.ready() && WiFi.status() == WL_CONNECTED) {
      // Sending data to Firebase
      Firebase.RTDB.setFloat(&fbdo, "Bottle/Temperature", g_temp);
      Firebase.RTDB.setInt(&fbdo, "Bottle/Turbidity", g_ntu);
      Firebase.RTDB.setInt(&fbdo, "Bottle/Volume", g_volume);
      Firebase.RTDB.setString(&fbdo, "Bottle/Status", g_waterStatus);

      // Reading Control Signals
      if (Firebase.RTDB.getBool(&fbdo, "Bottle/LedStatus")) {
        digitalWrite(LED_PIN, fbdo.boolData() ? HIGH : LOW);
      }
      if (Firebase.RTDB.getBool(&fbdo, "Bottle/BuzzerStatus")) {
        digitalWrite(BUZZER_PIN, fbdo.boolData() ? LOW : HIGH);
        a = fbdo.boolData();
      }
    }
    vTaskDelay(pdMS_TO_TICKS(5000));
  }
}

void taskUpdateDisplay(void *pvParameters) {
  for (;;) {
    display.clearDisplay();
    display.setCursor(15, 0);
    display.print("SMART BOTTLE");
    display.drawFastHLine(0, 10, 128, WHITE);

    // Determine temperature label
    String tempLabel = "";
    if (g_temp < 20) tempLabel = "COLD";
    else if (g_temp <= 35) tempLabel = "NORMAL";
    else tempLabel = "HOT";

    // Display temperature with label
    display.setCursor(0, 20);
    display.printf("Temp: %.1f C", g_temp);
    display.setCursor(80, 20);  // Right side of screen
    display.print(tempLabel);

    display.setCursor(0, 32);
    display.printf("Vol : %d ml", g_volume);
    display.setCursor(0, 44);
    display.printf("Turb: %d NTU", g_ntu);
    display.setCursor(0, 56);
    display.print("Status: " + g_waterStatus);

    display.display();
    vTaskDelay(pdMS_TO_TICKS(1000));
  }
}
void taskUltrasonic(void *pvParameters) {
  for (;;) {
    unsigned int uS = sonar.ping();
    float currentDist = (float)uS / US_ROUNDTRIP_CM;

    if (currentDist > 0 && currentDist <= 17) {
      g_dist = currentDist;
      g_volume = map(g_dist, 17, 5, 0, 800);
    } else if (currentDist > 17) {
      g_volume = 0;
    }
    // If currentDist = 0, keep last good value

    g_volume = constrain(g_volume, 0, 800);

    vTaskDelay(pdMS_TO_TICKS(200));  // fast update every 200ms
  }
}

/* ============================================================
   SETUP
============================================================ */
void setup() {
  Serial.begin(115200);
  pinMode(LED_PIN, OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT);
  digitalWrite(BUZZER_PIN, HIGH);

  // Initialize OLED
  Wire.begin(OLED_SDA, OLED_SCL);
  display.begin(SSD1306_SWITCHCAPVCC, 0x3C);
  display.clearDisplay();
  display.setTextColor(WHITE);
  display.setCursor(10, 25);
  display.println("WIFI CONNECTING...");
  display.display();

  // Connect WiFi
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nWiFi Connected!");

  // Sync Time for SSL
  configTime(0, 0, "pool.ntp.org", "time.nist.gov", "time.google.com");  // <-- added time.google.com
  Serial.print("Syncing Time");
  while (time(nullptr) < 1000000000L) {  // wait until epoch time > 1 billion
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nTime Synced!");

  // Firebase config
  config.api_key = API_KEY;
  config.database_url = DATABASE_URL;
  if (Firebase.signUp(&config, &auth, "", "")) {
    Serial.println("Firebase Auth Success");
  } else {
    Serial.printf("Auth Error: %s\n", config.signer.signupError.message.c_str());
  }
  config.token_status_callback = tokenStatusCallback;
  Firebase.begin(&config, &auth);
  Firebase.reconnectWiFi(true);

  tempSensor.begin();

  // --- CREATE TASKS PINNED TO CORES ---
  // Ultrasonic sensor on Core 0
  xTaskCreatePinnedToCore(taskUltrasonic, "Ultrasonic", 2048, NULL, 2, NULL, 0);

  // Temperature & Turbidity task on Core 1
  xTaskCreatePinnedToCore(taskReadSensors, "Sensors", 4096, NULL, 2, NULL, 1);

  // Display task on Core 1
  xTaskCreatePinnedToCore(taskUpdateDisplay, "Display", 4096, NULL, 1, NULL, 1);

  // Firebase task on Core 1
  xTaskCreatePinnedToCore(taskFirebase, "Firebase", 8192, NULL, 1, NULL, 1);
}


void loop() {
  vTaskDelete(NULL);
}
