#include <Arduino.h>
#include <ArduinoJson.h>
#include <ArduinoOTA.h>
#include <HTTPClient.h>
#include <LittleFS.h>
#include <Preferences.h>
#include <PubSubClient.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <Wire.h>
#include <Adafruit_SHT31.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <esp_task_wdt.h>
#include <mbedtls/md.h>
#include "device_config.h"

Preferences prefs;
DeviceConfig cfg;
WiFiClient plainClient;
WiFiClientSecure secureClient;
PubSubClient mqtt;
Adafruit_SHT31 sht31;
OneWire *oneWire = nullptr;
DallasTemperature *ds18b20 = nullptr;
uint32_t lastSample = 0, lastCommandPoll = 0;
bool safeMode = false;

String topic(const String &suffix) {
  return prefs.getString("topicBase", "") + "/" + suffix;
}

String isoTimestamp() {
  struct tm timeinfo;
  if (!getLocalTime(&timeinfo, 1000)) return "1970-01-01T00:00:00Z";
  char value[25]; strftime(value, sizeof(value), "%Y-%m-%dT%H:%M:%SZ", &timeinfo); return value;
}

String hmacSha256(const String &input, const String &secret) {
  byte output[32]; const mbedtls_md_info_t *info = mbedtls_md_info_from_type(MBEDTLS_MD_SHA256);
  mbedtls_md_hmac(info, (const unsigned char*)secret.c_str(), secret.length(), (const unsigned char*)input.c_str(), input.length(), output);
  char hex[65]; for (int i=0;i<32;i++) sprintf(hex + i*2, "%02x", output[i]); hex[64]=0; return String(hex);
}

void loadConfig() {
  prefs.begin("geovision", false);
  cfg.wifiSsid=prefs.getString("ssid", ""); cfg.wifiPassword=prefs.getString("wifiPass", "");
  cfg.deviceUid=prefs.getString("deviceUid", ""); cfg.deviceSecret=prefs.getString("deviceKey", "");
  cfg.apiBase=prefs.getString("apiBase", cfg.apiBase); cfg.mqttHost=prefs.getString("mqttHost", cfg.mqttHost);
  cfg.mqttPort=prefs.getUShort("mqttPort", cfg.mqttPort); cfg.sampleMs=prefs.getULong("sampleMs", cfg.sampleMs);
  cfg.mqttTls=prefs.getBool("mqttTls", true);
  cfg.shtSda=prefs.getChar("shtSda", -1); cfg.shtScl=prefs.getChar("shtScl", -1); cfg.ds18b20Pin=prefs.getChar("dsPin", -1);
  cfg.leakPin=prefs.getChar("leakPin", -1); cfg.doorPin=prefs.getChar("doorPin", -1); cfg.analogLevelPin=prefs.getChar("levelPin", -1);
  cfg.relayPin=prefs.getChar("relayPin", -1); cfg.ledPin=prefs.getChar("ledPin", -1); cfg.buzzerPin=prefs.getChar("buzzPin", -1);
}

void saveSerialConfiguration(JsonDocument &doc) {
  JsonObject wifi=doc["wifi"], server=doc["server"], pins=doc["pins"];
  prefs.putString("ssid", wifi["ssid"] | ""); prefs.putString("wifiPass", wifi["password"] | "");
  prefs.putString("deviceUid", doc["device_uid"] | ""); prefs.putString("provToken", doc["provisioning_token"] | "");
  prefs.putString("apiBase", server["api_base"] | "http://127.0.0.1:8010"); prefs.putString("mqttHost", server["mqtt_host"] | "127.0.0.1");
  prefs.putUShort("mqttPort", server["mqtt_port"] | 8883); prefs.putBool("mqttTls", server["mqtt_tls"] | true);
  prefs.putULong("sampleMs", doc["sample_ms"] | 10000);
  for (auto pair : {std::pair<const char*,const char*>("sht_sda","shtSda"), {"sht_scl","shtScl"}, {"ds18b20","dsPin"}, {"leak","leakPin"}, {"door","doorPin"}, {"analog_level","levelPin"}, {"relay","relayPin"}, {"led","ledPin"}, {"buzzer","buzzPin"}}) if (pins[pair.first].is<int>()) prefs.putChar(pair.second, pins[pair.first].as<int>());
  Serial.println("CONFIG_SAVED_RESTARTING"); delay(500); ESP.restart();
}

void handleSerialProvisioning() {
  if (!Serial.available()) return;
  String input=Serial.readStringUntil('\n'); JsonDocument doc;
  if (deserializeJson(doc, input)) { Serial.println("CONFIG_ERROR_INVALID_JSON"); return; }
  if (doc["factory_reset"] == true) { prefs.clear(); LittleFS.format(); Serial.println("FACTORY_RESET"); delay(300); ESP.restart(); }
  saveSerialConfiguration(doc);
}

bool connectWifi() {
  if (cfg.wifiSsid.isEmpty()) return false;
  WiFi.mode(WIFI_STA); WiFi.begin(cfg.wifiSsid.c_str(), cfg.wifiPassword.c_str());
  for (int i=0;i<30 && WiFi.status()!=WL_CONNECTED;i++) { delay(500); esp_task_wdt_reset(); }
  if (WiFi.status()==WL_CONNECTED) { configTime(0,0,"pool.ntp.org","time.google.com"); return true; }
  return false;
}

bool exchangeProvisioningToken() {
  if (!cfg.deviceSecret.isEmpty()) return true;
  String token=prefs.getString("provToken", ""); if (token.isEmpty() || WiFi.status()!=WL_CONNECTED) return false;
  HTTPClient http; http.begin(cfg.apiBase + "/iot/provision/exchange"); http.addHeader("Content-Type","application/json");
  JsonDocument request; request["device_uid"]=cfg.deviceUid; request["provisioning_token"]=token; request["firmware_version"]=GV_FIRMWARE_VERSION;
  String body; serializeJson(request,body); int code=http.POST(body); if(code!=200){ Serial.printf("PROVISION_FAILED_%d\n",code); http.end(); return false; }
  JsonDocument response; deserializeJson(response,http.getString()); http.end();
  cfg.deviceSecret=response["device_secret"].as<String>(); prefs.putString("deviceKey",cfg.deviceSecret); prefs.remove("provToken");
  String telemetry=response["topics"]["telemetry"].as<String>(); int slash=telemetry.lastIndexOf('/'); prefs.putString("topicBase",telemetry.substring(0,slash));
  Serial.println("PROVISIONED"); return true;
}

void initializePinsAndSensors() {
  if(cfg.ledPin>=0){pinMode(cfg.ledPin,OUTPUT);digitalWrite(cfg.ledPin,LOW);} if(cfg.relayPin>=0){pinMode(cfg.relayPin,OUTPUT);digitalWrite(cfg.relayPin,LOW);}
  if(cfg.buzzerPin>=0){pinMode(cfg.buzzerPin,OUTPUT);digitalWrite(cfg.buzzerPin,LOW);} if(cfg.leakPin>=0)pinMode(cfg.leakPin,INPUT_PULLUP); if(cfg.doorPin>=0)pinMode(cfg.doorPin,INPUT_PULLUP);
  if(cfg.shtSda>=0 && cfg.shtScl>=0){Wire.begin(cfg.shtSda,cfg.shtScl);sht31.begin(0x44);} if(cfg.ds18b20Pin>=0){oneWire=new OneWire(cfg.ds18b20Pin);ds18b20=new DallasTemperature(oneWire);ds18b20->begin();}
}

String makeTelemetry() {
  float humidity=NAN, temperature=NAN;
  if(cfg.ds18b20Pin>=0){ds18b20->requestTemperatures();temperature=ds18b20->getTempCByIndex(0);if(temperature<=-100)temperature=NAN;}
  if(cfg.shtSda>=0){humidity=sht31.readHumidity();if(isnan(temperature))temperature=sht31.readTemperature();}
  JsonDocument unsignedDoc;
  // Keys are inserted lexicographically to match backend canonical JSON.
  unsignedDoc["device_uid"]=cfg.deviceUid; JsonObject values=unsignedDoc["measurements"].to<JsonObject>();
  values["battery"]=100.0; if(cfg.doorPin>=0)values["door_open"]=digitalRead(cfg.doorPin)==HIGH;
  if(!isnan(humidity))values["humidity"]=humidity; values["safety_ok"]=!safeMode; values["signal"]=constrain(2*(WiFi.RSSI()+100),0,100);
  if(cfg.analogLevelPin>=0)values["tank_level"]=100.0*analogRead(cfg.analogLevelPin)/4095.0; if(!isnan(temperature))values["temperature"]=temperature;
  if(cfg.leakPin>=0)values["water_leak"]=digitalRead(cfg.leakPin)==LOW;
  unsignedDoc["message_id"]="esp32-"+String((uint32_t)esp_random(),HEX); JsonObject metadata=unsignedDoc["metadata"].to<JsonObject>(); metadata["firmware"]=GV_FIRMWARE_VERSION; metadata["reset_reason"]=(int)esp_reset_reason();
  unsignedDoc["nonce"]=String((uint32_t)esp_random(),HEX)+String((uint32_t)esp_random(),HEX); unsignedDoc["timestamp"]=isoTimestamp();
  String canonical; serializeJson(unsignedDoc,canonical); unsignedDoc["signature"]=hmacSha256(canonical,cfg.deviceSecret); String output;serializeJson(unsignedDoc,output);return output;
}

String makeState(const char *state) {
  JsonDocument doc; doc["device_uid"]=cfg.deviceUid; doc["measurements"]["safety_ok"]=!safeMode;
  doc["message_id"]="state-"+String((uint32_t)esp_random(),HEX); doc["metadata"]["firmware"]=GV_FIRMWARE_VERSION;
  doc["nonce"]=String((uint32_t)esp_random(),HEX)+String((uint32_t)esp_random(),HEX); doc["state"]=state; doc["timestamp"]=isoTimestamp();
  String canonical;serializeJson(doc,canonical);doc["signature"]=hmacSha256(canonical,cfg.deviceSecret);String output;serializeJson(doc,output);return output;
}

void bufferPayload(const String &payload) { File file=LittleFS.open("/telemetry.queue","a"); if(file){file.println(payload);file.close();} }

bool publishPayload(const String &payload) {
  if(mqtt.connected() && mqtt.publish(topic("telemetry").c_str(),payload.c_str(),false)) return true;
  HTTPClient http; http.begin(cfg.apiBase+"/iot/ingest");http.addHeader("Content-Type","application/json");http.addHeader("Authorization","Device "+cfg.deviceSecret);http.addHeader("X-Device-ID",cfg.deviceUid);
  JsonDocument full,rest;deserializeJson(full,payload);for(const char *key:{"message_id","timestamp","measurements","metadata"})rest[key]=full[key];String body;serializeJson(rest,body);int code=http.POST(body);http.end();return code>=200&&code<300;
}

void flushBuffer() { if(!LittleFS.exists("/telemetry.queue"))return;File input=LittleFS.open("/telemetry.queue","r"), output=LittleFS.open("/telemetry.tmp","w");while(input.available()){String line=input.readStringUntil('\n');if(line.length()&&!publishPayload(line))output.println(line);esp_task_wdt_reset();}input.close();output.close();LittleFS.remove("/telemetry.queue");LittleFS.rename("/telemetry.tmp","/telemetry.queue"); }

void commandCallback(char *topicName, byte *payload, unsigned int length) {
  String raw;for(unsigned i=0;i<length;i++)raw+=(char)payload[i];JsonDocument envelope;if(deserializeJson(envelope,raw))return;
  JsonObject command=envelope["payload"].as<JsonObject>();String canonical;serializeJson(command,canonical);
  if(hmacSha256(canonical,cfg.deviceSecret)!=envelope["signature"].as<String>()){Serial.println("COMMAND_SIGNATURE_REJECTED");return;}
  String name=command["name"]|"", status="completed"; bool allowed=!safeMode;
  if(name=="beacon_on"&&cfg.ledPin>=0)digitalWrite(cfg.ledPin,HIGH);else if(name=="beacon_off"&&cfg.ledPin>=0)digitalWrite(cfg.ledPin,LOW);
  else if(name=="buzzer_on"&&cfg.buzzerPin>=0)digitalWrite(cfg.buzzerPin,HIGH);else if(name=="buzzer_off"&&cfg.buzzerPin>=0)digitalWrite(cfg.buzzerPin,LOW);
  else if((name=="relay_on"||name=="demo_fan_on"||name=="low_voltage_valve_open")&&cfg.relayPin>=0&&allowed)digitalWrite(cfg.relayPin,HIGH);
  else if((name=="relay_off"||name=="demo_fan_off"||name=="low_voltage_valve_close")&&cfg.relayPin>=0)digitalWrite(cfg.relayPin,LOW);
  else if(name=="set_reporting_interval")cfg.sampleMs=constrain(command["arguments"]["milliseconds"]|10000,1000,3600000);
  else if(name=="restart"){status="acknowledged";}else if(name!="request_diagnostics")status="rejected";
  JsonDocument result;result["actual_state"]["relay"]=cfg.relayPin>=0?digitalRead(cfg.relayPin):false;result["command_id"]=command["id"];result["device_uid"]=cfg.deviceUid;result["message"]="ESP32 command handler";result["nonce"]=String((uint32_t)esp_random(),HEX)+String((uint32_t)esp_random(),HEX);result["status"]=status;result["timestamp"]=isoTimestamp();String canonicalResult;serializeJson(result,canonicalResult);result["signature"]=hmacSha256(canonicalResult,cfg.deviceSecret);String out;serializeJson(result,out);mqtt.publish(::topic("command-results").c_str(),out.c_str());
  if(name=="restart"&&status=="acknowledged"){delay(500);ESP.restart();}
}

void connectMqtt() {
  if(mqtt.connected()||cfg.deviceSecret.isEmpty()||WiFi.status()!=WL_CONNECTED)return;
  if(cfg.mqttTls){File cert=LittleFS.open("/ca.crt","r");if(!cert)return;String ca=cert.readString();cert.close();secureClient.setCACert(ca.c_str());mqtt.setClient(secureClient);}else mqtt.setClient(plainClient);
  mqtt.setServer(cfg.mqttHost.c_str(),cfg.mqttPort);mqtt.setCallback(commandCallback);
  String offline=makeState("offline");
  if(mqtt.connect(cfg.deviceUid.c_str(),topic("state").c_str(),1,true,offline.c_str())){mqtt.subscribe(topic("commands").c_str(),1);mqtt.subscribe(topic("configuration").c_str(),1);String online=makeState("online");mqtt.publish(topic("state").c_str(),online.c_str(),true);}
}

void setup() {
  Serial.begin(115200);delay(200);LittleFS.begin(true);loadConfig();
  uint8_t boots=prefs.getUChar("bootFails",0)+1;prefs.putUChar("bootFails",boots);safeMode=boots>3;
  esp_task_wdt_init(30,true);esp_task_wdt_add(NULL);
  connectWifi();exchangeProvisioningToken();initializePinsAndSensors();ArduinoOTA.setHostname(cfg.deviceUid.c_str());ArduinoOTA.begin();prefs.putUChar("bootFails",0);
  Serial.printf("GEOVISION_READY uid=%s safe_mode=%d\n",cfg.deviceUid.c_str(),safeMode);
}

void loop() {
  esp_task_wdt_reset();handleSerialProvisioning();if(WiFi.status()!=WL_CONNECTED)connectWifi();connectMqtt();mqtt.loop();ArduinoOTA.handle();
  if(millis()-lastSample>=cfg.sampleMs){lastSample=millis();String payload=makeTelemetry();if(!publishPayload(payload))bufferPayload(payload);else flushBuffer();}
  delay(10);
}
