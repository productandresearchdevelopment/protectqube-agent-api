import logging
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

        mod_type = db.query(ModuleType).filter(ModuleType.name == "Monitoring").first()
        if not mod_type:
            mod_type = ModuleType(
                name="Monitoring",
                icon="Activity",
                description="Diagnostic & telemetry monitoring modules",
            )
            db.add(mod_type)
            db.commit()
            db.refresh(mod_type)

            modules_to_seed = [
                {"name": "Dashboard", "route": "/dashboard", "icon": "LayoutDashboard"},
                {"name": "Connectivity Agent", "route": "/monitoring/connectivity", "icon": "Radio"},
                {"name": "DVR Health Agent", "route": "/monitoring/dvr", "icon": "Video"},
                {"name": "System Health Agent", "route": "/monitoring/system", "icon": "Cpu"},
                {"name": "Integrations", "route": "/integrations", "icon": "Link"},
                {"name": "Notifications", "route": "/notifications", "icon": "Bell"},
                {"name": "Settings", "route": "/settings", "icon": "Settings"},
            ]

            for m_data in modules_to_seed:
                m = Module(
                    module_type_id=mod_type.id,
                    name=m_data["name"],
                    route=m_data["route"],
                    icon=m_data["icon"],
                )
                db.add(m)
                db.commit()
                db.refresh(m)

                rm = RoleModule(role_id=admin_role.id, module_id=m.id, checked=True)
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
