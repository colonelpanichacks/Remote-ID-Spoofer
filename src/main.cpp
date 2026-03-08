#include <Arduino.h>
#include <ArduinoJson.h>
#include <esp_wifi.h>
#include <esp_wifi_types.h>
#include <esp_event.h>
#include <esp_netif.h>
#include <esp_system.h>
#include <cstring>
#include "opendroneid.h"
#include "odid_wifi.h"

#if defined(M5STAMP_S3)
  #include <Adafruit_NeoPixel.h>
#endif

// ── board auto-detect ──

#if defined(ARDUINO_XIAO_ESP32C5)
  #define BUZZER_PIN    25
  #define LED_PIN       27
  #define LED_ON        HIGH
  #define LED_OFF       LOW
  #define DUAL_BAND     true
  #define USE_NEOPIXEL  false
  #define BOARD_NAME    "XIAO ESP32-C5 (Dual-Band)"

#elif defined(M5STAMP_S3)
  // M5Stack Stamp S3: SK6812 RGB on GPIO21, buzzer on GPIO1 (wire your own)
  #define NEOPIXEL_PIN  21
  #define NEOPIXEL_NUM  1
  #define BUZZER_PIN    1
  #define LED_PIN       -1
  #define LED_ON        LOW
  #define LED_OFF       HIGH
  #define DUAL_BAND     false
  #define USE_NEOPIXEL  true
  #define BOARD_NAME    "M5Stack Stamp S3 (2.4GHz)"

#elif defined(LUATOS_ESP32C3)
  #define BUZZER_PIN  8
  #define LED_PIN     12
  #define LED_ON      HIGH
  #define LED_OFF     LOW
  #define DUAL_BAND   false
  #define USE_NEOPIXEL false
  #define BOARD_NAME  "LuatOS ESP32-C3 (2.4GHz)"

#else
  #define BUZZER_PIN    3
  #define LED_PIN       21
  #define LED_ON        LOW
  #define LED_OFF       HIGH
  #define DUAL_BAND     false
  #define USE_NEOPIXEL  false
  #define BOARD_NAME    "XIAO ESP32-S3 (2.4GHz)"
#endif

#if USE_NEOPIXEL
  static Adafruit_NeoPixel neopixel(NEOPIXEL_NUM, NEOPIXEL_PIN, NEO_GRB + NEO_KHZ800);
#endif

static const char*   BEACON_SSID     = "Starbucks WiFi";
static const size_t  BEACON_SSID_LEN = 14;
static const uint8_t AP_CHANNEL      = 6;
static const char*   CONFIG_SPOOF_MAC = "60:60:1f:d3:b2:6a";

// 5GHz channel table (UNII-3 band)
static const uint8_t CHANNELS_5G[]   = {149, 153, 157, 161, 165};
static const uint8_t NUM_5G_CHANNELS = 5;

// band mode: 0=2.4 only, 1=5GHz only, 2=dual
static uint8_t g_band_mode = DUAL_BAND ? 2 : 0;
static bool    g_5g_ch_enabled[5] = {true, true, true, true, true};

// ── default config (edit these for standalone operation) ──
// Set AUTOSTART to true to broadcast on boot without web UI
#define AUTOSTART       false
#define DEFAULT_ID      "FRAT0000000001"
#define DEFAULT_LAT     48.8220        // drone start lat
#define DEFAULT_LON     2.2700         // drone start lon
#define DEFAULT_ALT     80             // altitude meters
#define DEFAULT_PLAT    48.8215        // pilot lat
#define DEFAULT_PLON    2.2695         // pilot lon

static char    g_basic_id[ODID_ID_SIZE + 1] = "";
static double  g_drone_lat  = 0.0;
static double  g_drone_lon  = 0.0;
static int     g_drone_alt  = 0;
static double  g_pilot_lat  = 0.0;
static double  g_pilot_lon  = 0.0;
static bool    g_has_data   = false;
static bool    broadcastEnabled = false;

static bool    g_dynamic_override = false;
static uint8_t g_override_src_mac[6] = {0};
static uint8_t g_send_counter = 0;

static bool    buzzerMuted = false;
static bool    ledMuted    = false;

static const uint16_t TX_INTERVAL_MS = 1000;

// ── buzzer ──

static void beep(int freq, int ms) {
    if (buzzerMuted) return;
    tone(BUZZER_PIN, freq, ms);
    delay(ms);
    noTone(BUZZER_PIN);
}

static void playBootSound() {
    if (buzzerMuted) return;
    // Super Mario Bros - Underground/Dungeon (World 1-2) bass riff
    int notes[]     = { 262, 523, 220, 440, 233, 466 };
    int durations[] = {  80,  80,  80,  80,  80,  80 };
    for (int i = 0; i < 6; i++) {
        tone(BUZZER_PIN, notes[i], durations[i]);
        delay(durations[i] + 10);
        noTone(BUZZER_PIN);
    }
}

static void startBeep() {
    beep(1200, 60); delay(40);
    beep(1600, 60); delay(40);
    beep(2200, 80);
}

static void stopBeep() {
    beep(2000, 60); delay(40);
    beep(1400, 60); delay(40);
    beep(800, 100);
}

static void heartbeatTick() {
    if (buzzerMuted) return;
    tone(BUZZER_PIN, 2400, 15);
    delay(15);
    noTone(BUZZER_PIN);
}

// ── LED ──

#if USE_NEOPIXEL

static void ledInit() {
    neopixel.begin();
    neopixel.setBrightness(30);
    neopixel.clear();
    neopixel.show();
}

static void ledOn() {
    if (ledMuted) return;
    neopixel.setPixelColor(0, neopixel.Color(0, 255, 0));  // green
    neopixel.show();
}

static void ledOff() {
    neopixel.clear();
    neopixel.show();
}

static void ledFlash(int ms) {
    if (ledMuted) return;
    ledOn(); delay(ms); ledOff();
}

static void ledColor(uint8_t r, uint8_t g, uint8_t b) {
    if (ledMuted) return;
    neopixel.setPixelColor(0, neopixel.Color(r, g, b));
    neopixel.show();
}

#else

static void ledInit() {
    pinMode(LED_PIN, OUTPUT);
    ledOff();
}

static void ledOn()  { if (!ledMuted) digitalWrite(LED_PIN, LED_ON); }
static void ledOff() { digitalWrite(LED_PIN, LED_OFF); }

static void ledFlash(int ms) {
    if (ledMuted) return;
    ledOn(); delay(ms); ledOff();
}

static void ledColor(uint8_t r, uint8_t g, uint8_t b) {
    // simple LED: just on/off, ignore color
    if (r || g || b) ledOn(); else ledOff();
}

#endif

// ── ODID data builder ──

static void fill_uas_data(ODID_UAS_Data *uas, const char *basic_id,
                          double lat, double lon, int alt,
                          double pilot_lat, double pilot_lon) {
    memset(uas, 0, sizeof(*uas));

    odid_initBasicIDData(&uas->BasicID[0]);
    uas->BasicID[0].UAType = ODID_UATYPE_OTHER;
    uas->BasicID[0].IDType = ODID_IDTYPE_SERIAL_NUMBER;
    strncpy(uas->BasicID[0].UASID, basic_id, ODID_ID_SIZE);
    uas->BasicID[0].UASID[ODID_ID_SIZE] = '\0';
    uas->BasicIDValid[0] = 1;

    odid_initLocationData(&uas->Location);
    uas->Location.Status        = ODID_STATUS_AIRBORNE;
    uas->Location.Latitude      = lat;
    uas->Location.Longitude     = lon;
    uas->Location.AltitudeGeo   = alt;
    uas->Location.AltitudeBaro  = alt;
    uas->Location.Height        = (float)alt;
    uas->Location.HeightType    = ODID_HEIGHT_REF_OVER_TAKEOFF;
    uas->Location.HorizAccuracy = ODID_HOR_ACC_10_METER;
    uas->Location.VertAccuracy  = ODID_VER_ACC_10_METER;
    uas->Location.SpeedAccuracy = ODID_SPEED_ACC_1_METERS_PER_SECOND;
    uas->Location.TSAccuracy    = ODID_TIME_ACC_1_0_SECOND;
    uas->LocationValid          = 1;

    odid_initSystemData(&uas->System);
    uas->System.OperatorLocationType = ODID_OPERATOR_LOCATION_TYPE_LIVE_GNSS;
    uas->System.OperatorLatitude     = pilot_lat;
    uas->System.OperatorLongitude    = pilot_lon;
    uas->SystemValid                 = 1;
}

static void update_beacon_vendor_ie(ODID_UAS_Data *uas) {
    uint8_t pack_buf[256];
    int pack_len = odid_message_build_pack(uas, pack_buf, sizeof(pack_buf));
    if (pack_len <= 0) return;

    size_t vie_len = 7 + pack_len;
    uint8_t vie_buf[300];
    if (vie_len > sizeof(vie_buf)) return;

    vie_buf[0] = 0xDD;
    vie_buf[1] = (uint8_t)(4 + 1 + pack_len);
    vie_buf[2] = 0xFA;
    vie_buf[3] = 0x0B;
    vie_buf[4] = 0xBC;
    vie_buf[5] = 0x0D;
    vie_buf[6] = g_send_counter;
    memcpy(&vie_buf[7], pack_buf, pack_len);

    esp_wifi_set_vendor_ie(true, WIFI_VND_IE_TYPE_BEACON, WIFI_VND_IE_ID_0, vie_buf);
    esp_wifi_set_vendor_ie(true, WIFI_VND_IE_TYPE_PROBE_RESP, WIFI_VND_IE_ID_0, vie_buf);
}

static void send_nan_frames(ODID_UAS_Data *uas, uint8_t *src_mac, uint8_t *frame_buf) {
    int frame_len;

    frame_len = odid_wifi_build_nan_sync_beacon_frame(
        (char *)src_mac, frame_buf, 512);
    if (frame_len > 0)
        esp_wifi_80211_tx(WIFI_IF_AP, frame_buf, frame_len, true);

    frame_len = odid_wifi_build_message_pack_nan_action_frame(
        uas, (char *)src_mac, g_send_counter, frame_buf, 512);
    if (frame_len > 0) {
        esp_err_t err = esp_wifi_80211_tx(WIFI_IF_AP, frame_buf, frame_len, true);
        if (err != ESP_OK)
            Serial.printf("NAN tx err=%d\n", err);
    }
}

static void inject_odid(const char *basic_id,
                        double lat, double lon, int alt,
                        double pilot_lat, double pilot_lon) {
    if (basic_id[0] == '\0') return;

    ODID_UAS_Data uas;
    fill_uas_data(&uas, basic_id, lat, lon, alt, pilot_lat, pilot_lon);

    uint8_t ap_mac[6];
    esp_wifi_get_mac(WIFI_IF_AP, ap_mac);
    uint8_t *src_mac = g_dynamic_override ? g_override_src_mac : ap_mac;

    uint8_t frame_buf[512];

    // vendor IE always rides on AP beacons (ch6 2.4GHz)
    update_beacon_vendor_ie(&uas);

    bool do_2_4 = (g_band_mode == 0 || g_band_mode == 2);
    bool do_5   = (g_band_mode == 1 || g_band_mode == 2) && DUAL_BAND;

    // 2.4GHz NAN frames on AP channel
    if (do_2_4) {
        esp_wifi_set_channel(AP_CHANNEL, WIFI_SECOND_CHAN_NONE);
        send_nan_frames(&uas, src_mac, frame_buf);
    }

    // 5GHz NAN frames -- hop through enabled channels
    if (do_5) {
        for (uint8_t i = 0; i < NUM_5G_CHANNELS; i++) {
            if (!g_5g_ch_enabled[i]) continue;
            esp_wifi_set_channel(CHANNELS_5G[i], WIFI_SECOND_CHAN_NONE);
            delay(1);
            send_nan_frames(&uas, src_mac, frame_buf);
        }
        // hop back to AP channel for beacons
        esp_wifi_set_channel(AP_CHANNEL, WIFI_SECOND_CHAN_NONE);
    }

    g_send_counter = (g_send_counter + 1) % 3;
}

static void clear_vendor_ie() {
    esp_wifi_set_vendor_ie(false, WIFI_VND_IE_TYPE_BEACON, WIFI_VND_IE_ID_0, NULL);
    esp_wifi_set_vendor_ie(false, WIFI_VND_IE_TYPE_PROBE_RESP, WIFI_VND_IE_ID_0, NULL);
}

static void init_ap_ssid() {
    wifi_config_t cfg = {};
    memcpy(cfg.ap.ssid, BEACON_SSID, BEACON_SSID_LEN);
    cfg.ap.ssid_len = BEACON_SSID_LEN;
    cfg.ap.channel = AP_CHANNEL;
    cfg.ap.authmode = WIFI_AUTH_OPEN;
    cfg.ap.max_connection = 4;
    esp_wifi_set_config(WIFI_IF_AP, &cfg);
    esp_wifi_set_channel(AP_CHANNEL, WIFI_SECOND_CHAN_NONE);
}

static bool parse_mac(const char *str, uint8_t *out) {
    if (!str || strlen(str) != 17) return false;
    unsigned int b[6];
    if (sscanf(str, "%02x:%02x:%02x:%02x:%02x:%02x",
               &b[0], &b[1], &b[2], &b[3], &b[4], &b[5]) != 6)
        return false;
    for (int i = 0; i < 6; i++) out[i] = (uint8_t)b[i];
    return true;
}

// ═══════════════════════════════════════════

void setup() {
    Serial.begin(115200);
    delay(200);

    Serial.println("\n========================================");
    Serial.println("  Remote-ID-Spoofer");
    Serial.printf("  Board: %s\n", BOARD_NAME);
    #if DUAL_BAND
    Serial.println("  Bands: 2.4GHz + 5GHz (WiFi 6)");
    #else
    Serial.println("  Bands: 2.4GHz");
    #endif
    Serial.println("========================================\n");

    pinMode(BUZZER_PIN, OUTPUT);
    digitalWrite(BUZZER_PIN, LOW);
    ledInit();

    delay(300);
    playBootSound();
    ledFlash(200);

    if (!parse_mac(CONFIG_SPOOF_MAC, g_override_src_mac)) {
        uint32_t rnd = esp_random();
        g_override_src_mac[0] = 0x60;
        g_override_src_mac[1] = 0x60;
        g_override_src_mac[2] = 0x1f;
        g_override_src_mac[3] = (rnd)       & 0xFF;
        g_override_src_mac[4] = (rnd >> 8)  & 0xFF;
        g_override_src_mac[5] = (rnd >> 16) & 0xFF;
    }
    g_dynamic_override = true;

    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_ap();

    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_AP));
    ESP_ERROR_CHECK(esp_wifi_set_ps(WIFI_PS_NONE));

    init_ap_ssid();

    ESP_ERROR_CHECK(esp_wifi_start());
    ESP_ERROR_CHECK(esp_wifi_set_channel(AP_CHANNEL, WIFI_SECOND_CHAN_NONE));

    Serial.printf("WiFi AP started on ch%d\n", AP_CHANNEL);
    #if DUAL_BAND
    Serial.printf("5GHz TX enabled: ch");
    for (int i = 0; i < NUM_5G_CHANNELS; i++)
        Serial.printf("%d%s", CHANNELS_5G[i], i < NUM_5G_CHANNELS - 1 ? "," : "\n");
    #endif

    ledFlash(100);
    Serial.println("Ready. Awaiting serial commands.\n");

    #if AUTOSTART
    strncpy(g_basic_id, DEFAULT_ID, ODID_ID_SIZE);
    g_basic_id[ODID_ID_SIZE] = '\0';
    g_drone_lat = DEFAULT_LAT;
    g_drone_lon = DEFAULT_LON;
    g_drone_alt = DEFAULT_ALT;
    g_pilot_lat = DEFAULT_PLAT;
    g_pilot_lon = DEFAULT_PLON;
    g_has_data = true;
    broadcastEnabled = true;
    update_ap_ssid();
    startBeep();
    Serial.println("AUTOSTART: broadcasting with default config");
    Serial.printf("  ID=%s lat=%.4f lon=%.4f alt=%d\n",
                  g_basic_id, g_drone_lat, g_drone_lon, g_drone_alt);
    #endif
}

void loop() {
    static char json_buf[1024];
    static size_t json_idx = 0;
    static unsigned long lastTx = 0;

    while (Serial.available()) {
        char c = Serial.read();
        if (c == '\r') continue;

        if (c == '\n' || json_idx >= sizeof(json_buf) - 1) {
            json_buf[json_idx] = '\0';
            json_idx = 0;

            if (json_buf[0] != '{') continue;

            StaticJsonDocument<1024> doc;
            if (deserializeJson(doc, json_buf) != DeserializationError::Ok)
                continue;

            if (doc.containsKey("path") && !doc.containsKey("drone_lat") && !doc.containsKey("action"))
                continue;

            // Mute controls
            if (doc.containsKey("buzzer_mute")) {
                buzzerMuted = doc["buzzer_mute"].as<bool>();
                if (buzzerMuted) noTone(BUZZER_PIN);
            }
            if (doc.containsKey("led_mute")) {
                ledMuted = doc["led_mute"].as<bool>();
                if (ledMuted) ledOff();
            }

            // Band mode: 0=2.4 only, 1=5GHz only, 2=dual
            if (doc.containsKey("band_mode")) {
                uint8_t bm = doc["band_mode"].as<uint8_t>();
                #if DUAL_BAND
                g_band_mode = (bm <= 2) ? bm : 2;
                #else
                g_band_mode = 0;
                #endif
                Serial.printf("Band mode: %d\n", g_band_mode);
            }

            // 5GHz channel enables: array of booleans [ch149, ch153, ch157, ch161, ch165]
            if (doc.containsKey("channels_5g")) {
                JsonArray ch = doc["channels_5g"].as<JsonArray>();
                if (ch) {
                    for (uint8_t i = 0; i < NUM_5G_CHANNELS && i < ch.size(); i++)
                        g_5g_ch_enabled[i] = ch[i].as<bool>();
                }
            }

            if (doc.containsKey("basic_id")) {
                strncpy(g_basic_id, doc["basic_id"] | "", ODID_ID_SIZE);
                g_basic_id[ODID_ID_SIZE] = '\0';
            }

            if (doc.containsKey("drone_lat") && doc.containsKey("drone_long") && doc.containsKey("drone_altitude")) {
                g_drone_lat = doc["drone_lat"];
                g_drone_lon = doc["drone_long"];
                g_drone_alt = doc["drone_altitude"];
            }

            if (doc.containsKey("pilot_lat") && doc.containsKey("pilot_long")) {
                g_pilot_lat = doc["pilot_lat"];
                g_pilot_lon = doc["pilot_long"];
            }

            g_has_data = true;

            if (doc.containsKey("mac")) {
                const char *m = doc["mac"] | "";
                if (!parse_mac(m, g_override_src_mac))
                    g_dynamic_override = false;
                else
                    g_dynamic_override = true;
            }

            const char *action = doc["action"].as<const char *>();
            if (action) {
                Serial.printf("CMD: %s\n", action);

                if (strcmp(action, "stop") == 0) {
                    broadcastEnabled = false;
                    g_has_data = false;
                    clear_vendor_ie();
                    stopBeep();
                    ledOff();
                    Serial.println("STOP: broadcasts off");
                } else if (strcmp(action, "start") == 0) {
                    broadcastEnabled = true;
                    g_has_data = true;
                    startBeep();
                    ledFlash(150);
                    Serial.println("START: broadcasts on");
                } else if (strcmp(action, "pause") == 0) {
                    beep(1500, 80);
                    Serial.println("PAUSE: position frozen");
                }
            }

            if (doc.containsKey("path")) {
                JsonArray p = doc["path"].as<JsonArray>();
                if (p && p.size() == 0) g_has_data = false;
            }
        } else {
            json_buf[json_idx++] = c;
        }
    }

    if (!broadcastEnabled || !g_has_data) {
        delay(10);
        return;
    }

    if (millis() - lastTx >= TX_INTERVAL_MS) {
        lastTx = millis();
        inject_odid(g_basic_id, g_drone_lat, g_drone_lon, g_drone_alt, g_pilot_lat, g_pilot_lon);
        heartbeatTick();
        ledFlash(20);
        const char *bstr = g_band_mode == 0 ? "2.4G" : g_band_mode == 1 ? "5G" : "DUAL";
        Serial.printf("TX lat=%.4f lon=%.4f alt=%d band=%s\n", g_drone_lat, g_drone_lon, g_drone_alt, bstr);
    }
}