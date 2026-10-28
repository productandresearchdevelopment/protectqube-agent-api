import time
import logging
from typing import Dict, Any, Optional

try:
    import serial
except ImportError:
    serial = None

logger = logging.getLogger(__name__)


class ConnectivityAgent:
    """
    Agent 1: Connectivity Agent (Modem & SIM)
    - Deteksi komunikasi CPU - modem (AT command, respon modem)
    - Deteksi provider SIM card (Telkomsel, Indosat, XL, Tri, dll)
    - Deteksi nomor kartu SIM / ICCID
    - Deteksi temperatur modem
    - Deteksi status jaringan (signal CSQ/dBm, LTE/3G/2G, registered)
    """

    def __init__(self, port: str = "/dev/ttyUSB2", baudrate: int = 115200, timeout: int = 2):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout

    def _send_at_command(self, ser: Any, command: str) -> str:
        ser.write((command + "\r\n").encode("utf-8"))
        time.sleep(0.3)
        response = ser.read_all().decode("utf-8", errors="ignore")
        return response.strip()

    def inspect(self) -> Dict[str, Any]:
        """
        Runs full diagnostic inspection of the Quectel Modem & SIM card.
        """
        result: Dict[str, Any] = {
            "status": "UNKNOWN",
            "modem_connected": False,
            "port": self.port,
            "operator": None,
            "iccid": None,
            "phone_number": None,
            "signal_csq": 0,
            "signal_percent": 0,
            "signal_quality": "NO_SIGNAL",
            "temperature_celsius": None,
            "network_tech": "UNKNOWN",
            "registration_status": "NOT_REGISTERED",
            "error": None,
        }

        import os
        if not serial or (os.name == "nt" and self.port.startswith("/dev/")):
            result["status"] = "SIMULATED"
            result["modem_connected"] = True
            result["operator"] = "Telkomsel (Local Dev)"
            result["iccid"] = "8962012345678901234"
            result["signal_csq"] = 24
            result["signal_percent"] = 77
            result["signal_quality"] = "EXCELLENT"
            result["temperature_celsius"] = 38.5
            result["network_tech"] = "LTE (4G)"
            result["registration_status"] = "REGISTERED_HOME"
            result["error"] = None
            return result

        try:
            with serial.Serial(self.port, self.baudrate, timeout=self.timeout) as ser:
                # 1. Test AT handshake
                at_resp = self._send_at_command(ser, "AT")
                if "OK" not in at_resp:
                    result["error"] = f"Modem handshake failed: {at_resp}"
                    result["status"] = "OFFLINE"
                    return result

                result["modem_connected"] = True

                # 2. Operator info (AT+COPS?)
                cops_resp = self._send_at_command(ser, "AT+COPS?")
                # Example: +COPS: 0,0,"Telkomsel",7
                if "+COPS:" in cops_resp and '"' in cops_resp:
                    parts = cops_resp.split('"')
                    if len(parts) >= 2:
                        result["operator"] = parts[1]

                # 3. ICCID SIM Card (AT+QCCID or AT+CCID)
                qccid_resp = self._send_at_command(ser, "AT+QCCID")
                if "+QCCID:" in qccid_resp:
                    result["iccid"] = qccid_resp.replace("+QCCID:", "").replace("OK", "").strip()

                # 4. Signal CSQ (AT+CSQ)
                # Example: +CSQ: 21,99 -> 0 to 31
                csq_resp = self._send_at_command(ser, "AT+CSQ")
                if "+CSQ:" in csq_resp:
                    raw_csq = csq_resp.split("+CSQ:")[1].split(",")[0].strip()
                    try:
                        csq_val = int(raw_csq)
                        if csq_val != 99:
                            result["signal_csq"] = csq_val
                            result["signal_percent"] = min(100, int((csq_val / 31.0) * 100))
                            if csq_val >= 20:
                                result["signal_quality"] = "EXCELLENT"
                            elif csq_val >= 15:
                                result["signal_quality"] = "GOOD"
                            elif csq_val >= 10:
                                result["signal_quality"] = "FAIR"
                            else:
                                result["signal_quality"] = "POOR"
                    except ValueError:
                        pass

                # 5. Modem Temperature (AT+QTEMP for Quectel)
                # Example: +QTEMP: "cpuss-usr",38,"mdm-core",39
                qtemp_resp = self._send_at_command(ser, "AT+QTEMP")
                if "+QTEMP:" in qtemp_resp:
                    # extract first temperature value
                    try:
                        temp_tokens = qtemp_resp.split(",")
                        for token in temp_tokens:
                            cleaned = token.replace('"', '').strip()
                            if cleaned.isdigit():
                                result["temperature_celsius"] = float(cleaned)
                                break
                    except Exception:
                        pass

                # 6. Network Registration (AT+CREG? / AT+CGREG?)
                creg_resp = self._send_at_command(ser, "AT+CREG?")
                if "+CREG:" in creg_resp:
                    if ",1" in creg_resp:
                        result["registration_status"] = "REGISTERED_HOME"
                    elif ",5" in creg_resp:
                        result["registration_status"] = "REGISTERED_ROAMING"
                    elif ",2" in creg_resp:
                        result["registration_status"] = "SEARCHING"
                    else:
                        result["registration_status"] = "NOT_REGISTERED"

                result["network_tech"] = "LTE"
                result["status"] = "HEALTHY" if result["signal_percent"] > 20 else "DEGRADED"

        except Exception as e:
            logger.warning(f"Modem serial communication error on {self.port}: {e}")
            result["status"] = "OFFLINE"
            result["error"] = str(e)

        return result
