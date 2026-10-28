from typing import Dict, Any, List, Optional


class CellularService:
    """
    Service layer for Cellular Connectivity Monitoring:
    Modem, SIM Card, Signal (RSRP), Network Operator & CPU–Modem Communication
    """

    def __init__(self):
        # Master Fleet Mock Data matching UI Screenshots & Telemetry Specifications
        self._mock_gateways: List[Dict[str, Any]] = [
            {
                "no": 1,
                "id": "ZH72",
                "location": "Alfa H Sapri Pondok Aren",
                "type": "SmartBox Hitam",
                "model": "Raspberry Pi 3B+",
                "modem": "Quectel EC200E",
                "provider": "Telkomsel",
                "sim_status": "Aktif",
                "cpu_modem": "Connected",
                "network": "4G (LTE)",
                "signal_rsrp": "-78 dBm",
                "signal_bars": 4,
                "modem_temp": "45°C",
                "status": "Online",
                "last_update": "26 Oct 2026 14:32",
            },
            {
                "no": 2,
                "id": "ZV91",
                "location": "IDM Graha Morris Tambun",
                "type": "SmartBox Putih",
                "model": "Rockchip RK3328",
                "modem": "Quectel EC25-E",
                "provider": "Indosat",
                "sim_status": "Aktif",
                "cpu_modem": "No Response",
                "network": "4G (LTE)",
                "signal_rsrp": "-95 dBm",
                "signal_bars": 3,
                "modem_temp": "68°C",
                "status": "Degraded",
                "last_update": "26 Oct 2026 14:28",
            },
            {
                "no": 3,
                "id": "697D",
                "location": "Alfa Ahmad Dahlan III",
                "type": "SmartBox Hitam",
                "model": "Raspberry Pi 3B+",
                "modem": "SIM7600",
                "provider": "Telkomsel",
                "sim_status": "Aktif",
                "cpu_modem": "Connected",
                "network": "4G (LTE)",
                "signal_rsrp": "-102 dBm",
                "signal_bars": 2,
                "modem_temp": "52°C",
                "status": "Online",
                "last_update": "26 Oct 2026 14:15",
            },
            {
                "no": 4,
                "id": "ZR4R",
                "location": "Alfa Ruko Metland",
                "type": "SmartBox Putih",
                "model": "Rockchip RK3328",
                "modem": "Quectel EC200E",
                "provider": "XL Axiata",
                "sim_status": "Tidak Terdeteksi",
                "cpu_modem": "Not Detected",
                "network": "No Service",
                "signal_rsrp": "-",
                "signal_bars": 0,
                "modem_temp": "-",
                "status": "Offline",
                "last_update": "26 Oct 2026 13:50",
            },
            {
                "no": 5,
                "id": "ZJ2B",
                "location": "IDM Griya Mustikasari",
                "type": "SmartBox Hitam",
                "model": "Raspberry Pi 3B+",
                "modem": "SIM7600",
                "provider": "Telkomsel",
                "sim_status": "Aktif",
                "cpu_modem": "Connected",
                "network": "4G (LTE)",
                "signal_rsrp": "-88 dBm",
                "signal_bars": 4,
                "modem_temp": "41°C",
                "status": "Online",
                "last_update": "26 Oct 2026 12:40",
            },
            {
                "no": 6,
                "id": "QK18",
                "location": "Alfa Ciputat Raya",
                "type": "SmartBox Hitam",
                "model": "Raspberry Pi 3B+",
                "modem": "Quectel EC200E",
                "provider": "Telkomsel",
                "sim_status": "Aktif",
                "cpu_modem": "Connected",
                "network": "4G (LTE)",
                "signal_rsrp": "-74 dBm",
                "signal_bars": 5,
                "modem_temp": "39°C",
                "status": "Online",
                "last_update": "26 Oct 2026 12:35",
            },
            {
                "no": 7,
                "id": "NW55",
                "location": "IDM Margonda Depok",
                "type": "SmartBox Putih",
                "model": "Rockchip RK3328",
                "modem": "Quectel EC25-E",
                "provider": "Indosat",
                "sim_status": "Aktif",
                "cpu_modem": "Connected",
                "network": "4G (LTE)",
                "signal_rsrp": "-82 dBm",
                "signal_bars": 4,
                "modem_temp": "43°C",
                "status": "Online",
                "last_update": "26 Oct 2026 12:20",
            },
        ]

    def get_summary_metrics(self) -> Dict[str, Any]:
        """Summary card metrics for 2,000 Cellular Gateways"""
        return {
            "total_gateways": 2000,
            "online": 1720,
            "online_percent": 86.0,
            "offline": 210,
            "offline_percent": 10.5,
            "degraded": 70,
            "degraded_percent": 3.5,
            "smartbox_hitam": {
                "name": "SmartBox Hitam",
                "model": "Raspberry Pi 3B+",
                "total": 1050,
                "online": 900,
                "offline": 110,
                "degraded": 40,
            },
            "smartbox_putih": {
                "name": "SmartBox Putih",
                "model": "Rockchip RK3328",
                "total": 950,
                "online": 820,
                "offline": 100,
                "degraded": 30,
            },
        }

    def get_charts(self) -> Dict[str, Any]:
        """2 Donut charts + 2 Timeline line/area charts"""
        return {
            "cpu_modem_comm": {
                "total_label": "Connected",
                "total_count": 1960,
                "total_percent": 98.0,
                "slices": [
                    {"label": "Connected", "count": 1960, "percent": 98.0, "color": "#00c875"},
                    {"label": "Not Detected", "count": 20, "percent": 1.0, "color": "#e2445c"},
                    {"label": "No Response", "count": 12, "percent": 0.6, "color": "#fdab3d"},
                    {"label": "Driver Error", "count": 8, "percent": 0.4, "color": "#4a7cf6"},
                ],
            },
            "modem_network_status": {
                "total_label": "Online",
                "total_count": 1720,
                "total_percent": 86.0,
                "slices": [
                    {"label": "Online", "count": 1720, "percent": 86.0, "color": "#00c875"},
                    {"label": "Searching", "count": 50, "percent": 2.5, "color": "#2ed573"},
                    {"label": "No Service", "count": 120, "percent": 6.0, "color": "#e2445c"},
                    {"label": "SIM Error", "count": 40, "percent": 2.0, "color": "#4a7cf6"},
                    {"label": "Roaming", "count": 70, "percent": 3.5, "color": "#fdab3d"},
                ],
            },
            "signal_strength": {
                "avg": "-85 dBm",
                "max": "-62 dBm",
                "min": "-118 dBm",
                "timeline": [
                    {"time": "00:00", "value": -84.0},
                    {"time": "02:00", "value": -86.0},
                    {"time": "04:00", "value": -85.0},
                    {"time": "06:00", "value": -83.0},
                    {"time": "08:00", "value": -85.0},
                    {"time": "10:00", "value": -81.0},
                    {"time": "12:00", "value": -84.0},
                    {"time": "14:00", "value": -86.0},
                    {"time": "16:00", "value": -82.0},
                    {"time": "18:00", "value": -85.0},
                    {"time": "20:00", "value": -84.0},
                ],
            },
            "modem_temperature": {
                "avg": "42°C",
                "max": "85°C",
                "min": "28°C",
                "timeline": [
                    {"time": "00:00", "value": 30.0},
                    {"time": "02:00", "value": 38.0},
                    {"time": "04:00", "value": 41.0},
                    {"time": "06:00", "value": 43.0},
                    {"time": "08:00", "value": 48.0},
                    {"time": "10:00", "value": 46.0},
                    {"time": "12:00", "value": 44.0},
                    {"time": "14:00", "value": 47.0},
                    {"time": "16:00", "value": 43.0},
                    {"time": "18:00", "value": 42.0},
                    {"time": "20:00", "value": 40.0},
                ],
            },
        }

    def get_gateways_paged(
        self,
        search: Optional[str] = None,
        gateway_type: Optional[str] = None,
        provider: Optional[str] = None,
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

        if provider and provider != "Semua Provider":
            filtered = [
                g for g in filtered
                if g["provider"].lower() == provider.strip().lower()
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
        provider: Optional[str] = None,
        page: int = 1,
        page_size: int = 5,
    ) -> Dict[str, Any]:
        """Composite payload for Cellular Dashboard"""
        paged_gateways = self.get_gateways_paged(
            search=search,
            gateway_type=gateway_type,
            provider=provider,
            page=page,
            page_size=page_size,
        )

        return {
            "summary": self.get_summary_metrics(),
            "charts": self.get_charts(),
            "gateways": paged_gateways["items"],
            "pagination": paged_gateways["pagination"],
        }

    def get_gateway_detail(self, gateway_id: str) -> Dict[str, Any]:
        """Detailed telemetry for a specific gateway cellular connectivity"""
        gw = next((g for g in self._mock_gateways if g["id"].lower() == gateway_id.lower()), self._mock_gateways[0])
        
        is_hitam = "Hitam" in gw["type"]
        model_name = "SmartBox Hitam (Raspberry Pi 3B+)" if is_hitam else "SmartBox Putih (Rockchip RK3328)"

        if gw["id"] == "ZH72":
            return {
                "id": "ZH72",
                "location": "Alfa H Sapri Pondok Aren",
                "type": "SmartBox Hitam",
                "model": model_name,
                "modem": "Quectel EC200E",
                "provider": "Telkomsel",
                "sim_card": "Aktif",
                "ip_address": "10.10.72.15",
                "last_update": "26 Oct 2026 14:32:10",
                "service_status": "Running",
                "cpu_modem": {
                    "status": "Connected",
                    "message": "CPU dapat berkomunikasi dengan modem (driver OK)",
                    "port": "/dev/ttyUSB2",
                    "baudrate": 115200,
                    "driver": "qmi_wwan",
                    "last_check": "26 Oct 2026 14:32:05",
                },
                "signal_strength": {
                    "rsrp": -78,
                    "unit": "dBm",
                    "max_rsrp": "Max -62 dBm",
                    "min_rsrp": "Min -118 dBm",
                    "avg_rsrp": "Avg -85 dBm",
                    "sparkline": [-85, -82, -80, -78, -79, -77, -78],
                },
                "network_sim": {
                    "network_type": "4G",
                    "network_sub": "(LTE)",
                    "operator": "Telkomsel",
                    "sim_status": "Aktif",
                    "imsi": "510100123456789",
                    "iccid": "8962101234567890 0123",
                    "data_upload": "1.2 GB",
                    "data_download": "3.8 GB",
                    "roaming": "Tidak",
                },
                "modem_temperature": {
                    "temperature": 45,
                    "unit": "°C",
                    "max_temp": "Max 62°C",
                    "min_temp": "Min 28°C",
                    "avg_temp": "Avg 42°C",
                    "sparkline": [38, 40, 42, 45, 44, 46, 45],
                },
            }

        # Dynamic fallback for fleet gateways
        rsrp_val = int(gw["signal_rsrp"].replace(" dBm", "")) if "dBm" in gw.get("signal_rsrp", "") else -85
        temp_val = int(gw["modem_temp"].replace("°C", "")) if "°C" in gw.get("modem_temp", "") else 45

        return {
            "id": gw["id"],
            "location": gw["location"],
            "type": gw["type"],
            "model": model_name,
            "modem": gw["modem"],
            "provider": gw["provider"],
            "sim_card": gw["sim_status"],
            "ip_address": f"10.10.{gw['no'] % 250}.{10 + (gw['no'] % 200)}",
            "last_update": f"{gw.get('last_update', '26 Oct 2026 14:32')}:10",
            "service_status": "Running" if gw["status"] != "Offline" else "Stopped",
            "cpu_modem": {
                "status": gw["cpu_modem"],
                "message": "CPU dapat berkomunikasi dengan modem (driver OK)" if gw["cpu_modem"] == "Connected" else "Komunikasi dengan modem bermasalah",
                "port": "/dev/ttyUSB2",
                "baudrate": 115200,
                "driver": "qmi_wwan",
                "last_check": f"{gw.get('last_update', '26 Oct 2026 14:32')}:05",
            },
            "signal_strength": {
                "rsrp": rsrp_val,
                "unit": "dBm",
                "max_rsrp": f"Max {rsrp_val + 16} dBm",
                "min_rsrp": f"Min {rsrp_val - 40} dBm",
                "avg_rsrp": f"Avg {rsrp_val - 7} dBm",
                "sparkline": [rsrp_val - 7, rsrp_val - 4, rsrp_val - 2, rsrp_val, rsrp_val - 1, rsrp_val],
            },
            "network_sim": {
                "network_type": "4G" if "4G" in gw["network"] else "3G",
                "network_sub": "(LTE)" if "4G" in gw["network"] else "",
                "operator": gw["provider"],
                "sim_status": gw["sim_status"],
                "imsi": f"510100{gw['no']:09d}",
                "iccid": f"89621012{gw['no']:08d} 0123",
                "data_upload": f"{(gw['no'] % 3) + 0.8:.1f} GB",
                "data_download": f"{(gw['no'] % 5) + 2.5:.1f} GB",
                "roaming": "Tidak",
            },
            "modem_temperature": {
                "temperature": temp_val,
                "unit": "°C",
                "max_temp": f"Max {temp_val + 17}°C",
                "min_temp": f"Min {max(20, temp_val - 17)}°C",
                "avg_temp": f"Avg {temp_val - 3}°C",
                "sparkline": [temp_val - 7, temp_val - 5, temp_val - 3, temp_val, temp_val - 1, temp_val],
            },
        }


# Global singleton instance
cellular_service = CellularService()

