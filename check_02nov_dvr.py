from app.core.database import SessionLocal
from app.models.base_models import GatewayTelemetryHistory
from app.services.sla_calculator_service import SLACalculatorService, WIB
from datetime import datetime, timezone

db = SessionLocal()
service = SLACalculatorService()
dev_id = "gw-0218098c"

rows = db.query(GatewayTelemetryHistory).filter(
    GatewayTelemetryHistory.device_id == dev_id,
    GatewayTelemetryHistory.recorded_at >= datetime(2026, 11, 2, 0, 0, 0),
    GatewayTelemetryHistory.recorded_at <= datetime(2026, 11, 2, 23, 59, 59)
).order_by(GatewayTelemetryHistory.recorded_at.asc()).all()

print(f"Total rows on 02 Nov for {dev_id}: {len(rows)}")

for idx, r in enumerate(rows):
    m_up, n_up, d_up, is_rec = service.evaluate_record_status(
        r.raw_payload,
        r.sim_status,
        r.signal_csq,
        r.nvr_status,
        r.nvr_recording
    )
    r_wib = r.recorded_at.replace(tzinfo=timezone.utc).astimezone(WIB)
    if not m_up or not n_up or not d_up:
        print(f"Row #{idx} at {r_wib.strftime('%H:%M:%S')} | m_up={m_up}, n_up={n_up}, d_up={d_up}")
        logs = r.raw_payload.get("recent_system_logs", [])
        if logs:
            print(f"   Log: {logs[-1] if isinstance(logs, list) else logs}")

db.close()

