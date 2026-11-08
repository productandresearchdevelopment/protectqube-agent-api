import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.core.database import SessionLocal
from app.models.base_models import GatewayIncidentAlert
from app.models.notification_models import (
    NotificationEvent,
    NotificationDestination,
    NotificationTarget,
    Notification,
    NotificationDelivery,
)
from app.services.notification.registry import integration_registry

logger = logging.getLogger(__name__)

dispatch_pool = ThreadPoolExecutor(max_workers=5, thread_name_prefix="notif-dispatch")


class NotificationService:
    def __init__(self):
        self.registry = integration_registry
        self._active_outages: Dict[str, Dict[str, Any]] = {}

    def process_telemetry_for_notifications(
        self,
        db: Session,
        dev_id: str,
        loc_name: str,
        payload: Dict[str, Any],
        rec_dt: datetime,
    ):
        if not payload or not isinstance(payload, dict):
            return

        logs = payload.get("recent_system_logs") or []
        if isinstance(logs, str):
            logs = logs.strip().split("\n")
        logs_str = " ".join(str(l) for l in logs)
        latest_logs = logs[-3:] if len(logs) >= 3 else logs
        latest_str = " ".join(str(l) for l in latest_logs)

        sim = payload.get("cellular_sim", {})
        modem = payload.get("modem_usb", {})

        modem_down = (
            "[MODEM-CPU: TERPUTUS]" in logs_str
            or "[MODEM-CPU: FAIL]" in logs_str
            or "[MODEM-CPU: ERROR]" in logs_str
            or (isinstance(modem, dict) and modem.get("status") in ["FAIL", "DISCONNECTED"])
        )
        modem_up = (
            "[MODEM-CPU: OK]" in latest_str
            or (isinstance(modem, dict) and modem.get("status") in ["OK", "CONNECTED"])
        )

        if modem_down:
            self._handle_module_down(
                db=db,
                dev_id=dev_id,
                loc_name=loc_name,
                metric="cpu_modem",
                rec_dt=rec_dt,
                reason="Port serial USB modul modem terlepas atau komunikasi terputus",
            )
        elif modem_up:
            self._handle_module_recovery(
                db=db,
                dev_id=dev_id,
                loc_name=loc_name,
                metric="cpu_modem",
                rec_dt=rec_dt,
            )

        csq = 0
        if isinstance(sim, dict) and sim.get("signal_csq") is not None:
            try:
                csq = int(sim.get("signal_csq"))
            except (ValueError, TypeError):
                csq = 0
        elif payload.get("signal_csq") is not None:
            try:
                csq = int(payload.get("signal_csq"))
            except (ValueError, TypeError):
                csq = 0

        sim_unplugged = (
            "[SIM: DICABUT" in logs_str
            or "SIM DICABUT" in logs_str
            or "SIM TIDAK TERDETEKSI" in logs_str
            or "SIM: TIDAK TERDETEKSI" in logs_str
            or "[ALERT] Kartu SIM tidak terdeteksi atau dicabut" in logs_str
            or "+CPIN: NOT INSERTED" in logs_str
            or (isinstance(sim, dict) and sim.get("sim_inserted") is False)
            or payload.get("sim_status") in ["NOT_INSERTED", "NOT INSERTED", "REMOVED"]
        )
        data_disconnected = (
            "[SIM: ALIRAN DATA INTERNET TERPUTUS" in logs_str
            or "PPP/QMI DOWN" in logs_str
            or "[ALERT] Koneksi data seluler terputus" in logs_str
            or (isinstance(sim, dict) and isinstance(sim.get("data_traffic"), dict) and sim.get("data_traffic", {}).get("connected") is False)
        )
        signal_lost = (
            "[SIM: TIDAK ADA SINYAL" in logs_str
            or "REGISTRASI JARINGAN GAGAL" in logs_str
            or "TIDAK ADA SINYAL" in logs_str
        )
        signal_bad = (
            "[SIM: KUALITAS SINYAL SANGAT BURUK" in logs_str
            or (csq == 99)
            or (csq == 0 and not sim_unplugged)
        )

        cell_down_reason = None
        if sim_unplugged:
            cell_down_reason = "Kartu SIM tidak terdeteksi atau dicabut dari slot modem"
        elif data_disconnected:
            cell_down_reason = "Aliran data internet terputus (PPP/QMI Down)"
        elif signal_lost:
            cell_down_reason = "Tidak ada sinyal seluler / Registrasi jaringan BTS gagal"
        elif signal_bad:
            cell_down_reason = "Kualitas sinyal sangat buruk (CSQ 99 / drop ekstrem)"

        has_active_sim_flag = (
            (isinstance(sim, dict) and sim.get("sim_inserted") is True)
            or payload.get("sim_status") == "Active"
        )
        cell_up = (
            cell_down_reason is None
            and has_active_sim_flag
            and 1 <= csq <= 31
            and not any(
                "SIM: DICABUT" in str(l)
                or "SIM TIDAK TERDETEKSI" in str(l)
                or "TERPUTUS" in str(l)
                or "CSQ 99" in str(l)
                for l in latest_logs
            )
        )

        if cell_down_reason and not modem_down:
            self._handle_module_down(
                db=db,
                dev_id=dev_id,
                loc_name=loc_name,
                metric="cellular",
                rec_dt=rec_dt,
                reason=cell_down_reason,
            )
        elif cell_up:
            op = (isinstance(sim, dict) and sim.get("operator")) or payload.get("operator") or "Telkomsel"
            sim_info = f"{op} 4G LTE, CSQ {csq}"
            self._handle_module_recovery(
                db=db,
                dev_id=dev_id,
                loc_name=loc_name,
                metric="cellular",
                rec_dt=rec_dt,
                sim_info=sim_info,
            )

        nvr_st = str(payload.get("nvr_status") or "").lower()
        dvr_down = (
            "[NVR-CPU: TERPUTUS]" in logs_str
            or "[NVR: OFFLINE]" in logs_str
            or "NVR: OFFLINE" in logs_str
            or "[ALERT] Komunikasi Gateway CPU ke NVR Surveillance Terputus" in logs_str
            or nvr_st == "offline"
        )
        dvr_up = (
            "[NVR-CPU: OK]" in latest_str
            or "NVR: SEDANG MEREKAM" in latest_str
            or "NVR: STANDBY" in latest_str
            or nvr_st == "online"
        )

        if dvr_down:
            self._handle_module_down(
                db=db,
                dev_id=dev_id,
                loc_name=loc_name,
                metric="cpu_dvr",
                rec_dt=rec_dt,
                reason="Kabel LAN lepas atau NVR mati",
            )
        elif dvr_up:
            self._handle_module_recovery(
                db=db,
                dev_id=dev_id,
                loc_name=loc_name,
                metric="cpu_dvr",
                rec_dt=rec_dt,
            )

    def _handle_module_down(
        self,
        db: Session,
        dev_id: str,
        loc_name: str,
        metric: str,
        rec_dt: datetime,
        reason: str,
    ):
        outage_key = f"{dev_id}:{metric}"
        if outage_key not in self._active_outages:
            self._active_outages[outage_key] = {
                "device_id": dev_id,
                "location": loc_name,
                "metric": metric,
                "start_time": rec_dt,
                "last_seen_down": rec_dt,
                "reason": reason,
                "notified": True,
            }
            self.dispatch_module_event(
                db=db,
                dev_id=dev_id,
                loc_name=loc_name,
                metric=metric,
                is_recovered=False,
                rec_dt=rec_dt,
                reason=reason,
            )
        else:
            self._active_outages[outage_key]["last_seen_down"] = rec_dt

    def _handle_module_recovery(
        self,
        db: Session,
        dev_id: str,
        loc_name: str,
        metric: str,
        rec_dt: datetime,
        sim_info: Optional[str] = None,
    ):
        outage_key = f"{dev_id}:{metric}"
        if outage_key in self._active_outages:
            outage = self._active_outages.pop(outage_key)
            st = outage.get("start_time") or rec_dt
            diff_sec = max(60.0, (rec_dt - st).total_seconds())
            dur_m = max(1, round(diff_sec / 60.0))
            if dur_m >= 60:
                dur_str = f"{dur_m // 60} Jam {dur_m % 60} Menit" if dur_m % 60 else f"{dur_m // 60} Jam"
            else:
                dur_str = f"{dur_m} Menit"

            self.dispatch_module_event(
                db=db,
                dev_id=dev_id,
                loc_name=loc_name or outage.get("location") or "",
                metric=metric,
                is_recovered=True,
                rec_dt=rec_dt,
                duration_str=dur_str,
                sim_info=sim_info,
            )

    def dispatch_module_event(
        self,
        db: Session,
        dev_id: str,
        loc_name: str,
        metric: str,
        is_recovered: bool,
        rec_dt: datetime,
        reason: Optional[str] = None,
        duration_str: Optional[str] = None,
        sim_info: Optional[str] = None,
    ):
        try:
            dur = duration_str or "1 Menit"
            wib = timezone(timedelta(hours=7))
            t_wib = rec_dt.replace(tzinfo=timezone.utc).astimezone(wib) if rec_dt.tzinfo is None else rec_dt.astimezone(wib)
            ts_wib = t_wib.strftime("%Y-%m-%d %H:%M:%S (WIB)")

            if metric == "cellular":
                if is_recovered:
                    event_code = "gateway_cellular_recovered"
                    title = f"Cellular Recovered - {dev_id}"
                    sim_txt = sim_info or "4G LTE"
                    body = f"Koneksi seluler pada gateway {dev_id} telah pulih kembali ({sim_txt}) setelah mengalami downtime selama {dur}."
                    severity = "INFO"
                else:
                    event_code = "gateway_cellular_down"
                    title = f"Cellular Down - {dev_id}"
                    rsn = reason or "Kartu SIM tidak terdeteksi atau dicabut dari slot modem"
                    body = f"Koneksi seluler pada gateway {dev_id} terputus (Penyebab: {rsn})."
                    severity = "CRITICAL"

            elif metric == "cpu_modem":
                if is_recovered:
                    event_code = "gateway_modem_reconnected"
                    title = f"Modem Reconnected - {dev_id}"
                    body = f"Komunikasi port serial USB modem pada gateway {dev_id} telah terhubung kembali (OK) setelah mengalami downtime selama {dur}."
                    severity = "INFO"
                else:
                    event_code = "gateway_modem_disconnected"
                    title = f"Modem Disconnected - {dev_id}"
                    rsn = reason or "Port serial USB modul modem terlepas atau komunikasi terputus"
                    body = f"Komunikasi port serial USB modem pada gateway {dev_id} terputus (Penyebab: {rsn})."
                    severity = "CRITICAL"

            elif metric == "cpu_dvr":
                if is_recovered:
                    event_code = "gateway_dvr_recovered"
                    title = f"NVR Recovered - {dev_id}"
                    body = f"Perangkat NVR surveillance pada gateway {dev_id} telah pulih kembali dan aktif merekam setelah mengalami downtime selama {dur}."
                    severity = "INFO"
                else:
                    event_code = "gateway_dvr_offline"
                    title = f"NVR Offline - {dev_id}"
                    rsn = reason or "Kabel LAN lepas atau NVR mati"
                    body = f"Komunikasi gateway ke perangkat NVR surveillance pada {dev_id} terputus (Penyebab: {rsn})."
                    severity = "WARNING"

            else:
                act = "recovered" if is_recovered else "down"
                event_code = f"gateway_{metric}_{act}"
                title = f"{metric.capitalize()} {act.capitalize()} - {dev_id}"
                body = f"{metric.capitalize()} on gateway {dev_id} is {act}."
                severity = "INFO" if is_recovered else "WARNING"

            event_record = db.query(NotificationEvent).filter(NotificationEvent.event_code == event_code).first()
            if not event_record:
                return

            configured_channels = event_record.channels or []
            if not configured_channels:
                return

            norm_channels = []
            for c in configured_channels:
                if isinstance(c, str):
                    norm_channels.append({"channel_type": c, "is_enabled": True})
                elif isinstance(c, dict):
                    norm_channels.append(c)

            active_configured = [c for c in norm_channels if c.get("is_enabled", True)]
            if not active_configured:
                return

            in_app_entry = next((c for c in active_configured if c.get("channel_type") == "in_app"), None)
            in_app_enabled = bool(in_app_entry)

            recipient_overrides = {}
            channel_dest_ids = {}
            for c in active_configured:
                c_type = c.get("channel_type")
                if c_type and c_type != "in_app":
                    recipient_overrides[c_type] = c.get("recipient")
                    channel_dest_ids[c_type] = c.get("destination_ids") or []

            notif_data = {
                "event_code": event_code,
                "device_id": dev_id,
                "location": loc_name or "-",
                "metric": metric,
                "status": "RESOLVED" if is_recovered else "ACTIVE",
                "timestamp": ts_wib,
                "duration_str": dur if is_recovered else None,
            }

            notif_record = None
            if in_app_enabled:
                in_app_provider = self.registry.get("in_app")
                if in_app_provider:
                    notif_record = in_app_provider.create_in_app_record(
                        db=db,
                        event_code=event_code,
                        title=title,
                        body=body,
                        severity=severity,
                        data=notif_data
                    )
                    db.commit()

            active_destinations = db.query(NotificationDestination).filter(
                NotificationDestination.status == "CONNECTED"
            ).all()

            filtered_destinations = []
            for dest in active_destinations:
                if dest.provider_key in recipient_overrides or dest.provider_key in channel_dest_ids:
                    filtered_destinations.append(dest)

            if filtered_destinations:
                notif_id = notif_record.id if notif_record else None
                dest_info_list = [
                    {
                        "id": d.id,
                        "provider_key": d.provider_key,
                        "recipient_override": recipient_overrides.get(d.provider_key),
                        "destination_ids": channel_dest_ids.get(d.provider_key, [])
                    }
                    for d in filtered_destinations
                ]
                dispatch_pool.submit(self._async_dispatch_destinations, dest_info_list, title, body, notif_data, notif_id)

        except Exception as e:
            logger.error(f"[NotificationService] Error dispatching module event: {e}", exc_info=True)

    def dispatch_incident_event(self, db: Session, incident: GatewayIncidentAlert, event_type: str = "STARTED"):
        is_recovered = event_type.upper() in ["RESOLVED", "RECOVERED"]
        dur = incident.duration_str or (f"{int(incident.duration_minutes)} Menit" if incident.duration_minutes else "1 Menit")
        target_dt = incident.end_time if is_recovered and incident.end_time else (incident.start_time or datetime.utcnow())
        self.dispatch_module_event(
            db=db,
            dev_id=incident.device_id,
            loc_name="",
            metric=incident.metric,
            is_recovered=is_recovered,
            rec_dt=target_dt,
            reason=incident.description,
            duration_str=dur,
        )

    def _async_dispatch_destinations(
        self,
        dest_info_list: List[Dict[str, Any]],
        title: str,
        body: str,
        data: Dict[str, Any],
        notification_id: Optional[str]
    ):
        db = SessionLocal()
        try:
            for item in dest_info_list:
                dest_id = item["id"]
                custom_recipient = item.get("recipient_override")
                target_ids = item.get("destination_ids") or []
                dest = db.query(NotificationDestination).filter(
                    NotificationDestination.id == dest_id
                ).first()

                if not dest:
                    continue

                provider = self.registry.get(dest.provider_key)
                if not provider:
                    logger.warning(f"[NotificationService] Provider '{dest.provider_key}' not found in registry")
                    continue

                targets = []
                if target_ids:
                    targets = db.query(NotificationTarget).filter(
                        NotificationTarget.id.in_(target_ids),
                        NotificationTarget.is_active == True
                    ).all()

                if targets:
                    for target in targets:
                        effective_recipient = target.external_id
                        success, err_msg, resp_payload = provider.send(
                            recipient=effective_recipient,
                            title=title,
                            body=body,
                            data=data,
                            config=dest.config or {}
                        )

                        delivery = NotificationDelivery(
                            notification_id=notification_id,
                            destination_id=dest.id,
                            channel_type=dest.provider_key,
                            recipient=f"{target.display_name} ({effective_recipient})",
                            status="SUCCESS" if success else "FAILED",
                            error_message=err_msg if not success else None,
                            response_payload=resp_payload if isinstance(resp_payload, dict) else {"raw": str(resp_payload)},
                            sent_at=datetime.utcnow()
                        )
                        db.add(delivery)
                        db.commit()
                        logger.info(f"[NotificationService] Dispatched '{dest.provider_key}' to '{target.display_name}': status={delivery.status}")
                else:
                    effective_recipient = custom_recipient or str(
                        dest.config.get("default_chat_id")
                        or dest.config.get("default_recipient")
                        or dest.config.get("webhook_url")
                        or dest.config.get("default_recipients")
                        or ""
                    )

                    success, err_msg, resp_payload = provider.send(
                        recipient=effective_recipient,
                        title=title,
                        body=body,
                        data=data,
                        config=dest.config or {}
                    )

                    delivery = NotificationDelivery(
                        notification_id=notification_id,
                        destination_id=dest.id,
                        channel_type=dest.provider_key,
                        recipient=effective_recipient,
                        status="SUCCESS" if success else "FAILED",
                        error_message=err_msg if not success else None,
                        response_payload=resp_payload if isinstance(resp_payload, dict) else {"raw": str(resp_payload)},
                        sent_at=datetime.utcnow()
                    )
                    db.add(delivery)
                    db.commit()
                    logger.info(f"[NotificationService] Dispatched '{dest.provider_key}' for '{data.get('device_id')}': status={delivery.status}")
        except Exception as e:
            logger.error(f"[NotificationService] Async dispatch worker error: {e}")
        finally:
            db.close()

    def get_notifications(
        self,
        db: Session,
        page: int = 1,
        limit: int = 20,
        unread_only: bool = False,
        read_status: Optional[str] = None,
        severity: Optional[str] = None,
        search: Optional[str] = None,
    ):
        query = db.query(Notification)
        if unread_only or read_status == "UNREAD":
            query = query.filter(Notification.is_read == False)
        elif read_status == "READ":
            query = query.filter(Notification.is_read == True)

        if severity and severity.upper() != "ALL":
            query = query.filter(Notification.severity == severity.upper())

        if search and search.strip():
            term = f"%{search.strip()}%"
            query = query.filter(
                or_(
                    Notification.title.ilike(term),
                    Notification.body.ilike(term),
                    Notification.event_code.ilike(term),
                )
            )

        total = query.count()
        items = query.order_by(Notification.created_at.desc()).offset((page - 1) * limit).limit(limit).all()
        unread_count = db.query(Notification).filter(Notification.is_read == False).count()
        return {
            "items": items,
            "total": total,
            "page": page,
            "limit": limit,
            "unread_count": unread_count,
        }

    def get_deliveries(self, db: Session, page: int = 1, limit: int = 20, status: Optional[str] = None):
        query = db.query(NotificationDelivery)
        if status:
            query = query.filter(NotificationDelivery.status == status.upper())
        total = query.count()
        items = query.order_by(NotificationDelivery.sent_at.desc()).offset((page - 1) * limit).limit(limit).all()
        return {
            "items": items,
            "total": total,
            "page": page,
            "limit": limit,
        }

    def mark_as_read(self, db: Session, notification_id: str):
        notif = db.query(Notification).filter(Notification.id == notification_id).first()
        if notif:
            notif.is_read = True
            notif.read_at = datetime.utcnow()
            db.commit()
            db.refresh(notif)
        return notif

    def mark_all_as_read(self, db: Session):
        db.query(Notification).filter(Notification.is_read == False).update(
            {"is_read": True, "read_at": datetime.utcnow()}
        )
        db.commit()
        return True


notification_service = NotificationService()
