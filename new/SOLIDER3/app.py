"""
SOL-IDER - app.py
Solar Food Waste Dehydrator and Grinder
Raspberry Pi 4

Sensors: DHT22 x2, HX711 x1 (4 load cells via Wheatstone bridge), OLED SH1106

Run normally (with hardware):
  source /home/pi/myvenv/bin/activate
  cd /home/pi/solider2
  python app.py

Run in simulation mode (no hardware needed):
  SIMULATE=1 python app.py

Open browser:
  http://localhost:5000
  http://<your-pi-ip>:5000
"""

import os
import time
import threading
import random
import sqlite3
from datetime import datetime, timedelta
from flask import Flask, render_template, jsonify, request

# --------------------------------------------------------------------
# SIMULATION MODE
# Set SIMULATE=1 to run without any hardware connected
# --------------------------------------------------------------------

SIMULATE = os.environ.get("SIMULATE", "0") == "1"

if SIMULATE:
    print("[INFO] Simulation mode - no hardware required.")
else:
    print("[INFO] Hardware mode - connecting to sensors.")

# --------------------------------------------------------------------
# FLASK AND DATABASE SETUP
# --------------------------------------------------------------------

app     = Flask(__name__)
BASE_DIR = os.path.dirname(__file__)
DB_PATH  = os.path.join(BASE_DIR, 'data', 'solider.db')


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_db()
    c    = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS sensor_readings (
        id        INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT,
        temp1     REAL,
        temp2     REAL,
        hum1      REAL,
        hum2      REAL,
        weight    REAL
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS drying_records (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        start_time       TEXT,
        end_time         TEXT,
        initial_weight   REAL,
        final_weight     REAL,
        weight_reduced   REAL,
        duration_minutes INTEGER,
        avg_humidity     REAL,
        avg_temperature  REAL,
        notes            TEXT
    )''')
    conn.commit()
    conn.close()
    print("[DB] Database ready.")


# --------------------------------------------------------------------
# SETTINGS
# --------------------------------------------------------------------

# HX711 pins
HX_DOUT = 5
HX_SCK  = 6

# Load cell calibration
# Converted from Arduino: calibration_factor = 29.34 (grams)
# Python: 29.34 x 1000 = 29340.0 (per kg)
REFERENCE_UNIT = 29340.0
ZERO_THRESHOLD = 0.005

# OLED
OLED_PORT = 1
OLED_ADDR = 0x3C

# How often to read sensors (seconds)
READ_INTERVAL = 10

# Drying session thresholds
SESSION_START_WEIGHT = 4.0   # kg - session starts when weight >= this
SESSION_END_WEIGHT   = 2.0   # kg - session ends when weight <= this
SESSION_END_HUMIDITY = 30.0  # %  - session ends when humidity <= this


# --------------------------------------------------------------------
# SHARED STATE
# This is updated by the sensor thread and read by Flask routes
# --------------------------------------------------------------------

lock = threading.Lock()

state = {
    'temp1':   0.0,
    'temp2':   0.0,
    'hum1':    0.0,
    'hum2':    0.0,
    'weight':  0.0,
    'last_updated':         None,
    'simulate':             SIMULATE,
    'drying_in_progress':   False,
    'session_start_time':   None,
    'session_start_weight': None,
    # Internal accumulators for session averages
    '_hum_sum':   0.0,
    '_temp_sum':  0.0,
    '_readings':  0,
}


# --------------------------------------------------------------------
# SESSION HELPERS
# --------------------------------------------------------------------

def start_session(weight, trigger='auto'):
    """Start a new drying session."""
    state['drying_in_progress']   = True
    state['session_start_time']   = datetime.now()
    state['session_start_weight'] = weight
    state['_hum_sum']             = 0.0
    state['_temp_sum']            = 0.0
    state['_readings']            = 0
    print(f"[SESSION] Started ({trigger}) | weight: {weight:.3f} kg")


def end_session(weight, conn):
    """End the current drying session and save to database."""
    end_time   = datetime.now()
    start_time = state['session_start_time']
    start_w    = state['session_start_weight']
    readings   = max(1, state['_readings'])
    avg_hum    = round(state['_hum_sum']  / readings, 2)
    avg_temp   = round(state['_temp_sum'] / readings, 2)
    duration   = int((end_time - start_time).total_seconds() / 60)
    reduced    = round(start_w - weight, 3)

    conn.execute('''INSERT INTO drying_records
        (start_time, end_time, initial_weight, final_weight,
         weight_reduced, duration_minutes, avg_humidity, avg_temperature, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''', (
        start_time.strftime('%Y-%m-%d %H:%M:%S'),
        end_time.strftime('%Y-%m-%d %H:%M:%S'),
        start_w, weight, reduced, duration,
        avg_hum, avg_temp,
        'Auto-logged: humidity <=30% and weight <=2kg'
    ))

    state['drying_in_progress']   = False
    state['session_start_time']   = None
    state['session_start_weight'] = None
    state['_hum_sum']             = 0.0
    state['_temp_sum']            = 0.0
    state['_readings']            = 0
    print(f"[SESSION] Complete! Reduced {reduced:.3f} kg in {duration} min. Saved to database.")


# --------------------------------------------------------------------
# DHT22 HELPER
# --------------------------------------------------------------------

def read_dht(sensor, label):
    """Read DHT22 safely. Returns (temp, humidity) or (None, None)."""
    for _ in range(3):
        try:
            t = sensor.temperature
            h = sensor.humidity
            if t is not None and h is not None:
                return round(float(t), 1), round(float(h), 1)
        except RuntimeError:
            time.sleep(0.5)
        except Exception as e:
            print(f"[{label}] Error: {e}")
            break
    return None, None


# --------------------------------------------------------------------
# SIMULATION HELPER
# --------------------------------------------------------------------

_sim_step = 0

def sim_values():
    """Generate realistic fake sensor data for testing."""
    global _sim_step
    _sim_step += 1
    t  = round(38 + 6 * abs((_sim_step % 100) / 50 - 1) + random.uniform(-0.5, 0.5), 1)
    h  = round(max(20, 70 - _sim_step * 0.3 + random.uniform(-1, 1)), 1)
    w  = round(max(1.8, 5.0 - _sim_step * 0.02 + random.uniform(-0.05, 0.05)), 3)
    return t, round(t + random.uniform(-0.3, 0.3), 1), h, round(h + random.uniform(-0.3, 0.3), 1), w


# --------------------------------------------------------------------
# SENSOR LOOP - runs in background thread
# ALL hardware code is inside this function
# --------------------------------------------------------------------

def sensor_loop():
    """
    Reads all sensors in a loop.
    Updates shared state and database.
    Updates OLED display.
    All hardware imports and init are inside here.
    """

    print("[SENSORS] Sensor thread starting...")

    # -- Initialize hardware (only if not simulating) --
    dht1    = None
    dht2    = None
    hx      = None
    oled    = None
    oled_canvas = None
    offset_val  = 0.0

    if not SIMULATE:

        # DHT22
        try:
            import board
            import adafruit_dht
            dht1 = adafruit_dht.DHT22(board.D4)
            dht2 = adafruit_dht.DHT22(board.D17)
            print("[SENSORS] DHT22 Sensor 1 (GPIO 4)  - OK")
            print("[SENSORS] DHT22 Sensor 2 (GPIO 17) - OK")
        except Exception as e:
            print(f"[SENSORS] DHT22 init failed: {e}")

        # HX711 load cell
        # Using hx.get_data_mean() - correct method for this Python library
        # Weight formula: (raw - tare_offset) / REFERENCE_UNIT
        # Converted from Arduino: (raw - tare) / calibration_factor
        # where calibration_factor = 29.34 grams = 29340.0 per kg
        try:
            from hx711 import HX711
            hx = HX711(dout_pin=HX_DOUT, pd_sck_pin=HX_SCK)
            print("[SENSORS] HX711 - OK")
            print("[SENSORS] Taring load cell - keep scale EMPTY...")
            # Take 30 samples for accurate tare (same logic as Arduino's tare())
            offset_val = hx.get_data_mean(30)
            print(f"[SENSORS] Tare complete. Offset: {offset_val:.0f}")
        except Exception as e:
            print(f"[SENSORS] HX711 init failed: {e}")
            hx = None

        # OLED display
        try:
            from luma.core.interface.serial import i2c as luma_i2c
            from luma.core.render import canvas as luma_canvas
            from luma.oled.device import sh1106 as luma_sh1106
            serial      = luma_i2c(port=OLED_PORT, address=OLED_ADDR)
            oled        = luma_sh1106(serial)
            oled_canvas = luma_canvas
            print("[SENSORS] OLED SH1106 - OK")

            # Startup screen
            with oled_canvas(oled) as draw:
                draw.text((20,  5), "SOL-IDER",       fill="white")
                draw.text(( 5, 20), "Solar Dehydrator", fill="white")
                draw.text((10, 38), "Starting...",    fill="white")
            time.sleep(2)

        except Exception as e:
            print(f"[SENSORS] OLED init failed: {e}")
            oled = None

    print("[SENSORS] All sensors ready. Reading every 10 seconds.")
    print("")
    print(f"{'Time':<10}  {'Temp1':>7}  {'H1':>7}  {'Temp2':>7}  {'H2':>7}  {'Weight':>9}")
    print("-" * 60)

    # -- Main reading loop --
    while True:
        try:

            # Read sensors
            if SIMULATE:
                t1, t2, h1, h2, weight = sim_values()

            else:
                # Read DHT22 sensors
                if dht1:
                    t1, h1 = read_dht(dht1, "DHT22-1")
                else:
                    t1, h1 = None, None

                # Small delay required between DHT22 reads
                time.sleep(2.0)

                if dht2:
                    t2, h2 = read_dht(dht2, "DHT22-2")
                else:
                    t2, h2 = None, None

                # Read HX711 load cell
                # get_data_mean(30) = take 30 samples and return the mean
                # This is the correct Python hx711 library method
                # (NOT get_weight_mean which does not exist in this library)
                weight = 0.0
                if hx:
                    try:
                        raw    = hx.get_data_mean(30)
                        weight = (raw - offset_val) / REFERENCE_UNIT
                        if abs(weight) < ZERO_THRESHOLD:
                            weight = 0.0
                        weight = round(weight, 3)
                    except Exception as e:
                        print(f"[HX711] Read error: {e}")
                        weight = state['weight']

                # Fall back to last known values if sensor failed
                t1 = t1 if t1 is not None else state['temp1']
                t2 = t2 if t2 is not None else state['temp2']
                h1 = h1 if h1 is not None else state['hum1']
                h2 = h2 if h2 is not None else state['hum2']

            # Calculate averages
            avg_temp = round((t1 + t2) / 2, 1)
            avg_hum  = round((h1 + h2) / 2, 1)
            now_str  = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # Update shared state
            with lock:
                state['temp1']        = t1
                state['temp2']        = t2
                state['hum1']         = h1
                state['hum2']         = h2
                state['weight']       = weight
                state['last_updated'] = now_str

                # Accumulate session averages
                if state['drying_in_progress']:
                    state['_hum_sum']  += avg_hum
                    state['_temp_sum'] += avg_temp
                    state['_readings'] += 1

            # Save to database
            conn = get_db()
            conn.execute('''INSERT INTO sensor_readings
                (timestamp, temp1, temp2, hum1, hum2, weight)
                VALUES (?, ?, ?, ?, ?, ?)''',
                (now_str, t1, t2, h1, h2, weight))

            # Check drying logic
            with lock:
                in_progress = state['drying_in_progress']

                # Auto-start session when weight loaded
                if not in_progress and weight >= SESSION_START_WEIGHT:
                    start_session(weight, trigger='auto')

                # Auto-end session when food is dried
                elif in_progress and avg_hum <= SESSION_END_HUMIDITY and weight <= SESSION_END_WEIGHT:
                    end_session(weight, conn)

            conn.commit()
            conn.close()

            # Update OLED display
            if oled and oled_canvas:
                try:
                    status = "DRYING" if state['drying_in_progress'] else "IDLE"
                    with oled_canvas(oled) as draw:
                        draw.text((28,  0), "SOL-IDER",              fill="white")
                        draw.line((0, 12, 128, 12),                   fill="white")
                        draw.text(( 0, 15), f"T1:{t1:.1f}C  H1:{h1:.1f}%", fill="white")
                        draw.text(( 0, 27), f"T2:{t2:.1f}C  H2:{h2:.1f}%", fill="white")
                        draw.line((0, 39, 128, 39),                   fill="white")
                        draw.text(( 0, 42), f"WEIGHT: {weight:.3f} kg", fill="white")
                        draw.text(( 0, 54), f"STATUS: {status}",     fill="white")
                except Exception as e:
                    print(f"[OLED] Update error: {e}")

            # Print to terminal
            now = time.strftime("%H:%M:%S")
            print(f"{now:<10}  {t1:>7.1f}  {h1:>7.1f}  {t2:>7.1f}  {h2:>7.1f}  {weight:>9.3f}")

        except Exception as e:
            print(f"[LOOP ERROR] {e}")

        time.sleep(READ_INTERVAL)


# --------------------------------------------------------------------
# FLASK ROUTES
# --------------------------------------------------------------------

@app.route('/')
def home():
    return render_template('landing.html')


@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')


@app.route('/about')
def about():
    return render_template('about.html')


@app.route('/api/live')
def api_live():
    with lock:
        snap = dict(state)
    # Convert datetime to string if needed
    if snap.get('session_start_time') and not isinstance(snap['session_start_time'], str):
        snap['session_start_time'] = snap['session_start_time'].strftime('%Y-%m-%d %H:%M:%S')
    # Remove internal accumulators from response
    snap.pop('_hum_sum',  None)
    snap.pop('_temp_sum', None)
    snap.pop('_readings', None)
    return jsonify(snap)


@app.route('/api/history')
def api_history():
    days  = request.args.get('days', 7, type=int)
    since = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
    conn  = get_db()
    rows  = conn.execute('''
        SELECT timestamp,
               (temp1 + temp2) / 2 as avg_temp,
               (hum1  + hum2)  / 2 as avg_hum,
               weight
        FROM sensor_readings
        WHERE timestamp >= ?
        ORDER BY timestamp ASC
    ''', (since,)).fetchall()
    conn.close()
    data = [dict(r) for r in rows]
    # Downsample to max 300 points for performance
    if len(data) > 300:
        step = len(data) // 300
        data = data[::step]
    return jsonify(data)


@app.route('/api/records')
def api_records():
    days  = request.args.get('days', 30, type=int)
    since = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
    conn  = get_db()
    rows  = conn.execute(
        'SELECT * FROM drying_records WHERE end_time >= ? ORDER BY end_time DESC',
        (since,)).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route('/api/analysis')
def api_analysis():
    days  = request.args.get('days', 30, type=int)
    since = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
    conn  = get_db()
    recs  = [dict(r) for r in conn.execute(
        'SELECT * FROM drying_records WHERE end_time >= ?', (since,)
    ).fetchall()]
    conn.close()

    if not recs:
        return jsonify({'error': 'No records in this range'})

    n             = len(recs)
    total_reduced = sum(r['weight_reduced'] for r in recs)
    avg_dur       = sum(r['duration_minutes'] for r in recs) / n
    avg_pct       = sum(r['weight_reduced'] / r['initial_weight'] * 100 for r in recs) / n
    daily, weekly = {}, {}

    for r in recs:
        day        = r['end_time'][:10]
        daily[day] = daily.get(day, 0) + r['weight_reduced']
        wk         = f"W{datetime.strptime(r['end_time'][:10], '%Y-%m-%d').isocalendar()[1]}"
        weekly[wk] = weekly.get(wk, 0) + r['weight_reduced']

    rating = (
        'Excellent'         if avg_pct >= 55 else
        'Good'              if avg_pct >= 40 else
        'Fair'              if avg_pct >= 25 else
        'Needs Improvement'
    )

    return jsonify({
        'total_batches':           n,
        'total_weight_reduced_kg': round(total_reduced, 2),
        'avg_duration_minutes':    round(avg_dur, 1),
        'avg_reduction_pct':       round(avg_pct, 1),
        'efficiency_rating':       rating,
        'daily_totals':            daily,
        'weekly_totals':           weekly,
        'records':                 recs,
    })


@app.route('/api/records/add', methods=['POST'])
def api_records_add():
    """Manually add a drying record."""
    d = request.get_json()
    try:
        start   = datetime.strptime(d['start_time'], '%Y-%m-%d %H:%M:%S')
        end     = datetime.strptime(d['end_time'],   '%Y-%m-%d %H:%M:%S')
        iw      = float(d['initial_weight'])
        fw      = float(d['final_weight'])
        dur     = int((end - start).total_seconds() / 60)
        reduced = round(iw - fw, 3)
        conn    = get_db()
        conn.execute('''INSERT INTO drying_records
            (start_time, end_time, initial_weight, final_weight,
             weight_reduced, duration_minutes, avg_humidity, avg_temperature, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''', (
            start.strftime('%Y-%m-%d %H:%M:%S'),
            end.strftime('%Y-%m-%d %H:%M:%S'),
            iw, fw, reduced, dur,
            float(d.get('avg_humidity', 0)),
            float(d.get('avg_temperature', 0)),
            d.get('notes', 'Manual entry')
        ))
        conn.commit()
        conn.close()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'msg': str(e)}), 400


@app.route('/api/start_session', methods=['POST'])
def api_start_session():
    """Manually start a drying session."""
    with lock:
        if state['drying_in_progress']:
            return jsonify({'ok': False, 'msg': 'Session already in progress.'}), 400
        start_session(state['weight'], trigger='manual')
    return jsonify({'ok': True, 'msg': 'Drying session started manually.'})


@app.route('/api/end_session', methods=['POST'])
def api_end_session():
    """Manually end the current drying session."""
    with lock:
        if not state['drying_in_progress']:
            return jsonify({'ok': False, 'msg': 'No active session.'}), 400
        conn = get_db()
        end_session(state['weight'], conn)
        conn.commit()
        conn.close()
    return jsonify({'ok': True, 'msg': 'Session ended and saved.'})


# --------------------------------------------------------------------
# MAIN - Start everything
# --------------------------------------------------------------------

if __name__ == '__main__':
    print("")
    print("=" * 50)
    print("  SOL-IDER")
    print("  Solar Integrated Food Waste Dehydrator")
    print(f"  Mode: {'SIMULATION' if SIMULATE else 'HARDWARE'}")
    print("=" * 50)
    print("")

    # Initialize database
    init_db()
    print("")

    # Start sensor thread in background
    # daemon=True means it stops automatically when the app stops
    sensor_thread = threading.Thread(target=sensor_loop, daemon=True)
    sensor_thread.start()
    print("")

    # Start Flask web server
    print("=" * 50)
    print("  Web app is running!")
    print("=" * 50)
    print("")
    print("  This Pi         : http://localhost:5000")
    print("  Other devices   : http://<your-pi-ip>:5000")
    print("  Find IP address : hostname -I")
    print("")
    print("  Press Ctrl+C to stop.")
    print("")

    app.run(host='0.0.0.0', port=5000, debug=False)
