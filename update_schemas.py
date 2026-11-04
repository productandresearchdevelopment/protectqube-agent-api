import re

def update_cellular():
    path = "backend/app/schemas/cellular_report.py"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    
    old_block = """class TroubleEventItem(BaseModel):
    no: int
    start_time: str
    end_time: str
    duration: str
    cause: str"""
    
    new_block = """class TroubleEventItem(BaseModel):
    no: int
    start_time: str
    end_time: str
    duration: str
    cause: Optional[str] = None
    category: Optional[str] = None
    metric: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    reason: Optional[str] = None
    status: Optional[str] = "Resolved"
    duration_minutes: Optional[float] = None
    date_str: Optional[str] = None
    telemetry_history_id: Optional[int] = None"""

    content = content.replace("\r\n", "\n")
    if old_block in content:
        content = content.replace(old_block, new_block)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        print("Updated cellular_report.py")
    else:
        print("old_block not found in cellular_report.py")

def update_dvr():
    path = "backend/app/schemas/dvr_report.py"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    
    old_block = """class DVRReportTroubleEvent(BaseModel):
    no: int
    start_time: str
    end_time: str
    duration: str
    category: str
    description: str"""
    
    new_block = """class DVRReportTroubleEvent(BaseModel):
    no: int
    start_time: str
    end_time: str
    duration: str
    category: Optional[str] = None
    description: Optional[str] = None
    metric: Optional[str] = None
    title: Optional[str] = None
    cause: Optional[str] = None
    reason: Optional[str] = None
    status: Optional[str] = "Resolved"
    duration_minutes: Optional[float] = None
    date_str: Optional[str] = None
    telemetry_history_id: Optional[int] = None"""

    content = content.replace("\r\n", "\n")
    if old_block in content:
        content = content.replace(old_block, new_block)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        print("Updated dvr_report.py")
    else:
        print("old_block not found in dvr_report.py")

if __name__ == "__main__":
    update_cellular()
    update_dvr()

