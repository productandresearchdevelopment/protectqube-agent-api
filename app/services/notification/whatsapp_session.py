import os
import re
import time
import io
import base64
import logging
import threading
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, Tuple
try:
    import qrcode
except ImportError:
    qrcode = None

try:
    from neonize.client import NewClient
    from neonize.events import ConnectedEv, PairStatusEv, LoggedOutEv
    from neonize.utils.jid import build_jid
except ImportError:
    NewClient = None
    ConnectedEv = None
    PairStatusEv = None
    LoggedOutEv = None
    build_jid = None
from app.core.database import SessionLocal
from app.models.notification_models import NotificationDestination

logger = logging.getLogger(__name__)


class WhatsAppSessionManager:
    _instance: Optional["WhatsAppSessionManager"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_manager()
        return cls._instance

    def _init_manager(self):
        env_path = os.getenv("WHATSAPP_SESSION_PATH")
        if env_path:
            self.db_path = env_path
        else:
            base_dir = Path(__file__).resolve().parent.parent.parent.parent
            self.db_path = str(base_dir / "whatsapp_session.db")
        self._client: Optional[NewClient] = None
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._qr_base64: Optional[str] = None
        self._qr_timestamp: float = 0
        self._pairing_code: Optional[str] = None
        self._pairing_phone: Optional[str] = None
        self._status: str = "NOT_CONFIGURED"
        self._phone: Optional[str] = None
        self._jid: Optional[str] = None

    def _update_db_status(self, status: str, config_data: Optional[Dict[str, Any]] = None):
        try:
            db = SessionLocal()
            dest = db.query(NotificationDestination).filter(
                NotificationDestination.provider_key == "whatsapp"
            ).first()
            if not dest:
                dest = NotificationDestination(
                    provider_key="whatsapp",
                    name="WhatsApp",
                    config=config_data or {},
                    status=status,
                    last_tested_at=datetime.utcnow(),
                )
                db.add(dest)
            else:
                dest.status = status
                if config_data is not None:
                    dest.config = config_data
                dest.last_tested_at = datetime.utcnow()
                dest.updated_at = datetime.utcnow()
            db.commit()
            db.close()
        except Exception as e:
            logger.error(f"Failed to update WhatsApp destination status: {e}")

    def _on_qr(self, client: NewClient, data_qr: bytes):
        if qrcode is None:
            return
        try:
            qr = qrcode.QRCode(box_size=10, border=3)
            qr.add_data(data_qr.decode("utf-8", errors="ignore"))
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            buf = io.BytesIO()
            img.save(buf)
            self._qr_base64 = f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode('utf-8')}"
            self._qr_timestamp = time.time()
            self._status = "QR_READY"
        except Exception as e:
            logger.error(f"Error generating QR code: {e}")

    def _on_connected(self, client: NewClient, ev: ConnectedEv):
        if client.is_logged_in:
            self._status = "CONNECTED"
            try:
                me = client.get_me()
                if me and me.JID:
                    self._jid = str(me.JID)
                    self._phone = str(me.JID.User)
            except Exception as e:
                logger.warning(f"Could not retrieve device JID: {e}")
            self._update_db_status(
                "CONNECTED",
                {
                    "phone": self._phone or self._pairing_phone or "",
                    "jid": self._jid or "",
                    "connected_at": datetime.utcnow().isoformat(),
                },
            )

    def _on_pair_status(self, client: NewClient, ev: PairStatusEv):
        self._status = "CONNECTED"
        self._update_db_status(
            "CONNECTED",
            {
                "phone": self._pairing_phone or "",
                "connected_at": datetime.utcnow().isoformat(),
            },
        )

    def _on_logged_out(self, client: NewClient, ev: LoggedOutEv):
        self._status = "NOT_CONFIGURED"
        self._qr_base64 = None
        self._pairing_code = None
        self._phone = None
        self._jid = None
        self._update_db_status("NOT_CONFIGURED", {})

    def start_session(self):
        if NewClient is None:
            logger.warning("neonize is not installed, cannot start WhatsApp session")
            return
        with self._lock:
            if self._client is not None and self._client.is_connected:
                return
            self._client = NewClient(self.db_path)
            self._client.qr(self._on_qr)
            self._client.event(ConnectedEv)(self._on_connected)
            self._client.event(PairStatusEv)(self._on_pair_status)
            self._client.event(LoggedOutEv)(self._on_logged_out)
            self._thread = threading.Thread(target=self._client.connect, daemon=True)
            self._thread.start()

    def reset_for_pairing(self):
        with self._lock:
            try:
                if self._client and self._client.is_logged_in:
                    self._client.logout()
            except Exception:
                pass
            try:
                if self._client:
                    self._client.disconnect()
            except Exception:
                pass
            self._client = None
            self._thread = None
            self._qr_base64 = None
            self._pairing_code = None
            self._status = "NOT_CONFIGURED"
            if os.path.exists(self.db_path):
                try:
                    os.remove(self.db_path)
                except Exception:
                    pass

    def request_qr(self, force_new: bool = True) -> Dict[str, Any]:
        if force_new and self._client and self._client.is_logged_in:
            self.reset_for_pairing()
        self.start_session()
        for _ in range(30):
            if self._qr_base64:
                return {
                    "is_logged_in": False,
                    "status": "QR_READY",
                    "qr_code": self._qr_base64,
                }
            if not force_new and self._client and self._client.is_logged_in:
                return {
                    "is_logged_in": True,
                    "status": "CONNECTED",
                    "phone": self._phone,
                    "jid": self._jid,
                    "qr_code": None,
                }
            time.sleep(0.3)
        return {
            "is_logged_in": False,
            "status": "CONNECTING",
            "qr_code": self._qr_base64,
        }

    def request_pairing_code(self, phone: str) -> str:
        clean = re.sub(r"[^\d]", "", phone)
        if clean.startswith("0"):
            clean = "62" + clean[1:]
        if len(clean) < 8:
            raise ValueError("Invalid phone number format. Must include country code.")
        if self._client and self._client.is_logged_in:
            self.reset_for_pairing()
        self.start_session()
        for _ in range(40):
            if self._client and self._client.is_connected:
                break
            time.sleep(0.3)
        if not self._client or not self._client.is_connected:
            raise RuntimeError("Connection to WhatsApp server timed out. Please try again.")
        raw_code = self._client.PairPhone(clean, True)
        formatted = f"{raw_code[:4]}-{raw_code[4:]}" if len(raw_code) == 8 and "-" not in raw_code else raw_code
        self._pairing_code = formatted
        self._pairing_phone = clean
        return formatted

    def ensure_connected(self, timeout_sec: float = 6.0) -> bool:
        if self._client and self._client.is_logged_in:
            return True
        if not self._client and os.path.exists(self.db_path):
            self.start_session()
        start = time.time()
        while time.time() - start < timeout_sec:
            if self._client and self._client.is_logged_in:
                return True
            time.sleep(0.3)
        return bool(self._client and self._client.is_logged_in)

    def get_status(self) -> Dict[str, Any]:
        if not self._client and os.path.exists(self.db_path):
            self.start_session()
            time.sleep(0.4)

        is_connected = bool(self._client and self._client.is_connected)
        is_logged_in = bool(self._client and self._client.is_logged_in)
        if is_logged_in:
            self._status = "CONNECTED"
            if not self._phone and self._client:
                try:
                    me = self._client.get_me()
                    if me and me.JID:
                        self._jid = str(me.JID)
                        self._phone = str(me.JID.User)
                except Exception:
                    pass
        return {
            "is_connected": is_connected,
            "is_logged_in": is_logged_in,
            "status": "CONNECTED" if is_logged_in else self._status,
            "qr_code": self._qr_base64,
            "pairing_code": self._pairing_code,
            "phone": self._phone or self._pairing_phone,
            "jid": self._jid,
        }

    def send_message(self, recipient: str, body: str) -> Tuple[bool, str, Any]:
        if NewClient is None or build_jid is None:
            return False, "neonize library is not installed", None
        if not self._client or not self._client.is_logged_in:
            if os.path.exists(self.db_path):
                self.ensure_connected(timeout_sec=5.0)

        if not self._client or not self._client.is_logged_in:
            return False, "WhatsApp is not connected or logged in. Please link your device first.", None
        raw = str(recipient or "").strip()
        is_group = "@g.us" in raw or (raw.startswith("120363") and len(raw) > 15)
        clean = re.sub(r"[^\d]", "", raw)
        if not is_group and clean.startswith("0"):
            clean = "62" + clean[1:]
        if not clean:
            return False, "Recipient phone number or group ID is invalid.", None
        try:
            server = "g.us" if is_group else "s.whatsapp.net"
            target_jid = build_jid(clean, server=server)
            resp = self._client.send_message(target_jid, body)
            return True, "", {"to": clean, "server": server, "response": str(resp)}
        except Exception as e:
            logger.error(f"WhatsApp send error: {e}")
            return False, str(e), None

    def disconnect(self) -> bool:
        try:
            if self._client and self._client.is_logged_in:
                self._client.logout()
        except Exception as e:
            logger.warning(f"Error during logout: {e}")
        try:
            if self._client:
                self._client.disconnect()
        except Exception as e:
            logger.warning(f"Error during disconnect: {e}")
        self._client = None
        self._thread = None
        self._qr_base64 = None
        self._pairing_code = None
        self._status = "NOT_CONFIGURED"
        self._phone = None
        self._jid = None
        self._update_db_status("NOT_CONFIGURED", {})
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except Exception as e:
                logger.warning(f"Could not remove session db: {e}")
        return True


whatsapp_session_manager = WhatsAppSessionManager()
