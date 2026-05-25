"""Smart Home integratsiya — MQTT orqali qurilmalarni boshqarish.

"Chiroqni yoq" → MQTT publish → smart lamp ON
"Konditsionerni o'chir" → MQTT → AC OFF
"Harorat qancha?" → MQTT subscribe → sensor data

Protocol: MQTT (Mosquitto broker, Raspberry Pi da local)
Compatible: Zigbee2MQTT, Tasmota, ESPHome, Home Assistant
"""

import asyncio
import json
import re
from typing import Optional, Dict, Any, Callable

import structlog

from alisa.core.config import get_config

logger = structlog.get_logger()

# Try to import MQTT
try:
    import paho.mqtt.client as mqtt
    MQTT_AVAILABLE = True
except ImportError:
    MQTT_AVAILABLE = False


# Device registry — config.yaml dan yuklanadi
DEFAULT_DEVICES = {
    "chiroq": {"topic": "zigbee2mqtt/lamp/set", "on": '{"state":"ON"}', "off": '{"state":"OFF"}'},
    "lamp": {"topic": "zigbee2mqtt/lamp/set", "on": '{"state":"ON"}', "off": '{"state":"OFF"}'},
    "konditsioner": {"topic": "zigbee2mqtt/ac/set", "on": '{"state":"ON"}', "off": '{"state":"OFF"}'},
    "ac": {"topic": "zigbee2mqtt/ac/set", "on": '{"state":"ON"}', "off": '{"state":"OFF"}'},
    "televizor": {"topic": "zigbee2mqtt/tv/set", "on": '{"state":"ON"}', "off": '{"state":"OFF"}'},
    "tv": {"topic": "zigbee2mqtt/tv/set", "on": '{"state":"ON"}', "off": '{"state":"OFF"}'},
}


class SmartHome:
    """MQTT-based smart home controller."""

    def __init__(self):
        self.devices = DEFAULT_DEVICES.copy()
        self.client: Optional[Any] = None
        self.sensor_data: Dict[str, Any] = {}
        self._connected = False

        cfg = get_config().get("smart_home", {})
        self.broker = cfg.get("broker", "localhost")
        self.port = cfg.get("port", 1883)

        # Load custom devices from config
        for dev in cfg.get("devices", []):
            self.devices[dev["name"]] = {"topic": dev["topic"], "on": dev.get("on", '{"state":"ON"}'), "off": dev.get("off", '{"state":"OFF"}')}

        if MQTT_AVAILABLE:
            self._connect()

    def _connect(self):
        """Connect to MQTT broker."""
        try:
            self.client = mqtt.Client()
            self.client.on_message = self._on_message
            self.client.connect(self.broker, self.port, 60)
            self.client.subscribe("zigbee2mqtt/+")  # Subscribe to all devices
            self.client.loop_start()
            self._connected = True
            logger.info("mqtt_connected", broker=self.broker)
        except Exception as e:
            logger.warning("mqtt_connect_failed", error=str(e))
            self._connected = False

    def _on_message(self, client, userdata, msg):
        """Handle incoming MQTT messages (sensor data)."""
        try:
            data = json.loads(msg.payload.decode())
            device = msg.topic.split("/")[-1] if "/" in msg.topic else msg.topic
            self.sensor_data[device] = data
        except Exception:
            pass

    def parse_command(self, text: str) -> Optional[str]:
        """Parse smart home command. Returns response or None."""
        text_lower = text.lower()

        # ON commands
        for trigger in ["yoq", "yoqib", "включи", "turn on", "ochir"]:
            if trigger in text_lower and "o'chir" not in text_lower:
                device = self._find_device(text_lower)
                if device:
                    return self._control(device, "on")

        # OFF commands
        for trigger in ["o'chir", "выключи", "turn off"]:
            if trigger in text_lower:
                device = self._find_device(text_lower)
                if device:
                    return self._control(device, "off")

        # Temperature query
        if any(w in text_lower for w in ["harorat", "temperatura", "temperature"]):
            return self._get_temperature()

        return None

    def _find_device(self, text: str) -> Optional[str]:
        """Find device name in text."""
        for name in self.devices:
            if name in text:
                return name
        return None

    def _control(self, device_name: str, action: str) -> str:
        """Control a device."""
        if not MQTT_AVAILABLE or not self._connected:
            return f"{device_name} boshqaruvi mavjud emas (MQTT ulanmagan)."

        device = self.devices[device_name]
        payload = device["on"] if action == "on" else device["off"]

        try:
            self.client.publish(device["topic"], payload)
            action_uz = "yoqildi" if action == "on" else "o'chirildi"
            logger.info("smart_home_command", device=device_name, action=action)
            return f"{device_name.capitalize()} {action_uz}."
        except Exception as e:
            return f"Xatolik: {e}"

    def _get_temperature(self) -> str:
        """Get temperature from sensors."""
        for device, data in self.sensor_data.items():
            if "temperature" in data:
                return f"Harorat: {data['temperature']}°C"
        return "Harorat sensori topilmadi."

    def disconnect(self):
        if self.client and self._connected:
            self.client.loop_stop()
            self.client.disconnect()


_smart_home: Optional[SmartHome] = None


def get_smart_home() -> SmartHome:
    global _smart_home
    if _smart_home is None:
        _smart_home = SmartHome()
    return _smart_home
