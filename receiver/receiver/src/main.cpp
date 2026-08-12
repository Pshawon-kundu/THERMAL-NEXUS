// Thermal Nexus ESP32 receiver bridge.
//
// Pipeline:
//   Sensor/RF packet -> ESP32 receiver -> MQTT -> Python ingestion -> SQLite -> Streamlit
//
// Supported inbound packet formats:
//   1. Full JSON contract:
//      {"protocol_version":1,"message_type":"telemetry",...}
//   2. Compact line for simple firmware bring-up:
//      TNX,run_id,node_id,sequence,timestamp,temp_c,state,risk,battery_v,rssi,sensor_valid
//
// The ESP32 publishes PROJECT_COLLECTED data only. Simulation/replay remains handled by
// the Python simulator and is still labeled SYNTHETIC.

#include <Arduino.h>
#include <ArduinoJson.h>
#include <LoRa.h>
#include <MQTT.h>
#include <WiFi.h>

#ifndef WIFI_SSID
#define WIFI_SSID "CHANGE_ME"
#endif

#ifndef WIFI_PASSWORD
#define WIFI_PASSWORD "CHANGE_ME"
#endif

#ifndef MQTT_HOST
#define MQTT_HOST "192.168.1.10"
#endif

#ifndef MQTT_PORT
#define MQTT_PORT 1883
#endif

#ifndef MQTT_TOPIC_PREFIX
#define MQTT_TOPIC_PREFIX "thermal-nexus/v1"
#endif

#ifndef NODE_ID
#define NODE_ID "NODE_01"
#endif

#ifndef RUN_ID
#define RUN_ID "esp32-live-run"
#endif

#ifndef LORA_FREQ
#define LORA_FREQ 433E6
#endif

#ifndef LORA_SS
#define LORA_SS 5
#endif

#ifndef LORA_RST
#define LORA_RST 14
#endif

#ifndef LORA_DIO0
#define LORA_DIO0 2
#endif

static constexpr int SERIAL_BAUD = 115200;
static constexpr uint32_t WIFI_RETRY_MS = 5000;
static constexpr uint32_t MQTT_RETRY_MS = 3000;
static constexpr size_t MQTT_BUFFER_BYTES = 2048;

WiFiClient wifiClient;
MQTTClient mqttClient(MQTT_BUFFER_BYTES);

static bool loraReady = false;
static uint32_t lastWifiAttemptMs = 0;
static uint32_t lastMqttAttemptMs = 0;
static uint32_t receivedPackets = 0;
static uint32_t publishedMessages = 0;
static uint32_t rejectedPackets = 0;
static uint32_t duplicatePackets = 0;
static bool haveLastSequence = false;
static long lastSequence = -1;
static String serialBuffer;

static String topicFor(const char *nodeId, const char *messageType) {
  String topic = MQTT_TOPIC_PREFIX;
  topic += "/nodes/";
  topic += nodeId;
  topic += "/";
  topic += messageType;
  return topic;
}

static String systemTopic() {
  String topic = MQTT_TOPIC_PREFIX;
  topic += "/system/status";
  return topic;
}

static String fallbackTimestamp() {
  uint32_t seconds = millis() / 1000;
  char output[32];
  snprintf(
      output,
      sizeof(output),
      "1970-01-01T%02lu:%02lu:%02luZ",
      (seconds / 3600UL) % 24UL,
      (seconds / 60UL) % 60UL,
      seconds % 60UL);
  return String(output);
}

static bool isValidState(const String &state) {
  return state == "STABLE" || state == "TRANSITION" ||
         state == "EXCURSION_RISK" || state == "SENSOR_FAULT" ||
         state == "MODEL_FAULT" || state == "LOW_BATTERY";
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
  Serial.print("[WIFI] connecting to ");
  Serial.println(WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
}

static void publishSystemStatus(const char *status) {
  if (!mqttClient.connected()) {
    return;
  }
  JsonDocument doc;
  doc["protocol_version"] = 1;
  doc["message_type"] = "status";
  doc["timestamp"] = fallbackTimestamp();
  doc["receiver_id"] = "esp32-mqtt-receiver";
  doc["status"] = status;
  doc["received_packets"] = receivedPackets;
  doc["published_messages"] = publishedMessages;
  doc["rejected_packets"] = rejectedPackets;
  doc["duplicate_packets"] = duplicatePackets;
  String payload;
  serializeJson(doc, payload);
  mqttClient.publish(systemTopic(), payload, false, 1);
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

  String clientId = "thermal-nexus-esp32-";
  clientId += String((uint32_t)ESP.getEfuseMac(), HEX);
  Serial.print("[MQTT] connecting to ");
  Serial.print(MQTT_HOST);
  Serial.print(":");
  Serial.println(MQTT_PORT);

  if (mqttClient.connect(clientId.c_str())) {
    Serial.println("[MQTT] connected");
    publishSystemStatus("online");
  } else {
    Serial.println("[MQTT] connect failed");
  }
}

static bool publishJsonPayload(JsonDocument &doc) {
  const char *messageType = doc["message_type"] | "";
  const char *nodeId = doc["node_id"] | NODE_ID;
  if (strcmp(messageType, "telemetry") != 0 &&
      strcmp(messageType, "decision") != 0 &&
      strcmp(messageType, "alert") != 0) {
    Serial.println("[DROP] unsupported message_type");
    return false;
  }

  doc["protocol_version"] = doc["protocol_version"] | 1;
  doc["run_id"] = doc["run_id"] | RUN_ID;
  doc["node_id"] = nodeId;
  doc["data_source_type"] = "PROJECT_COLLECTED";
  doc["timestamp"] = doc["timestamp"] | fallbackTimestamp();

  if (!mqttClient.connected()) {
    Serial.println("[DROP] MQTT disconnected");
    return false;
  }

  String payload;
  serializeJson(doc, payload);
  bool ok = mqttClient.publish(topicFor(nodeId, messageType), payload, false, 1);
  if (ok) {
    publishedMessages++;
    Serial.print("[MQTT TX] ");
    Serial.print(messageType);
    Serial.print(" node=");
    Serial.print(nodeId);
    Serial.print(" bytes=");
    Serial.println(payload.length());
  } else {
    Serial.println("[MQTT TX] publish failed");
  }
  return ok;
}

static bool publishTelemetryAndDecision(
    const String &runId,
    const String &nodeId,
    long sequence,
    const String &timestamp,
    float temperatureC,
    const String &state,
    float risk,
    float batteryVoltage,
    int rssiDbm,
    bool sensorValid) {
  if (!isValidState(state) || risk < 0.0f || risk > 1.0f) {
    Serial.println("[DROP] invalid state/risk");
    return false;
  }

  JsonDocument telemetry;
  telemetry["protocol_version"] = 1;
  telemetry["message_type"] = "telemetry";
  telemetry["timestamp"] = timestamp;
  telemetry["run_id"] = runId;
  telemetry["node_id"] = nodeId;
  telemetry["sequence_number"] = sequence;
  telemetry["temperature_c"] = temperatureC;
  telemetry["sensor_valid"] = sensorValid;
  telemetry["battery_voltage"] = batteryVoltage;
  telemetry["rssi_dbm"] = rssiDbm;
  telemetry["data_source_type"] = "PROJECT_COLLECTED";

  JsonDocument decision;
  decision["protocol_version"] = 1;
  decision["message_type"] = "decision";
  decision["timestamp"] = timestamp;
  decision["run_id"] = runId;
  decision["node_id"] = nodeId;
  decision["sequence_number"] = sequence;
  decision["predicted_state"] = state;
  decision["risk_probability"] = risk;
  decision["applied_state"] = state;
  decision["sampling_interval_seconds"] = 1.0;
  decision["transmission_interval_seconds"] = 1.0;
  decision["model_valid"] = true;
  decision["model_version"] = "esp32_receiver_bridge_v1";
  decision["data_source_type"] = "PROJECT_COLLECTED";

  bool tOk = publishJsonPayload(telemetry);
  bool dOk = publishJsonPayload(decision);
  return tOk && dOk;
}

static bool parseCompactPacket(const String &line) {
  String parts[11];
  int partCount = 0;
  int start = 0;
  for (int i = 0; i <= line.length() && partCount < 11; i++) {
    if (i == line.length() || line[i] == ',') {
      parts[partCount++] = line.substring(start, i);
      parts[partCount - 1].trim();
      start = i + 1;
    }
  }
  if (partCount != 11 || parts[0] != "TNX") {
    Serial.println("[DROP] malformed compact packet");
    return false;
  }

  long sequence = parts[3].toInt();
  if (haveLastSequence && sequence <= lastSequence) {
    duplicatePackets++;
    Serial.print("[DUP] seq=");
    Serial.println(sequence);
    return true;
  }
  haveLastSequence = true;
  lastSequence = sequence;

  String timestamp = parts[4].length() ? parts[4] : fallbackTimestamp();
  return publishTelemetryAndDecision(
      parts[1],
      parts[2],
      sequence,
      timestamp,
      parts[5].toFloat(),
      parts[6],
      parts[7].toFloat(),
      parts[8].toFloat(),
      parts[9].toInt(),
      parts[10].toInt() != 0);
}

static bool processPacket(String line) {
  line.trim();
  if (!line.length()) {
    return false;
  }
  receivedPackets++;
  Serial.print("[RX] ");
  Serial.println(line);

  if (line[0] == '{') {
    JsonDocument doc;
    DeserializationError error = deserializeJson(doc, line);
    if (error) {
      Serial.print("[DROP] JSON parse failed: ");
      Serial.println(error.c_str());
      rejectedPackets++;
      return false;
    }
    bool ok = publishJsonPayload(doc);
    if (!ok) {
      rejectedPackets++;
    }
    return ok;
  }

  bool ok = parseCompactPacket(line);
  if (!ok) {
    rejectedPackets++;
  }
  return ok;
}

static void setupLoRa() {
  LoRa.setPins(LORA_SS, LORA_RST, LORA_DIO0);
  loraReady = LoRa.begin(LORA_FREQ);
  if (!loraReady) {
    Serial.println("[LORA] unavailable; serial packet input still enabled");
    return;
  }
  LoRa.enableCrc();
  LoRa.receive();
  Serial.println("[LORA] receiver ready");
}

static void pollLoRa() {
  if (!loraReady) {
    return;
  }
  int packetSize = LoRa.parsePacket();
  if (packetSize <= 0) {
    return;
  }
  String line;
  while (LoRa.available()) {
    line += (char)LoRa.read();
  }
  processPacket(line);
}

static void pollSerial() {
  while (Serial.available()) {
    char ch = (char)Serial.read();
    if (ch == '\n' || ch == '\r') {
      if (serialBuffer.length()) {
        processPacket(serialBuffer);
        serialBuffer = "";
      }
    } else if (serialBuffer.length() < 1800) {
      serialBuffer += ch;
    } else {
      Serial.println("[DROP] serial line too long");
      serialBuffer = "";
      rejectedPackets++;
    }
  }
}

void setup() {
  Serial.begin(SERIAL_BAUD);
  delay(300);
  Serial.println();
  Serial.println("[BOOT] Thermal Nexus ESP32 MQTT receiver");
  Serial.println("[MODE] PROJECT_COLLECTED MQTT bridge");

  setupLoRa();
  WiFi.mode(WIFI_STA);
  mqttClient.begin(MQTT_HOST, MQTT_PORT, wifiClient);
}

void loop() {
  ensureWifi();
  ensureMqtt();
  mqttClient.loop();
  pollLoRa();
  pollSerial();
}
