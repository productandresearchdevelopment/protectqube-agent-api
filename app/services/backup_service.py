import asyncio
import logging
import os
import re
import secrets
import shutil
import subprocess
import tempfile
import zipfile
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import unquote, urlparse
from zoneinfo import ZoneInfo

from minio import Minio

from app.core.config import settings

logger = logging.getLogger("backup-service")

MAX_BACKUP_DAYS = 7
RESTRICT_RE = re.compile(r"(?i)^\\(un)?restrict\b")
SECURITY_LABEL_RE = re.compile(r"(?i)^SECURITY LABEL\b")
BACKUP_FOLDER_RE = re.compile(r"backup/(\d{8})/")


def get_minio_client() -> Minio:
    endpoint = settings.MINIO_ENDPOINT
    if settings.MINIO_PORT and settings.MINIO_PORT not in (80, 443):
        endpoint = f"{settings.MINIO_ENDPOINT}:{settings.MINIO_PORT}"

    return Minio(
        endpoint=endpoint,
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=settings.MINIO_USE_SSL,
    )


def parse_db_url(db_url: str):
    clean_url = db_url.replace("postgresql+psycopg2://", "postgresql://").replace(
        "postgresql+asyncpg://", "postgresql://"
    )
    parsed = urlparse(clean_url)
    return {
        "host": parsed.hostname or "localhost",
        "port": str(parsed.port or 5432),
        "user": unquote(parsed.username or "postgres"),
        "password": unquote(parsed.password or ""),
        "dbname": parsed.path.lstrip("/"),
    }


def clean_sql_file(input_path: str, output_path: str):
    with open(input_path, "r", encoding="utf-8", errors="replace") as fin, open(
        output_path, "w", encoding="utf-8"
    ) as fout:
        last_line_blank = False
        for line in fin:
            if RESTRICT_RE.match(line) or SECURITY_LABEL_RE.match(line):
                continue
            if not line.strip():
                if not last_line_blank:
                    fout.write("\n")
                last_line_blank = True
                continue
            last_line_blank = False
            fout.write(line)


def cleanup_old_backups(
    client: Minio, bucket: str, env: str, tz: ZoneInfo, days_old: int = MAX_BACKUP_DAYS
):
    logger.info(f"[BACKUP] Checking for backups older than {days_old} days in MinIO...")
    prefix = f"{env}/backup/"
    now = datetime.now(tz)
    to_delete = []

    try:
        objects = client.list_objects(bucket, prefix=prefix, recursive=True)
        for obj in objects:
            match = BACKUP_FOLDER_RE.search(obj.object_name)
            if not match:
                continue
            folder_str = match.group(1)
            try:
                folder_date = datetime.strptime(folder_str, "%Y%m%d").replace(tzinfo=tz)
                if (now - folder_date).days >= days_old:
                    to_delete.append(obj.object_name)
            except ValueError:
                continue

        if not to_delete:
            logger.info("[BACKUP] No old backups found to clean up.")
            return

        logger.info(f"[BACKUP] Removing {len(to_delete)} expired backup object(s) from MinIO...")
        for obj_name in to_delete:
            client.remove_object(bucket, obj_name)
            logger.info(f"[BACKUP] Old backup removed: {obj_name}")
    except Exception as exc:
        logger.warning(f"[BACKUP] Cleanup warning: {exc}")


def perform_database_backup():
    logger.info("[BACKUP] Starting database backup to MinIO...")

    db_config = parse_db_url(settings.DATABASE_URL)
    if not db_config["dbname"]:
        logger.error("[BACKUP] Database name could not be parsed from DATABASE_URL.")
        return

    tz = ZoneInfo("Asia/Jakarta")
    now = datetime.now(tz)
    date_segment = now.strftime("%Y%m%d_%H%M%S")
    date_folder = date_segment[:8]

    tmp_dir = tempfile.mkdtemp(prefix=f"backup_{date_segment}_")
    try:
        db_name = db_config["dbname"]
        sql_path = os.path.join(tmp_dir, f"{db_name}_{date_segment}.sql")
        sql_clean_path = os.path.join(tmp_dir, f"{db_name}_{date_segment}_clean.sql")
        dump_path = os.path.join(tmp_dir, f"{db_name}_{date_segment}.dump")
        zip_path = os.path.join(tmp_dir, f"{db_name}_{date_segment}.zip")

        env_vars = os.environ.copy()
        if db_config["password"]:
            env_vars["PGPASSWORD"] = db_config["password"]

        # 1. Plain SQL dump
        logger.info("[BACKUP] Running pg_dump (plain SQL)...")
        plain_cmd = [
            "pg_dump",
            "-h", db_config["host"],
            "-p", db_config["port"],
            "-U", db_config["user"],
            "-d", db_name,
            "-F", "p",
            "--no-owner",
            "--no-privileges",
            "--no-acl",
            "--no-security-labels",
            "--column-inserts",
            "--clean",
            "--if-exists",
            "--encoding=UTF8",
            "-f", sql_path,
        ]
        res = subprocess.run(plain_cmd, env=env_vars, capture_output=True, text=True)
        if res.returncode != 0:
            logger.error(f"[BACKUP] pg_dump (plain) failed: {res.stderr}")
            return

        # 2. Clean SQL file
        logger.info("[BACKUP] Cleaning SQL file...")
        clean_sql_file(sql_path, sql_clean_path)
        os.replace(sql_clean_path, sql_path)

        # 3. Custom dump (.dump)
        logger.info("[BACKUP] Running pg_dump (custom .dump)...")
        custom_cmd = [
            "pg_dump",
            "-h", db_config["host"],
            "-p", db_config["port"],
            "-U", db_config["user"],
            "-d", db_name,
            "-F", "c",
            "-f", dump_path,
        ]
        res = subprocess.run(custom_cmd, env=env_vars, capture_output=True, text=True)
        if res.returncode != 0:
            logger.error(f"[BACKUP] pg_dump (custom) failed: {res.stderr}")
            return

        # 4. Compress into ZIP
        logger.info("[BACKUP] Compressing backup into ZIP archive...")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            if os.path.exists(sql_path):
                zf.write(sql_path, arcname=os.path.basename(sql_path))
            if os.path.exists(dump_path):
                zf.write(dump_path, arcname=os.path.basename(dump_path))

        # 5. Upload to MinIO
        client = get_minio_client()
        bucket = settings.MINIO_BUCKET_NAME
        if not client.bucket_exists(bucket):
            client.make_bucket(bucket)

        file_name = f"backup_{date_segment}_{secrets.token_hex(4)}.zip"
        object_key = f"{settings.ENVIRONMENT}/backup/{date_folder}/{file_name}"

        logger.info(f"[BACKUP] Uploading {zip_path} to MinIO bucket '{bucket}' as '{object_key}'...")
        client.fput_object(
            bucket_name=bucket,
            object_name=object_key,
            file_path=zip_path,
            content_type="application/zip",
            metadata={
                "Original-Name": file_name,
                "Database": db_name,
                "Timestamp": date_segment,
                "Env": settings.ENVIRONMENT,
            },
        )
        logger.info(f"[BACKUP] Backup uploaded successfully: {object_key}")

        # 6. Rotate old backups in MinIO (keep latest 7 days)
        cleanup_old_backups(client, bucket, settings.ENVIRONMENT, tz, MAX_BACKUP_DAYS)
        logger.info("[BACKUP] Database backup completed successfully!")
    except Exception as exc:
        logger.error(f"[BACKUP] Database backup failed: {exc}", exc_info=True)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


async def run_backup_scheduler():
    logger.info("[BACKUP] Starting daily database backup scheduler (target: 23:59 WIB)...")
    while True:
        try:
            tz = ZoneInfo("Asia/Jakarta")
            now = datetime.now(tz)

            target = now.replace(hour=23, minute=59, second=0, microsecond=0)
            if now >= target:
                target = (now + timedelta(days=1)).replace(
                    hour=23, minute=59, second=0, microsecond=0
                )

            sleep_seconds = (target - now).total_seconds()
            logger.info(
                f"[BACKUP] Next backup scheduled at {target.strftime('%Y-%m-%d %H:%M:%S')} WIB (in {int(sleep_seconds)}s)"
            )

            while sleep_seconds > 0:
                step = min(sleep_seconds, 60.0)
                await asyncio.sleep(step)
                now = datetime.now(tz)
                sleep_seconds = (target - now).total_seconds()

            logger.info("[BACKUP] Scheduled time reached. Executing daily database backup...")
            await asyncio.to_thread(perform_database_backup)

            # Sleep 120s to prevent duplicate execution in the same minute
            await asyncio.sleep(120)
        except asyncio.CancelledError:
            logger.info("[BACKUP] Daily backup scheduler cancelled.")
            break
        except Exception as exc:
            logger.error(f"[BACKUP] Error in backup scheduler loop: {exc}", exc_info=True)
            await asyncio.sleep(60)
