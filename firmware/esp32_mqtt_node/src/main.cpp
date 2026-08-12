  #include <Arduino.h>
#include <PubSubClient.h>
#include <WiFi.h>

#ifndef WIFI_SSID
#define WIFI_SSID "YOUR_WIFI"
#endif

#ifndef WIFI_PASSWORD
#define WIFI_PASSWORD "YOUR_PASSWORD"
#endif

#ifndef MQTT_HOST
#define MQTT_HOST "192.168.0.193"
#endif

#ifndef MQTT_PORT
#define MQTT_PORT 1883
#endif

#ifndef MQTT_TOPIC_PREFIX
#define MQTT_TOPIC_PREFIX "thermal-nexus/v1"
#endif

#ifndef NODE_ID
#define NODE_ID "ESP32_DEV_01"
#endif

#ifndef RUN_ID
#define RUN_ID "ESP32_LIVE_001"
#endif

#ifndef REAL_SENSOR
#define REAL_SENSOR 0
#endif

#ifndef SENSOR_INTERVAL_MS
#define SENSOR_INTERVAL_MS 1000
#endif

#ifndef MQTT_PUBLISH_INTERVAL_MS
#define MQTT_PUBLISH_INTERVAL_MS 2000
#endif

static constexpr uint32_t WIFI_RETRY_MS = 5000;
static constexpr uint32_t MQTT_RETRY_MS = 3000;
static constexpr size_t PAYLOAD_BYTES = 640;

struct SensorReading {
  float temperatureC;
  bool valid;
  const char *dataSourceType;
};

WiFiClient wifiClient;
PubSubClient mqttClient(wifiClient);

static uint32_t lastWifiAttemptMs = 0;
static uint32_t lastMqttAttemptMs = 0;
static uint32_t lastSensorReadMs = 0;
static uint32_t lastPublishMs = 0;
static uint32_t sequenceNumber = 0;
static SensorReading latestReading = {NAN, false, "SYNTHETIC"};

static String telemetryTopic() {
  String topic = MQTT_TOPIC_PREFIX;
  topic += "/nodes/";
  topic += NODE_ID;
  topic += "/telemetry";
  return topic;
}

static SensorReading readSimulatedSensor() {
  static const float pattern[] = {4.1f, 4.2f, 4.4f, 4.8f, 5.3f,
                                  5.9f, 6.7f, 7.5f, 8.2f};
  static size_t index = 0;
  float value = pattern[index % (sizeof(pattern) / sizeof(pattern[0]))];
  index++;
  return {value, true, "SYNTHETIC"};
}

static SensorReading readRealSensor() {
  // Hardware hook for TMP117 or another validated physical sensor.
  // Do not publish PROJECT_COLLECTED until an actual sensor read succeeds.
  return {NAN, false, "PROJECT_COLLECTED"};
}

static SensorReading readSensor() {
#if REAL_SENSOR
  return readRealSensor();
#else
  return readSimulatedSensor();
#endif
}

static void ensureWifi() {
  if (WiFi.status() == WL_CONNECTED) {
    return;
  }

  uint32_t now = millis();
  if (now - lastWifiAttemptMs < WIFI_RETRY_MS) {
    return;
  }
  lastWifiAttemptMs = now;

  Serial.println("[WIFI] connecting...");
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
}

static void logWifiConnectedOnce() {
  static bool logged = false;
  if (WiFi.status() == WL_CONNECTED && !logged) {
    logged = true;
    Serial.print("[WIFI] connected IP=");
    Serial.println(WiFi.localIP());
  }
  if (WiFi.status() != WL_CONNECTED) {
    logged = false;
  }
}

static void ensureMqtt() {
  if (WiFi.status() != WL_CONNECTED || mqttClient.connected()) {
    return;
  }

  uint32_t now = millis();
  if (now - lastMqttAttemptMs < MQTT_RETRY_MS) {
    return;
  }
  lastMqttAttemptMs = now;

  String clientId = "thermal-nexus-";
  clientId += NODE_ID;
  clientId += "-";
  clientId += String((uint32_t)ESP.getEfuseMac(), HEX);

  Serial.print("[MQTT] connecting to ");
  Serial.print(MQTT_HOST);
  Serial.print(":");
  Serial.println(MQTT_PORT);

  if (mqttClient.connect(clientId.c_str())) {
    Serial.println("[MQTT] connected");
  } else {
    Serial.print("[MQTT] disconnected rc=");
    Serial.println(mqttClient.state());
  }
}

static bool buildTelemetryPayload(char *buffer, size_t length, SensorReading reading) {
  const char *battery = "null";
  int written = snprintf(
      buffer,
      length,
      "{\"protocol_version\":1,"
      "\"message_type\":\"telemetry\","
      "\"timestamp_ms\":%lu,"
      "\"run_id\":\"%s\","
      "\"node_id\":\"%s\","
      "\"sequence_number\":%lu,"
      "\"temperature_c\":%.2f,"
      "\"sensor_valid\":%s,"
      "\"battery_voltage\":%s,"
      "\"data_source_type\":\"%s\"}",
      (unsigned long)millis(),
      RUN_ID,
      NODE_ID,
      (unsigned long)sequenceNumber,
      reading.temperatureC,
      reading.valid ? "true" : "false",
      battery,
      reading.dataSourceType);
  return written > 0 && (size_t)written < length;
}

static void maybeReadSensor() {
  uint32_t now = millis();
  if (now - lastSensorReadMs < SENSOR_INTERVAL_MS) {
    return;
  }
  lastSensorReadMs = now;
  latestReading = readSensor();

  if (!latestReading.valid) {
    Serial.println("[SENSOR] invalid - no telemetry published");
    return;
  }

  Serial.print("[SENSOR] temp=");
  Serial.print(latestReading.temperatureC, 2);
  Serial.print(" source=");
  Serial.println(latestReading.dataSourceType);
}

static void maybePublishTelemetry() {
  uint32_t now = millis();
  if (now - lastPublishMs < MQTT_PUBLISH_INTERVAL_MS) {
    return;
  }
  lastPublishMs = now;

  if (!latestReading.valid) {
    return;
  }
  if (!mqttClient.connected()) {
    Serial.println("[MQTT] publish skipped - disconnected");
    return;
  }

  sequenceNumber++;
  char payload[PAYLOAD_BYTES];
  if (!buildTelemetryPayload(payload, sizeof(payload), latestReading)) {
    Serial.println("[MQTT] publish failed - payload too large");
    return;
  }

  bool ok = mqttClient.publish(telemetryTopic().c_str(), payload);
  if (ok) {
    Serial.print("[MQTT] published seq=");
    Serial.print(sequenceNumber);
    Serial.print(" temp=");
    Serial.println(latestReading.temperatureC, 2);
  } else {
    Serial.print("[MQTT] publish failed seq=");
    Serial.println(sequenceNumber);
  }
}

void setup() {
  Serial.begin(115200);
  delay(300);
  Serial.println();
  Serial.println("[BOOT] Thermal Nexus ESP32 MQTT Node");
#if REAL_SENSOR
  Serial.println("[MODE] REAL_SENSOR requested");
#else
  Serial.println("[MODE] SIMULATED_SENSOR -> SYNTHETIC provenance");
#endif

  mqttClient.setServer(MQTT_HOST, MQTT_PORT);
  ensureWifi();
}

void loop() {
  ensureWifi();
  logWifiConnectedOnce();
  ensureMqtt();
  mqttClient.loop();
  maybeReadSensor();
  maybePublishTelemetry();
}
