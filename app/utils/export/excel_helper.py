import io
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

WIB = timezone(timedelta(hours=7))

# ─── Color Palette & Styles ──────────────────────────────────────────────────
# Modern Dark Navy header matching ProtectQube reference pattern
COLOR_HEADER_BG = "1E293B"       # Dark Slate / Navy
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
ZEBRA_FILL = PatternFill(start_color=COLOR_ZEBRA_ROW, end_color=COLOR_ZEBRA_ROW, fill_type="solid")
KPI_FILL = PatternFill(start_color=COLOR_KPI_BG, end_color=COLOR_KPI_BG, fill_type="solid")

HEADER_FONT = Font(name=FONT_FAMILY, size=10, bold=True, color=COLOR_HEADER_TEXT)
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


def _style_table_headers(ws, row_idx: int, headers: List[str]):
    """Styles the main table header row."""
    ws.row_dimensions[row_idx].height = 24
    for col_idx, text in enumerate(headers, 1):
        cell = ws.cell(row=row_idx, column=col_idx, value=text)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = BORDER_THIN


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


# ─── 1. Health Report Excel Builder ──────────────────────────────────────────

def build_health_report_excel(
    gateways: List[Dict[str, Any]],
    summary: Optional[Dict[str, Any]] = None,
    date_range: Optional[str] = None,
) -> io.BytesIO:
    """Builds a formatted Excel workbook for System Health Report."""
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

    headers = [
        "No.",
        "Location",
        "Type",
        "Uptime SLA (%)",
        "CPU Avg (%)",
        "CPU Max (%)",
        "RAM Avg (%)",
        "RAM Max (%)",
        "Storage Avg (%)",
        "Storage Peak (%)",
        "Storage Health",
        "Storage Life (%)",
        "Temp Avg (°C)",
        "Temp Peak (°C)",
        "SLA Status",
    ]
    _style_table_headers(ws, start_row, headers)

    curr_row = start_row + 1
    for idx, gw in enumerate(gateways, 1):
        ws.row_dimensions[curr_row].height = 20
        is_even = (idx % 2 == 0)
        row_fill = ZEBRA_FILL if is_even else None

        sla_pct = float(gw.get("uptime_percent", gw.get("sla", 0.0)))
        status_sla = gw.get("status", "Achieved" if sla_pct >= 99.5 else "Not Achieved")

        values = [
            idx,
            gw.get("location") or gw.get("id"),
            gw.get("type", "SmartBox Putih"),
            round(sla_pct, 1),
            round(float(gw.get("cpu_avg", 0)), 1),
            round(float(gw.get("cpu_max", 0)), 1),
            round(float(gw.get("ram_avg", 0)), 1),
            round(float(gw.get("ram_max", 0)), 1),
            round(float(gw.get("sd_avg", 0)), 1),
            round(float(gw.get("sd_max", 0)), 1),
            gw.get("sd_health_status", "Good"),
            int(gw.get("sd_life_pct", 100)),
            round(float(gw.get("temp_avg", 0)), 1),
            round(float(gw.get("temp_max", 0)), 1),
            status_sla,
        ]

        for col_idx, val in enumerate(values, 1):
            cell = ws.cell(row=curr_row, column=col_idx, value=val)
            cell.font = DATA_FONT
            cell.border = BORDER_THIN
            if row_fill:
                cell.fill = row_fill

            # Formatting & alignment
            if col_idx in [1, 11, 15]:
                cell.alignment = Alignment(horizontal="center", vertical="center")
            elif col_idx in [2, 3]:
                cell.alignment = Alignment(horizontal="left", vertical="center")
            else:
                cell.alignment = Alignment(horizontal="right", vertical="center")

            # Colored SLA status
            if col_idx == 15:
                if "Achieved" in str(val) or "Tercapai" in str(val):
                    cell.font = Font(name=FONT_FAMILY, size=10, bold=True, color=COLOR_SUCCESS_TEXT)
                else:
                    cell.font = Font(name=FONT_FAMILY, size=10, bold=True, color=COLOR_DANGER_TEXT)

        curr_row += 1

    _autofit_columns(ws)
    
    stream = io.BytesIO()
    wb.save(stream)
    stream.seek(0)
    return stream


# ─── 2. Cellular Report Excel Builder ────────────────────────────────────────

def build_cellular_report_excel(
    gateways: List[Dict[str, Any]],
    summary: Optional[Dict[str, Any]] = None,
    date_range: Optional[str] = None,
) -> io.BytesIO:
    """Builds a formatted Excel workbook for Cellular Report."""
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

    headers = [
        "No.",
        "Location",
        "Type",
        "SIM Provider",
        "Signal CSQ",
        "Signal RSRP (dBm)",
        "Cellular IP",
        "Modem Status",
        "Cellular SLA (%)",
        "SLA Status",
    ]
    _style_table_headers(ws, start_row, headers)

    curr_row = start_row + 1
    for idx, gw in enumerate(gateways, 1):
        ws.row_dimensions[curr_row].height = 20
        is_even = (idx % 2 == 0)
        row_fill = ZEBRA_FILL if is_even else None

        sla_pct = float(gw.get("sla_percent", gw.get("sla", gw.get("uptime_percent", 0.0))))
        status_sla = gw.get("status", "Achieved" if sla_pct >= 98.0 else "Not Achieved")

        values = [
            idx,
            gw.get("location") or gw.get("id"),
            gw.get("type", "SmartBox Putih"),
            gw.get("provider", "Telkomsel"),
            gw.get("signal_csq", 24),
            gw.get("signal_rsrp", -85),
            gw.get("ip_address", "-"),
            gw.get("modem_status", "Connected"),
            round(sla_pct, 1),
            status_sla,
        ]

        for col_idx, val in enumerate(values, 1):
            cell = ws.cell(row=curr_row, column=col_idx, value=val)
            cell.font = DATA_FONT
            cell.border = BORDER_THIN
            if row_fill:
                cell.fill = row_fill

            if col_idx in [1, 5, 8, 10]:
                cell.alignment = Alignment(horizontal="center", vertical="center")
            elif col_idx in [2, 3, 4, 7]:
                cell.alignment = Alignment(horizontal="left", vertical="center")
            else:
                cell.alignment = Alignment(horizontal="right", vertical="center")

            if col_idx == 10:
                if "Achieved" in str(val) or "Tercapai" in str(val):
                    cell.font = Font(name=FONT_FAMILY, size=10, bold=True, color=COLOR_SUCCESS_TEXT)
                else:
                    cell.font = Font(name=FONT_FAMILY, size=10, bold=True, color=COLOR_DANGER_TEXT)

        curr_row += 1

    _autofit_columns(ws)

    stream = io.BytesIO()
    wb.save(stream)
    stream.seek(0)
    return stream


# ─── 3. DVR Report Excel Builder ─────────────────────────────────────────────

def build_dvr_report_excel(
    gateways: List[Dict[str, Any]],
    summary: Optional[Dict[str, Any]] = None,
    date_range: Optional[str] = None,
) -> io.BytesIO:
    """Builds a formatted Excel workbook for DVR & Recording Report."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "DVR & Recording Report"
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
        title="Fleet DVR & Camera Recording Performance Report",
        date_range=date_range,
        total_records=len(gateways),
        kpis=kpis,
    )

    headers = [
        "No.",
        "Location",
        "Type",
        "DVR / NVR Model",
        "CPU - DVR Status",
        "Total Cameras",
        "Recording Cameras",
        "Recording Status",
        "Storage Usage (%)",
        "Recording SLA (%)",
        "SLA Status",
    ]
    _style_table_headers(ws, start_row, headers)

    curr_row = start_row + 1
    for idx, gw in enumerate(gateways, 1):
        ws.row_dimensions[curr_row].height = 20
        is_even = (idx % 2 == 0)
        row_fill = ZEBRA_FILL if is_even else None

        sla_pct = float(gw.get("sla", gw.get("sla_percent", 0.0)))
        status_sla = gw.get("status", "Achieved" if sla_pct >= 98.0 else "Not Achieved")

        total_cams = gw.get("total_kamera", 4)
        rec_cams = gw.get("kamera_online", total_cams)
        rec_status_label = f"{rec_cams}/{total_cams} Recording" if gw.get("cpu_dvr") == "Connected" else "Not Recording"

        values = [
            idx,
            gw.get("location") or gw.get("id"),
            gw.get("type", "SmartBox Putih"),
            gw.get("dvr_model", "Hikvision DS-7104NI"),
            gw.get("cpu_dvr", "Connected"),
            total_cams,
            rec_cams,
            rec_status_label,
            round(float(gw.get("storage_usage_percent", 0)), 1),
            round(sla_pct, 1),
            status_sla,
        ]

        for col_idx, val in enumerate(values, 1):
            cell = ws.cell(row=curr_row, column=col_idx, value=val)
            cell.font = DATA_FONT
            cell.border = BORDER_THIN
            if row_fill:
                cell.fill = row_fill

            if col_idx in [1, 5, 6, 7, 8, 11]:
                cell.alignment = Alignment(horizontal="center", vertical="center")
            elif col_idx in [2, 3, 4]:
                cell.alignment = Alignment(horizontal="left", vertical="center")
            else:
                cell.alignment = Alignment(horizontal="right", vertical="center")

            if col_idx == 11:
                if "Achieved" in str(val) or "Tercapai" in str(val):
                    cell.font = Font(name=FONT_FAMILY, size=10, bold=True, color=COLOR_SUCCESS_TEXT)
                else:
                    cell.font = Font(name=FONT_FAMILY, size=10, bold=True, color=COLOR_DANGER_TEXT)

        curr_row += 1

    _autofit_columns(ws)

    stream = io.BytesIO()
    wb.save(stream)
    stream.seek(0)
    return stream

