#pragma once
#include <Arduino.h>

struct DeviceConfig {
  String wifiSsid, wifiPassword, deviceUid, deviceSecret;
  String apiBase = "http://127.0.0.1:8010";
  String mqttHost = "127.0.0.1";
  uint16_t mqttPort = 8883;
  uint32_t sampleMs = 10000;
  bool mqttTls = true;
  int8_t shtSda = -1, shtScl = -1, ds18b20Pin = -1, leakPin = -1;
  int8_t doorPin = -1, ultrasonicTriggerPin = -1, ultrasonicEchoPin = -1;
  int8_t analogLevelPin = -1, relayPin = -1, ledPin = -1, buzzerPin = -1;
  int8_t gpsRx = -1, gpsTx = -1;  // u-blox NEO-6M/M8N NMEA over UART (GPS Asset Tracker)
};
