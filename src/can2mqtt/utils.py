from urllib.parse import urlparse


def parse_mqtt_server_url(mqtt_server: str):
    extra_auth = {}
    if mqtt_server.startswith("mqtt://"):
        parsed = urlparse(mqtt_server)
        mqtt_server = parsed.hostname
        extra_auth = dict(
            username=parsed.username,
            password=parsed.password,
            port=int(parsed.port or 1883),
        )
    return mqtt_server, extra_auth


def redact_auth(extra_auth: dict) -> dict:
    """extra_auth for logging: the password replaced with ``***``."""
    return {k: ("***" if k == "password" and v else v) for k, v in extra_auth.items()}
