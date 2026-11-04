from app.core.database import SessionLocal
from app.models.base_models import GatewayTelemetryHistory
from app.services.sla_calculator_service import SLACalculatorService, WIB
from datetime import datetime, timezone

db = SessionLocal()
service = SLACalculatorService()

devices = [r[0] for r in db.query(GatewayTelemetryHistory.device_id).distinct().all()]

total_cpu_down_rows = 0
total_cell_down_rows = 0
total_dvr_down_rows = 0

print(f"Scanning {len(devices)} devices for Strict Log Point 1-3 downtime...")

for dev in devices:
    rows = db.query(GatewayTelemetryHistory).filter(
        GatewayTelemetryHistory.device_id == dev,
        GatewayTelemetryHistory.recorded_at >= datetime(2026, 1, 1)
    ).order_by(GatewayTelemetryHistory.recorded_at.asc()).all()

    cpu_down = []
    cell_down = []
    dvr_down = []

    for idx, r in enumerate(rows):
        m_up, n_up, d_up, is_rec = service.evaluate_record_status(
            r.raw_payload,
            r.sim_status,
            r.signal_csq,
            r.nvr_status,
            r.nvr_recording
        )
        r_wib = r.recorded_at.replace(tzinfo=timezone.utc).astimezone(WIB)
        if not m_up:
            cpu_down.append((r_wib, r.id))
        if not n_up:
            cell_down.append((r_wib, r.id))
        if not d_up:
            dvr_down.append((r_wib, r.id))

    total_cpu_down_rows += len(cpu_down)
    total_cell_down_rows += len(cell_down)
    total_dvr_down_rows += len(dvr_down)

    if cpu_down or cell_down or dvr_down:
        print(f"\nDevice {dev} ({len(rows)} rows):")
        print(f"  CPU-Modem down rows: {len(cpu_down)}")
        for c in cpu_down[:3]: print(f"    {c[0].strftime('%Y-%m-%d %H:%M:%S WIB')} | {c[1]}")
        print(f"  Cellular down rows : {len(cell_down)}")
        for c in cell_down[:3]: print(f"    {c[0].strftime('%Y-%m-%d %H:%M:%S WIB')} | {c[1]}")
        print(f"  DVR down rows      : {len(dvr_down)}")
        for c in dvr_down[:3]: print(f"    {c[0].strftime('%Y-%m-%d %H:%M:%S WIB')} | {c[1]}")

print(f"\n==========================================")
print(f"TOTAL CPU-Modem down rows across all DB: {total_cpu_down_rows}")
print(f"TOTAL Cellular down rows across all DB : {total_cell_down_rows}")
print(f"TOTAL DVR down rows across all DB      : {total_dvr_down_rows}")

db.close()

