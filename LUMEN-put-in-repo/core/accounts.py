"""Optional LUMEN accounts — local encrypted vault (no cloud required)."""

from __future__ import annotations

import base64
import hashlib
import json
import re
import secrets
import time
from pathlib import Path

from core.paths import user_data

ACCOUNTS_DIR = user_data() / "accounts"
REGISTRY_PATH = ACCOUNTS_DIR / "registry.json"
SESSION_PATH = user_data() / "session.json"


def _derive_key(password: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 220_000, dklen=32)


def _xor_crypt(data: bytes, key: bytes) -> bytes:
    out = bytearray(len(data))
    for i, b in enumerate(data):
        out[i] = b ^ key[i % len(key)]
    return bytes(out)


class AccountManager:
    """Register, sign in, and sync bookmarks/settings/passwords to a local vault."""

    def __init__(self):
        ACCOUNTS_DIR.mkdir(parents=True, exist_ok=True)
        self._user: str | None = None
        self._vault_key: bytes | None = None
        self._load_session()

    def _load_registry(self) -> dict:
        try:
            if REGISTRY_PATH.is_file():
                return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
        return {"users": {}}

    def _save_registry(self, data: dict) -> None:
        REGISTRY_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _vault_path(self, username: str) -> Path:
        safe = re.sub(r"[^\w.-]", "_", username.lower())
        return ACCOUNTS_DIR / f"{safe}.vault"

    def register(self, username: str, password: str, email: str = "") -> tuple[bool, str]:
        user = username.strip().lower()
        if not re.match(r"^[a-z0-9._-]{3,32}$", user):
            return False, "Username must be 3–32 characters (letters, numbers, . _ -)."
        if len(password) < 6:
            return False, "Password must be at least 6 characters."

        reg = self._load_registry()
        if user in reg.get("users", {}):
            return False, "That username is already taken."

        salt = secrets.token_bytes(16)
        pwd_hash = hashlib.sha256(_derive_key(password, salt) + salt).hexdigest()
        reg.setdefault("users", {})[user] = {
            "salt": base64.b64encode(salt).decode("ascii"),
            "hash": pwd_hash,
            "email": email.strip()[:120],
            "created": time.time(),
        }
        self._save_registry(reg)

        vault = {
            "profile": {"username": user, "email": email.strip()[:120], "display_name": user.title()},
            "bookmarks": [],
            "settings": {},
            "passwords": [],
            "updated": time.time(),
        }
        self._write_vault(user, password, vault)
        ok, msg = self.login(user, password)
        return (ok, "Account created." if ok else msg)

    def login(self, username: str, password: str) -> tuple[bool, str]:
        user = username.strip().lower()
        reg = self._load_registry()
        entry = reg.get("users", {}).get(user)
        if not entry:
            return False, "Account not found."

        salt = base64.b64decode(entry["salt"])
        key = _derive_key(password, salt)
        check = hashlib.sha256(key + salt).hexdigest()
        if check != entry["hash"]:
            return False, "Incorrect password."

        self._user = user
        self._vault_key = key
        SESSION_PATH.write_text(
            json.dumps({"user": user, "token": secrets.token_hex(16), "at": time.time()}),
            encoding="utf-8",
        )
        return True, f"Signed in as {user}."

    def logout(self) -> None:
        self._user = None
        self._vault_key = None
        try:
            SESSION_PATH.unlink(missing_ok=True)
        except OSError:
            pass

    def _load_session(self) -> None:
        try:
            if SESSION_PATH.is_file():
                data = json.loads(SESSION_PATH.read_text(encoding="utf-8"))
                user = data.get("user")
                if user and self._vault_path(user).is_file():
                    self._user = user
        except (json.JSONDecodeError, OSError):
            pass

    def restore_session(self, password: str) -> tuple[bool, str]:
        if not self._user:
            return False, "No saved session."
        return self.login(self._user, password)

    @property
    def logged_in(self) -> bool:
        return self._user is not None and self._vault_key is not None

    @property
    def username(self) -> str | None:
        return self._user

    def _write_vault(self, user: str, password: str, data: dict) -> None:
        reg = self._load_registry()
        entry = reg.get("users", {}).get(user)
        salt = base64.b64decode(entry["salt"]) if entry else secrets.token_bytes(16)
        key = _derive_key(password, salt) if not self._vault_key else self._vault_key
        raw = json.dumps(data, indent=2).encode("utf-8")
        enc = base64.b64encode(_xor_crypt(raw, key)).decode("ascii")
        self._vault_path(user).write_text(enc, encoding="utf-8")

    def read_vault(self) -> dict:
        if not self._user or not self._vault_key:
            return {}
        try:
            enc = self._vault_path(self._user).read_text(encoding="utf-8")
            raw = _xor_crypt(base64.b64decode(enc), self._vault_key)
            return json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, OSError, ValueError):
            return {}

    def save_vault(self, data: dict) -> None:
        if not self._user or not self._vault_key:
            return
        data["updated"] = time.time()
        enc_data = base64.b64encode(
            _xor_crypt(json.dumps(data, indent=2).encode("utf-8"), self._vault_key)
        ).decode("ascii")
        self._vault_path(self._user).write_text(enc_data, encoding="utf-8")

    def sync_from_browser(self, *, bookmarks: list, settings: dict, profile: dict | None = None) -> None:
        if not self.logged_in:
            return
        vault = self.read_vault()
        vault["bookmarks"] = bookmarks[:200]
        vault["settings"] = {k: settings.get(k) for k in (
            "theme", "search_engine", "user_name", "voice_control", "spoken_replies",
            "use_ollama", "ad_block", "firewall",
        )}
        if profile:
            vault["profile"] = {**vault.get("profile", {}), **profile}
        self.save_vault(vault)

    def apply_to_browser(self) -> dict:
        """Return merged data from vault for the browser to apply."""
        if not self.logged_in:
            return {}
        vault = self.read_vault()
        return {
            "bookmarks": vault.get("bookmarks", []),
            "settings": vault.get("settings", {}),
            "profile": vault.get("profile", {}),
            "passwords": vault.get("passwords", []),
        }

    def save_password(self, site: str, username: str, password: str, label: str = "") -> None:
        if not self.logged_in:
            return
        vault = self.read_vault()
        passwords = list(vault.get("passwords", []))
        entry = {
            "site": site[:200],
            "username": username[:120],
            "password": password[:200],
            "label": label[:80],
            "updated": time.time(),
        }
        passwords = [p for p in passwords if p.get("site") != site or p.get("username") != username]
        passwords.insert(0, entry)
        vault["passwords"] = passwords[:100]
        self.save_vault(vault)

    def list_passwords(self) -> list[dict]:
        if not self.logged_in:
            return []
        return list(self.read_vault().get("passwords", []))
