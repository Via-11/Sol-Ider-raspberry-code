# Sol-ider — Solar Food Waste Dehydrator
> Raspberry Pi 4 · Flask · SQLite · DHT22 × 2 · HX711 × 4 · OLED SH1106

---

## 📁 Project Structure

```
solider/
├── app.py                    ← Main Flask app
├── requirements.txt
├── data/
│   └── solider.db            ← SQLite database (auto-created)
├── templates/
│   ├── landing.html
│   └── dashboard.html
└── static/
    ├── css/dashboard.css
    └── js/dashboard.js
```

---

## 🚀 Running on Raspberry Pi (with hardware)

```bash
# 1. Install dependencies
pip install flask adafruit-circuitpython-dht RPi.GPIO hx711 luma.oled luma.core

# 2. Run
python app.py
```

Open: `http://<pi-ip>:5000`

---

## 💻 Simulation Mode (no hardware — for dev/demo)

```bash
pip install flask
SIMULATE=1 python app.py
```

Then click **"🌱 Seed Demo Data"** in the dashboard header to populate charts.

---

## 🔌 Hardware Wiring

| Component     | Pi GPIO Pin |
|---------------|-------------|
| DHT22 #1 DATA | GPIO 4 (D4) |
| DHT22 #2 DATA | GPIO 17 (D17) |
| HX711 DT      | GPIO 5 |
| HX711 SCK     | GPIO 6 |
| OLED SDA      | I2C SDA (GPIO 2) |
| OLED SCL      | I2C SCL (GPIO 3) |

---

## ⚙️ Key Settings (app.py)

| Setting | Default | Description |
|---|---|---|
| `READ_INTERVAL` | 10s | How often sensors are polled |
| `SESSION_START_WEIGHT` | 5.0 kg | Weight threshold to auto-start a session |
| `SESSION_END_WEIGHT` | 2.0 kg | Weight threshold to auto-end |
| `SESSION_END_HUMIDITY` | 30% | Humidity threshold to auto-end |
| `CALIBRATION_FACTOR` | 29.34 | HX711 calibration — adjust per your scale |

---

## 📡 API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/api/live` | GET | Latest sensor readings + session state |
| `/api/history?hours=24` | GET | Sensor history (last N hours) |
| `/api/records?days=30` | GET | Drying records (last N days) |
| `/api/start_session` | POST | Manually start a drying session |
| `/api/end_session` | POST | Manually end and record current session |
| `/api/records/add` | POST | Manually add a drying record |
| `/api/seed` | POST | Seed demo data (simulation only) |

---

## 🌱 Session Logic

A **drying session** starts when:
- Weight ≥ 5 kg is detected (auto), **OR**
- User clicks **▶ Start Drying Session** (manual)

A session **ends and is recorded** when:
- Humidity ≤ 30% **AND** weight ≤ 2 kg (auto), **OR**
- User clicks **Mark as Complete ✓** (manual)

---

## 🚢 Deploying on GitHub

The app runs on `localhost:5000` by default. For remote access on your LAN (e.g., from a phone/laptop), just connect to the Pi's IP:

```bash
python app.py
# Access from any device on same network:
# http://192.168.1.xxx:5000
```

For public deployment, use `gunicorn` + `ngrok` or host on Render/Railway.
