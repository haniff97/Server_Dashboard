#!/usr/bin/env python3
"""
MQTT to Prometheus Exporter
Subscribes to MQTT topics from ESP32 and exposes metrics for Prometheus
"""
import paho.mqtt.client as mqtt
from prometheus_client import start_http_server, Gauge
import time

# Prometheus metrics for ESP32 devices
esp32_temperature = Gauge('esp32_temperature_celsius', 'Temperature from ESP32', ['device_id', 'location'])
esp32_humidity = Gauge('esp32_humidity_percent', 'Humidity from ESP32', ['device_id', 'location'])
esp32_motion = Gauge('esp32_motion_detected', 'Motion detected', ['device_id', 'location'])
esp32_light = Gauge('esp32_light_level', 'Light level', ['device_id', 'location'])

# MQTT Configuration
MQTT_BROKER = "localhost"
MQTT_PORT = 1883
MQTT_TOPICS = [
    "homelab/esp32/+/temperature",
    "homelab/esp32/+/humidity", 
    "homelab/esp32/+/motion",
    "homelab/esp32/+/light"
]

def on_connect(client, userdata, flags, rc):
    print(f"✅ Connected to MQTT broker with code: {rc}")
    for topic in MQTT_TOPICS:
        client.subscribe(topic)
        print(f"📡 Subscribed to {topic}")

def on_message(client, userdata, msg):
    """Parse MQTT message and update Prometheus metrics"""
    try:
        topic_parts = msg.topic.split('/')
        
        if len(topic_parts) >= 4:
            device_id = topic_parts[2]
            sensor_type = topic_parts[3]
            value = float(msg.payload.decode())
            
            if sensor_type == 'temperature':
                esp32_temperature.labels(device_id=device_id, location='homelab').set(value)
                print(f"🌡️  [{device_id}] Temperature: {value}°C")
            
            elif sensor_type == 'humidity':
                esp32_humidity.labels(device_id=device_id, location='homelab').set(value)
                print(f"💧 [{device_id}] Humidity: {value}%")
            
            elif sensor_type == 'motion':
                esp32_motion.labels(device_id=device_id, location='homelab').set(value)
                print(f"🚶 [{device_id}] Motion: {value}")
            
            elif sensor_type == 'light':
                esp32_light.labels(device_id=device_id, location='homelab').set(value)
                print(f"💡 [{device_id}] Light: {value}")
                
    except Exception as e:
        print(f"❌ Error processing message: {e}")

if __name__ == '__main__':
    print("🚀 Starting MQTT to Prometheus exporter on port 9324...")
    start_http_server(9324)
    
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    
    print(f"🔌 Connecting to MQTT broker at {MQTT_BROKER}:{MQTT_PORT}...")
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    
    print("👂 Listening for ESP32 sensor data...")
    client.loop_forever()
