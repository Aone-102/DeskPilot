import os
import time
import uuid
import secrets
import hashlib
import socket
import datetime
import qrcode
import qrcode.image.svg

# Active session token for desktop app
LOCAL_SESSION_TOKEN = secrets.token_hex(24)

# Pending pairing requests: { pairing_code: { "created_at": float, "expires_at": float, "secret": str } }
PENDING_PAIRINGS = {}


def get_local_lan_ip():
    """Returns the primary LAN IP address of this PC."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "127.0.0.1"


def get_pc_hostname():
    """Returns the computer name / hostname."""
    try:
        return socket.gethostname()
    except Exception:
        return "DeskPilot-PC"


def get_or_create_server_id(config):
    """
    Returns a unique server/PC ID persistently stored in config.json.
    Ensures that each PC has its own distinct, non-overlapping QR pairing link and identifier.
    Derived deterministically from the machine's hardware GUID & hostname so it stays consistent per PC.
    """
    phone_cfg = config.setdefault("phone", {})
    if "serverId" not in phone_cfg or not phone_cfg["serverId"]:
        # Deterministic 8-character hex ID based on this specific PC's hardware node and hostname
        host_hash = hashlib.sha256(f"{get_pc_hostname()}_{uuid.getnode()}".encode("utf-8")).hexdigest()[:8]
        phone_cfg["serverId"] = f"dp_{host_hash}"
    return phone_cfg["serverId"]


def create_pairing_code(ttl_seconds=600):
    """
    Creates a 6-digit pairing code with an expiration time.
    """
    now = time.time()
    # Clean expired
    expired = [k for k, v in PENDING_PAIRINGS.items() if v["expires_at"] < now]
    for k in expired:
        PENDING_PAIRINGS.pop(k, None)

    code = f"{secrets.randbelow(900000) + 100000}"
    secret = secrets.token_urlsafe(16)
    PENDING_PAIRINGS[code] = {
        "created_at": now,
        "expires_at": now + ttl_seconds,
        "secret": secret
    }
    return code, secret


def get_or_create_active_pairing():
    """Returns an active pairing code or creates a new one."""
    now = time.time()
    for code, info in PENDING_PAIRINGS.items():
        if info["expires_at"] > now:
            return code, info["secret"]
    return create_pairing_code()


def verify_pairing_code(code):
    now = time.time()
    info = PENDING_PAIRINGS.get(str(code).strip())
    if info and info["expires_at"] > now:
        return True, info["secret"]
    return False, None


def generate_qr_svg(url):
    """Generates standalone SVG string for the given URL."""
    img = qrcode.make(url, image_factory=qrcode.image.svg.SvgPathImage)
    return img.to_string().decode("utf-8")


def hash_token(token_str):
    return hashlib.sha256(token_str.encode("utf-8")).hexdigest()


def register_new_device(config, device_name):
    """
    Generates a persistent long-term token for the phone,
    stores its SHA256 hash in config, and returns the raw token to the phone.
    """
    phone_cfg = config.setdefault("phone", {})
    devices = phone_cfg.setdefault("devices", [])

    raw_token = secrets.token_hex(32)
    token_hash = hash_token(raw_token)
    device_id = str(uuid.uuid4())
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    device_info = {
        "id": device_id,
        "name": device_name or "스마트폰",
        "tokenHash": token_hash,
        "createdAt": now_str,
        "lastUsedAt": now_str
    }
    devices.append(device_info)
    return raw_token, device_info


def verify_phone_token(config, raw_token):
    """
    Verifies if the provided token matches any registered device.
    """
    if not raw_token:
        return False, None

    token_hash = hash_token(raw_token)
    devices = config.get("phone", {}).get("devices", [])
    for dev in devices:
        if dev.get("tokenHash") == token_hash:
            dev["lastUsedAt"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            return True, dev
    return False, None


def revoke_device(config, device_id):
    """
    Revokes a smartphone device by ID.
    """
    devices = config.get("phone", {}).get("devices", [])
    initial_len = len(devices)
    config["phone"]["devices"] = [d for d in devices if d.get("id") != device_id]
    return len(config["phone"]["devices"]) < initial_len

