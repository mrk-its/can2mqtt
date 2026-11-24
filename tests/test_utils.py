"""MQTT server URL parsing and the password kept out of logs (run: pytest tests/)."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from can2mqtt.utils import parse_mqtt_server_url, redact_auth  # noqa: E402


def test_parse_url_with_credentials():
    server, auth = parse_mqtt_server_url("mqtt://user:p@ss@broker:1884")
    assert server == "broker"
    assert auth == {"username": "user", "password": "p@ss", "port": 1884}


def test_parse_plain_host():
    assert parse_mqtt_server_url("localhost") == ("localhost", {})


def test_redact_auth_masks_password():
    _, auth = parse_mqtt_server_url("mqtt://user:secret@broker")
    redacted = redact_auth(auth)
    assert redacted == {"username": "user", "password": "***", "port": 1883}
    assert "secret" not in str(redacted)
    assert auth["password"] == "secret"  # the client still gets the real one


def test_redact_auth_without_password():
    _, auth = parse_mqtt_server_url("mqtt://user@broker")
    assert redact_auth(auth)["password"] is None
    assert redact_auth({}) == {}
