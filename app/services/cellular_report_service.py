from typing import Dict, Any, List, Optional
import io
import csv


class CellularReportService:
    """
    Service layer for Cellular Historical Telemetry Report:
    Fleet SIM cards, CPU-Modem communication SLA, Network Connection uptime,
    RSRP/Temp analytics, and incident trouble events.
    """

    def __init__(self):
        # 10 primary rows from user's screenshot
        self._primary_rows: List[Dict[str, Any]] = [
            {
                "no": 1,
                "id": "ZH72",
                "location": "Alfa H Sapri Pondok Aren",
                "type": "SmartBox Hitam",
                "modem": "Quectel EC200E",
                "provider": "Telkomsel",
                "sim_number": "6281212345678",
                "cpu_modem_uptime": "728h 15m",
                "cpu_modem_offline": "15h 45m",
                "cpu_modem_success_rate": 98.5,
                "cpu_modem_avg_resp_ms": 220,
                "network_uptime": "720h 30m",
                "network_offline": "23h 30m",
                "network_success_rate": 97.4,
                "network_avg_rsrp": -78,
                "network_avg_temp": 45,
                "trouble_events_count": 3,
                "trouble_last_offline": "26 Oct 2026 14:32",
            },
            {
                "no": 2,
                "id": "ZV91",
                "location": "IDM Graha Morris Tambun",
                "type": "SmartBox Putih",
                "modem": "Quectel EC25-E",
                "provider": "Indosat",
                "sim_number": "6281511122334",
                "cpu_modem_uptime": "710h 05m",
                "cpu_modem_offline": "33h 55m",
                "cpu_modem_success_rate": 96.2,
                "cpu_modem_avg_resp_ms": 310,
                "network_uptime": "689h 20m",
                "network_offline": "54h 40m",
                "network_success_rate": 93.8,
                "network_avg_rsrp": -92,
                "network_avg_temp": 52,
                "trouble_events_count": 7,
                "trouble_last_offline": "25 Oct 2026 08:17",
            },
            {
                "no": 3,
                "id": "697D",
                "location": "Alfa Ahmad Dahlan III",
                "type": "SmartBox Hitam",
                "modem": "SIM7600",
                "provider": "Telkomsel",
                "sim_number": "6281234455667",
                "cpu_modem_uptime": "731h 20m",
                "cpu_modem_offline": "12h 40m",
                "cpu_modem_success_rate": 99.1,
                "cpu_modem_avg_resp_ms": 180,
                "network_uptime": "731h 10m",
                "network_offline": "12h 50m",
                "network_success_rate": 98.7,
                "network_avg_rsrp": -76,
                "network_avg_temp": 41,
                "trouble_events_count": 2,
                "trouble_last_offline": "18 Oct 2026 22:11",
            },
            {
                "no": 4,
                "id": "ZR4R",
                "location": "Alfa Ruko Metland",
                "type": "SmartBox Putih",
                "modem": "Quectel EC200E",
                "provider": "XL Axiata",
                "sim_number": "6281778899001",
                "cpu_modem_uptime": "608h 30m",
                "cpu_modem_offline": "135h 30m",
                "cpu_modem_success_rate": 87.3,
                "cpu_modem_avg_resp_ms": 520,
                "network_uptime": "578h 10m",
                "network_offline": "165h 50m",
                "network_success_rate": 84.6,
                "network_avg_rsrp": -102,
                "network_avg_temp": 51,
                "trouble_events_count": 12,
                "trouble_last_offline": "24 Oct 2026 03:10",
            },
            {
                "no": 5,
                "id": "ZJ2B",
                "location": "IDM Griya Mustikasari",
                "type": "SmartBox Hitam",
                "modem": "SIM7600",
                "provider": "Telkomsel",
                "sim_number": "6281299988776",
                "cpu_modem_uptime": "730h 05m",
                "cpu_modem_offline": "13h 55m",
                "cpu_modem_success_rate": 99.4,
                "cpu_modem_avg_resp_ms": 160,
                "network_uptime": "724h 40m",
                "network_offline": "19h 20m",
                "network_success_rate": 98.9,
                "network_avg_rsrp": -80,
                "network_avg_temp": 42,
                "trouble_events_count": 4,
                "trouble_last_offline": "19 Oct 2026 11:48",
            },
            {
                "no": 6,
                "id": "Z81C",
                "location": "Alfa Cileungsi",
                "type": "SmartBox Putih",
                "modem": "Quectel EC25-E",
                "provider": "Indosat",
                "sim_number": "6281566677889",
                "cpu_modem_uptime": "696h 10m",
                "cpu_modem_offline": "47h 50m",
                "cpu_modem_success_rate": 94.6,
                "cpu_modem_avg_resp_ms": 280,
                "network_uptime": "696h 50m",
                "network_offline": "47h 10m",
                "network_success_rate": 94.1,
                "network_avg_rsrp": -88,
                "network_avg_temp": 48,
                "trouble_events_count": 6,
                "trouble_last_offline": "23 Oct 2026 16:05",
            },
            {
                "no": 7,
                "id": "Z92D",
                "location": "Alfa Cimanogis",
                "type": "SmartBox Hitam",
                "modem": "Quectel EC200E",
                "provider": "Telkomsel",
                "sim_number": "6281287654321",
                "cpu_modem_uptime": "727h 50m",
                "cpu_modem_offline": "16h 10m",
                "cpu_modem_success_rate": 99.0,
                "cpu_modem_avg_resp_ms": 210,
                "network_uptime": "720h 05m",
                "network_offline": "23h 55m",
                "network_success_rate": 98.3,
                "network_avg_rsrp": -79,
                "network_avg_temp": 43,
                "trouble_events_count": 5,
                "trouble_last_offline": "20 Oct 2026 09:22",
            },
            {
                "no": 8,
                "id": "Z55A",
                "location": "SPBU Cileungsi",
                "type": "SmartBox Hitam",
                "modem": "SIM7600",
                "provider": "Telkomsel",
                "sim_number": "6281387766554",
                "cpu_modem_uptime": "701h 15m",
                "cpu_modem_offline": "42h 45m",
                "cpu_modem_success_rate": 95.1,
                "cpu_modem_avg_resp_ms": 260,
                "network_uptime": "694h 20m",
                "network_offline": "49h 40m",
                "network_success_rate": 94.8,
                "network_avg_rsrp": -91,
                "network_avg_temp": 50,
                "trouble_events_count": 8,
                "trouble_last_offline": "21 Oct 2026 01:14",
            },
            {
                "no": 9,
                "id": "Z11F",
                "location": "Alfa Sawangan",
                "type": "SmartBox Putih",
                "modem": "Quectel EC25-E",
                "provider": "Indosat",
                "sim_number": "6281554433221",
                "cpu_modem_uptime": "686h 20m",
                "cpu_modem_offline": "57h 40m",
                "cpu_modem_success_rate": 92.8,
                "cpu_modem_avg_resp_ms": 330,
                "network_uptime": "673h 10m",
                "network_offline": "70h 50m",
                "network_success_rate": 91.2,
                "network_avg_rsrp": -96,
                "network_avg_temp": 55,
                "trouble_events_count": 9,
                "trouble_last_offline": "26 Oct 2026 05:33",
            },
            {
                "no": 10,
                "id": "Z63K",
                "location": "Alfa Cinere",
                "type": "SmartBox Hitam",
                "modem": "Quectel EC200E",
                "provider": "XL Axiata",
                "sim_number": "6281122339988",
                "cpu_modem_uptime": "653h 50m",
                "cpu_modem_offline": "90h 10m",
                "cpu_modem_success_rate": 88.1,
                "cpu_modem_avg_resp_ms": 410,
                "network_uptime": "650h 30m",
                "network_offline": "93h 30m",
                "network_success_rate": 86.5,
                "network_avg_rsrp": -104,
                "network_avg_temp": 53,
                "trouble_events_count": 11,
                "trouble_last_offline": "22 Oct 2026 18:49",
            },
        ]

        # Expand fleet to 2,000 items
        self._fleet: List[Dict[str, Any]] = list(self._primary_rows)
        providers = ["Telkomsel", "Indosat", "XL Axiata", "Smartfren"]
        modems = ["Quectel EC200E", "Quectel EC25-E", "SIM7600"]
        locations = [
            "Alfa Ciledug Raya",
            "IDM Bintaro Sektor 9",
            "Alfa Ciputat Molek",
            "IDM Cinere Gandul",
            "Alfa Serpong Utara",
            "IDM BSD City Sektor 1",
            "Alfa Pamulang Barat",
            "IDM Karawaci Baru",
        ]

        for i in range(11, 2001):
            is_black = (i % 2 == 1)
            gw_type = "SmartBox Hitam" if is_black else "SmartBox Putih"
            provider = providers[i % len(providers)]
            modem = modems[i % len(modems)]
            loc = f"{locations[i % len(locations)]} #{i}"
            hex_id = f"Z{hex(0x100 + i)[2:].upper()[:3]}"
            sim_prefix = "62812" if provider == "Telkomsel" else ("62815" if provider == "Indosat" else "62817")
            sim_num = f"{sim_prefix}{10000000 + i}"

            up_h = 700 + (i % 40)
            up_m = (i * 7) % 60
            off_h = 744 - up_h
            off_m = (60 - up_m) % 60
            sr = round(90.0 + (i % 100) * 0.098, 1)
            net_sr = round(max(70.0, sr - 0.8), 1)
            resp = 160 + (i % 300)
            rsrp = -75 - (i % 35)
            temp = 40 + (i % 18)
            events = 1 + (i % 12)
            day = 10 + (i % 16)
            hour = (i % 24)
            minute = (i * 3) % 60

            self._fleet.append({
                "no": i,
                "id": hex_id,
                "location": loc,
                "type": gw_type,
                "modem": modem,
                "provider": provider,
                "sim_number": sim_num,
                "cpu_modem_uptime": f"{up_h}h {up_m:02d}m",
                "cpu_modem_offline": f"{off_h}h {off_m:02d}m",
                "cpu_modem_success_rate": sr,
                "cpu_modem_avg_resp_ms": resp,
                "network_uptime": f"{up_h - 2}h {up_m:02d}m",
                "network_offline": f"{off_h + 2}h {off_m:02d}m",
                "network_success_rate": net_sr,
                "network_avg_rsrp": rsrp,
                "network_avg_temp": temp,
                "trouble_events_count": events,
                "trouble_last_offline": f"{day} Oct 2026 {hour:02d}:{minute:02d}",
            })

    def get_report(
        self,
        search: Optional[str] = None,
        gateway_type: Optional[str] = None,
        provider: Optional[str] = None,
        location: Optional[str] = None,
        date_range: Optional[str] = None,
        page: int = 1,
        page_size: int = 10,
    ) -> Dict[str, Any]:
        """Filter & paginate fleet records for Cellular Report"""
        filtered = self._fleet

        if search:
            q = search.lower().strip()
            filtered = [
                g for g in filtered
                if q in g["id"].lower() or q in g["location"].lower() or q in g["sim_number"]
            ]

        if gateway_type and gateway_type not in ["Semua Tipe", "All"]:
            filtered = [g for g in filtered if gateway_type.lower() in g["type"].lower()]

        if provider and provider not in ["Semua Provider", "All"]:
            filtered = [g for g in filtered if provider.lower() in g["provider"].lower()]

        if location and location not in ["Semua Lokasi", "All"]:
            filtered = [g for g in filtered if location.lower() in g["location"].lower()]

        total_items = len(filtered)
        total_pages = max(1, (total_items + page_size - 1) // page_size)
        page = max(1, min(page, total_pages))
        start_idx = (page - 1) * page_size
        end_idx = min(start_idx + page_size, total_items)

        items_slice = filtered[start_idx:end_idx]

        return {
            "gateways": items_slice,
            "pagination": {
                "total_items": total_items,
                "total_pages": total_pages,
                "current_page": page,
                "page_size": page_size,
                "showing_start": start_idx + 1 if total_items > 0 else 0,
                "showing_end": end_idx,
            },
        }

    def export_csv(
        self,
        search: Optional[str] = None,
        gateway_type: Optional[str] = None,
        provider: Optional[str] = None,
        location: Optional[str] = None,
    ) -> str:
        """Export report data to CSV string format"""
        data = self.get_report(
            search=search,
            gateway_type=gateway_type,
            provider=provider,
            location=location,
            page=1,
            page_size=2000,
        )

        output = io.StringIO()
        writer = csv.writer(output)
        
        # Headers
        writer.writerow([
            "No",
            "Gateway ID",
            "Lokasi",
            "Tipe",
            "Modem",
            "Provider",
            "No. SIM Card",
            "CPU-Modem Uptime",
            "CPU-Modem Offline",
            "CPU-Modem Success Rate (%)",
            "CPU-Modem Avg Resp (ms)",
            "Network Uptime",
            "Network Offline",
            "Network Success Rate (%)",
            "Network Avg RSRP (dBm)",
            "Network Avg Suhu (C)",
            "Jumlah Event Gangguan",
            "Terakhir Offline",
        ])

        for g in data["gateways"]:
            writer.writerow([
                g["no"],
                g["id"],
                g["location"],
                g["type"],
                g["modem"],
                g["provider"],
                g["sim_number"],
                g["cpu_modem_uptime"],
                g["cpu_modem_offline"],
                g["cpu_modem_success_rate"],
                g["cpu_modem_avg_resp_ms"],
                g["network_uptime"],
                g["network_offline"],
                g.get("network_success_rate", 98.0),
                g["network_avg_rsrp"],
                g["network_avg_temp"],
                g["trouble_events_count"],
                g["trouble_last_offline"],
            ])

        return output.getvalue()

    def get_gateway_detail(self, gateway_id: str, date_range: Optional[str] = None) -> Dict[str, Any]:
        """
        Detailed performance telemetry for a specific gateway in Cellular Report:
        - Device profile & specifications
        - 10 Key performance indicators (Uptime, Offline, Success Rate, Response Time, RSRP, Temp, etc)
        - Monthly Status Timeline segments
        - Trouble Incident History events
        """
        # Find matching gateway from primary rows or generated fleet
        matched = next((g for g in self._primary_rows if g["id"].lower() == gateway_id.lower()), None)
        
        if not matched:
            # Fallback to generated item
            all_fleet = self._generate_fleet()
            matched = next((g for g in all_fleet if g["id"].lower() == gateway_id.lower()), None)
            
        if not matched:
            matched = self._primary_rows[0] # Default to ZH72

        period_text = date_range or "01 Oct 2026 - 31 Oct 2026"
        is_zh72 = matched["id"] == "ZH72"

        # Trouble events
        if is_zh72:
            trouble_events = [
                {
                    "no": 1,
                    "start_time": "08 Oct 2026 02:14",
                    "end_time": "08 Oct 2026 06:32",
                    "duration": "4h 18m",
                    "cause": "No Service (Provider)",
                },
                {
                    "no": 2,
                    "start_time": "18 Oct 2026 22:11",
                    "end_time": "19 Oct 2026 01:05",
                    "duration": "2h 54m",
                    "cause": "Sinyal Lemah (-110 dBm)",
                },
                {
                    "no": 3,
                    "start_time": "26 Oct 2026 14:32",
                    "end_time": "26 Oct 2026 17:05",
                    "duration": "2h 33m",
                    "cause": "Modem Reboot / No Response",
                },
            ]
            timeline_segments = [
                {"status": "online", "start_pct": 0, "width_pct": 23.5, "label": "Online", "period": "01 Oct - 08 Oct"},
                {"status": "offline", "start_pct": 23.5, "width_pct": 4.5, "label": "Offline (No Service)", "period": "08 Oct 02:14 - 06:32"},
                {"status": "online", "start_pct": 28.0, "width_pct": 22.0, "label": "Online", "period": "08 Oct - 16 Oct"},
                {"status": "no_data", "start_pct": 50.0, "width_pct": 3.0, "label": "No Data (Provider Outage)", "period": "16 Oct 11:00 - 13:00"},
                {"status": "degraded", "start_pct": 53.0, "width_pct": 3.5, "label": "Degraded Signal (-105 dBm)", "period": "17 Oct"},
                {"status": "online", "start_pct": 56.5, "width_pct": 2.0, "label": "Online", "period": "18 Oct"},
                {"status": "offline", "start_pct": 58.5, "width_pct": 3.5, "label": "Offline (Sinyal Lemah)", "period": "18 Oct 22:11 - 19 Oct 01:05"},
                {"status": "online", "start_pct": 62.0, "width_pct": 18.0, "label": "Online", "period": "19 Oct - 25 Oct"},
                {"status": "degraded", "start_pct": 80.0, "width_pct": 2.5, "label": "Degraded Signal", "period": "25 Oct"},
                {"status": "offline", "start_pct": 82.5, "width_pct": 3.5, "label": "Offline (Modem Reboot)", "period": "26 Oct 14:32 - 17:05"},
                {"status": "online", "start_pct": 86.0, "width_pct": 14.0, "label": "Online", "period": "26 Oct - 31 Oct"},
            ]
        else:
            event_count = matched.get("trouble_events_count", 2)
            trouble_events = [
                {
                    "no": 1,
                    "start_time": f"10 Oct 2026 04:12",
                    "end_time": f"10 Oct 2026 07:30",
                    "duration": "3h 18m",
                    "cause": "Network Disconnected (Provider)",
                },
                {
                    "no": 2,
                    "start_time": matched.get("trouble_last_offline", "25 Oct 2026 08:17"),
                    "end_time": "25 Oct 2026 10:45",
                    "duration": "2h 28m",
                    "cause": "Sinyal Lemah / RSRP Low",
                },
            ][:event_count]
            timeline_segments = [
                {"status": "online", "start_pct": 0, "width_pct": 30.0, "label": "Online", "period": "01 Oct - 10 Oct"},
                {"status": "offline", "start_pct": 30.0, "width_pct": 5.0, "label": "Offline", "period": "10 Oct"},
                {"status": "online", "start_pct": 35.0, "width_pct": 42.0, "label": "Online", "period": "10 Oct - 25 Oct"},
                {"status": "degraded", "start_pct": 77.0, "width_pct": 3.0, "label": "Degraded", "period": "25 Oct"},
                {"status": "offline", "start_pct": 80.0, "width_pct": 4.0, "label": "Offline", "period": "25 Oct"},
                {"status": "online", "start_pct": 84.0, "width_pct": 16.0, "label": "Online", "period": "25 Oct - 31 Oct"},
            ]

        # Extract percentages
        cpu_uptime_str = matched.get("cpu_modem_uptime", "728h 15m")
        cpu_offline_str = matched.get("cpu_modem_offline", "15h 45m")
        net_uptime_str = matched.get("network_uptime", "720h 30m")
        net_offline_str = matched.get("network_offline", "23h 30m")
        success_pct = matched.get("cpu_modem_success_rate", 98.5)
        
        # Calculate uptime percentages based on 744 hours (31 days)
        cpu_up_pct = f"{round((728.25 / 744.0) * 100, 1)}%" if is_zh72 else f"{round(success_pct, 1)}%"
        cpu_off_pct = f"{round(100.0 - float(cpu_up_pct.replace('%', '')), 1)}%"
        net_up_pct = "96.8%" if is_zh72 else f"{round(success_pct - 1.7, 1)}%"
        net_off_pct = f"{round(100.0 - float(net_up_pct.replace('%', '')), 1)}%"

        return {
            "id": matched["id"],
            "status": "Online",
            "location": matched["location"],
            "type": matched["type"],
            "modem": matched["modem"],
            "provider": matched["provider"],
            "sim_number": matched["sim_number"],
            "sim_status": "Aktif",
            "ip_address": f"10.10.{hash(matched['id']) % 89 + 10}.15" if not is_zh72 else "10.10.72.15",
            "period": period_text,
            "period_hours": "(744 jam)",
            "cpu_modem_uptime": cpu_uptime_str,
            "cpu_modem_uptime_pct": cpu_up_pct,
            "cpu_modem_offline": cpu_offline_str,
            "cpu_modem_offline_pct": cpu_off_pct,
            "success_rate": f"{success_pct}%",
            "success_rate_checks": "(21,456 / 21,780 check)" if is_zh72 else "(20,980 / 21,780 check)",
            "avg_response_time": f"{matched.get('cpu_modem_avg_resp_ms', 220)} ms",
            "network_uptime": net_uptime_str,
            "network_uptime_pct": net_up_pct,
            "network_offline": net_offline_str,
            "network_offline_pct": net_off_pct,
            "avg_rsrp": f"{matched.get('network_avg_rsrp', -78)} dBm",
            "avg_modem_temp": f"{matched.get('network_avg_temp', 45)}°C",
            "temp_range": "(Min 32°C | Max 62°C)",
            "total_gangguan": f"{matched.get('trouble_events_count', 3)} event",
            "timeline_segments": timeline_segments,
            "trouble_events": trouble_events,
        }


# Singleton service instance
cellular_report_service = CellularReportService()

