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

logger = logging.getLogger(__name__)


def init_db():
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables verified/created successfully.")

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

    except Exception as e:
        logger.error(f"Error during db initialization/seeding: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    init_db()
