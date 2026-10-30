"""
Standalone seed script for ProtectQube AIOps database.
Usage:
    python seed.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.database import SessionLocal, engine
from app.core.config import settings
from app.core.security import get_password_hash
from app.models.base_models import (
    User,
    Role,
    ModuleType,
    Module,
    RoleModule,
    EmailVerificationStatus,
)


def seed():
    print(f"[*] Connecting to database: {settings.DATABASE_URL.split('@')[-1] if '@' in settings.DATABASE_URL else settings.DATABASE_URL} ...")
    db = SessionLocal()
    try:
        admin_role = db.query(Role).filter(Role.name == "Super Admin").first()
        if not admin_role:
            admin_role = Role(
                id="a93f5563-415b-4733-8f46-5249009da2c3",
                name="Super Admin",
                alias="super-admin",
                color="#2563eb",
                description="Full access to ProtectQube AIOps Gateway and Telemetry",
            )
            db.add(admin_role)
            print("[+] Seeded Role: Super Admin")
        else:
            print("[OK] Role already exists: Super Admin")

        engineer_role = db.query(Role).filter(Role.name == "Field Engineer").first()
        if not engineer_role:
            engineer_role = Role(
                id="ec52373a-c444-453a-a59a-52db228e59af",
                name="Field Engineer",
                alias="engineer",
                color="#10b981",
                description="Field technician for gateway inspection and maintenance",
            )
            db.add(engineer_role)
            print("[+] Seeded Role: Field Engineer")
        else:
            print("[OK] Role already exists: Field Engineer")

        db.commit()

        mod_type = db.query(ModuleType).filter(ModuleType.name == "Monitoring").first()
        if not mod_type:
            mod_type = ModuleType(
                id="b11c97a2-1b1a-4f51-b825-911223344556",
                name="Monitoring",
                icon="Activity",
                description="Diagnostic & telemetry monitoring modules",
            )
            db.add(mod_type)
            db.commit()
            print("[+] Seeded ModuleType: Monitoring")
        else:
            print("[OK] ModuleType already exists: Monitoring")

        modules_data = [
            {"id": 1, "name": "Dashboard", "route": "/", "icon": "LayoutDashboard"},
            {"id": 2, "name": "Cellular Connectivity", "route": "#cellular", "icon": "Radio"},
            {"id": 3, "name": "DVR Recording", "route": "#dvr", "icon": "Video"},
            {"id": 4, "name": "System Health", "route": "#system", "icon": "Activity"},
            {"id": 5, "name": "Reports", "route": "#reports", "icon": "FileText"},
        ]

        for m_data in modules_data:
            m = db.query(Module).filter(Module.id == m_data["id"]).first()
            if not m:
                m = Module(
                    id=m_data["id"],
                    module_type_id=mod_type.id,
                    name=m_data["name"],
                    route=m_data["route"],
                    icon=m_data["icon"],
                )
                db.add(m)
                db.commit()
                print(f"[+] Seeded Module: {m_data['name']}")
            else:
                print(f"[OK] Module already exists: {m_data['name']}")

            rm = db.query(RoleModule).filter(
                RoleModule.role_id == admin_role.id,
                RoleModule.module_id == m_data["id"],
            ).first()
            if not rm:
                rm = RoleModule(
                    id=f"rm-admin-mod-{m_data['id']}",
                    role_id=admin_role.id,
                    module_id=m_data["id"],
                    checked=True,
                )
                db.add(rm)
                db.commit()

        admin_user = db.query(User).filter(User.username == "admin").first()
        if not admin_user:
            admin_user = User(
                id="a6066a42-caef-4c20-af86-51d004449ef8",
                name="SmartBox Administrator",
                username="admin",
                email="admin@smartbox.local",
                password=get_password_hash("admin123"),
                role_id=admin_role.id,
                email_verified=True,
                email_verification_status=EmailVerificationStatus.VERIFIED,
            )
            db.add(admin_user)
            db.commit()
            print("[+] Seeded default User: 'admin' (password: admin123)")
        else:
            print("[OK] User already exists: 'admin'")

        print("\n[SUCCESS] All baseline tables and auth seed data are ready!")
        print(f"Login credentials:\n  Username: admin\n  Password: admin123")

    except Exception as e:
        db.rollback()
        print(f"[ERROR] Seeding failed: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
