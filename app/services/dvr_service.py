from typing import Dict, Any, List, Optional


class DVRService:
    """
    Service layer for DVR & Recording Monitoring:
    DVR/NVR device status, camera channels, video loss, recording integrity,
    hard disk storage utilization, and CPU–DVR communication diagnostics.
    """

    def __init__(self):
        # 5 primary gateways explicitly visible in the screenshot
        self._primary_gateways: List[Dict[str, Any]] = [
            {
                "no": 1,
                "id": "ZH72",
                "location": "Alfa H Sapri Pondok Aren",
                "type": "SmartBox Hitam",
                "dvr_model": "Hikvision DS-7608NI-K2",
                "cpu_dvr": "Connected",
                "total_kamera": 8,
                "kamera_online": 8,
                "kamera_no_video": 0,
                "kamera_offline": 0,
                "recording_status": "Normal",
                "storage_usage_percent": 45,
                "dvr_health": "Good",
                "last_update": "26 Oct 2026 14:32",
            },
            {
                "no": 2,
                "id": "ZV91",
                "location": "IDM Graha Morris Tambun",
                "type": "SmartBox Putih",
                "dvr_model": "Hikvision DS-7616NI-K2",
                "cpu_dvr": "No Response",
                "total_kamera": 16,
                "kamera_online": 14,
                "kamera_no_video": 1,
                "kamera_offline": 1,
                "recording_status": "Not Recording",
                "storage_usage_percent": 78,
                "dvr_health": "Warning",
                "last_update": "26 Oct 2026 14:28",
            },
            {
                "no": 3,
                "id": "697D",
                "location": "Alfa Ahmad Dahlan III",
                "type": "SmartBox Hitam",
                "dvr_model": "Dahua NVR4108HS-8P",
                "cpu_dvr": "Connected",
                "total_kamera": 8,
                "kamera_online": 7,
                "kamera_no_video": 1,
                "kamera_offline": 0,
                "recording_status": "Normal",
                "storage_usage_percent": 62,
                "dvr_health": "Good",
                "last_update": "26 Oct 2026 14:15",
            },
            {
                "no": 4,
                "id": "ZR4R",
                "location": "Alfa Ruko Metland",
                "type": "SmartBox Putih",
                "dvr_model": "Hikvision DS-7608NI-K2",
                "cpu_dvr": "Not Detected",
                "total_kamera": 8,
                "kamera_online": 6,
                "kamera_no_video": 0,
                "kamera_offline": 2,
                "recording_status": "Recording Error",
                "storage_usage_percent": 92,
                "dvr_health": "Critical",
                "last_update": "26 Oct 2026 13:50",
            },
            {
                "no": 5,
                "id": "ZJ2B",
                "location": "IDM Griya Mustikasari",
                "type": "SmartBox Hitam",
                "dvr_model": "Dahua NVR4216-16P",
                "cpu_dvr": "Connected",
                "total_kamera": 16,
                "kamera_online": 15,
                "kamera_no_video": 0,
                "kamera_offline": 1,
                "recording_status": "Normal",
                "storage_usage_percent": 58,
                "dvr_health": "Good",
                "last_update": "26 Oct 2026 12:40",
            },
        ]

        # Populate fleet up to 2,000 items
        self._fleet: List[Dict[str, Any]] = list(self._primary_gateways)
        locations_pool = [
            "Alfa Ciledug Raya",
            "IDM Bintaro Sektor 9",
            "Alfa Kebayoran Lama",
            "IDM Fatmawati Raya",
            "Alfa Ciputat Molek",
            "IDM Cinere Gandul",
            "Alfa Serpong Utara",
            "IDM BSD City Sektor 1",
            "Alfa Pamulang Barat",
            "IDM Karawaci Baru",
            "Alfa Alam Sutera",
            "IDM Gading Serpong",
        ]
        models_pool = [
            "Hikvision DS-7608NI-K2",
            "Hikvision DS-7616NI-K2",
            "Dahua NVR4108HS-8P",
            "Dahua NVR4216-16P",
            "Uniview NVR301-08S3",
        ]

        for i in range(6, 2001):
            is_black = (i % 2 == 1)
            gw_type = "SmartBox Hitam" if is_black else "SmartBox Putih"
            model = models_pool[i % len(models_pool)]
            loc = f"{locations_pool[i % len(locations_pool)]} #{i}"
            hex_id = f"{hex(0x1000 + i)[2:].upper()}"
            
            # Health distribution matching UI proportions:
            # Normal ~88%, Issue ~9%, Offline ~3%
            dice = i % 100
            if dice < 88:
                cpu_dvr = "Connected"
                total_cam = 8 if i % 3 != 0 else 16
                online_cam = total_cam
                no_vid = 0
                offline_cam = 0
                rec_status = "Normal"
                storage_pct = 40 + (i % 35)
                health = "Good"
            elif dice < 97:
                # Issue / Warning
                cpu_dvr = "No Response" if dice % 2 == 0 else "Not Detected"
                total_cam = 8 if i % 2 == 0 else 16
                offline_cam = 1 + (dice % 2)
                no_vid = 1 if dice % 3 == 0 else 0
                online_cam = total_cam - offline_cam - no_vid
                rec_status = "Not Recording" if dice % 2 == 0 else "Recording Error"
                storage_pct = 75 + (i % 20)
                health = "Warning" if storage_pct < 90 else "Critical"
            else:
                # Offline
                cpu_dvr = "Driver Error" if dice == 98 else "No Response"
                total_cam = 8
                online_cam = 0
                no_vid = 0
                offline_cam = 8
                rec_status = "Recording Error"
                storage_pct = 95
                health = "Critical"

            self._fleet.append({
                "no": i,
                "id": hex_id,
                "location": loc,
                "type": gw_type,
                "dvr_model": model,
                "cpu_dvr": cpu_dvr,
                "total_kamera": total_cam,
                "kamera_online": online_cam,
                "kamera_no_video": no_vid,
                "kamera_offline": offline_cam,
                "recording_status": rec_status,
                "storage_usage_percent": storage_pct,
                "dvr_health": health,
                "last_update": f"26 Oct 2026 {10 + (i % 4)}:{10 + (i % 50):02d}",
            })

    def get_summary(self) -> Dict[str, Any]:
        """Summary card metrics matching exact UI values"""
        return {
            "total_gateways": 2000,
            "recording_normal": 1760,
            "recording_normal_percent": 88.0,
            "issue": 180,
            "issue_percent": 9.0,
            "offline": 60,
            "offline_percent": 3.0,
            "total_kamera": 8150,
            "kamera_online": 7350,
            "kamera_no_video": 480,
            "kamera_offline": 320,
            "total_storage_tb": 512,
            "storage_used_tb": 410,
            "storage_warning_tb": 72,
            "storage_critical_tb": 30,
        }

    def get_charts(self) -> Dict[str, Any]:
        """Donut and timeline charts exactly matching screenshot metrics"""
        return {
            "cpu_dvr_comm": {
                "total_label": "Gateway",
                "total_count": 2000,
                "slices": [
                    {"label": "Connected", "count": 1850, "percent": 92.5, "color": "#00c875"},
                    {"label": "No Response", "count": 80, "percent": 4.0, "color": "#e2445c"},
                    {"label": "Not Detected", "count": 40, "percent": 2.0, "color": "#fdab3d"},
                    {"label": "Driver Error", "count": 30, "percent": 1.5, "color": "#579bfc"},
                ],
            },
            "status_kamera": {
                "total_label": "Kamera",
                "total_count": 8150,
                "slices": [
                    {"label": "Online", "count": 7350, "percent": 90.2, "color": "#00c875"},
                    {"label": "No Video", "count": 480, "percent": 5.9, "color": "#fdab3d"},
                    {"label": "Offline", "count": 320, "percent": 3.9, "color": "#e2445c"},
                ],
            },
            "recording_status": {
                "total_label": "Kamera",
                "total_count": 8150,
                "slices": [
                    {"label": "Recording", "count": 7200, "percent": 88.3, "color": "#00c875"},
                    {"label": "Not Recording", "count": 500, "percent": 6.1, "color": "#fdab3d"},
                    {"label": "Recording Error", "count": 270, "percent": 3.3, "color": "#e2445c"},
                    {"label": "Unknown", "count": 180, "percent": 2.2, "color": "#00d2d3"},
                ],
            },
            "storage_usage": {
                "avg": "64%",
                "max": "92%",
                "min": "38%",
                "timeline": [
                    {"time": "00:00", "value": 50.0},
                    {"time": "04:00", "value": 58.0},
                    {"time": "08:00", "value": 62.0},
                    {"time": "12:00", "value": 68.0},
                    {"time": "16:00", "value": 74.0},
                    {"time": "20:00", "value": 64.0},
                ],
            },
        }

    def get_gateways(
        self,
        search: Optional[str] = None,
        gateway_type: Optional[str] = None,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 5,
    ) -> Dict[str, Any]:
        """Filter & paginate fleet records for the table"""
        filtered = self._fleet

        if search:
            q = search.lower().strip()
            filtered = [
                g for g in filtered
                if q in g["id"].lower() or q in g["location"].lower() or q in g["dvr_model"].lower()
            ]

        if gateway_type and gateway_type not in ["Semua Tipe", "All"]:
            filtered = [g for g in filtered if gateway_type.lower() in g["type"].lower()]

        if status and status not in ["Semua Status", "All"]:
            s = status.lower()
            if s == "normal":
                filtered = [g for g in filtered if g["dvr_health"] == "Good"]
            elif s == "issue":
                filtered = [g for g in filtered if g["dvr_health"] == "Warning"]
            elif s == "offline":
                filtered = [g for g in filtered if g["dvr_health"] == "Critical" or g["cpu_dvr"] != "Connected"]

        total_items = len(filtered)
        total_pages = max(1, (total_items + page_size - 1) // page_size)
        page = max(1, min(page, total_pages))
        start_idx = (page - 1) * page_size
        end_idx = min(start_idx + page_size, total_items)

        items_slice = filtered[start_idx:end_idx]

        return {
            "items": items_slice,
            "pagination": {
                "total_items": total_items,
                "total_pages": total_pages,
                "current_page": page,
                "page_size": page_size,
                "showing_start": start_idx + 1 if total_items > 0 else 0,
                "showing_end": end_idx,
            },
        }

    def get_dashboard(
        self,
        search: Optional[str] = None,
        gateway_type: Optional[str] = None,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 5,
    ) -> Dict[str, Any]:
        """Unified dashboard payload for frontend consumer"""
        summary = self.get_summary()
        charts = self.get_charts()
        gw_result = self.get_gateways(
            search=search,
            gateway_type=gateway_type,
            status=status,
            page=page,
            page_size=page_size,
        )

        return {
            "summary": summary,
            "charts": charts,
            "gateways": gw_result["items"],
            "pagination": gw_result["pagination"],
        }

    def get_gateway_detail(self, gateway_id: str) -> Dict[str, Any]:
        """Detailed telemetry for a specific gateway DVR and Camera recording preview"""
        gw = next((g for g in self._primary_gateways if g["id"].lower() == gateway_id.lower()), self._primary_gateways[0])

        is_hitam = "Hitam" in gw["type"]
        model_name = "SmartBox Hitam (Raspberry Pi 3B+)" if is_hitam else "SmartBox Putih (Rockchip RK3328)"

        camera_names = [
            "CAM 01 - Area Kasir 1",
            "CAM 02 - Pintu Masuk Utama",
            "CAM 03 - Area Belanja Rak A",
            "CAM 04 - Area Belanja Rak B",
            "CAM 05 - Gudang Belakang",
            "CAM 06 - Area Parkir Depan",
            "CAM 07 - Kasir 2 (Express)",
            "CAM 08 - Ruang Panel & Server",
            "CAM 09 - Lorong Gondola C",
            "CAM 10 - Area Chiller / Minuman",
            "CAM 11 - Pintu Darurat Belakang",
            "CAM 12 - Area Kasir 3",
            "CAM 13 - Area Parkir Belakang",
            "CAM 14 - Ruang Manager Toko",
            "CAM 15 - Area Teras Depan",
            "CAM 16 - Loading Dock Barang",
        ]

        total_cams = gw["total_kamera"]
        online_cams = gw["kamera_online"]
        no_video_cams = gw["kamera_no_video"]
        offline_cams = gw["kamera_offline"]

        cam_list: List[Dict[str, Any]] = []
        for i in range(total_cams):
            c_status = "Online"
            is_rec = True
            if i >= online_cams + no_video_cams:
                c_status = "Offline"
                is_rec = False
            elif i >= online_cams:
                c_status = "No Video"
                is_rec = False

            cam_list.append({
                "channel": i + 1,
                "name": camera_names[i] if i < len(camera_names) else f"CAM {i+1:02d} - Channel {i+1}",
                "status": c_status,
                "is_recording": is_rec,
                "fps": 25 if c_status == "Online" else 0,
                "resolution": "1080P Full HD" if c_status == "Online" else "-",
                "bitrate": "2048 Kbps" if c_status == "Online" else "0 Kbps",
                "timestamp": f"{gw.get('last_update', '26 Oct 2026 14:32')}:10",
            })

        storage_pct = gw["storage_usage_percent"]
        total_tb = 4.0 if total_cams == 8 else 8.0
        used_tb = round((storage_pct / 100.0) * total_tb, 1)

        return {
            "id": gw["id"],
            "location": gw["location"],
            "type": gw["type"],
            "model": model_name,
            "dvr_model": gw["dvr_model"],
            "ip_address": f"192.168.1.{100 + (gw['no'] % 100)}",
            "last_update": f"{gw.get('last_update', '26 Oct 2026 14:32')}:10",
            "service_status": "Running" if gw["cpu_dvr"] == "Connected" else "Degraded",
            "cpu_dvr": {
                "status": gw["cpu_dvr"],
                "message": "Komunikasi protokol SDK Hikvision terhubung stabil (driver OK)" if gw["cpu_dvr"] == "Connected" else "Koneksi ke DVR gagal atau tidak merespons",
                "port": "8000 (SDK/ISAPI)",
                "response_time": "12 ms" if gw["cpu_dvr"] == "Connected" else "Timeout",
                "packet_loss": "0%" if gw["cpu_dvr"] == "Connected" else "100%",
                "last_check": f"{gw.get('last_update', '26 Oct 2026 14:32')}:05",
            },
            "camera_status": {
                "total": total_cams,
                "online": online_cams,
                "no_video": no_video_cams,
                "offline": offline_cams,
                "percent": int((online_cams / total_cams) * 100) if total_cams else 0,
                "sparkline": [online_cams, online_cams, online_cams, online_cams, online_cams],
            },
            "recording_storage": {
                "status": gw["recording_status"],
                "used_tb": used_tb,
                "total_tb": total_tb,
                "percent": storage_pct,
                "retention_days": 30 if storage_pct < 85 else 18,
                "sparkline": [max(10, storage_pct - 3), max(10, storage_pct - 2), storage_pct - 1, storage_pct],
            },
            "dvr_health": {
                "status": gw["dvr_health"],
                "hdd_status": "Normal (SMART OK)" if gw["dvr_health"] == "Good" else "Warning Sector Check",
                "temperature": f"{38 + (gw['no'] % 5)}°C",
                "fan_status": "Normal",
                "bad_sector": 0 if gw["dvr_health"] == "Good" else 4,
            },
            "cameras": cam_list,
        }


# Singleton service instance
dvr_service = DVRService()

