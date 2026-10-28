# ProtectQube AI Ops - Backend API Gateway

REST API and Telemetry Service untuk pemantauan diagnostik armada SmartBox Edge Gateway. Dibangun menggunakan FastAPI, SQLAlchemy ORM, Alembic migrations, PostgreSQL, dan MQTT Mosquitto broker.

## Tech Stack
* **Framework:** FastAPI / Python 3.10+
* **Database:** PostgreSQL (SQLAlchemy ORM + Alembic)
* **Auth:** JWT (Access & Refresh Tokens) + Passlib Bcrypt
* **Messaging:** Eclipse Mosquitto (MQTT) & WebSockets

## Fitur Utama
1. **Connectivity Agent:** Monitoring Quectel AT commands, provider seluler, nomor kartu, suhu modem, dan sinyal RSRP.
2. **DVR Health Agent:** Monitoring integritas CPU-DVR, retensi storage HDD, dan deteksi channel kamera offline/drop frame.
3. **System Health Agent:** Monitoring CPU, RAM, suhu, dan wear-out endurance life SD card.
4. **Auth & RBAC:** Role-based access control (Super Admin, Field Engineer) dan modular permissions.

## Cara Menjalankan

### 1. Setup Virtual Environment & Dependencies
```bash
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

pip install -r requirements.txt
```

### 2. Setup Environment Variables
Salin template konfigurasi:
```bash
cp .env.example .env
```
Sesuaikan kredensial `DATABASE_URL` (PostgreSQL) dan `SECRET_KEY`.

### 3. Migrasi Database & Seeding Data Awal
```bash
alembic upgrade head
python seed.py
```
*Kredensial Default Super Admin:*
* **Username:** `admin`
* **Password:** `admin123`

### 4. Jalankan Server API
```bash
python main.py
```
* **Swagger API Docs:** [http://localhost:8000/api/v1/docs](http://localhost:8000/api/v1/docs)
* **ReDoc:** [http://localhost:8000/api/v1/redoc](http://localhost:8000/api/v1/redoc)
