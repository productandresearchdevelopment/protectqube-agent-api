import logging
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.core.database import Base, engine, SessionLocal
from app.core.security import get_password_hash
from app.models.base_models import (
    User,
    Role,
    ModuleType,
    Module,
    RoleModule,
    EmailVerificationStatus,
    GatewayTelemetryHistory,
)
from app.models.notification_models import (
    NotificationEvent,
    NotificationDestination,
)

logger = logging.getLogger(__name__)


def init_db():
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables verified successfully.")

    # Automatically ensure audit columns (created_by, updated_by, deleted_by) exist
    tables = [
        "users", "roles", "module_types", "modules", "role_modules",
        "uploads", "user_sessions", "user_otps",
        "gateway_telemetry_histories", "gateway_incident_alerts",
        "notification_events", "notification_destinations",
        "notification_targets", "notifications", "notification_deliveries"
    ]
    try:
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            for tbl in tables:
                for col in ["created_by", "updated_by", "deleted_by"]:
                    try:
                        conn.execute(text(f'ALTER TABLE "{tbl}" ADD COLUMN IF NOT EXISTS "{col}" VARCHAR(36);'))
                    except Exception:
                        pass
        logger.info("Audit columns (created_by, updated_by, deleted_by) verified on all tables.")
    except Exception as e:
        logger.warning(f"Could not verify audit columns on tables: {e}")

    db: Session = SessionLocal()
    try:
        admin_role = db.query(Role).filter(Role.name == "Super Admin").first()
        if not admin_role:
            admin_role = Role(
                name="Super Admin",
                alias="super-admin",
                color="#2563eb",
                description="Full access to SmartBox Gateway and Diagnostics",
            )
            db.add(admin_role)
            db.commit()
            db.refresh(admin_role)

            engineer_role = Role(
                name="Field Engineer",
                alias="engineer",
                color="#10b981",
                description="Field technician for gateway inspection and maintenance",
            )
            db.add(engineer_role)
            db.commit()

        admin_user = db.query(User).filter(User.username == "admin").first()
        if not admin_user:
            admin_user = User(
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
            logger.info("Default user 'admin' (password: admin123) seeded.")

        # Seed Standard Module Types matching reference (mini-erp)
        standard_types_data = [
            {"name": "directory", "description": "Directory", "icon": "FoldersIcon"},
            {"name": "label menu", "description": "Label displayed in frontend menu", "icon": "LabelIcon"},
            {"name": "route accordion", "description": "Route displayed in accordion", "icon": "MenuCircleIcon"},
            {"name": "route menu", "description": "Route displayed in frontend menu", "icon": "MoreIcon"},
            {"name": "route hidden", "description": "Hidden routes not displayed in frontend", "icon": "FolderBlockIcon"},
            {"name": "service api", "description": "CRUD operations and API endpoints", "icon": "ApiIcon"},
        ]

        type_map = {}
        for t_info in standard_types_data:
            m_type = db.query(ModuleType).filter(ModuleType.name == t_info["name"]).first()
            if not m_type:
                m_type = ModuleType(
                    name=t_info["name"],
                    description=t_info["description"],
                    icon=t_info["icon"],
                )
                db.add(m_type)
                db.commit()
                db.refresh(m_type)
            else:
                m_type.description = t_info["description"]
                m_type.icon = t_info["icon"]
                db.commit()
            type_map[t_info["name"]] = m_type.id

        # Clean up legacy dummy modules if present
        legacy_dummy_names = ["Dashboard", "Connectivity Agent", "DVR Health Agent", "System Health Agent", "Settings"]
        for dummy_name in legacy_dummy_names:
            d_mods = db.query(Module).filter(Module.name == dummy_name).all()
            for dm in d_mods:
                db.query(RoleModule).filter(RoleModule.module_id == dm.id).delete()
                db.delete(dm)
        db.commit()

        # Real System Modules
        route_menu_id = type_map["route menu"]
        service_api_id = type_map["service api"]
        label_menu_id = type_map["label menu"]

        modules_to_seed = [
            # Top-level menus
            {"name": "Overview", "route": "/", "icon": "LayoutDashboard", "type_id": route_menu_id, "description": "Dashboard overview and real-time summary"},
            {"name": "System Health", "route": "/system-health", "icon": "Cpu", "type_id": route_menu_id, "description": "CPU, RAM, SD card, and host metrics"},
            {"name": "Cellular", "route": "/cellular", "icon": "Radio", "type_id": route_menu_id, "description": "Cellular connection, signal, and operator status"},
            {"name": "DVR & Recording", "route": "/dvr-recording", "icon": "Video", "type_id": route_menu_id, "description": "NVR/DVR connectivity and video recording status"},
            
            # Reports Group
            {"name": "Reports", "route": "/reports", "icon": "FileText", "type_id": route_menu_id, "description": "System historical data and export reports"},
            {"name": "Report Cellular", "route": "/reports/cellular", "icon": "Radio", "type_id": route_menu_id, "parent_name": "Reports", "description": "Cellular SLA and uptime reports"},
            {"name": "Report DVR", "route": "/reports/dvr", "icon": "Video", "type_id": route_menu_id, "parent_name": "Reports", "description": "DVR recording SLA and downtime reports"},
            {"name": "Report Health", "route": "/reports/health", "icon": "Activity", "type_id": route_menu_id, "parent_name": "Reports", "description": "System health and resource reports"},
            
            # Reports Service APIs (Level 2)
            {"name": "Export Report Cellular Excel", "route": "/api/v1/reports/cellular/export", "type_id": service_api_id, "parent_name": "Report Cellular", "description": "Export cellular SLA report to Excel"},
            {"name": "Export Report DVR Excel", "route": "/api/v1/reports/dvr/export", "type_id": service_api_id, "parent_name": "Report DVR", "description": "Export DVR health report to Excel"},
            {"name": "Export Report Health Excel", "route": "/api/v1/reports/health/export", "type_id": service_api_id, "parent_name": "Report Health", "description": "Export system health report to Excel"},

            # Configuration Group
            {"name": "Configuration", "route": "/configuration", "icon": "Settings", "type_id": route_menu_id, "description": "System RBAC, users, roles, modules, and integrations"},
            {"name": "Users Management", "route": "/configuration/users", "icon": "Users", "type_id": route_menu_id, "parent_name": "Configuration", "description": "Manage system users and access"},
            {"name": "Roles Management", "route": "/configuration/roles", "icon": "Shield", "type_id": route_menu_id, "parent_name": "Configuration", "description": "Manage user roles and permissions matrix"},
            {"name": "Modules Management", "route": "/configuration/modules", "icon": "Layers", "type_id": route_menu_id, "parent_name": "Configuration", "description": "Manage system capabilities and navigation tree"},
            {"name": "Integrations", "route": "/configuration/integrations", "icon": "Network", "type_id": route_menu_id, "parent_name": "Configuration", "description": "Third-party platform integrations"},
            {"name": "Notifications", "route": "/configuration/notifications", "icon": "Bell", "type_id": route_menu_id, "parent_name": "Configuration", "description": "Alert channels and rules"},

            # Users Service APIs (Level 2)
            {"name": "User Get All", "route": "/api/v1/users", "type_id": service_api_id, "parent_name": "Users Management", "description": "Retrieve all system users"},
            {"name": "User Create", "route": "/api/v1/users", "type_id": service_api_id, "parent_name": "Users Management", "description": "Create a new user account"},
            {"name": "User Update", "route": "/api/v1/users/:id", "type_id": service_api_id, "parent_name": "Users Management", "description": "Update user details and assignment"},
            {"name": "User Delete", "route": "/api/v1/users/:id", "type_id": service_api_id, "parent_name": "Users Management", "description": "Delete or deactivate user account"},

            # Roles Service APIs (Level 2)
            {"name": "Role Get All", "route": "/api/v1/roles", "type_id": service_api_id, "parent_name": "Roles Management", "description": "Retrieve all defined roles"},
            {"name": "Role Create", "route": "/api/v1/roles", "type_id": service_api_id, "parent_name": "Roles Management", "description": "Create a new security role"},
            {"name": "Role Update Permissions", "route": "/api/v1/roles/:id/permissions", "type_id": service_api_id, "parent_name": "Roles Management", "description": "Update role module permissions matrix"},

            # Modules Service APIs (Level 2)
            {"name": "Module Get All", "route": "/api/v1/modules", "type_id": service_api_id, "parent_name": "Modules Management", "description": "Retrieve all modules hierarchical tree"},
            {"name": "Module Create", "route": "/api/v1/modules", "type_id": service_api_id, "parent_name": "Modules Management", "description": "Create a new module or service node"},
            {"name": "Module Delete", "route": "/api/v1/modules/:id", "type_id": service_api_id, "parent_name": "Modules Management", "description": "Delete module node from system"},
        ]

        for m_data in modules_to_seed:
            existing_m = db.query(Module).filter(
                (Module.name == m_data["name"])
            ).first()
            parent_id = None
            if "parent_name" in m_data:
                parent_mod = db.query(Module).filter(Module.name == m_data["parent_name"]).first()
                if parent_mod:
                    parent_id = parent_mod.id

            if not existing_m:
                new_m = Module(
                    module_type_id=m_data["type_id"],
                    parent_id=parent_id,
                    name=m_data["name"],
                    route=m_data["route"],
                    icon=m_data.get("icon"),
                    description=m_data.get("description"),
                )
                db.add(new_m)
                db.commit()
                db.refresh(new_m)
                rm = db.query(RoleModule).filter(
                    RoleModule.role_id == admin_role.id, RoleModule.module_id == new_m.id
                ).first()
                if not rm:
                    rm = RoleModule(role_id=admin_role.id, module_id=new_m.id, checked=True)
                    db.add(rm)
            else:
                existing_m.module_type_id = m_data["type_id"]
                if parent_id is not None:
                    existing_m.parent_id = parent_id
                if m_data.get("route"):
                    existing_m.route = m_data["route"]
                if m_data.get("icon"):
                    existing_m.icon = m_data["icon"]
                if m_data.get("description"):
                    existing_m.description = m_data["description"]
                db.commit()

                # Ensure admin role has permission
                rm = db.query(RoleModule).filter(
                    RoleModule.role_id == admin_role.id, RoleModule.module_id == existing_m.id
                ).first()
                if not rm:
                    rm = RoleModule(role_id=admin_role.id, module_id=existing_m.id, checked=True)
                    db.add(rm)
        db.commit()

        events_data = [
            {
                "event_code": "gateway_cellular_down",
                "name": "Cellular Connection Down",
                "category": "cellular",
                "description": "Triggered when SIM is removed, no signal, or PPP drops",
            },
            {
                "event_code": "gateway_cellular_recovered",
                "name": "Cellular Connection Recovered",
                "category": "cellular",
                "description": "Triggered when cellular connection returns to normal",
            },
            {
                "event_code": "gateway_modem_disconnected",
                "name": "Modem-CPU Disconnected",
                "category": "hardware",
                "description": "Triggered when modem USB port is unplugged or hardware lost",
            },
            {
                "event_code": "gateway_modem_reconnected",
                "name": "Modem-CPU Reconnected",
                "category": "hardware",
                "description": "Triggered when modem hardware reconnects to CPU",
            },
            {
                "event_code": "gateway_dvr_offline",
                "name": "NVR / Camera Offline",
                "category": "dvr",
                "description": "Triggered when NVR or camera becomes unreachable over LAN",
            },
            {
                "event_code": "gateway_dvr_recovered",
                "name": "NVR / Camera Recovered",
                "category": "dvr",
                "description": "Triggered when NVR resumes recording or becomes online",
            },
        ]

        for ed in events_data:
            existing_ev = db.query(NotificationEvent).filter(NotificationEvent.event_code == ed["event_code"]).first()
            if not existing_ev:
                ev = NotificationEvent(**ed)
                db.add(ev)
        db.commit()


    except Exception as e:
        logger.error(f"Error during db initialization/seeding: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    init_db()
