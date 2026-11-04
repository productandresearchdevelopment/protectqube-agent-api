from app.core.database import SessionLocal
from app.models.base_models import GatewayTelemetryHistory
from app.services.sla_calculator_service import SLACalculatorService, WIB
from datetime import datetime, timezone, timedelta

db = SessionLocal()
service = SLACalculatorService()

dev_id = "gw-0218098c"
rows = db.query(GatewayTelemetryHistory).filter(
    GatewayTelemetryHistory.device_id == dev_id,
    GatewayTelemetryHistory.recorded_at >= datetime(2026, 1, 1)
).order_by(GatewayTelemetryHistory.recorded_at.asc()).all()

# Let's test calculate_daily_breakdown with Opsi A (Strict Points 1-3 only)
now_wib = datetime.now(timezone.utc).astimezone(WIB)
start_dt = datetime(2026, 11, 1, 0, 0, 0, tzinfo=timezone.utc)
end_dt = datetime(2026, 11, 4, 23, 59, 59, tzinfo=timezone.utc)

s_date = start_dt.astimezone(WIB).date()
e_date = end_dt.astimezone(WIB).date()

cur_date = s_date
while cur_date <= e_date:
    d_start = datetime(cur_date.year, cur_date.month, cur_date.day, 0, 0, 0, tzinfo=WIB)
    d_end = datetime(cur_date.year, cur_date.month, cur_date.day, 23, 59, 59, tzinfo=WIB)

    day_cpu_down_sec = 0.0
    day_cell_down_sec = 0.0
    day_dvr_down_sec = 0.0

    for i in range(len(rows) - 1):
        curr_r = rows[i]
        next_r = rows[i + 1]
        t1 = curr_r.recorded_at.replace(tzinfo=timezone.utc).astimezone(WIB) if curr_r.recorded_at.tzinfo is None else curr_r.recorded_at.astimezone(WIB)
        t2 = next_r.recorded_at.replace(tzinfo=timezone.utc).astimezone(WIB) if next_r.recorded_at.tzinfo is None else next_r.recorded_at.astimezone(WIB)

        overlap_s = max(t1, d_start)
        overlap_e = min(t2, d_end)

        if overlap_e > overlap_s:
            dur = (overlap_e - overlap_s).total_seconds()
            m_up, n_up, d_up, is_rec = service.evaluate_record_status(
                curr_r.raw_payload,
                curr_r.sim_status,
                curr_r.signal_csq,
                curr_r.nvr_status,
                curr_r.nvr_recording
            )
            if not m_up:
                day_cpu_down_sec += dur
            if not n_up:
                day_cell_down_sec += dur
            if not d_up:
                day_dvr_down_sec += dur

    cpu_down_min = round(min(86400.0, day_cpu_down_sec) / 60.0, 1)
    cell_down_min = round(min(86400.0, day_cell_down_sec) / 60.0, 1)
    dvr_down_min = round(min(86400.0, day_dvr_down_sec) / 60.0, 1)

    print(f"Date: {cur_date.strftime('%d %b %Y')} | CPU Down: {cpu_down_min}m | Cell Down: {cell_down_min}m | DVR Down: {dvr_down_min}m")
    cur_date += timedelta(days=1)

db.close()

