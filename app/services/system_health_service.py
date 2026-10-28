from typing import Dict, Any, List, Optional


class SystemHealthService:
    """
    Service layer for System Health Fleet Monitoring.
    Handles business logic, aggregation, filtering, and data provider for 2,000 SmartBoxes.
    """

    def __init__(self):
        # Master Fleet Mock Data matching UI Screenshots & Diagnostic Specifications
        self._mock_gateways: List[Dict[str, Any]] = [
            {
                "no": 1,
                "id": "ZH72",
                "location": "Alfa H Sapri Pondok Aren",
                "type": "SmartBox Hitam",
                "model": "Raspberry Pi 3B+",
                "cpu": 28,
                "ram": 46,
                "sd_used_gb": 29,
                "sd_total_gb": 32,
                "sd_percent": 72,
                "sd_health": "Good",
                "uptime": "14 days 6 hours",
                "status": "Healthy",
                "last_update": "26 Oct 2026 14:32",
            },
            {
                "no": 2,
                "id": "ZV91",
                "location": "IDM Graha Morris Tambun",
                "type": "SmartBox Putih",
                "model": "Rockchip RK3328",
                "cpu": 72,
                "ram": 68,
                "sd_used_gb": 26,
                "sd_total_gb": 32,
                "sd_percent": 81,
                "sd_health": "Wear",
                "uptime": "3 days 12 hours",
                "status": "Warning",
                "last_update": "26 Oct 2026 14:28",
            },
            {
                "no": 3,
                "id": "697D",
                "location": "Alfa Ahmad Dahlan III",
                "type": "SmartBox Hitam",
                "model": "Raspberry Pi 3B+",
                "cpu": 15,
                "ram": 32,
                "sd_used_gb": 18,
                "sd_total_gb": 32,
                "sd_percent": 56,
                "sd_health": "Good",
                "uptime": "20 days 4 hours",
                "status": "Healthy",
                "last_update": "26 Oct 2026 14:15",
            },
            {
                "no": 4,
                "id": "ZR4R",
                "location": "Alfa Ruko Metland",
                "type": "SmartBox Putih",
                "model": "Rockchip RK3328",
                "cpu": 93,
                "ram": 78,
                "sd_used_gb": 30,
                "sd_total_gb": 32,
                "sd_percent": 94,
                "sd_health": "Bad",
                "uptime": "1 day 2 hours",
                "status": "Critical",
                "last_update": "26 Oct 2026 13:50",
            },
            {
                "no": 5,
                "id": "ZJ2B",
                "location": "IDM Griya Mustikasari",
                "type": "SmartBox Hitam",
                "model": "Raspberry Pi 3B+",
                "cpu": 48,
                "ram": 52,
                "sd_used_gb": 24,
                "sd_total_gb": 32,
                "sd_percent": 75,
                "sd_health": "Wear",
                "uptime": "7 days 18 hours",
                "status": "Warning",
                "last_update": "26 Oct 2026 12:40",
            },
            {
                "no": 6,
                "id": "QK18",
                "location": "Alfa Ciputat Raya",
                "type": "SmartBox Hitam",
                "model": "Raspberry Pi 3B+",
                "cpu": 22,
                "ram": 38,
                "sd_used_gb": 19,
                "sd_total_gb": 32,
                "sd_percent": 59,
                "sd_health": "Good",
                "uptime": "25 days 2 hours",
                "status": "Healthy",
                "last_update": "26 Oct 2026 12:35",
            },
            {
                "no": 7,
                "id": "NW55",
                "location": "IDM Margonda Depok",
                "type": "SmartBox Putih",
                "model": "Rockchip RK3328",
                "cpu": 35,
                "ram": 42,
                "sd_used_gb": 22,
                "sd_total_gb": 32,
                "sd_percent": 68,
                "sd_health": "Good",
                "uptime": "12 days 8 hours",
                "status": "Healthy",
                "last_update": "26 Oct 2026 12:20",
            },
        ]

    def get_summary_metrics(self) -> Dict[str, Any]:
        """Summary card metrics for 2,000 SmartBoxes"""
        return {
            "total_gateways": 2000,
            "healthy": 1890,
            "healthy_percent": 94.5,
            "warning": 80,
            "warning_percent": 4.0,
            "critical": 30,
            "critical_percent": 1.5,
            "smartbox_hitam": {
                "name": "SmartBox Hitam",
                "model": "Raspberry Pi 3B+",
                "total": 1050,
                "healthy": 980,
                "warning": 55,
                "critical": 15,
            },
            "smartbox_putih": {
                "name": "SmartBox Putih",
                "model": "Rockchip RK3328",
                "total": 950,
                "healthy": 870,
                "warning": 25,
                "critical": 55,
            },
        }

    def get_chart_telemetry(self) -> Dict[str, Any]:
        """24-Hour historical average timeline for CPU, RAM, SD Card, and Uptime"""
        return {
            "cpu": {
                "avg": 28.0,
                "max": 92.0,
                "min": 5.0,
                "timeline": [
                    {"time": "00:00", "value": 30.0},
                    {"time": "02:00", "value": 45.0},
                    {"time": "04:00", "value": 42.0},
                    {"time": "06:00", "value": 41.0},
                    {"time": "08:00", "value": 40.0},
                    {"time": "10:00", "value": 42.0},
                    {"time": "12:00", "value": 33.0},
                    {"time": "14:00", "value": 35.0},
                    {"time": "16:00", "value": 48.0},
                    {"time": "18:00", "value": 36.0},
                    {"time": "20:00", "value": 38.0},
                ],
            },
            "ram": {
                "avg": 46.0,
                "max": 88.0,
                "min": 12.0,
                "timeline": [
                    {"time": "00:00", "value": 42.0},
                    {"time": "02:00", "value": 36.0},
                    {"time": "04:00", "value": 39.0},
                    {"time": "06:00", "value": 47.0},
                    {"time": "08:00", "value": 45.0},
                    {"time": "10:00", "value": 41.0},
                    {"time": "12:00", "value": 34.0},
                    {"time": "14:00", "value": 43.0},
                    {"time": "16:00", "value": 44.0},
                    {"time": "18:00", "value": 46.0},
                    {"time": "20:00", "value": 48.0},
                ],
            },
            "sd_card": {
                "avg": 62.0,
                "max": 98.0,
                "min": 18.0,
                "timeline": [
                    {"time": "00:00", "value": 56.0},
                    {"time": "02:00", "value": 59.0},
                    {"time": "04:00", "value": 60.0},
                    {"time": "06:00", "value": 66.0},
                    {"time": "08:00", "value": 62.0},
                    {"time": "10:00", "value": 58.0},
                    {"time": "12:00", "value": 53.0},
                    {"time": "14:00", "value": 66.0},
                    {"time": "16:00", "value": 68.0},
                    {"time": "18:00", "value": 63.0},
                    {"time": "20:00", "value": 65.0},
                ],
            },
            "uptime": {
                "avg": 96.2,
                "timeline": [
                    {"time": "00:00", "value": 96.5},
                    {"time": "04:00", "value": 96.0},
                    {"time": "08:00", "value": 97.2},
                    {"time": "12:00", "value": 95.8},
                    {"time": "16:00", "value": 96.4},
                    {"time": "20:00", "value": 96.2},
                ],
            },
        }

    def get_gateways_paged(
        self,
        search: Optional[str] = None,
        gateway_type: Optional[str] = None,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 5,
    ) -> Dict[str, Any]:
        """Filters, sorts, and paginates gateway list"""
        filtered = self._mock_gateways

        if search:
            query = search.strip().lower()
            filtered = [
                g for g in filtered
                if query in g["id"].lower() or query in g["location"].lower()
            ]

        if gateway_type and gateway_type != "Semua Tipe":
            filtered = [
                g for g in filtered
                if g["type"].lower() == gateway_type.strip().lower()
            ]

        if status and status != "Semua Status":
            filtered = [
                g for g in filtered
                if g["status"].lower() == status.strip().lower()
            ]

        total_items = 2000
        total_pages = 400

        start_index = (page - 1) * page_size
        items = filtered[start_index : start_index + page_size] if start_index < len(filtered) else filtered[:page_size]

        return {
            "items": items,
            "pagination": {
                "total_items": total_items,
                "total_pages": total_pages,
                "current_page": page,
                "page_size": page_size,
                "showing_start": (page - 1) * page_size + 1,
                "showing_end": min(page * page_size, total_items),
            },
        }

    def get_full_dashboard(
        self,
        search: Optional[str] = None,
        gateway_type: Optional[str] = None,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 5,
    ) -> Dict[str, Any]:
        """Composite payload for System Health Dashboard"""
        paged_gateways = self.get_gateways_paged(
            search=search,
            gateway_type=gateway_type,
            status=status,
            page=page,
            page_size=page_size,
        )

        return {
            "summary": self.get_summary_metrics(),
            "charts": self.get_chart_telemetry(),
            "gateways": paged_gateways["items"],
            "pagination": paged_gateways["pagination"],
        }

    def get_gateway_detail(self, gateway_id: str) -> Dict[str, Any]:
        """Detailed telemetry for a specific gateway (for bottom detail panel)"""
        # Find gateway or fallback to first
        gw = next((g for g in self._mock_gateways if g["id"].lower() == gateway_id.lower()), self._mock_gateways[0])
        
        is_hitam = "Hitam" in gw["type"]
        model_name = "SmartBox Hitam (Raspberry Pi 3B+)" if is_hitam else "SmartBox Putih (Rockchip RK3328)"
        
        # Exact values from screenshot for ZH72
        if gw["id"] == "ZH72":
            return {
                "id": "ZH72",
                "location": "Alfa H Sapri Pondok Aren",
                "type": "SmartBox Hitam",
                "model": model_name,
                "ip_address": "10.10.72.15",
                "uptime": "14 days 6 hours",
                "last_update": "26 Oct 2026 14:32:10",
                "service_status": "Running",
                "cpu_percent": 28,
                "cpu_min": "Min 5%",
                "cpu_max": "Max 92%",
                "cpu_sparkline": [15, 20, 25, 22, 28, 32, 28],
                "ram_percent": 46,
                "ram_min": "Min 12%",
                "ram_max": "Max 88%",
                "ram_sparkline": [38, 42, 45, 46, 44, 46, 46],
                "sd_percent": 72,
                "sd_used_gb": 29,
                "sd_total_gb": 32,
                "sd_sparkline": [70, 71, 71, 72, 72, 72, 72],
                "sd_health": {
                    "status": "Good",
                    "bad_sector": 0,
                    "wear_level": "12%",
                    "temperature": "38°C",
                    "io_error": 0,
                },
                "uptime_days": 14,
                "uptime_hours": 6,
                "uptime_status": "Running",
                "uptime_subtext": "Normal Operation",
                "month_period": "01 Oct 2026 - 31 Oct 2026",
                "month_total_hours": 744,
                "uptime_duration": "720h 15m",
                "uptime_pct": "96.8%",
                "downtime_duration": "23h 45m",
                "downtime_pct": "3.2%",
                "sla_target": 99.5,
                "sla_target_hours": "740h 17m",
                "sla_status": "Breach",
                "sla_downtime_allowed": "3h 43m",
                "downtime_events": [
                    {
                        "no": 1,
                        "start_time": "04 Oct 2026 02:15",
                        "end_time": "04 Oct 2026 08:30",
                        "duration": "6h 15m",
                        "accumulated_hours": "6h 15m",
                        "category": "Listrik Padam (PLN)",
                        "reason": "Gangguan suplai daya PLN area Pondok Aren",
                        "sla_impact_pct": 0.84,
                        "status": "Resolved",
                    },
                    {
                        "no": 2,
                        "start_time": "12 Oct 2026 11:20",
                        "end_time": "12 Oct 2026 15:05",
                        "duration": "3h 45m",
                        "accumulated_hours": "10h 00m",
                        "category": "MCB / Power Trip",
                        "reason": "MCB switch toko trip saat beban puncak",
                        "sla_impact_pct": 0.50,
                        "status": "Resolved",
                    },
                    {
                        "no": 3,
                        "start_time": "19 Oct 2026 23:40",
                        "end_time": "20 Oct 2026 09:10",
                        "duration": "9h 30m",
                        "accumulated_hours": "19h 30m",
                        "category": "Maintenance Gedung",
                        "reason": "Pemeliharaan panel daya & kelistrikan toko",
                        "sla_impact_pct": 1.28,
                        "status": "Resolved",
                    },
                    {
                        "no": 4,
                        "start_time": "27 Oct 2026 14:10",
                        "end_time": "27 Oct 2026 18:25",
                        "duration": "4h 15m",
                        "accumulated_hours": "23h 45m",
                        "category": "Hard Reboot & OS Recovery",
                        "reason": "Pemulihan sistem otomatis paska tegangan drop",
                        "sla_impact_pct": 0.57,
                        "status": "Resolved",
                    },
                ],
            }
        
        # General gateway detail
        uptime_pct_val = max(88.0, min(99.9, 100.0 - (0.4 if gw["status"] == "Normal" else (2.5 if gw["status"] == "Warning" else 5.8))))
        downtime_pct_val = round(100.0 - uptime_pct_val, 1)
        total_hours = 744
        uptime_hours_total = total_hours * (uptime_pct_val / 100.0)
        downtime_hours_total = total_hours - uptime_hours_total
        up_h = int(uptime_hours_total)
        up_m = int(round((uptime_hours_total - up_h) * 60))
        down_h = int(downtime_hours_total)
        down_m = int(round((downtime_hours_total - down_h) * 60))
        is_sla_met = uptime_pct_val >= 99.5

        gen_downtime_events = [
            {
                "no": 1,
                "start_time": "11 Oct 2026 01:30",
                "end_time": f"11 Oct 2026 {1 + down_h:02d}:{down_m:02d}",
                "duration": f"{down_h}h {down_m:02d}m",
                "accumulated_hours": f"{down_h}h {down_m:02d}m",
                "category": "Maintenance Terjadwal" if is_sla_met else "Gangguan Daya Lokasi",
                "reason": "Restart pemeliharaan firmware" if is_sla_met else "Tegangan tidak stabil / adaptor drop",
                "sla_impact_pct": round(downtime_pct_val, 2),
                "status": "Resolved",
            }
        ]

        return {
            "id": gw["id"],
            "location": gw["location"],
            "type": gw["type"],
            "model": model_name,
            "ip_address": f"10.10.{gw['no'] % 250}.{10 + (gw['no'] % 200)}",
            "uptime": gw.get("uptime", "5 days 10 hours"),
            "last_update": f"{gw.get('last_update', '26 Oct 2026 14:32')}:10",
            "service_status": "Running" if gw["status"] != "Critical" else "Degraded",
            "cpu_percent": gw["cpu"],
            "cpu_min": "Min 8%",
            "cpu_max": f"Max {min(99, gw['cpu'] + 30)}%",
            "cpu_sparkline": [max(5, gw["cpu"] - 10), max(8, gw["cpu"] - 5), gw["cpu"], min(95, gw["cpu"] + 8), gw["cpu"]],
            "ram_percent": gw["ram"],
            "ram_min": "Min 15%",
            "ram_max": f"Max {min(98, gw['ram'] + 25)}%",
            "ram_sparkline": [max(10, gw["ram"] - 8), gw["ram"] - 2, gw["ram"], min(95, gw["ram"] + 5), gw["ram"]],
            "sd_percent": gw["sd_percent"],
            "sd_used_gb": gw["sd_used_gb"],
            "sd_total_gb": gw["sd_total_gb"],
            "sd_sparkline": [gw["sd_percent"] - 2, gw["sd_percent"] - 1, gw["sd_percent"], gw["sd_percent"]],
            "sd_health": {
                "status": "Good" if gw["sd_percent"] < 80 else ("Caution" if gw["sd_percent"] < 90 else "Poor"),
                "bad_sector": 0 if gw["sd_percent"] < 85 else 2,
                "wear_level": f"{gw['sd_percent'] // 5}%",
                "temperature": f"{35 + (gw['cpu'] // 5)}°C",
                "io_error": 0,
            },
            "uptime_days": 10 + (gw["no"] % 20),
            "uptime_hours": gw["no"] % 24,
            "uptime_status": "Running",
            "uptime_subtext": "Normal Operation",
            "month_period": "01 Oct 2026 - 31 Oct 2026",
            "month_total_hours": 744,
            "uptime_duration": f"{up_h}h {up_m:02d}m",
            "uptime_pct": f"{uptime_pct_val:.1f}%",
            "downtime_duration": f"{down_h}h {down_m:02d}m",
            "downtime_pct": f"{downtime_pct_val:.1f}%",
            "sla_target": 99.5,
            "sla_target_hours": "740h 17m",
            "sla_status": "Tercapai" if is_sla_met else "Breach",
            "sla_downtime_allowed": "3h 43m",
            "downtime_events": gen_downtime_events,
        }


# Global singleton instance
system_health_service = SystemHealthService()

