import psycopg2
import uuid
from datetime import datetime

DATABASE_URL = "postgresql://postgres:Dysaputra1701@localhost:5433/agent_pqube"

def run_seed():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    # 1. Check parent module Cellular
    cur.execute("SELECT id, name, route FROM modules WHERE id = 8 OR LOWER(name) = 'cellular'")
    cellular_module = cur.fetchone()
    print("Parent Cellular Module:", cellular_module)
    if not cellular_module:
        print("Error: Cellular module not found!")
        return

    parent_id = cellular_module[0]

    # 2. Module type: route hidden (4927388a-0f64-4503-8d11-f001d03cc729) or route menu
    cur.execute("SELECT id FROM module_types WHERE name = 'route hidden'")
    mtype = cur.fetchone()
    module_type_id = mtype[0] if mtype else '4927388a-0f64-4503-8d11-f001d03cc729'
    print("Module Type ID for tabs:", module_type_id)

    # 3. Super Admin role
    cur.execute("SELECT id FROM roles WHERE LOWER(name) LIKE '%super%'")
    super_role = cur.fetchone()
    super_role_id = super_role[0] if super_role else None
    print("Super Admin Role ID:", super_role_id)

    # 4. Define the 6 tabs
    tabs_data = [
        {
            "name": "Cellular - Overview",
            "route": "/cellular/overview",
            "icon": "LayoutDashboard",
            "description": "Tab Overview pada detail Cellular"
        },
        {
            "name": "Cellular - CPU – Modem",
            "route": "/cellular/cpu-modem",
            "icon": "Cpu",
            "description": "Tab CPU & Modem telemetry pada detail Cellular"
        },
        {
            "name": "Cellular - Modem & SIM",
            "route": "/cellular/modem-sim",
            "icon": "Radio",
            "description": "Tab Modem & SIM status pada detail Cellular"
        },
        {
            "name": "Cellular - Signal & Network",
            "route": "/cellular/signal-network",
            "icon": "Network",
            "description": "Tab Signal & Network quality pada detail Cellular"
        },
        {
            "name": "Cellular - Event Log",
            "route": "/cellular/event-log",
            "icon": "FileText",
            "description": "Tab Event Log pada detail Cellular"
        },
        {
            "name": "Cellular - System Logs",
            "route": "/cellular/system-logs",
            "icon": "Terminal",
            "description": "Tab System Logs (telemetri per-menit) pada detail Cellular"
        }
    ]

    now = datetime.utcnow()

    # Get current max module id
    cur.execute("SELECT COALESCE(MAX(id), 0) FROM modules")
    current_max_id = cur.fetchone()[0]

    for item in tabs_data:
        # Check if already exists
        cur.execute("SELECT id FROM modules WHERE name = %s OR route = %s", (item["name"], item["route"]))
        existing = cur.fetchone()
        if existing:
            mod_id = existing[0]
            print(f"Module '{item['name']}' already exists with ID: {mod_id}")
            # Ensure parent_id is set
            cur.execute("UPDATE modules SET parent_id = %s, module_type_id = %s, icon = %s, description = %s, updated_at = %s WHERE id = %s",
                        (parent_id, module_type_id, item["icon"], item["description"], now, mod_id))
        else:
            current_max_id += 1
            mod_id = current_max_id
            cur.execute("""
                INSERT INTO modules (id, module_type_id, parent_id, name, icon, route, description, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (mod_id, module_type_id, parent_id, item["name"], item["icon"], item["route"], item["description"], now, now))
            print(f"Created module '{item['name']}' with ID: {mod_id}")

        # Check and grant role_modules for Super Admin and other admin roles if needed
        if super_role_id:
            cur.execute("SELECT id FROM role_modules WHERE role_id = %s AND module_id = %s", (super_role_id, mod_id))
            rm_exist = cur.fetchone()
            if not rm_exist:
                rm_id = f"rm-{uuid.uuid4().hex[:12]}"
                cur.execute("""
                    INSERT INTO role_modules (id, role_id, module_id, checked, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (rm_id, super_role_id, mod_id, True, now, now))
                print(f"  -> Granted permission to Super Admin (role_module id: {rm_id})")

    conn.commit()
    cur.close()
    conn.close()
    print("\nSUCCESS: All cellular tab modules have been registered and granted to Super Admin!")

if __name__ == "__main__":
    run_seed()
