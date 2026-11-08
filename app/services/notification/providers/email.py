import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, Any, Tuple
from app.services.notification.providers.base import BaseNotificationProvider

logger = logging.getLogger(__name__)


class EmailProvider(BaseNotificationProvider):
    provider_key = "email"
    display_name = "Email"
    description = "Send notifications via Gmail SMTP"
    icon = "Mail"

    def get_config_schema(self) -> Dict[str, Any]:
        return {
            "fields": [
                {
                    "name": "smtp_host",
                    "label": "SMTP Host",
                    "type": "text",
                    "required": True,
                    "placeholder": "smtp.gmail.com or mail.qualita.co.id",
                    "help": "Outgoing mail server address.",
                },
                {
                    "name": "smtp_port",
                    "label": "SMTP Port",
                    "type": "number",
                    "required": True,
                    "placeholder": "587 or 465",
                    "help": "Usually 587 (STARTTLS) or 465 (SSL).",
                },
                {
                    "name": "smtp_user",
                    "label": "SMTP Username",
                    "type": "text",
                    "required": True,
                    "placeholder": "alerts@qualita.co.id",
                    "help": "Email address or username to authenticate.",
                },
                {
                    "name": "smtp_password",
                    "label": "SMTP Password",
                    "type": "password",
                    "required": True,
                    "placeholder": "Your SMTP password or App Password",
                    "help": "Application password or account password.",
                },
                {
                    "name": "from_email",
                    "label": "Sender Email",
                    "type": "text",
                    "required": False,
                    "placeholder": "ProtectQube Alerts <alerts@qualita.co.id>",
                    "help": "From address displayed to recipients.",
                },
            ]
        }

    def test_connection(self, config: Dict[str, Any]) -> Tuple[bool, str]:
        host = config.get("smtp_host", "").strip()
        port_raw = config.get("smtp_port", 587)
        try:
            port = int(port_raw) if port_raw else 587
        except ValueError:
            return False, "SMTP Port must be a number (e.g., 587 or 465)."

        user = config.get("smtp_user", "").strip()
        pwd = config.get("smtp_password", "").strip()

        if not host:
            return False, "SMTP Host is required (e.g., smtp.gmail.com)."
        if not user:
            return False, "SMTP Username / Email is required."
        if not pwd:
            return False, "SMTP Password is required."

        try:
            if port == 465:
                server = smtplib.SMTP_SSL(host, port, timeout=10)
            else:
                server = smtplib.SMTP(host, port, timeout=10)
                server.starttls()
            server.login(user, pwd)
            server.quit()
            return True, f"SMTP authentication successful ({host}:{port})!"
        except smtplib.SMTPAuthenticationError:
            return False, "SMTP authentication failed: Invalid Username or Password. (For Gmail, you must use a 16-character 'App Password', not your primary account password)."
        except (smtplib.SMTPConnectError, TimeoutError, smtplib.SMTPServerDisconnected):
            return False, f"Failed to connect to SMTP server {host}:{port}. Verify Host/Port and ensure outgoing connections are permitted."
        except Exception as e:
            logger.error(f"[EmailProvider] Test connection error: {e}")
            return False, f"SMTP connection failed: {str(e)}"

    def send(self, recipient: str, title: str, body: str, data: Dict[str, Any], config: Dict[str, Any]) -> Tuple[bool, str, Any]:
        host = config.get("smtp_host", "").strip()
        port = int(config.get("smtp_port", 587) or 587)
        user = config.get("smtp_user", "").strip()
        pwd = config.get("smtp_password", "").strip()
        from_email = config.get("from_email", user).strip() or user

        if not host or not user or not pwd:
            return False, "Missing SMTP host, user or password", None

        recipients_str = recipient.strip() if recipient else ""
        if not recipients_str:
            return False, "No recipient email address specified", None

        recipients = [r.strip() for r in recipients_str.split(",") if r.strip()]

        msg = MIMEMultipart("alternative")
        msg["Subject"] = title
        msg["From"] = from_email
        msg["To"] = ", ".join(recipients)

        dev_id = data.get("device_id", "")
        metric = data.get("metric", "")
        duration = data.get("duration_str", "")

        html_content = f"""
        <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <div style="background-color: #0073ea; padding: 16px; border-radius: 8px 8px 0 0; color: #fff;">
                    <h2 style="margin: 0;">{title}</h2>
                </div>
                <div style="padding: 20px; border: 1px solid #e2e8f0; border-top: none; border-radius: 0 0 8px 8px;">
                    <p style="font-size: 15px;">{body}</p>
                    <table style="width: 100%; border-collapse: collapse; margin-top: 15px;">
                        <tr>
                            <td style="padding: 8px; border-bottom: 1px solid #edf2f7; font-weight: bold; width: 140px;">Gateway Device</td>
                            <td style="padding: 8px; border-bottom: 1px solid #edf2f7;"><code>{dev_id}</code></td>
                        </tr>
                        <tr>
                            <td style="padding: 8px; border-bottom: 1px solid #edf2f7; font-weight: bold;">Metric / Component</td>
                            <td style="padding: 8px; border-bottom: 1px solid #edf2f7;">{metric}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px; border-bottom: 1px solid #edf2f7; font-weight: bold;">Downtime Duration</td>
                            <td style="padding: 8px; border-bottom: 1px solid #edf2f7;">{duration}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px; font-weight: bold;">Timestamp</td>
                            <td style="padding: 8px;">{data.get('timestamp', '')}</td>
                        </tr>
                    </table>
                </div>
            </body>
        </html>
        """

        part = MIMEText(html_content, "html")
        msg.attach(part)

        try:
            if port == 465:
                server = smtplib.SMTP_SSL(host, port, timeout=12)
            else:
                server = smtplib.SMTP(host, port, timeout=12)
                server.starttls()
            server.login(user, pwd)
            server.sendmail(from_email, recipients, msg.as_string())
            server.quit()
            return True, "", {"recipients": recipients, "status": "SENT"}
        except Exception as e:
            logger.error(f"[EmailProvider] Send error: {e}")
            return False, str(e), None
