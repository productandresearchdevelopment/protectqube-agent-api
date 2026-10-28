from typing import Dict, Any, List, Optional
import io
import csv


class DVRReportService:
    """
    Service layer for DVR Historical Telemetry Report:
    Fleet DVR/NVR models, CPU-DVR communication SLA, Camera channel health,
    Recording status breakdown, Storage utilization, and incident trouble events.
    """

    def __init__(self):
        # 10 primary rows from user's screenshot
        self._primary_rows: List[Dict[str, Any]] = [
            {
                "no": 1,
                "id": "ZH72",
                "location": "Alfa H Sapri Pondok Aren",
                "type": "SmartBox Hitam",
                "dvr_model": "Hikvision DS-7616NI",
                "cpu_dvr_uptime": "720h 15m",
                "cpu_dvr_offline": "23h 45m",
                "cpu_dvr_success_rate": 98.8,
                "cpu_dvr_avg_resp_ms": 180,
                "kamera_total": 4,
                "kamera_online": 4,
                "kamera_no_video": 0,
                "kamera_offline": 0,
                "rec_uptime": "708h 20m",
                "rec_tidak_merekam": "12h 30m",
                "rec_error": "3h 10m",
                "storage_kapasitas": "4 TB",
                "storage_terpakai_pct": 68,
                "storage_rata_rata": "2.7 TB",
                "jumlah_event": 12,
                "terakhir_offline": "26 Oct 2026 14:32",
            },
            {
                "no": 2,
                "id": "ZV91",
                "location": "IDM Graha Morris Tambun",
                "type": "SmartBox Putih",
                "dvr_model": "Dahua NVRS216",
                "cpu_dvr_uptime": "689h 10m",
                "cpu_dvr_offline": "54h 50m",
                "cpu_dvr_success_rate": 92.6,
                "cpu_dvr_avg_resp_ms": 320,
                "kamera_total": 8,
                "kamera_online": 7,
                "kamera_no_video": 1,
                "kamera_offline": 0,
                "rec_uptime": "670h 40m",
                "rec_tidak_merekam": "40h 10m",
                "rec_error": "33h 10m",
                "storage_kapasitas": "4 TB",
                "storage_terpakai_pct": 82,
                "storage_rata_rata": "3.3 TB",
                "jumlah_event": 28,
                "terakhir_offline": "25 Oct 2026 08:17",
            },
            {
                "no": 3,
                "id": "697D",
                "location": "Alfa Ahmad Dahlan III",
                "type": "SmartBox Hitam",
                "dvr_model": "Hikvision DS-7608NI",
                "cpu_dvr_uptime": "731h 20m",
                "cpu_dvr_offline": "12h 40m",
                "cpu_dvr_success_rate": 99.2,
                "cpu_dvr_avg_resp_ms": 160,
                "kamera_total": 4,
                "kamera_online": 4,
                "kamera_no_video": 0,
                "kamera_offline": 0,
                "rec_uptime": "728h 10m",
                "rec_tidak_merekam": "15h 00m",
                "rec_error": "45m",
                "storage_kapasitas": "2 TB",
                "storage_terpakai_pct": 54,
                "storage_rata_rata": "1.1 TB",
                "jumlah_event": 6,
                "terakhir_offline": "18 Oct 2026 22:11",
            },
            {
                "no": 4,
                "id": "ZR4R",
                "location": "Alfa Ruko Metland",
                "type": "SmartBox Putih",
                "dvr_model": "Hikvision DS-7616NI",
                "cpu_dvr_uptime": "608h 30m",
                "cpu_dvr_offline": "135h 30m",
                "cpu_dvr_success_rate": 87.4,
                "cpu_dvr_avg_resp_ms": 420,
                "kamera_total": 8,
                "kamera_online": 6,
                "kamera_no_video": 1,
                "kamera_offline": 1,
                "rec_uptime": "580h 20m",
                "rec_tidak_merekam": "120h 10m",
                "rec_error": "43h 30m",
                "storage_kapasitas": "4 TB",
                "storage_terpakai_pct": 91,
                "storage_rata_rata": "3.6 TB",
                "jumlah_event": 52,
                "terakhir_offline": "24 Oct 2026 03:10",
            },
            {
                "no": 5,
                "id": "ZJ2B",
                "location": "IDM Griya Mustikasari",
                "type": "SmartBox Hitam",
                "dvr_model": "Dahua NVRS216",
                "cpu_dvr_uptime": "730h 05m",
                "cpu_dvr_offline": "13h 55m",
                "cpu_dvr_success_rate": 99.1,
                "cpu_dvr_avg_resp_ms": 200,
                "kamera_total": 6,
                "kamera_online": 6,
                "kamera_no_video": 0,
                "kamera_offline": 0,
                "rec_uptime": "726h 40m",
                "rec_tidak_merekam": "16h 30m",
                "rec_error": "50m",
                "storage_kapasitas": "4 TB",
                "storage_terpakai_pct": 63,
                "storage_rata_rata": "2.5 TB",
                "jumlah_event": 8,
                "terakhir_offline": "19 Oct 2026 11:48",
            },
            {
                "no": 6,
                "id": "Z81C",
                "location": "Alfa Cileungsi",
                "type": "SmartBox Putih",
                "dvr_model": "Hikvision DS-7608NI",
                "cpu_dvr_uptime": "696h 10m",
                "cpu_dvr_offline": "47h 50m",
                "cpu_dvr_success_rate": 94.8,
                "cpu_dvr_avg_resp_ms": 310,
                "kamera_total": 4,
                "kamera_online": 3,
                "kamera_no_video": 1,
                "kamera_offline": 0,
                "rec_uptime": "680h 20m",
                "rec_tidak_merekam": "58h 30m",
                "rec_error": "5h 10m",
                "storage_kapasitas": "2 TB",
                "storage_terpakai_pct": 77,
                "storage_rata_rata": "1.5 TB",
                "jumlah_event": 21,
                "terakhir_offline": "23 Oct 2026 16:05",
            },
            {
                "no": 7,
                "id": "Z92D",
                "location": "Alfa Cimanogis",
                "type": "SmartBox Hitam",
                "dvr_model": "Dahua NVRS216",
                "cpu_dvr_uptime": "727h 50m",
                "cpu_dvr_offline": "16h 10m",
                "cpu_dvr_success_rate": 99.0,
                "cpu_dvr_avg_resp_ms": 190,
                "kamera_total": 8,
                "kamera_online": 8,
                "kamera_no_video": 0,
                "kamera_offline": 0,
                "rec_uptime": "720h 30m",
                "rec_tidak_merekam": "22h 50m",
                "rec_error": "55m",
                "storage_kapasitas": "4 TB",
                "storage_terpakai_pct": 49,
                "storage_rata_rata": "1.9 TB",
                "jumlah_event": 7,
                "terakhir_offline": "20 Oct 2026 09:22",
            },
            {
                "no": 8,
                "id": "Z55A",
                "location": "SPBU Cileungsi",
                "type": "SmartBox Hitam",
                "dvr_model": "Hikvision DS-7616NI",
                "cpu_dvr_uptime": "701h 15m",
                "cpu_dvr_offline": "42h 45m",
                "cpu_dvr_success_rate": 95.3,
                "cpu_dvr_avg_resp_ms": 280,
                "kamera_total": 8,
                "kamera_online": 7,
                "kamera_no_video": 1,
                "kamera_offline": 0,
                "rec_uptime": "690h 10m",
                "rec_tidak_merekam": "48h 30m",
                "rec_error": "5h 20m",
                "storage_kapasitas": "4 TB",
                "storage_terpakai_pct": 71,
                "storage_rata_rata": "2.8 TB",
                "jumlah_event": 18,
                "terakhir_offline": "21 Oct 2026 01:14",
            },
            {
                "no": 9,
                "id": "Z11F",
                "location": "Alfa Sawangan",
                "type": "SmartBox Putih",
                "dvr_model": "Dahua NVRS216",
                "cpu_dvr_uptime": "686h 20m",
                "cpu_dvr_offline": "57h 40m",
                "cpu_dvr_success_rate": 92.8,
                "cpu_dvr_avg_resp_ms": 350,
                "kamera_total": 4,
                "kamera_online": 4,
                "kamera_no_video": 0,
                "kamera_offline": 0,
                "rec_uptime": "671h 00m",
                "rec_tidak_merekam": "60h 20m",
                "rec_error": "12h 40m",
                "storage_kapasitas": "2 TB",
                "storage_terpakai_pct": 88,
                "storage_rata_rata": "1.8 TB",
                "jumlah_event": 35,
                "terakhir_offline": "26 Oct 2026 05:33",
            },
            {
                "no": 10,
                "id": "Z63K",
                "location": "Alfa Cinere",
                "type": "SmartBox Hitam",
                "dvr_model": "Hikvision DS-7608NI",
                "cpu_dvr_uptime": "653h 50m",
                "cpu_dvr_offline": "90h 10m",
                "cpu_dvr_success_rate": 88.1,
                "cpu_dvr_avg_resp_ms": 410,
                "kamera_total": 8,
                "kamera_online": 5,
                "kamera_no_video": 2,
                "kamera_offline": 1,
                "rec_uptime": "620h 30m",
                "rec_tidak_merekam": "95h 10m",
                "rec_error": "28h 20m",
                "storage_kapasitas": "4 TB",
                "storage_terpakai_pct": 78,
                "storage_rata_rata": "3.1 TB",
                "jumlah_event": 40,
                "terakhir_offline": "22 Oct 2026 18:49",
            },
        ]

        # Expand fleet to 2,000 items
        self._fleet: List[Dict[str, Any]] = list(self._primary_rows)
        dvr_models = [
            "Hikvision DS-7616NI",
            "Dahua NVRS216",
            "Hikvision DS-7608NI",
            "Dahua NVR4108HS-8P",
            "Uniview NVR301-08S3",
        ]
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
            model = dvr_models[i % len(dvr_models)]
            loc = f"{locations[i % len(locations)]} #{i}"
            hex_id = f"Z{hex(0x100 + i)[2:].upper()[:3]}"

            up_h = 690 + (i % 45)
            up_m = (i * 9) % 60
            off_h = 744 - up_h
            off_m = (60 - up_m) % 60
            sr = round(91.0 + (i % 85) * 0.098, 1)
            resp = 160 + (i % 280)
            
            tot_cam = 4 if i % 3 == 0 else (6 if i % 5 == 0 else 8)
            no_vid = 1 if i % 4 == 0 else 0
            off_cam = 1 if i % 9 == 0 else 0
            on_cam = max(0, tot_cam - no_vid - off_cam)

            rec_up_h = up_h - (i % 8)
            rec_up_m = up_m
            rec_off_h = off_h + (i % 8)
            rec_err_h = 1 + (i % 15)
            
            cap = "4 TB" if tot_cam >= 8 else "2 TB"
            terpakai = 50 + (i % 44)
            rata_rata = f"{round((int(cap[0]) * terpakai) / 100, 1)} TB"

            events = 2 + (i % 38)
            day = 10 + (i % 16)
            hour = (i % 24)
            minute = (i * 3) % 60

            self._fleet.append({
                "no": i,
                "id": hex_id,
                "location": loc,
                "type": gw_type,
                "dvr_model": model,
                "cpu_dvr_uptime": f"{up_h}h {up_m:02d}m",
                "cpu_dvr_offline": f"{off_h}h {off_m:02d}m",
                "cpu_dvr_success_rate": sr,
                "cpu_dvr_avg_resp_ms": resp,
                "kamera_total": tot_cam,
                "kamera_online": on_cam,
                "kamera_no_video": no_vid,
                "kamera_offline": off_cam,
                "rec_uptime": f"{rec_up_h}h {rec_up_m:02d}m",
                "rec_tidak_merekam": f"{rec_off_h}h 20m",
                "rec_error": f"{rec_err_h}h 10m",
                "storage_kapasitas": cap,
                "storage_terpakai_pct": terpakai,
                "storage_rata_rata": rata_rata,
                "jumlah_event": events,
                "terakhir_offline": f"{day} Oct 2026 {hour:02d}:{minute:02d}",
            })

    def get_report(
        self,
        search: Optional[str] = None,
        gateway_type: Optional[str] = None,
        dvr_brand: Optional[str] = None,
        location: Optional[str] = None,
        date_range: Optional[str] = None,
        page: int = 1,
        page_size: int = 10,
    ) -> Dict[str, Any]:
        """Filter & paginate fleet records for DVR Report"""
        filtered = self._fleet

        if search:
            q = search.lower().strip()
            filtered = [
                g for g in filtered
                if q in g["id"].lower() or q in g["location"].lower() or q in g["dvr_model"].lower()
            ]

        if gateway_type and gateway_type not in ["Semua Tipe", "All"]:
            filtered = [g for g in filtered if gateway_type.lower() in g["type"].lower()]

        if dvr_brand and dvr_brand not in ["Semua Merek DVR", "All"]:
            filtered = [g for g in filtered if dvr_brand.lower() in g["dvr_model"].lower()]

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
        dvr_brand: Optional[str] = None,
        location: Optional[str] = None,
    ) -> str:
        """Export DVR report data to CSV string format"""
        data = self.get_report(
            search=search,
            gateway_type=gateway_type,
            dvr_brand=dvr_brand,
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
            "DVR/NVR",
            "CPU-DVR Uptime",
            "CPU-DVR Offline",
            "CPU-DVR Success Rate (%)",
            "CPU-DVR Avg Resp (ms)",
            "Kamera Total",
            "Kamera Online",
            "Kamera No Video",
            "Kamera Offline",
            "Recording Uptime",
            "Tidak Merekam",
            "Recording Error",
            "Storage Kapasitas",
            "Storage Terpakai (%)",
            "Storage Rata-rata",
            "Jumlah Event",
            "Terakhir Offline",
        ])

        for g in data["gateways"]:
            writer.writerow([
                g["no"],
                g["id"],
                g["location"],
                g["type"],
                g["dvr_model"],
                g["cpu_dvr_uptime"],
                g["cpu_dvr_offline"],
                g["cpu_dvr_success_rate"],
                g["cpu_dvr_avg_resp_ms"],
                g["kamera_total"],
                g["kamera_online"],
                g["kamera_no_video"],
                g["kamera_offline"],
                g["rec_uptime"],
                g["rec_tidak_merekam"],
                g["rec_error"],
                g["storage_kapasitas"],
                g["storage_terpakai_pct"],
                g["storage_rata_rata"],
                g["jumlah_event"],
                g["terakhir_offline"],
            ])

        return output.getvalue()

    def get_gateway_detail(self, gateway_id: str, date_range: Optional[str] = None) -> Dict[str, Any]:
        """
        Detailed performance telemetry for a specific gateway in DVR Report:
        - Device profile & specifications
        - 10 Key performance indicators (CPU-DVR, Recording Uptime, Tidak Merekam, Recording Error, Storage HDD, Kamera)
        - Multi-track timeline (CPU - DVR, Recording, Kamera)
        - Trouble Incident History events with categories
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
            trouble_events = [
                {
                    "no": 1,
                    "start_time": "08 Oct 2026 02:14",
                    "end_time": "08 Oct 2026 06:32",
                    "duration": "4h 18m",
                    "category": "CPU – DVR",
                    "description": "DVR No Response",
                },
                {
                    "no": 2,
                    "start_time": "12 Oct 2026 11:20",
                    "end_time": "12 Oct 2026 13:05",
                    "duration": "1h 45m",
                    "category": "Recording",
                    "description": "Tidak ada rekaman",
                },
                {
                    "no": 3,
                    "start_time": "18 Oct 2026 22:11",
                    "end_time": "19 Oct 2026 02:05",
                    "duration": "3h 54m",
                    "category": "Kamera",
                    "description": "Channel 3 No Video",
                },
                {
                    "no": 4,
                    "start_time": "23 Oct 2026 10:15",
                    "end_time": "23 Oct 2026 12:40",
                    "duration": "2h 25m",
                    "category": "Recording",
                    "description": "Recording Error",
                },
                {
                    "no": 5,
                    "start_time": "26 Oct 2026 14:32",
                    "end_time": "26 Oct 2026 17:05",
                    "duration": "2h 33m",
                    "category": "CPU – DVR",
                    "description": "DVR Timeout",
                },
            ]
            timeline_tracks = [
                {
                    "track_name": "CPU – DVR",
                    "segments": [
                        {"status": "online", "start_pct": 0, "width_pct": 23.5, "label": "Online", "period": "01 Oct - 08 Oct"},
                        {"status": "offline", "start_pct": 23.5, "width_pct": 4.5, "label": "DVR No Response", "period": "08 Oct 02:14 - 06:32"},
                        {"status": "online", "start_pct": 28.0, "width_pct": 23.0, "label": "Online", "period": "08 Oct - 16 Oct"},
                        {"status": "no_data", "start_pct": 51.0, "width_pct": 3.0, "label": "No Data", "period": "16 Oct"},
                        {"status": "degraded", "start_pct": 54.0, "width_pct": 3.5, "label": "Degraded Response", "period": "17 Oct"},
                        {"status": "online", "start_pct": 57.5, "width_pct": 18.0, "label": "Online", "period": "18 Oct - 23 Oct"},
                        {"status": "offline", "start_pct": 75.5, "width_pct": 3.5, "label": "DVR Timeout", "period": "23 Oct"},
                        {"status": "online", "start_pct": 79.0, "width_pct": 8.0, "label": "Online", "period": "24 Oct - 26 Oct"},
                        {"status": "offline", "start_pct": 87.0, "width_pct": 3.5, "label": "DVR Timeout", "period": "26 Oct 14:32 - 17:05"},
                        {"status": "online", "start_pct": 90.5, "width_pct": 9.5, "label": "Online", "period": "26 Oct - 31 Oct"},
                    ],
                },
                {
                    "track_name": "Recording",
                    "segments": [
                        {"status": "online", "start_pct": 0, "width_pct": 30.0, "label": "Recording Normal", "period": "01 Oct - 10 Oct"},
                        {"status": "offline", "start_pct": 30.0, "width_pct": 3.5, "label": "Tidak ada rekaman", "period": "10 Oct - 11 Oct"},
                        {"status": "online", "start_pct": 33.5, "width_pct": 2.5, "label": "Recording Normal", "period": "11 Oct - 12 Oct"},
                        {"status": "offline", "start_pct": 36.0, "width_pct": 3.0, "label": "Tidak ada rekaman", "period": "12 Oct 11:20 - 13:05"},
                        {"status": "online", "start_pct": 39.0, "width_pct": 18.0, "label": "Recording Normal", "period": "13 Oct - 18 Oct"},
                        {"status": "degraded", "start_pct": 57.0, "width_pct": 3.5, "label": "Bitrate Drop", "period": "18 Oct"},
                        {"status": "online", "start_pct": 60.5, "width_pct": 14.5, "label": "Recording Normal", "period": "19 Oct - 23 Oct"},
                        {"status": "offline", "start_pct": 75.0, "width_pct": 3.5, "label": "Recording Error", "period": "23 Oct 10:15 - 12:40"},
                        {"status": "online", "start_pct": 78.5, "width_pct": 8.5, "label": "Recording Normal", "period": "24 Oct - 26 Oct"},
                        {"status": "offline", "start_pct": 87.0, "width_pct": 3.5, "label": "Storage Busy / Error", "period": "26 Oct"},
                        {"status": "online", "start_pct": 90.5, "width_pct": 9.5, "label": "Recording Normal", "period": "27 Oct - 31 Oct"},
                    ],
                },
                {
                    "track_name": "Kamera",
                    "segments": [
                        {"status": "online", "start_pct": 0, "width_pct": 55.0, "label": "4/4 Channel Online", "period": "01 Oct - 18 Oct"},
                        {"status": "offline", "start_pct": 55.0, "width_pct": 4.5, "label": "Channel 3 No Video", "period": "18 Oct 22:11 - 19 Oct 02:05"},
                        {"status": "online", "start_pct": 59.5, "width_pct": 17.5, "label": "4/4 Channel Online", "period": "19 Oct - 24 Oct"},
                        {"status": "degraded", "start_pct": 77.0, "width_pct": 3.5, "label": "Camera 2 Degraded", "period": "24 Oct"},
                        {"status": "online", "start_pct": 80.5, "width_pct": 6.5, "label": "4/4 Channel Online", "period": "25 Oct - 26 Oct"},
                        {"status": "offline", "start_pct": 87.0, "width_pct": 3.5, "label": "Camera 1 Offline", "period": "26 Oct"},
                        {"status": "online", "start_pct": 90.5, "width_pct": 9.5, "label": "4/4 Channel Online", "period": "27 Oct - 31 Oct"},
                    ],
                },
            ]
        else:
            trouble_events = [
                {
                    "no": 1,
                    "start_time": "10 Oct 2026 03:15",
                    "end_time": "10 Oct 2026 05:45",
                    "duration": "2h 30m",
                    "category": "Recording",
                    "description": "Tidak ada rekaman (Storage full)",
                },
                {
                    "no": 2,
                    "start_time": matched.get("terakhir_offline", "25 Oct 2026 08:17"),
                    "end_time": "25 Oct 2026 11:00",
                    "duration": "2h 43m",
                    "category": "CPU – DVR",
                    "description": "DVR Connection Timeout",
                },
            ]
            timeline_tracks = [
                {
                    "track_name": "CPU – DVR",
                    "segments": [
                        {"status": "online", "start_pct": 0, "width_pct": 78.0, "label": "Online", "period": "01 Oct - 25 Oct"},
                        {"status": "offline", "start_pct": 78.0, "width_pct": 4.0, "label": "DVR Timeout", "period": "25 Oct"},
                        {"status": "online", "start_pct": 82.0, "width_pct": 18.0, "label": "Online", "period": "25 Oct - 31 Oct"},
                    ],
                },
                {
                    "track_name": "Recording",
                    "segments": [
                        {"status": "online", "start_pct": 0, "width_pct": 30.0, "label": "Recording Normal", "period": "01 Oct - 10 Oct"},
                        {"status": "offline", "start_pct": 30.0, "width_pct": 4.0, "label": "Storage Full", "period": "10 Oct"},
                        {"status": "online", "start_pct": 34.0, "width_pct": 66.0, "label": "Recording Normal", "period": "10 Oct - 31 Oct"},
                    ],
                },
                {
                    "track_name": "Kamera",
                    "segments": [
                        {"status": "online", "start_pct": 0, "width_pct": 100.0, "label": "All Channels Online", "period": "01 Oct - 31 Oct"},
                    ],
                },
            ]

        # Percentages
        cpu_up = matched.get("cpu_dvr_uptime", "720h 15m")
        cpu_off = matched.get("cpu_dvr_offline", "23h 45m")
        rec_up = matched.get("rec_uptime", "708h 20m")
        rec_no = matched.get("rec_tidak_merekam", "12h 30m")
        rec_err = matched.get("rec_error", "3h 10m")

        return {
            "id": matched["id"],
            "status": "Online",
            "location": matched["location"],
            "type": matched["type"],
            "dvr_model": matched["dvr_model"],
            "kamera_channels": f"{matched.get('kamera_total', 4)} Channel",
            "storage_capacity": matched.get("storage_kapasitas", "4 TB"),
            "period": period_text,
            "period_hours": "(744 jam)",
            "cpu_dvr_uptime": cpu_up,
            "cpu_dvr_uptime_pct": "96.8%" if is_zh72 else "94.5%",
            "cpu_dvr_offline": cpu_off,
            "cpu_dvr_offline_pct": "3.2%" if is_zh72 else "5.5%",
            "success_rate": f"{matched.get('cpu_dvr_success_rate', 98.8)}%",
            "success_rate_checks": "(5,421 / 5,486 check)" if is_zh72 else "(5,280 / 5,486 check)",
            "avg_response_time": f"{matched.get('cpu_dvr_avg_resp_ms', 180)} ms",
            "rec_uptime": rec_up,
            "rec_uptime_pct": "95.2%" if is_zh72 else "92.0%",
            "rec_tidak_merekam": rec_no,
            "rec_tidak_merekam_pct": "1.7%" if is_zh72 else "4.2%",
            "rec_error": rec_err,
            "rec_error_pct": "0.4%" if is_zh72 else "1.1%",
            "storage_used_pct": 38 if is_zh72 else matched.get("storage_terpakai_pct", 68),
            "kamera_total": matched.get("kamera_total", 4),
            "kamera_online": matched.get("kamera_online", 4),
            "kamera_no_video": matched.get("kamera_no_video", 0),
            "kamera_offline": matched.get("kamera_offline", 0),
            "timeline_tracks": timeline_tracks,
            "trouble_events": trouble_events,
        }


# Singleton service instance
dvr_report_service = DVRReportService()

