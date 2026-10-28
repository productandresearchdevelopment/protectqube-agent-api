from typing import Dict, Any, List, Optional
import io
import csv


class HealthReportService:
    """
    Service layer for System Health Historical Telemetry Report:
    SBC telemetry, CPU/RAM/SD load analytics, SD Card endurance wear-out health,
    system temperature spikes, and 24/7 uptime stability.
    """

    def __init__(self):
        # 10 primary rows from user's screenshot
        self._primary_rows: List[Dict[str, Any]] = [
            {
                "no": 1,
                "id": "ZH72",
                "location": "Alfa H Sapri P. Aren",
                "type": "SmartBox Hitam",
                "cpu_avg": 32,
                "cpu_max": 78,
                "cpu_gt_80_duration": "5h 20m",
                "ram_avg": 43,
                "ram_max": 81,
                "ram_gt_80_duration": "2h 10m",
                "sd_avg": 68,
                "sd_max": 82,
                "sd_gt_90_duration": "-",
                "sd_health_status": "Good",
                "sd_life_pct": 92,
                "temp_avg": 45,
                "temp_max": 62,
                "uptime_duration": "720h 15m",
                "uptime_pct": 96.8,
                "jumlah_event": 12,
            },
            {
                "no": 2,
                "id": "ZV91",
                "location": "IDM Graha Moris",
                "type": "SmartBox Putih",
                "cpu_avg": 48,
                "cpu_max": 92,
                "cpu_gt_80_duration": "28h 30m",
                "ram_avg": 61,
                "ram_max": 95,
                "ram_gt_80_duration": "32h 10m",
                "sd_avg": 84,
                "sd_max": 96,
                "sd_gt_90_duration": "18h 45m",
                "sd_health_status": "Caution",
                "sd_life_pct": 76,
                "temp_avg": 52,
                "temp_max": 78,
                "uptime_duration": "689h 10m",
                "uptime_pct": 92.6,
                "jumlah_event": 28,
            },
            {
                "no": 3,
                "id": "697D",
                "location": "Alfa Ahmad Dahlan",
                "type": "SmartBox Hitam",
                "cpu_avg": 22,
                "cpu_max": 65,
                "cpu_gt_80_duration": "0h 10m",
                "ram_avg": 36,
                "ram_max": 70,
                "ram_gt_80_duration": "1h 05m",
                "sd_avg": 54,
                "sd_max": 70,
                "sd_gt_90_duration": "-",
                "sd_health_status": "Good",
                "sd_life_pct": 95,
                "temp_avg": 41,
                "temp_max": 58,
                "uptime_duration": "731h 20m",
                "uptime_pct": 99.2,
                "jumlah_event": 6,
            },
            {
                "no": 4,
                "id": "ZR4R",
                "location": "Alfa Ruko Metland",
                "type": "SmartBox Putih",
                "cpu_avg": 65,
                "cpu_max": 98,
                "cpu_gt_80_duration": "72h 40m",
                "ram_avg": 72,
                "ram_max": 96,
                "ram_gt_80_duration": "68h 15m",
                "sd_avg": 91,
                "sd_max": 98,
                "sd_gt_90_duration": "54h 20m",
                "sd_health_status": "Caution",
                "sd_life_pct": 68,
                "temp_avg": 58,
                "temp_max": 85,
                "uptime_duration": "608h 30m",
                "uptime_pct": 87.4,
                "jumlah_event": 52,
            },
            {
                "no": 5,
                "id": "ZJ2B",
                "location": "IDM Griya Mustika",
                "type": "SmartBox Hitam",
                "cpu_avg": 28,
                "cpu_max": 70,
                "cpu_gt_80_duration": "2h 15m",
                "ram_avg": 46,
                "ram_max": 75,
                "ram_gt_80_duration": "3h 40m",
                "sd_avg": 63,
                "sd_max": 82,
                "sd_gt_90_duration": "-",
                "sd_health_status": "Good",
                "sd_life_pct": 90,
                "temp_avg": 42,
                "temp_max": 60,
                "uptime_duration": "730h 05m",
                "uptime_pct": 99.1,
                "jumlah_event": 8,
            },
            {
                "no": 6,
                "id": "Z81C",
                "location": "Alfa Cileungsi",
                "type": "SmartBox Putih",
                "cpu_avg": 51,
                "cpu_max": 88,
                "cpu_gt_80_duration": "18h 20m",
                "ram_avg": 58,
                "ram_max": 90,
                "ram_gt_80_duration": "16h 35m",
                "sd_avg": 77,
                "sd_max": 94,
                "sd_gt_90_duration": "12h 10m",
                "sd_health_status": "Caution",
                "sd_life_pct": 72,
                "temp_avg": 48,
                "temp_max": 72,
                "uptime_duration": "696h 10m",
                "uptime_pct": 94.8,
                "jumlah_event": 21,
            },
            {
                "no": 7,
                "id": "Z92D",
                "location": "Alfa Cimanogis",
                "type": "SmartBox Hitam",
                "cpu_avg": 35,
                "cpu_max": 80,
                "cpu_gt_80_duration": "6h 50m",
                "ram_avg": 49,
                "ram_max": 78,
                "ram_gt_80_duration": "4h 10m",
                "sd_avg": 49,
                "sd_max": 68,
                "sd_gt_90_duration": "-",
                "sd_health_status": "Good",
                "sd_life_pct": 94,
                "temp_avg": 43,
                "temp_max": 63,
                "uptime_duration": "727h 50m",
                "uptime_pct": 99.0,
                "jumlah_event": 7,
            },
            {
                "no": 8,
                "id": "Z55A",
                "location": "SPBU Cileungsi",
                "type": "SmartBox Hitam",
                "cpu_avg": 41,
                "cpu_max": 85,
                "cpu_gt_80_duration": "12h 10m",
                "ram_avg": 55,
                "ram_max": 88,
                "ram_gt_80_duration": "10h 20m",
                "sd_avg": 71,
                "sd_max": 90,
                "sd_gt_90_duration": "6h 35m",
                "sd_health_status": "Good",
                "sd_life_pct": 89,
                "temp_avg": 50,
                "temp_max": 73,
                "uptime_duration": "701h 15m",
                "uptime_pct": 95.3,
                "jumlah_event": 18,
            },
            {
                "no": 9,
                "id": "Z11F",
                "location": "Alfa Sawangan",
                "type": "SmartBox Putih",
                "cpu_avg": 62,
                "cpu_max": 96,
                "cpu_gt_80_duration": "45h 30m",
                "ram_avg": 68,
                "ram_max": 93,
                "ram_gt_80_duration": "38h 20m",
                "sd_avg": 88,
                "sd_max": 97,
                "sd_gt_90_duration": "30h 10m",
                "sd_health_status": "Poor",
                "sd_life_pct": 45,
                "temp_avg": 55,
                "temp_max": 78,
                "uptime_duration": "686h 20m",
                "uptime_pct": 92.8,
                "jumlah_event": 35,
            },
            {
                "no": 10,
                "id": "Z63K",
                "location": "Alfa Cinere",
                "type": "SmartBox Hitam",
                "cpu_avg": 39,
                "cpu_max": 82,
                "cpu_gt_80_duration": "8h 45m",
                "ram_avg": 52,
                "ram_max": 81,
                "ram_gt_80_duration": "6h 10m",
                "sd_avg": 78,
                "sd_max": 95,
                "sd_gt_90_duration": "20h 30m",
                "sd_health_status": "Caution",
                "sd_life_pct": 70,
                "temp_avg": 53,
                "temp_max": 82,
                "uptime_duration": "653h 50m",
                "uptime_pct": 88.1,
                "jumlah_event": 40,
            },
        ]

        # Expand fleet to 2,000 items
        self._fleet: List[Dict[str, Any]] = list(self._primary_rows)
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
            loc = f"{locations[i % len(locations)]} #{i}"
            hex_id = f"Z{hex(0x100 + i)[2:].upper()[:3]}"

            c_avg = 25 + (i % 45)
            c_max = min(99, c_avg + 25 + (i % 20))
            c_gt = f"{i % 30}h {(i * 5) % 60:02d}m" if c_max >= 80 else "-"

            r_avg = 35 + (i % 40)
            r_max = min(99, r_avg + 20 + (i % 20))
            r_gt = f"{i % 25}h {(i * 7) % 60:02d}m" if r_max >= 80 else "-"

            s_avg = 45 + (i % 45)
            s_max = min(99, s_avg + 15 + (i % 15))
            s_gt = f"{i % 18}h {(i * 3) % 60:02d}m" if s_max >= 90 else "-"

            life = max(30, 98 - (i % 60))
            if life >= 85:
                status = "Good"
            elif life >= 60:
                status = "Caution"
            else:
                status = "Poor"

            t_avg = 40 + (i % 18)
            t_max = t_avg + 15 + (i % 15)

            up_h = 670 + (i % 60)
            up_m = (i * 9) % 60
            up_pct = round(88.0 + (i % 100) * 0.118, 1)

            events = 2 + (i % 45)

            self._fleet.append({
                "no": i,
                "id": hex_id,
                "location": loc,
                "type": gw_type,
                "cpu_avg": c_avg,
                "cpu_max": c_max,
                "cpu_gt_80_duration": c_gt,
                "ram_avg": r_avg,
                "ram_max": r_max,
                "ram_gt_80_duration": r_gt,
                "sd_avg": s_avg,
                "sd_max": s_max,
                "sd_gt_90_duration": s_gt,
                "sd_health_status": status,
                "sd_life_pct": life,
                "temp_avg": t_avg,
                "temp_max": t_max,
                "uptime_duration": f"{up_h}h {up_m:02d}m",
                "uptime_pct": up_pct,
                "jumlah_event": events,
            })

    def get_report(
        self,
        search: Optional[str] = None,
        gateway_type: Optional[str] = None,
        location: Optional[str] = None,
        date_range: Optional[str] = None,
        page: int = 1,
        page_size: int = 10,
    ) -> Dict[str, Any]:
        """Filter & paginate fleet records for System Health Report"""
        filtered = self._fleet

        if search:
            q = search.lower().strip()
            filtered = [
                g for g in filtered
                if q in g["id"].lower() or q in g["location"].lower()
            ]

        if gateway_type and gateway_type not in ["Semua Tipe", "All"]:
            filtered = [g for g in filtered if gateway_type.lower() in g["type"].lower()]

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
        location: Optional[str] = None,
    ) -> str:
        """Export System Health report data to CSV string format"""
        data = self.get_report(
            search=search,
            gateway_type=gateway_type,
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
            "CPU Avg (%)",
            "CPU Max (%)",
            "CPU > 80% (jam)",
            "RAM Avg (%)",
            "RAM Max (%)",
            "RAM > 80% (jam)",
            "SD Card Avg (%)",
            "SD Card Max (%)",
            "SD Card > 90% (jam)",
            "SD Card Status",
            "SD Card Life (%)",
            "Suhu Sistem Avg (C)",
            "Suhu Sistem Max (C)",
            "Uptime Durasi",
            "Uptime Persentase (%)",
            "Jumlah Event",
        ])

        for g in data["gateways"]:
            writer.writerow([
                g["no"],
                g["id"],
                g["location"],
                g["type"],
                g["cpu_avg"],
                g["cpu_max"],
                g["cpu_gt_80_duration"],
                g["ram_avg"],
                g["ram_max"],
                g["ram_gt_80_duration"],
                g["sd_avg"],
                g["sd_max"],
                g["sd_gt_90_duration"],
                g["sd_health_status"],
                g["sd_life_pct"],
                g["temp_avg"],
                g["temp_max"],
                g["uptime_duration"],
                g["uptime_pct"],
                g["jumlah_event"],
            ])

        return output.getvalue()

    def get_gateway_detail(self, gateway_id: str, date_range: Optional[str] = None) -> Dict[str, Any]:
        """
        Detailed performance telemetry for a specific gateway in System Health Report:
        - Device profile & SBC specs (CPU, RAM, SD, Modem)
        - 7 Key performance indicators (Uptime, Avg CPU, Avg RAM, SD Usage, SD Health, Suhu)
        - 3 Historical Line charts (CPU %, RAM %, SD Card %)
        - Multi-track timeline (CPU, RAM, SD Card, Suhu)
        - Event History with categories, values & descriptions
        """
        matched = next((g for g in self._primary_rows if g["id"].lower() == gateway_id.lower()), None)
        if not matched:
            all_fleet = self._generate_fleet()
            matched = next((g for g in all_fleet if g["id"].lower() == gateway_id.lower()), None)
        if not matched:
            matched = self._primary_rows[0]

        period_text = date_range or "01 Oct 2026 - 31 Oct 2026"
        is_zh72 = matched["id"] == "ZH72"

        if is_zh72:
            events = [
                {
                    "no": 1,
                    "start_time": "03 Oct 2026 14:20",
                    "end_time": "03 Oct 2026 16:10",
                    "duration": "1h 50m",
                    "category": "CPU High",
                    "value": "92%",
                    "description": "Proses tinggi (vision)",
                },
                {
                    "no": 2,
                    "start_time": "09 Oct 2026 09:15",
                    "end_time": "09 Oct 2026 12:30",
                    "duration": "3h 15m",
                    "category": "SD Usage High",
                    "value": "91%",
                    "description": "Storage mendekati penuh",
                },
                {
                    "no": 3,
                    "start_time": "16 Oct 2026 22:10",
                    "end_time": "17 Oct 2026 00:05",
                    "duration": "1h 55m",
                    "category": "RAM High",
                    "value": "88%",
                    "description": "Memory leak",
                },
                {
                    "no": 4,
                    "start_time": "23 Oct 2026 05:40",
                    "end_time": "23 Oct 2026 07:20",
                    "duration": "1h 40m",
                    "category": "Suhu High",
                    "value": "62°C",
                    "description": "Suhu di atas threshold",
                },
                {
                    "no": 5,
                    "start_time": "26 Oct 2026 11:10",
                    "end_time": "26 Oct 2026 12:05",
                    "duration": "55m",
                    "category": "CPU High",
                    "value": "85%",
                    "description": "Proses tracking",
                },
                {
                    "no": 6,
                    "start_time": "29 Oct 2026 18:25",
                    "end_time": "29 Oct 2026 20:30",
                    "duration": "2h 05m",
                    "category": "SD Usage High",
                    "value": "94%",
                    "description": "Pembersihan diperlukan",
                },
            ]
            timeline_tracks = [
                {
                    "track_name": "CPU",
                    "segments": [
                        {"status": "normal", "start_pct": 0, "width_pct": 8.0, "label": "Normal", "period": "01 Oct - 03 Oct"},
                        {"status": "cpu_high", "start_pct": 8.0, "width_pct": 3.5, "label": "CPU High (92%)", "period": "03 Oct 14:20 - 16:10"},
                        {"status": "normal", "start_pct": 11.5, "width_pct": 71.0, "label": "Normal", "period": "03 Oct - 26 Oct"},
                        {"status": "cpu_high", "start_pct": 82.5, "width_pct": 3.5, "label": "CPU High (85%)", "period": "26 Oct 11:10 - 12:05"},
                        {"status": "normal", "start_pct": 86.0, "width_pct": 14.0, "label": "Normal", "period": "26 Oct - 31 Oct"},
                    ],
                },
                {
                    "track_name": "RAM",
                    "segments": [
                        {"status": "normal", "start_pct": 0, "width_pct": 50.0, "label": "Normal", "period": "01 Oct - 16 Oct"},
                        {"status": "ram_high", "start_pct": 50.0, "width_pct": 4.0, "label": "RAM High (88%)", "period": "16 Oct 22:10 - 17 Oct 00:05"},
                        {"status": "normal", "start_pct": 54.0, "width_pct": 46.0, "label": "Normal", "period": "17 Oct - 31 Oct"},
                    ],
                },
                {
                    "track_name": "SD Card",
                    "segments": [
                        {"status": "normal", "start_pct": 0, "width_pct": 28.0, "label": "Normal", "period": "01 Oct - 09 Oct"},
                        {"status": "sd_high", "start_pct": 28.0, "width_pct": 4.0, "label": "SD Usage High (91%)", "period": "09 Oct 09:15 - 12:30"},
                        {"status": "normal", "start_pct": 32.0, "width_pct": 60.0, "label": "Normal", "period": "09 Oct - 29 Oct"},
                        {"status": "sd_high", "start_pct": 92.0, "width_pct": 3.5, "label": "SD Usage High (94%)", "period": "29 Oct 18:25 - 20:30"},
                        {"status": "normal", "start_pct": 95.5, "width_pct": 4.5, "label": "Normal", "period": "29 Oct - 31 Oct"},
                    ],
                },
                {
                    "track_name": "Suhu",
                    "segments": [
                        {"status": "normal", "start_pct": 0, "width_pct": 12.0, "label": "Normal", "period": "01 Oct - 04 Oct"},
                        {"status": "suhu_high", "start_pct": 12.0, "width_pct": 3.5, "label": "Suhu 58°C", "period": "04-05 Oct"},
                        {"status": "normal", "start_pct": 15.5, "width_pct": 57.0, "label": "Normal", "period": "05 Oct - 23 Oct"},
                        {"status": "suhu_high", "start_pct": 72.5, "width_pct": 4.0, "label": "Suhu High (62°C)", "period": "23 Oct 05:40 - 07:20"},
                        {"status": "normal", "start_pct": 76.5, "width_pct": 23.5, "label": "Normal", "period": "23 Oct - 31 Oct"},
                    ],
                },
            ]
        else:
            events = [
                {
                    "no": 1,
                    "start_time": "12 Oct 2026 14:10",
                    "end_time": "12 Oct 2026 16:30",
                    "duration": "2h 20m",
                    "category": "CPU High",
                    "value": f"{matched.get('cpu_max', 85)}%",
                    "description": "Background batch task",
                },
                {
                    "no": 2,
                    "start_time": "20 Oct 2026 09:00",
                    "end_time": "20 Oct 2026 11:25",
                    "duration": "2h 25m",
                    "category": "RAM High",
                    "value": f"{matched.get('ram_max', 88)}%",
                    "description": "Peak service usage",
                },
            ]
            timeline_tracks = [
                {
                    "track_name": "CPU",
                    "segments": [
                        {"status": "normal", "start_pct": 0, "width_pct": 38.0, "label": "Normal", "period": "01 Oct - 12 Oct"},
                        {"status": "cpu_high", "start_pct": 38.0, "width_pct": 4.0, "label": "CPU High", "period": "12 Oct"},
                        {"status": "normal", "start_pct": 42.0, "width_pct": 58.0, "label": "Normal", "period": "12 Oct - 31 Oct"},
                    ],
                },
                {
                    "track_name": "RAM",
                    "segments": [
                        {"status": "normal", "start_pct": 0, "width_pct": 64.0, "label": "Normal", "period": "01 Oct - 20 Oct"},
                        {"status": "ram_high", "start_pct": 64.0, "width_pct": 4.0, "label": "RAM High", "period": "20 Oct"},
                        {"status": "normal", "start_pct": 68.0, "width_pct": 32.0, "label": "Normal", "period": "20 Oct - 31 Oct"},
                    ],
                },
                {
                    "track_name": "SD Card",
                    "segments": [
                        {"status": "normal", "start_pct": 0, "width_pct": 100.0, "label": "Normal", "period": "01 Oct - 31 Oct"},
                    ],
                },
                {
                    "track_name": "Suhu",
                    "segments": [
                        {"status": "normal", "start_pct": 0, "width_pct": 100.0, "label": "Normal", "period": "01 Oct - 31 Oct"},
                    ],
                },
            ]

        # Historical trend data points
        cpu_trend = [
            {"date": "01 Oct", "value": 26},
            {"date": "03 Oct", "value": 34},
            {"date": "05 Oct", "value": 29},
            {"date": "08 Oct", "value": 35},
            {"date": "10 Oct", "value": 31},
            {"date": "12 Oct", "value": 38},
            {"date": "15 Oct", "value": 32},
            {"date": "18 Oct", "value": 78},
            {"date": "20 Oct", "value": 42},
            {"date": "22 Oct", "value": 30},
            {"date": "25 Oct", "value": 28},
            {"date": "28 Oct", "value": 33},
            {"date": "31 Oct", "value": 36},
        ]
        ram_trend = [
            {"date": "01 Oct", "value": 40},
            {"date": "03 Oct", "value": 45},
            {"date": "05 Oct", "value": 42},
            {"date": "08 Oct", "value": 47},
            {"date": "10 Oct", "value": 43},
            {"date": "12 Oct", "value": 49},
            {"date": "15 Oct", "value": 44},
            {"date": "18 Oct", "value": 52},
            {"date": "20 Oct", "value": 38},
            {"date": "22 Oct", "value": 43},
            {"date": "25 Oct", "value": 56},
            {"date": "28 Oct", "value": 41},
            {"date": "31 Oct", "value": 47},
        ]
        sd_trend = [
            {"date": "01 Oct", "value": 65},
            {"date": "03 Oct", "value": 64},
            {"date": "05 Oct", "value": 67},
            {"date": "08 Oct", "value": 71},
            {"date": "10 Oct", "value": 68},
            {"date": "12 Oct", "value": 70},
            {"date": "15 Oct", "value": 69},
            {"date": "18 Oct", "value": 73},
            {"date": "20 Oct", "value": 82},
            {"date": "22 Oct", "value": 67},
            {"date": "25 Oct", "value": 72},
            {"date": "28 Oct", "value": 68},
            {"date": "31 Oct", "value": 74},
        ]

        raw_uptime = matched.get("uptime_pct", 96.8)
        try:
            up_float = float(str(raw_uptime).replace("%", ""))
        except Exception:
            up_float = 96.8

        down_float = round(100.0 - up_float, 2)
        total_hrs = 744.0
        up_hrs = total_hrs * (up_float / 100.0)
        down_hrs = total_hrs - up_hrs

        up_h = int(up_hrs)
        up_m = int(round((up_hrs - up_h) * 60))
        down_h = int(down_hrs)
        down_m = int(round((down_hrs - down_h) * 60))

        sla_status_str = "Met" if up_float >= 99.5 else "Breach"

        return {
            "id": matched["id"],
            "status": "Online",
            "location": matched["location"],
            "type": matched["type"],
            "cpu_spec": "RK3328 (6 TOPS)",
            "ram_spec": "8 GB",
            "sd_spec": "128 GB",
            "modem_spec": "Quectel EC200E",
            "provider_spec": "Telkomsel (6281212345678)",
            "period": period_text,
            "period_hours": "(744 jam)",
            "uptime_duration": f"{up_h}h {up_m}m" if "uptime_duration" not in matched else matched["uptime_duration"],
            "uptime_pct": f"{up_float}%",
            "downtime_duration": f"{down_h}h {down_m}m",
            "downtime_pct": f"{down_float}%",
            "sla_target": "99.5%",
            "sla_target_hours": "740h 17m",
            "sla_status": sla_status_str,
            "sla_downtime_allowed": "3h 43m",
            "cpu_avg": matched.get("cpu_avg", 32),
            "cpu_max": matched.get("cpu_max", 78),
            "ram_avg": matched.get("ram_avg", 43),
            "ram_max": matched.get("ram_max", 81),
            "sd_avg": matched.get("sd_avg", 68),
            "sd_max": matched.get("sd_max", 82),
            "sd_health_status": matched.get("sd_health_status", "Good"),
            "sd_life_pct": matched.get("sd_life_pct", 92),
            "temp_avg": matched.get("temp_avg", 45),
            "temp_max": matched.get("temp_max", 62),
            "cpu_trend": cpu_trend,
            "ram_trend": ram_trend,
            "sd_trend": sd_trend,
            "timeline_tracks": timeline_tracks,
            "events": events,
        }


# Singleton service instance
health_report_service = HealthReportService()

