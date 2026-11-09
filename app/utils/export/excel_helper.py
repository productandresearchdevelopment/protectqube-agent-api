import io
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

WIB = timezone(timedelta(hours=7))

# ─── Color Palette & Styles ──────────────────────────────────────────────────
# Modern Dark Navy & Slate matching ProtectQube reference pattern
COLOR_HEADER_BG = "1E293B"       # Dark Navy (Tier 1 Header)
COLOR_SUBHEADER_BG = "334155"    # Slate Navy (Tier 2 Sub-header)
COLOR_HEADER_TEXT = "FFFFFF"     # White
COLOR_ZEBRA_ROW = "F8FAFC"       # Light Slate
COLOR_BORDER = "CBD5E1"          # Thin border gray
COLOR_KPI_BG = "F1F5F9"          # Light KPI card background
COLOR_SUCCESS_TEXT = "047857"    # Emerald
COLOR_DANGER_TEXT = "B91C1C"     # Rose
COLOR_WARNING_TEXT = "B45309"    # Amber

FONT_FAMILY = "Segoe UI"

BORDER_THIN = Border(
    left=Side(style="thin", color=COLOR_BORDER),
    right=Side(style="thin", color=COLOR_BORDER),
    top=Side(style="thin", color=COLOR_BORDER),
    bottom=Side(style="thin", color=COLOR_BORDER),
)

HEADER_FILL = PatternFill(start_color=COLOR_HEADER_BG, end_color=COLOR_HEADER_BG, fill_type="solid")
SUBHEADER_FILL = PatternFill(start_color=COLOR_SUBHEADER_BG, end_color=COLOR_SUBHEADER_BG, fill_type="solid")
ZEBRA_FILL = PatternFill(start_color=COLOR_ZEBRA_ROW, end_color=COLOR_ZEBRA_ROW, fill_type="solid")
KPI_FILL = PatternFill(start_color=COLOR_KPI_BG, end_color=COLOR_KPI_BG, fill_type="solid")

HEADER_FONT = Font(name=FONT_FAMILY, size=10, bold=True, color=COLOR_HEADER_TEXT)
SUBHEADER_FONT = Font(name=FONT_FAMILY, size=9, bold=True, color="FFFFFF")
DATA_FONT = Font(name=FONT_FAMILY, size=10, color="0F172A")
TITLE_FONT = Font(name=FONT_FAMILY, size=14, bold=True, color="0F172A")
SUBTITLE_FONT = Font(name=FONT_FAMILY, size=9, italic=True, color="64748B")
KPI_LABEL_FONT = Font(name=FONT_FAMILY, size=8, bold=True, color="64748B")
KPI_VAL_FONT = Font(name=FONT_FAMILY, size=12, bold=True, color="0F172A")


def _apply_title_block(
    ws,
    title: str,
    date_range: Optional[str] = None,
    total_records: int = 0,
    kpis: Optional[List[tuple]] = None,
) -> int:
    """Writes corporate header block, generation timestamp, and optional KPI tiles."""
    now_wib = datetime.now(WIB).strftime("%Y-%m-%d %H:%M:%S WIB")

    # Title
    ws["A1"] = "PROTECTQUBE AIOPS"
    ws["A1"].font = Font(name=FONT_FAMILY, size=9, bold=True, color="0073EA")

    ws["A2"] = title
    ws["A2"].font = TITLE_FONT

    period_str = date_range if date_range else "Current Period"
    ws["A3"] = f"Monitored Period: {period_str}  |  Generated on: {now_wib}  |  Total Records: {total_records}"
    ws["A3"].font = SUBTITLE_FONT

    current_row = 5

    # Optional KPI tiles row
    if kpis:
        col_start = 1
        for label, val in kpis:
            col_letter = get_column_letter(col_start)
            next_col_letter = get_column_letter(col_start + 1)

            cell_label = ws[f"{col_letter}{current_row}"]
            cell_label.value = label.upper()
            cell_label.font = KPI_LABEL_FONT
            cell_label.alignment = Alignment(horizontal="center")
            cell_label.fill = KPI_FILL
            cell_label.border = BORDER_THIN
            ws.merge_cells(f"{col_letter}{current_row}:{next_col_letter}{current_row}")

            cell_val = ws[f"{col_letter}{current_row + 1}"]
            cell_val.value = val
            cell_val.font = KPI_VAL_FONT
            cell_val.alignment = Alignment(horizontal="center")
            cell_val.fill = KPI_FILL
            cell_val.border = BORDER_THIN
            ws.merge_cells(f"{col_letter}{current_row + 1}:{next_col_letter}{current_row + 1}")

            col_start += 2

        current_row += 3
    else:
        current_row = 5

    return current_row


def _merge_and_style_header_block(
    ws,
    start_row: int,
    start_col: int,
    end_row: int,
    end_col: int,
    title: str,
    fill=HEADER_FILL,
    font=HEADER_FONT,
    alignment=None,
):
    """Styles a 2-tier merged rectangular header area ensuring all cells receive borders and fills."""
    if alignment is None:
        alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    for r in range(start_row, end_row + 1):
        for c in range(start_col, end_col + 1):
            cell = ws.cell(row=r, column=c)
            cell.fill = fill
            cell.border = BORDER_THIN
            cell.font = font
            cell.alignment = alignment

    ws.cell(row=start_row, column=start_col, value=title)
    if start_row != end_row or start_col != end_col:
        ws.merge_cells(start_row=start_row, start_column=start_col, end_row=end_row, end_column=end_col)


def _autofit_columns(ws, min_width=12, max_width=45):
    """Auto-adjusts column widths to content with safety margins."""
    for col in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            # Skip title row and merged rows for width estimation
            if cell.row in [1, 2, 3, 5, 6]:
                continue
            if cell.value:
                s = str(cell.value)
                max_len = max(max_len, len(s))

        calc_width = max(min_width, min(max_len + 3, max_width))
        ws.column_dimensions[col_letter].width = calc_width


# ─── 1. DVR Report Excel Builder (2-Tier Header with Merged Groups) ───────────

def build_dvr_report_excel(
    gateways: List[Dict[str, Any]],
    summary: Optional[Dict[str, Any]] = None,
    date_range: Optional[str] = None,
) -> io.BytesIO:
    """
    Builds a formatted Excel workbook for DVR & Recording Report matching the UI:
    - 2-Tier grouped headers with vertical & horizontal cell merges
    - Exact columns: Location, Type, DVR/NVR, CPU-DVR (Uptime, Offline, SR),
      Camera (Total, Online, Loss, SR), Recording (Record, Not Record, SR),
      DVR Storage (Capacity, Used, Retention), Combined SLA %
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "DVR Report"
    ws.views.sheetView[0].showGridLines = True

    kpis = []
    if summary:
        kpis = [
            ("Total Gateway", summary.get("total_gateways", len(gateways))),
            ("SLA Reached (>=98%)", f"{summary.get('sla_tercapai', 0)} ({summary.get('sla_tercapai_percent', 0)}%)"),
            ("Warning (85-98%)", f"{summary.get('sla_warning', 0)} ({summary.get('sla_warning_percent', 0)}%)"),
            ("Breached (<85%)", f"{summary.get('sla_critical', 0)} ({summary.get('sla_critical_percent', 0)}%)"),
        ]

    start_row = _apply_title_block(
        ws,
        title="Fleet DVR & Recording Performance Report",
        date_range=date_range,
        total_records=len(gateways),
        kpis=kpis,
    )

    r1 = start_row
    r2 = start_row + 1

    ws.row_dimensions[r1].height = 24
    ws.row_dimensions[r2].height = 20

    # 1. Tier 1 Headers (Merged Vertically or Horizontally)
    _merge_and_style_header_block(ws, r1, 1, r2, 1, "No.")
    _merge_and_style_header_block(ws, r1, 2, r2, 2, "Location")
    _merge_and_style_header_block(ws, r1, 3, r2, 3, "Type")
    _merge_and_style_header_block(ws, r1, 4, r2, 4, "DVR / NVR")
    _merge_and_style_header_block(ws, r1, 5, r1, 7, "CPU – DVR Communication")
    _merge_and_style_header_block(ws, r1, 8, r1, 11, "Camera Status")
    _merge_and_style_header_block(ws, r1, 12, r1, 14, "Recording Status")
    _merge_and_style_header_block(ws, r1, 15, r1, 17, "DVR Storage")
    _merge_and_style_header_block(ws, r1, 18, r2, 18, "SLA (%)")

    # 2. Tier 2 Sub-headers
    sub_headers = {
        5: "Uptime",
        6: "Offline",
        7: "Success Rate (%)",
        8: "Total",
        9: "Online",
        10: "Loss",
        11: "Success Rate (%)",
        12: "Record",
        13: "Not Record",
        14: "Success Rate (%)",
        15: "Capacity",
        16: "Used (%)",
        17: "Retention",
    }
    for col_idx, text in sub_headers.items():
        _merge_and_style_header_block(
            ws, r2, col_idx, r2, col_idx, text, fill=SUBHEADER_FILL, font=SUBHEADER_FONT
        )

    # 3. Data Rows
    curr_row = r2 + 1
    for idx, gw in enumerate(gateways, 1):
        ws.row_dimensions[curr_row].height = 20
        is_even = (idx % 2 == 0)
        row_fill = ZEBRA_FILL if is_even else None

        cam_tot = gw.get("kamera_total", 0)
        cam_on = gw.get("kamera_online", 0)
        cam_loss = gw.get("kamera_offline") if gw.get("kamera_offline") is not None else max(0, cam_tot - cam_on)
        cam_sr = round((cam_on / max(1, cam_tot)) * 100.0, 1) if cam_tot > 0 else 100.0

        sla_val = gw.get("sla")
        if sla_val is None:
            cpu_sr = float(gw.get("cpu_dvr_success_rate", 100.0))
            rec_sr = float(gw.get("rec_success_rate", 100.0))
            sla_val = round((cpu_sr + cam_sr + rec_sr) / 3.0, 1)

        row_values = [
            idx,
            gw.get("location") or gw.get("id"),
            gw.get("type", "SmartBox Putih"),
            gw.get("dvr_model", "Hikvision DS-7104NI"),
            gw.get("cpu_dvr_uptime", "0m"),
            gw.get("cpu_dvr_offline", "0m"),
            f"{gw.get('cpu_dvr_success_rate', 100.0)}%",
            cam_tot,
            cam_on,
            cam_loss,
            f"{cam_sr}%",
            gw.get("rec_uptime", "0m"),
            gw.get("rec_tidak_merekam", "0m"),
            f"{gw.get('rec_success_rate', 100.0)}%",
            gw.get("storage_kapasitas", "4.0 TB"),
            f"{gw.get('storage_terpakai_pct', 0)}%",
            gw.get("storage_rata_rata", "30 Hari"),
            f"{sla_val}%",
        ]

        for col_idx, val in enumerate(row_values, 1):
            cell = ws.cell(row=curr_row, column=col_idx, value=val)
            cell.font = DATA_FONT
            cell.border = BORDER_THIN
            if row_fill:
                cell.fill = row_fill

            if col_idx in [1, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18]:
                cell.alignment = Alignment(horizontal="center", vertical="center")
            else:
                cell.alignment = Alignment(horizontal="left", vertical="center")

            # Green highlight for normal uptime/record, red for downtime
            if col_idx in [5, 9, 12]:
                cell.font = Font(name=FONT_FAMILY, size=10, bold=True, color=COLOR_SUCCESS_TEXT)
            elif col_idx in [6, 10, 13]:
                if str(val) not in ["0m", "0", "0h", "0.0"]:
                    cell.font = Font(name=FONT_FAMILY, size=10, bold=True, color=COLOR_DANGER_TEXT)
            elif col_idx == 18:
                try:
                    num_sla = float(str(val).replace("%", ""))
                    if num_sla >= 98.0:
                        cell.font = Font(name=FONT_FAMILY, size=10, bold=True, color=COLOR_SUCCESS_TEXT)
                    elif num_sla >= 85.0:
                        cell.font = Font(name=FONT_FAMILY, size=10, bold=True, color=COLOR_WARNING_TEXT)
                    else:
                        cell.font = Font(name=FONT_FAMILY, size=10, bold=True, color=COLOR_DANGER_TEXT)
                except Exception:
                    pass

        curr_row += 1

    _autofit_columns(ws)

    stream = io.BytesIO()
    wb.save(stream)
    stream.seek(0)
    return stream


# ─── 2. Cellular Report Excel Builder (2-Tier Header with Merged Groups) ──────

def build_cellular_report_excel(
    gateways: List[Dict[str, Any]],
    summary: Optional[Dict[str, Any]] = None,
    date_range: Optional[str] = None,
) -> io.BytesIO:
    """
    Builds a formatted Excel workbook for Cellular Report matching the UI:
    - 2-Tier grouped headers: Location, Type, Modem Device (Name, Avg Temp),
      SIM Card & Data (Provider, SIM Card No., Remaining Quota),
      CPU – Modem (Uptime, Downtime, SR), Network Connection (Uptime, Downtime, SR, RSRP)
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Cellular Report"
    ws.views.sheetView[0].showGridLines = True

    kpis = []
    if summary:
        kpis = [
            ("Total Gateway", summary.get("total_gateways", len(gateways))),
            ("SLA Reached (>=98%)", f"{summary.get('sla_tercapai', 0)} ({summary.get('sla_tercapai_percent', 0)}%)"),
            ("Warning (85-98%)", f"{summary.get('sla_warning', 0)} ({summary.get('sla_warning_percent', 0)}%)"),
            ("Breached (<85%)", f"{summary.get('sla_critical', 0)} ({summary.get('sla_critical_percent', 0)}%)"),
        ]

    start_row = _apply_title_block(
        ws,
        title="Fleet Cellular & Modem SLA Report",
        date_range=date_range,
        total_records=len(gateways),
        kpis=kpis,
    )

    r1 = start_row
    r2 = start_row + 1

    ws.row_dimensions[r1].height = 24
    ws.row_dimensions[r2].height = 20

    # 1. Tier 1 Headers
    _merge_and_style_header_block(ws, r1, 1, r2, 1, "No.")
    _merge_and_style_header_block(ws, r1, 2, r2, 2, "Location")
    _merge_and_style_header_block(ws, r1, 3, r2, 3, "Type")
    _merge_and_style_header_block(ws, r1, 4, r1, 5, "Modem Device")
    _merge_and_style_header_block(ws, r1, 6, r1, 8, "SIM Card & Data")
    _merge_and_style_header_block(ws, r1, 9, r1, 11, "CPU – Modem Communication")
    _merge_and_style_header_block(ws, r1, 12, r1, 15, "Network Connection")
    _merge_and_style_header_block(ws, r1, 16, r2, 16, "SLA")

    # 2. Tier 2 Sub-headers
    sub_headers = {
        4: "Name",
        5: "Avg Temp (°C)",
        6: "Provider",
        7: "SIM Card No.",
        8: "Remaining Quota",
        9: "Uptime",
        10: "Downtime",
        11: "Success Rate (%)",
        12: "Uptime",
        13: "Downtime",
        14: "Success Rate (%)",
        15: "Avg RSRP (dBm)",
    }
    for col_idx, text in sub_headers.items():
        _merge_and_style_header_block(
            ws, r2, col_idx, r2, col_idx, text, fill=SUBHEADER_FILL, font=SUBHEADER_FONT
        )

    # 3. Data Rows
    curr_row = r2 + 1
    for idx, gw in enumerate(gateways, 1):
        ws.row_dimensions[curr_row].height = 20
        is_even = (idx % 2 == 0)
        row_fill = ZEBRA_FILL if is_even else None

        sla_val = gw.get("sla")
        if sla_val is None:
            c_sr = float(gw.get("cpu_modem_success_rate", 100.0))
            n_sr = float(gw.get("network_success_rate", 100.0))
            sla_val = round((c_sr + n_sr) / 2.0, 1)

        row_values = [
            idx,
            gw.get("location") or gw.get("id"),
            gw.get("type", "SmartBox Putih"),
            gw.get("modem", "Quectel EC25"),
            f"{gw.get('modem_temp', gw.get('network_avg_temp', 42))}°C",
            gw.get("provider", "Telkomsel"),
            gw.get("sim_number", "-"),
            gw.get("quota_info", "15.4 GB"),
            gw.get("cpu_modem_uptime", "0m"),
            gw.get("cpu_modem_offline", "0m"),
            f"{gw.get('cpu_modem_success_rate', 100.0)}%",
            gw.get("network_uptime", "0m"),
            gw.get("network_offline", "0m"),
            f"{gw.get('network_success_rate', 100.0)}%",
            f"{gw.get('network_avg_rsrp', -85)} dBm",
            f"{sla_val}%",
        ]

        for col_idx, val in enumerate(row_values, 1):
            cell = ws.cell(row=curr_row, column=col_idx, value=val)
            cell.font = DATA_FONT
            cell.border = BORDER_THIN
            if row_fill:
                cell.fill = row_fill

            if col_idx in [1, 5, 8, 9, 10, 11, 12, 13, 14, 15, 16]:
                cell.alignment = Alignment(horizontal="center", vertical="center")
            else:
                cell.alignment = Alignment(horizontal="left", vertical="center")

            if col_idx in [9, 12]:
                cell.font = Font(name=FONT_FAMILY, size=10, bold=True, color=COLOR_SUCCESS_TEXT)
            elif col_idx in [10, 13]:
                if str(val) not in ["0m", "0", "0h"]:
                    cell.font = Font(name=FONT_FAMILY, size=10, bold=True, color=COLOR_DANGER_TEXT)
            elif col_idx == 16:
                try:
                    num_sla = float(str(val).replace("%", ""))
                    if num_sla >= 98.0:
                        cell.font = Font(name=FONT_FAMILY, size=10, bold=True, color=COLOR_SUCCESS_TEXT)
                    elif num_sla >= 85.0:
                        cell.font = Font(name=FONT_FAMILY, size=10, bold=True, color=COLOR_WARNING_TEXT)
                    else:
                        cell.font = Font(name=FONT_FAMILY, size=10, bold=True, color=COLOR_DANGER_TEXT)
                except Exception:
                    pass

        curr_row += 1

    _autofit_columns(ws)

    stream = io.BytesIO()
    wb.save(stream)
    stream.seek(0)
    return stream


# ─── 3. Health Report Excel Builder (2-Tier Header with Merged Groups) ────────

def build_health_report_excel(
    gateways: List[Dict[str, Any]],
    summary: Optional[Dict[str, Any]] = None,
    date_range: Optional[str] = None,
) -> io.BytesIO:
    """
    Builds a formatted Excel workbook for System Health Report matching the UI:
    - 2-Tier grouped headers: Location, Type, CPU (Avg, Max, >80%), RAM (Avg, Max, >80%),
      Storage Usage (Avg, Max, >90%), Storage Health (Status, Life %),
      System Temperature (Avg, Peak), Uptime SLA (Duration, SLA %)
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "System Health Report"
    ws.views.sheetView[0].showGridLines = True

    kpis = []
    if summary:
        kpis = [
            ("Total Gateway", summary.get("total_gateways", len(gateways))),
            ("Normal Health", f"{summary.get('normal', 0)} ({summary.get('normal_percent', 0)}%)"),
            ("Warning / Caution", f"{summary.get('warning', 0)} ({summary.get('warning_percent', 0)}%)"),
            ("Critical Health", f"{summary.get('critical', 0)} ({summary.get('critical_percent', 0)}%)"),
        ]

    start_row = _apply_title_block(
        ws,
        title="Fleet System Health Performance Report",
        date_range=date_range,
        total_records=len(gateways),
        kpis=kpis,
    )

    r1 = start_row
    r2 = start_row + 1

    ws.row_dimensions[r1].height = 24
    ws.row_dimensions[r2].height = 20

    # 1. Tier 1 Headers
    _merge_and_style_header_block(ws, r1, 1, r2, 1, "No.")
    _merge_and_style_header_block(ws, r1, 2, r2, 2, "Location")
    _merge_and_style_header_block(ws, r1, 3, r2, 3, "Type")
    _merge_and_style_header_block(ws, r1, 4, r1, 5, "Device")
    _merge_and_style_header_block(ws, r1, 6, r1, 8, "CPU Status")
    _merge_and_style_header_block(ws, r1, 9, r1, 11, "RAM Status")
    _merge_and_style_header_block(ws, r1, 12, r1, 14, "Storage Usage")
    _merge_and_style_header_block(ws, r1, 15, r1, 16, "Storage Health")
    _merge_and_style_header_block(ws, r1, 17, r1, 18, "System Temperature")
    _merge_and_style_header_block(ws, r1, 19, r2, 19, "SLA")

    # 2. Tier 2 Sub-headers
    sub_headers = {
        4: "Uptime",
        5: "Downtime",
        6: "Avg (%)",
        7: "Max (%)",
        8: ">80% Duration",
        9: "Avg (%)",
        10: "Max (%)",
        11: ">80% Duration",
        12: "Avg (%)",
        13: "Max (%)",
        14: ">90% Duration",
        15: "Health Status",
        16: "Life (%)",
        17: "Avg (°C)",
        18: "Peak (°C)",
    }
    for col_idx, text in sub_headers.items():
        _merge_and_style_header_block(
            ws, r2, col_idx, r2, col_idx, text, fill=SUBHEADER_FILL, font=SUBHEADER_FONT
        )

    # 3. Data Rows
    curr_row = r2 + 1
    for idx, gw in enumerate(gateways, 1):
        ws.row_dimensions[curr_row].height = 20
        is_even = (idx % 2 == 0)
        row_fill = ZEBRA_FILL if is_even else None

        sla_val = gw.get("sla")
        if sla_val is None:
            sla_val = gw.get("uptime_pct", 100.0)
        sla_val = round(float(sla_val), 1)

        row_values = [
            idx,
            gw.get("location") or gw.get("id"),
            gw.get("type", "SmartBox Putih"),
            gw.get("uptime_duration", "0m"),
            gw.get("downtime_duration", "0m"),
            f"{gw.get('cpu_avg', 0)}%",
            f"{gw.get('cpu_max', 0)}%",
            gw.get("cpu_gt_80_duration", "-"),
            f"{gw.get('ram_avg', 0)}%",
            f"{gw.get('ram_max', 0)}%",
            gw.get("ram_gt_80_duration", "-"),
            f"{gw.get('sd_avg', 0)}%",
            f"{gw.get('sd_max', 0)}%",
            gw.get("sd_gt_90_duration", "-"),
            gw.get("sd_health_status", "Good"),
            f"{gw.get('sd_life_pct', 100)}%",
            f"{gw.get('temp_avg', 45)}°C",
            f"{gw.get('temp_max', 55)}°C",
            f"{sla_val}%",
        ]

        for col_idx, val in enumerate(row_values, 1):
            cell = ws.cell(row=curr_row, column=col_idx, value=val)
            cell.font = DATA_FONT
            cell.border = BORDER_THIN
            if row_fill:
                cell.fill = row_fill

            if col_idx in [1, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19]:
                cell.alignment = Alignment(horizontal="center", vertical="center")
            else:
                cell.alignment = Alignment(horizontal="left", vertical="center")

            if col_idx == 5:
                down_str = str(val or "0m").strip()
                if down_str not in ["0m", "0s", "0h 00m", "-"]:
                    cell.font = Font(name=FONT_FAMILY, size=10, bold=True, color=COLOR_DANGER_TEXT)
            elif col_idx == 19:
                try:
                    num_sla = float(str(val).replace("%", ""))
                    if num_sla >= 99.5:
                        cell.font = Font(name=FONT_FAMILY, size=10, bold=True, color=COLOR_SUCCESS_TEXT)
                    elif num_sla >= 95.0:
                        cell.font = Font(name=FONT_FAMILY, size=10, bold=True, color=COLOR_WARNING_TEXT)
                    else:
                        cell.font = Font(name=FONT_FAMILY, size=10, bold=True, color=COLOR_DANGER_TEXT)
                except Exception:
                    pass

        curr_row += 1

    _autofit_columns(ws)

    stream = io.BytesIO()
    wb.save(stream)
    stream.seek(0)
    return stream
