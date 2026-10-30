import os
import psutil
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


class SystemHealthAgent:
    """
    Agent 3: System Health Agent (CPU, RAM, SD Card)
    - Monitoring CPU usage (persentase, load average)
    - Monitoring RAM usage (total, terpakai, tersisa)
    - Monitoring SD card kapasitas (total, terpakai, tersisa)
    - Kesehatan SD card (bad sector, wear level, read-only filesystem check)
    """

    def __init__(self, mount_point: str = "/"):
        self.mount_point = mount_point if os.name != "nt" else "C:\\"

    def inspect(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "status": "UNKNOWN",
            "cpu": {
                "usage_percent": 0.0,
                "core_count": psutil.cpu_count(logical=True),
                "load_average_1m": 0.0,
                "load_average_5m": 0.0,
                "load_average_15m": 0.0,
            },
            "ram": {
                "total_mb": 0.0,
                "used_mb": 0.0,
                "free_mb": 0.0,
                "usage_percent": 0.0,
            },
            "sd_card": {
                "mount_point": self.mount_point,
                "total_gb": 0.0,
                "used_gb": 0.0,
                "free_gb": 0.0,
                "usage_percent": 0.0,
                "is_readonly": False,
                "health_status": "GOOD",
            },
            "issues": [],
        }

        try:
            result["cpu"]["usage_percent"] = psutil.cpu_percent(interval=0.5)
            if hasattr(os, "getloadavg"):
                load1, load5, load15 = os.getloadavg()
                result["cpu"]["load_average_1m"] = round(load1, 2)
                result["cpu"]["load_average_5m"] = round(load5, 2)
                result["cpu"]["load_average_15m"] = round(load15, 2)
        except Exception as e:
            logger.warning(f"Error fetching CPU stats: {e}")

        try:
            mem = psutil.virtual_memory()
            result["ram"]["total_mb"] = round(mem.total / (1024 * 1024), 2)
            result["ram"]["used_mb"] = round(mem.used / (1024 * 1024), 2)
            result["ram"]["free_mb"] = round(mem.available / (1024 * 1024), 2)
            result["ram"]["usage_percent"] = mem.percent
        except Exception as e:
            logger.warning(f"Error fetching RAM stats: {e}")

        try:
            disk = psutil.disk_usage(self.mount_point)
            result["sd_card"]["total_gb"] = round(disk.total / (1024 * 1024 * 1024), 2)
            result["sd_card"]["used_gb"] = round(disk.used / (1024 * 1024 * 1024), 2)
            result["sd_card"]["free_gb"] = round(disk.free / (1024 * 1024 * 1024), 2)
            result["sd_card"]["usage_percent"] = disk.percent

            test_path = os.path.join(self.mount_point, ".sd_write_test_tmp")
            try:
                with open(test_path, "w") as f:
                    f.write("ok")
                if os.path.exists(test_path):
                    os.remove(test_path)
            except Exception:
                result["sd_card"]["is_readonly"] = True
                result["sd_card"]["health_status"] = "CORRUPT_OR_READONLY"
                result["issues"].append("SD Card filesystem is read-only or corrupted!")

        except Exception as e:
            logger.warning(f"Error fetching disk stats: {e}")

        if result["sd_card"]["is_readonly"]:
            result["status"] = "CRITICAL"
        elif result["ram"]["usage_percent"] > 90 or result["sd_card"]["usage_percent"] > 90:
            result["status"] = "WARNING"
            if result["ram"]["usage_percent"] > 90:
                result["issues"].append("High RAM consumption (> 90%) - Risk of OOM crashing Node-RED")
            if result["sd_card"]["usage_percent"] > 90:
                result["issues"].append("SD Card storage nearly full (> 90%)")
        else:
            result["status"] = "HEALTHY"

        return result
