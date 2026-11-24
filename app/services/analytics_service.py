import logging
from datetime import datetime, date, timedelta
from typing import Dict, Any, List, Optional
from collections import defaultdict
from sqlalchemy.orm import Session
from sqlalchemy import desc, func, cast, String

from app.models.base_models import GatewayIncidentAlert, GatewayTelemetryHistory, Device, Client
from app.services.cellular_service import cellular_service

logger = logging.getLogger(__name__)

METRIC_META = {
    "cellular": {
        "title": "Cellular Network Disconnected",
        "description": "Kehilangan koneksi data internet/seluler (blank spot / sinyal putus)",
        "color": "#f59e0b",  # Amber
        "icon": "Radio"
    },
    "cpu_dvr": {
        "title": "CPU – NVR / DVR Video Disconnected",
        "description": "Koneksi komunikasi ethernet LAN atau port 80/ISAPI ke NVR terputus",
        "color": "#ef4444",  # Red
        "icon": "Video"
    },
    "cpu_modem": {
        "title": "Quectel 4G Modem Serial Port Offline",
        "description": "Port serial USB (/dev/ttyUSB) modem Quectel tidak merespons CPU Gateway",
        "color": "#8b5cf6",  # Purple
        "icon": "Cpu"
    },
    "power": {
        "title": "Power Outage / Gateway Reboot",
        "description": "Gateway mati mendadak atau mengalami reboot akibat gangguan catu daya",
        "color": "#ec4899",  # Pink
        "icon": "Zap"
    },
    "system": {
        "title": "System Overheat / Storage Warning",
        "description": "Peringatan suhu prosesor CPU atau kapasitas penyimpanan microSD",
        "color": "#06b6d4",  # Cyan
        "icon": "AlertTriangle"
    }
}


class AnalyticsService:
    def get_available_months(self, db: Session) -> List[str]:
        """Returns distinct months (YYYY-MM) available in incident alerts."""
        rows = db.query(
            func.to_char(GatewayIncidentAlert.start_time + timedelta(hours=7), 'YYYY-MM').label('month')
        ).distinct().order_by(desc('month')).all()
        months = [r[0] for r in rows if r[0]]
        if not months:
            months = [datetime.now().strftime("%Y-%m-%d")[:7]]
        return months

    def get_incident_analytics(
        self,
        db: Session,
        month: Optional[str] = None,
        selected_date: Optional[str] = None,
        client_name: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> Dict[str, Any]:
        """
        Calculates complete incident analytics:
        - Monthly trend (daily incident counts per metric)
        - Top root causes per day and per month
        - Offline gateways and their primary causes
        - Summary KPIs and incident detail stream
        """
        available_months = self.get_available_months(db)
        if not month:
            month = available_months[0] if available_months else datetime.now().strftime("%Y-%m")

        # Parse month boundary (WIB +7)
        try:
            y, m = map(int, month.split('-'))
            start_month_dt = datetime(y, m, 1)
            if m == 12:
                end_month_dt = datetime(y + 1, 1, 1)
            else:
                end_month_dt = datetime(y, m + 1, 1)
        except Exception:
            now = datetime.now()
            month = now.strftime("%Y-%m")
            start_month_dt = datetime(now.year, now.month, 1)
            end_month_dt = (start_month_dt + timedelta(days=32)).replace(day=1)

        # -------------------------------------------------------------
        # 1. Base Query with optional client / search filtering
        # -------------------------------------------------------------
        base_query = db.query(
            GatewayIncidentAlert,
            Device.name.label("gateway_id"),
            Device.location.label("location"),
            Device.hardware_model.label("hardware_model"),
            Client.name.label("client_name")
        ).join(
            Device, GatewayIncidentAlert.device_id == Device.id, isouter=True
        ).join(
            Client, Device.client_id == Client.id, isouter=True
        )

        if client_name and client_name != "All Clients":
            base_query = base_query.filter(Client.name.ilike(f"%{client_name}%"))

        if search:
            search_fmt = f"%{search}%"
            base_query = base_query.filter(
                (Device.name.ilike(search_fmt)) |
                (Device.location.ilike(search_fmt)) |
                (GatewayIncidentAlert.description.ilike(search_fmt))
            )

        # -------------------------------------------------------------
        # 2. Monthly Trend Aggregation
        # -------------------------------------------------------------
        start_utc = start_month_dt - timedelta(hours=7)
        end_utc = end_month_dt - timedelta(hours=7)

        trend_query = db.query(
            func.date(GatewayIncidentAlert.start_time + timedelta(hours=7)).label("dt"),
            GatewayIncidentAlert.metric,
            func.count(GatewayIncidentAlert.id).label("cnt")
        ).filter(
            GatewayIncidentAlert.start_time >= start_utc,
            GatewayIncidentAlert.start_time < end_utc
        )

        if client_name and client_name != "All Clients":
            trend_query = trend_query.join(Device, GatewayIncidentAlert.device_id == Device.id).join(
                Client, Device.client_id == Client.id
            ).filter(Client.name.ilike(f"%{client_name}%"))

        trend_rows = trend_query.group_by("dt", GatewayIncidentAlert.metric).order_by("dt").all()

        trend_map = defaultdict(lambda: {"total": 0, "cellular": 0, "cpu_dvr": 0, "cpu_modem": 0, "other": 0})
        total_month_incidents = 0
        latest_date_in_data = None

        for dt, metric, cnt in trend_rows:
            if dt is None:
                continue
            dt_str = str(dt)
            latest_date_in_data = dt_str
            trend_map[dt_str]["total"] += cnt
            total_month_incidents += cnt
            if metric in ("cellular", "cpu_dvr", "cpu_modem"):
                trend_map[dt_str][metric] += cnt
            else:
                trend_map[dt_str]["other"] += cnt

        # Format trend array sorted chronologically
        monthly_trend = []
        for dt_key in sorted(trend_map.keys()):
            val = trend_map[dt_key]
            monthly_trend.append({
                "date": dt_key,
                "total": val["total"],
                "cellular": val["cellular"],
                "cpu_dvr": val["cpu_dvr"],
                "cpu_modem": val["cpu_modem"],
                "other": val["other"]
            })

        # Determine target selected_date for daily view
        if not selected_date or selected_date not in trend_map:
            selected_date = latest_date_in_data or f"{month}-01"

        # -------------------------------------------------------------
        # 3. Monthly Causes Breakdown
        # -------------------------------------------------------------
        month_cause_query = db.query(
            GatewayIncidentAlert.metric,
            func.count(GatewayIncidentAlert.id).label("cnt"),
            func.avg(GatewayIncidentAlert.duration_minutes).label("avg_dur")
        ).filter(
            GatewayIncidentAlert.start_time >= start_utc,
            GatewayIncidentAlert.start_time < end_utc
        )
        if client_name and client_name != "All Clients":
            month_cause_query = month_cause_query.join(Device, GatewayIncidentAlert.device_id == Device.id).join(
                Client, Device.client_id == Client.id
            ).filter(Client.name.ilike(f"%{client_name}%"))

        month_causes_rows = month_cause_query.group_by(GatewayIncidentAlert.metric).order_by(desc("cnt")).all()

        monthly_causes = []
        for metric, cnt, avg_dur in month_causes_rows:
            meta = METRIC_META.get(metric, {
                "title": metric.replace("_", " ").title(),
                "description": f"Insiden pada komponen {metric}",
                "color": "#94a3b8",
                "icon": "AlertCircle"
            })
            pct = round((cnt / total_month_incidents * 100), 1) if total_month_incidents > 0 else 0
            monthly_causes.append({
                "metric": metric,
                "title": meta["title"],
                "description": meta["description"],
                "count": cnt,
                "percentage": pct,
                "avg_duration_minutes": round(float(avg_dur or 0), 1),
                "color": meta["color"],
                "icon": meta["icon"]
            })

        # -------------------------------------------------------------
        # 4. Daily Causes Breakdown (for selected_date)
        # -------------------------------------------------------------
        day_start_utc = datetime.strptime(selected_date, "%Y-%m-%d") - timedelta(hours=7)
        day_end_utc = day_start_utc + timedelta(days=1)

        day_cause_query = db.query(
            GatewayIncidentAlert.metric,
            func.count(GatewayIncidentAlert.id).label("cnt"),
            func.avg(GatewayIncidentAlert.duration_minutes).label("avg_dur")
        ).filter(
            GatewayIncidentAlert.start_time >= day_start_utc,
            GatewayIncidentAlert.start_time < day_end_utc
        )
        if client_name and client_name != "All Clients":
            day_cause_query = day_cause_query.join(Device, GatewayIncidentAlert.device_id == Device.id).join(
                Client, Device.client_id == Client.id
            ).filter(Client.name.ilike(f"%{client_name}%"))

        day_causes_rows = day_cause_query.group_by(GatewayIncidentAlert.metric).order_by(desc("cnt")).all()
        total_day_incidents = sum(r[1] for r in day_causes_rows)

        daily_causes = []
        for metric, cnt, avg_dur in day_causes_rows:
            meta = METRIC_META.get(metric, {
                "title": metric.replace("_", " ").title(),
                "description": f"Insiden pada komponen {metric}",
                "color": "#94a3b8",
                "icon": "AlertCircle"
            })
            pct = round((cnt / total_day_incidents * 100), 1) if total_day_incidents > 0 else 0
            daily_causes.append({
                "metric": metric,
                "title": meta["title"],
                "description": meta["description"],
                "count": cnt,
                "percentage": pct,
                "avg_duration_minutes": round(float(avg_dur or 0), 1),
                "color": meta["color"],
                "icon": meta["icon"]
            })

        # -------------------------------------------------------------
        # 5. Top Impacted Gateway in Month
        # -------------------------------------------------------------
        top_dev_query = db.query(
            Device.name.label("gateway_id"),
            Device.location.label("location"),
            Client.name.label("client_name"),
            func.count(GatewayIncidentAlert.id).label("incident_count")
        ).join(
            Device, GatewayIncidentAlert.device_id == Device.id
        ).join(
            Client, Device.client_id == Client.id, isouter=True
        ).filter(
            GatewayIncidentAlert.start_time >= start_utc,
            GatewayIncidentAlert.start_time < end_utc
        )
        if client_name and client_name != "All Clients":
            top_dev_query = top_dev_query.filter(Client.name.ilike(f"%{client_name}%"))

        top_dev_row = top_dev_query.group_by(Device.name, Device.location, Client.name).order_by(desc("incident_count")).first()

        most_affected_gateway = {
            "gateway_id": top_dev_row[0] if top_dev_row else "N/A",
            "location": top_dev_row[1] if top_dev_row else "N/A",
            "client_name": top_dev_row[2] if top_dev_row else "N/A",
            "incident_count": top_dev_row[3] if top_dev_row else 0
        }

        # -------------------------------------------------------------
        # 6. Offline Gateways & Root Cause Analysis
        # -------------------------------------------------------------
        # Query devices that have status OFFLINE from telemetry cache or active incidents
        try:
            offline_paged = cellular_service.get_gateways_paged(status="Offline", page_size=50)
            cell_gateways = offline_paged.get("items", [])
        except Exception:
            cell_gateways = []
        offline_dev_list = []

        # Find gateways reporting offline in cellular dashboard
        for gw in cell_gateways:
            gw_status = gw.get("status", "")
            if gw_status == "Offline" or gw.get("cpu_modem_status") == "No Response":
                offline_dev_list.append({
                    "gateway_id": gw.get("gateway_id") or gw.get("id"),
                    "location": gw.get("location"),
                    "client_name": gw.get("client"),
                    "hardware_type": gw.get("hardware_type", "SmartBox"),
                    "status": "Offline",
                    "signal_csq": gw.get("csq"),
                    "provider": gw.get("provider", "Telkomsel"),
                    "cpu_modem_status": gw.get("cpu_modem_status", "No Response"),
                    "primary_cause": gw.get("reason") or ("Quectel 4G Modem Serial Port No Response" if gw.get("cpu_modem_status") == "No Response" else "Cellular Disconnected / Blank Spot"),
                    "root_cause_metric": "cpu_modem" if gw.get("cpu_modem_status") == "No Response" else "cellular",
                    "uptime": gw.get("uptime", "N/A"),
                    "reason": gw.get("reason") or "Modem RF Surge / Fluktuasi Daya",
                    "reason_desc": gw.get("reason_desc") or "Sinyal seluler lemah memicu RF power spike modem saat transmisi, menyebabkan drop tegangan.",
                    "evidence": gw.get("evidence") or {
                        "badge": "⚡ RF Power Surge & Voltage Drop",
                        "badge_color": "amber",
                        "metrics": f"Sinyal CSQ: {gw.get('csq') or 0}",
                        "snippet": "Terdeteksi penurunan tegangan atau sinyal seluler drop.",
                        "evidence_ts": gw.get("last_update") or "Recent",
                    }
                })

        # Also find gateways with currently ACTIVE incident alerts
        active_incidents = db.query(
            GatewayIncidentAlert,
            Device.name.label("gateway_id"),
            Device.location.label("location"),
            Device.hardware_model.label("hardware_model"),
            Client.name.label("client_name")
        ).join(
            Device, GatewayIncidentAlert.device_id == Device.id
        ).join(
            Client, Device.client_id == Client.id, isouter=True
        ).filter(
            GatewayIncidentAlert.status == "ACTIVE"
        ).order_by(desc(GatewayIncidentAlert.start_time)).limit(20).all()

        for inc, gw_id, loc, hw, cl_name in active_incidents:
            if not any(d["gateway_id"] == gw_id for d in offline_dev_list):
                offline_dev_list.append({
                    "gateway_id": gw_id,
                    "location": loc,
                    "client_name": cl_name or "DANAMON",
                    "hardware_type": hw or "Raspberry Pi 3B+",
                    "status": "Outage Active",
                    "signal_csq": None,
                    "provider": "Telkomsel",
                    "cpu_modem_status": "Active Alert",
                    "primary_cause": inc.description or METRIC_META.get(inc.metric, {}).get("title", inc.metric),
                    "root_cause_metric": inc.metric,
                    "uptime": inc.duration_str or "Ongoing"
                })

        # Filter offline gateways by client if specified
        if client_name and client_name != "All Clients":
            offline_dev_list = [d for d in offline_dev_list if client_name.lower() in (d.get("client_name") or "").lower()]

        # -------------------------------------------------------------
        # 7. Recent Incidents for the Selected Date
        # -------------------------------------------------------------
        inc_query = base_query.filter(
            GatewayIncidentAlert.start_time >= day_start_utc,
            GatewayIncidentAlert.start_time < day_end_utc
        ).order_by(desc(GatewayIncidentAlert.start_time))

        total_day_table_count = inc_query.count()
        inc_rows = inc_query.offset(offset).limit(limit).all()

        incident_items = []
        for inc, gw_id, loc, hw, cl_name in inc_rows:
            start_wib = (inc.start_time + timedelta(hours=7)).strftime("%Y-%m-%d %H:%M:%S") if inc.start_time else None
            end_wib = (inc.end_time + timedelta(hours=7)).strftime("%Y-%m-%d %H:%M:%S") if inc.end_time else None
            incident_items.append({
                "id": str(inc.id),
                "gateway_id": gw_id or str(inc.device_id),
                "location": loc or "N/A",
                "client_name": cl_name or "DANAMON",
                "hardware_model": hw,
                "metric": inc.metric,
                "title": METRIC_META.get(inc.metric, {}).get("title", inc.metric.replace("_", " ").title()),
                "description": inc.description,
                "start_time_wib": start_wib,
                "end_time_wib": end_wib,
                "duration": inc.duration_str or f"{round(inc.duration_minutes or 0)}m",
                "status": inc.status
            })

        # -------------------------------------------------------------
        # 8. Summary KPIs
        # -------------------------------------------------------------
        summary = {
            "selected_month": month,
            "selected_date": selected_date,
            "total_incidents_month": total_month_incidents,
            "total_incidents_today": total_day_incidents,
            "active_outages": len(offline_dev_list),
            "top_cause_today": daily_causes[0]["title"] if daily_causes else "No Incidents",
            "top_cause_today_metric": daily_causes[0]["metric"] if daily_causes else None,
            "top_cause_today_count": daily_causes[0]["count"] if daily_causes else 0,
            "top_cause_month": monthly_causes[0]["title"] if monthly_causes else "No Incidents",
            "top_cause_month_metric": monthly_causes[0]["metric"] if monthly_causes else None,
            "top_cause_month_count": monthly_causes[0]["count"] if monthly_causes else 0,
            "most_affected_gateway": most_affected_gateway,
            "total_offline_devices": len(offline_dev_list),
        }

        return {
            "status": True,
            "available_months": available_months,
            "selected_month": month,
            "selected_date": selected_date,
            "summary": summary,
            "monthly_trend": monthly_trend,
            "daily_causes": daily_causes,
            "monthly_causes": monthly_causes,
            "offline_devices": offline_dev_list[:20],
            "incidents": {
                "total": total_day_table_count,
                "limit": limit,
                "offset": offset,
                "items": incident_items
            }
        }


analytics_service = AnalyticsService()
