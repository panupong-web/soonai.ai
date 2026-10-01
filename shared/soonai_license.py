"""Client for the optional SoonAI Cloudflare license service."""
from __future__ import annotations

import base64
import ctypes
import json
import os
import tempfile
import time
from urllib.parse import urlparse
import uuid
from ctypes import wintypes

import requests

from runtime import DATA_DIR

STATE_FILE = DATA_DIR / "license.json"
OFFLINE_GRACE_SECONDS = 72 * 60 * 60


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD),
                ("pbData", ctypes.POINTER(ctypes.c_char))]


def _dpapi(data: bytes, protect: bool) -> bytes | None:
    if os.name != "nt" or not data:
        return None
    try:
        crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        buffer = ctypes.create_string_buffer(data, len(data))
        incoming = _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
        outgoing = _DataBlob()
        fn = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
        if not fn(ctypes.byref(incoming), None, None, None, None, 0x01,
                  ctypes.byref(outgoing)):
            return None
        try:
            return ctypes.string_at(outgoing.pbData, outgoing.cbData)
        finally:
            kernel32.LocalFree(outgoing.pbData)
    except Exception:
        return None


def _protect_token(token: str) -> str:
    if os.name != "nt":
        return token
    protected = _dpapi(token.encode("utf-8"), True)
    if protected is None:
        raise RuntimeError("Windows DPAPI could not protect the license session; refusing plaintext storage.")
    return "dpapi:" + base64.b64encode(protected).decode("ascii")


def _unprotect_token(value: str) -> str:
    if not value.startswith("dpapi:"):
        return value
    try:
        protected = base64.b64decode(value[6:], validate=True)
        clear = _dpapi(protected, False)
        if clear is None:
            raise RuntimeError("Windows cannot decrypt the license session. Activate this device again.")
        return clear.decode("utf-8")
    except (ValueError, UnicodeDecodeError) as exc:
        raise RuntimeError("The saved license session is damaged. Activate this device again.") from exc


def _read_state() -> dict:
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {}
        token = data.get("session_token", "")
        if token:
            data["session_token"] = _unprotect_token(str(token))
        return data
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as exc:
        raise RuntimeError("The local license state file is invalid; remove it and activate again.") from exc


def _write_state(state: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    stored = dict(state)
    if stored.get("session_token"):
        stored["session_token"] = _protect_token(str(stored["session_token"]))
    encoded = (json.dumps(stored, indent=2) + "\n").encode("utf-8")
    fd, temp_name = tempfile.mkstemp(prefix=".license-", dir=str(DATA_DIR))
    try:
        if os.name != "nt":
            os.chmod(temp_name, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, STATE_FILE)
        if os.name != "nt":
            os.chmod(STATE_FILE, 0o600)
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass


def service_url(cfg: dict) -> str:
    value = (os.environ.get("SOONAI_LICENSE_API_URL")
             or cfg.get("license_api_url") or "").strip().rstrip("/")
    if not value:
        raise RuntimeError("License service is not configured. Set SOONAI_LICENSE_API_URL after deploying the Worker.")
    parsed = urlparse(value)
    local_http = parsed.scheme == "http" and parsed.hostname in ("127.0.0.1", "localhost", "::1")
    if parsed.scheme != "https" and not local_http:
        raise RuntimeError("The license service URL must use HTTPS.")
    return value


def _device_id(state: dict) -> str:
    device_id = state.get("device_id")
    if isinstance(device_id, str) and len(device_id) >= 16:
        return device_id
    return str(uuid.uuid4()) + str(uuid.uuid4()).replace("-", "")


def activate(cfg: dict, license_key: str, device_name: str = "") -> dict:
    state = _read_state()
    device_id = _device_id(state)
    response = requests.post(
        service_url(cfg) + "/v1/activate",
          json={"license_key": license_key.strip(), "device_id": device_id,
              "device_name": device_name[:100]},
        timeout=(5, 12),
    )
    if response.status_code != 200:
        try:
            message = response.json().get("error", "Activation failed")
        except (ValueError, AttributeError):
            message = "Activation failed"
        raise RuntimeError(str(message)[:200])
    body = response.json()
    token = body.get("session_token")
    if not isinstance(token, str) or not token.startswith("sat_"):
        raise RuntimeError("License service returned an invalid activation response.")
    state.update({"device_id": device_id, "session_token": token,
                  "last_validated": int(time.time()),
                  "max_devices": int(body.get("max_devices", 3))})
    _write_state(state)
    return state


def deactivate(cfg: dict) -> None:
    state = _read_state()
    token = state.get("session_token", "")
    if token:
        response = requests.post(
            service_url(cfg) + "/v1/deactivate",
            headers={"Authorization": f"Bearer {token}"}, timeout=(5, 12))
        if response.status_code not in (200, 401):
            raise RuntimeError("License service could not deactivate this device.")
    _write_state({"device_id": state.get("device_id", "")})


def status(cfg: dict, refresh: bool = True) -> tuple[bool, str]:
    state = _read_state()
    token = state.get("session_token", "")
    if not token:
        return False, "This device is not activated. Run: soonai license activate"
    try:
        endpoint = service_url(cfg)
        response = requests.post(endpoint + "/v1/validate",
                                 headers={"Authorization": f"Bearer {token}"},
                                 timeout=(5, 8))
        if response.status_code == 200 and response.json().get("valid") is True:
            state["last_validated"] = int(time.time())
            _write_state(state)
            return True, "License active"
        if response.status_code in (401, 403):
            return False, "License is invalid or revoked. Activate this device again."
        raise RuntimeError("License service is temporarily unavailable.")
    except (requests.RequestException, RuntimeError) as exc:
        last = int(state.get("last_validated", 0) or 0)
        if last and time.time() - last <= OFFLINE_GRACE_SECONDS:
            hours = int((OFFLINE_GRACE_SECONDS - (time.time() - last)) // 3600)
            return True, f"Offline grace active ({max(hours, 0)} hours remaining)"
        return False, str(exc)
