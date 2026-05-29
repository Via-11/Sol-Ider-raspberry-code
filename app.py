import os
import time
import threading
import random
import sqlite3
import subprocess
from datetime import datetime, timedelta
from flask import Flask, render_template, jsonify, request

SIMULATE = os.environ.get("SIMULATE", "0") == "1"

if SIMULATE:
    print("[INFO] Simulation mode - no hardware required.")
else:
    print("[INFO] Hardware mode - connecting to sensors.")

# FLASK AND DATABASE SETUP

app      = Flask(__name__)
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

# SETTINGS

HX_DOUT        = 5
HX_SCK         = 6
REFERENCE_UNIT = 23588.0
ZERO_THRESHOLD = 0.005
OLED_PORT      = 1
OLED_ADDR      = 0x3C
READ_INTERVAL  = 10

# Drying completion thresholds 
MOISTURE_REMOVAL_TARGET = 0.80          # 80 % moisture removed

HUM_THRESHOLD_SMALL = 35.0            
HUM_THRESHOLD_LARGE = 40.0          
HUM_CUTOFF_WEIGHT   = 1.0             

# Auto-start
SESSION_START_WEIGHT = 0.200         

# SHARED STATE

lock = threading.Lock()

state = {
    'temp1':   0.0,
    'temp2':   0.0,
    'hum1':    0.0,
    'hum2':    0.0,
    'weight':  0.0,
    'last_updated':               None,
    'simulate':                   SIMULATE,
    'drying_in_progress':         False,
    'session_start_time':         None,
    'session_start_weight':       None,
    'session_end_weight_target':  None,   # 20% of start weight
    'session_end_humidity_target':None,   # 35% or 40% depending on load
    '_hum_sum':   0.0,
    '_temp_sum':  0.0,
    '_readings':  0,
}

# SESSION HELPERS

def _compute_thresholds(initial_weight):
    """Return (end_weight_kg, end_humidity_pct) for a given starting weight."""
    end_weight  = round(initial_weight * (1.0 - MOISTURE_REMOVAL_TARGET), 3)
    end_humidity = HUM_THRESHOLD_SMALL if initial_weight <= HUM_CUTOFF_WEIGHT else HUM_THRESHOLD_LARGE
    return end_weight, end_humidity


def start_session(weight, trigger='auto'):
    end_w, end_h = _compute_thresholds(weight)
    state['drying_in_progress']      = True
    state['session_start_time']      = datetime.now()
    state['session_start_weight']    = weight
    state['session_end_weight_target']   = end_w
    state['session_end_humidity_target'] = end_h
    state['_hum_sum']                = 0.0
    state['_temp_sum']               = 0.0
    state['_readings']               = 0
    print(f"[SESSION] Started ({trigger}) | weight: {weight:.3f} kg | "
          f"target ≤ {end_w:.3f} kg & ≤ {end_h:.1f}% RH")


def end_session(weight, conn):
    end_time   = datetime.now()
    start_time = state['session_start_time']
    start_w    = state['session_start_weight']
    end_w_tgt  = state.get('session_end_weight_target', start_w * 0.20)
    end_h_tgt  = state.get('session_end_humidity_target', 40.0)
    readings   = max(1, state['_readings'])
    avg_hum    = round(state['_hum_sum']  / readings, 2)
    avg_temp   = round(state['_temp_sum'] / readings, 2)
    duration   = int((end_time - start_time).total_seconds() / 60)
    reduced    = round(start_w - weight, 3)
    red_pct    = round((reduced / start_w) * 100, 1) if start_w > 0 else 0.0

    notes = (
        f"Auto-logged: humidity ≤{end_h_tgt}% and weight ≤{end_w_tgt:.3f} kg "
        f"({int(MOISTURE_REMOVAL_TARGET*100)}% moisture removal target)"
    )

    conn.execute('''INSERT INTO drying_records
        (start_time, end_time, initial_weight, final_weight,
         weight_reduced, duration_minutes, avg_humidity, avg_temperature, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''', (
        start_time.strftime('%Y-%m-%d %H:%M:%S'),
        end_time.strftime('%Y-%m-%d %H:%M:%S'),
        start_w, weight, reduced, duration,
        avg_hum, avg_temp, notes
    ))

    state['drying_in_progress']          = False
    state['session_start_time']          = None
    state['session_start_weight']        = None
    state['session_end_weight_target']   = None
    state['session_end_humidity_target'] = None
    state['_hum_sum']                    = 0.0
    state['_temp_sum']                   = 0.0
    state['_readings']                   = 0
    print(f"[SESSION] Complete! Reduced {reduced:.3f} kg ({red_pct}%) in {duration} min. Saved.")

# DHT22 

def read_dht(sensor, label):
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

# SIMULATION HELPER

_sim_step = 0
_sim_start_w = 1.0   

def sim_values():
    global _sim_step, _sim_start_w
    _sim_step += 1
    if state['drying_in_progress'] and state['session_start_weight']:
        _sim_start_w = state['session_start_weight']

    target_w = _sim_start_w * 0.20
    span_w   = _sim_start_w - target_w
    progress = min(1.0, _sim_step / 200)          

    t = round(38 + 6 * abs((_sim_step % 100) / 50 - 1) + random.uniform(-0.5, 0.5), 1)
    h = round(max(18, 70 - progress * 40 + random.uniform(-1, 1)), 1)   # 70 → 30 %
    w = round(max(target_w, _sim_start_w - span_w * progress + random.uniform(-0.01, 0.01)), 3)
    return t, round(t + random.uniform(-0.3, 0.3), 1), h, round(h + random.uniform(-0.3, 0.3), 1), w

# SENSOR LOOP

def sensor_loop():
    print("[SENSORS] Sensor thread starting...")

    dht1        = None
    dht2        = None
    hx          = None
    oled        = None
    oled_canvas = None
    offset_val  = 0.0

    if not SIMULATE:
        try:
            import board
            import adafruit_dht
            dht1 = adafruit_dht.DHT22(board.D4)
            dht2 = adafruit_dht.DHT22(board.D17)
            print("[SENSORS] DHT22 x2 - OK")
        except Exception as e:
            print(f"[SENSORS] DHT22 init failed: {e}")

        try:
            from hx711 import HX711
            hx = HX711(dout_pin=HX_DOUT, pd_sck_pin=HX_SCK)
            print("[SENSORS] HX711 - OK. Taring (keep scale EMPTY)...")
            offset_val = hx.get_data_mean(30)
            print(f"[SENSORS] Tare complete. Offset: {offset_val:.0f}")
        except Exception as e:
            print(f"[SENSORS] HX711 init failed: {e}")
            hx = None

        try:
            from luma.core.interface.serial import i2c as luma_i2c
            from luma.core.render import canvas as luma_canvas_mod
            from luma.oled.device import sh1106 as luma_sh1106
            serial      = luma_i2c(port=OLED_PORT, address=OLED_ADDR)
            oled        = luma_sh1106(serial)
            oled_canvas = luma_canvas_mod
            print("[SENSORS] OLED SH1106 - OK")
            with oled_canvas(oled) as draw:
                draw.text((20,  5), "SOL-IDER",        fill="white")
                draw.text(( 5, 20), "Solar Dehydrator", fill="white")
                draw.text((10, 38), "Starting...",      fill="white")
            time.sleep(2)
        except Exception as e:
            print(f"[SENSORS] OLED init failed: {e}")
            oled = None

    print("[SENSORS] Ready. Reading every 10 seconds.")
    print(f"{'Time':<10}  {'Temp1':>7}  {'H1':>7}  {'Temp2':>7}  {'H2':>7}  {'Weight':>9}")
    print("-" * 60)

    while True:
        try:
            if SIMULATE:
                t1, t2, h1, h2, weight = sim_values()
            else:
                t1, h1 = read_dht(dht1, "DHT22-1") if dht1 else (None, None)
                time.sleep(2.0)
                t2, h2 = read_dht(dht2, "DHT22-2") if dht2 else (None, None)

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

                t1 = t1 if t1 is not None else state['temp1']
                t2 = t2 if t2 is not None else state['temp2']
                h1 = h1 if h1 is not None else state['hum1']
                h2 = h2 if h2 is not None else state['hum2']

            avg_temp = round((t1 + t2) / 2, 1)
            avg_hum  = round((h1 + h2) / 2, 1)
            now_str  = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            with lock:
                state['temp1']        = t1
                state['temp2']        = t2
                state['hum1']         = h1
                state['hum2']         = h2
                state['weight']       = weight
                state['last_updated'] = now_str
                if state['drying_in_progress']:
                    state['_hum_sum']  += avg_hum
                    state['_temp_sum'] += avg_temp
                    state['_readings'] += 1

            conn = get_db()
            conn.execute(
                'INSERT INTO sensor_readings (timestamp,temp1,temp2,hum1,hum2,weight) VALUES (?,?,?,?,?,?)',
                (now_str, t1, t2, h1, h2, weight))

            with lock:
                in_progress = state['drying_in_progress']
                if not in_progress and weight >= SESSION_START_WEIGHT:                    start_session(weight, trigger='auto')
                elif in_progress and avg_hum <= state['session_end_humidity_target'] and weight <= state['session_end_weight_target']:
                    end_session(weight, conn)

            conn.commit()
            conn.close()

            if oled and oled_canvas:
                try:
                    status = "DRYING" if state['drying_in_progress'] else "IDLE"
                    with oled_canvas(oled) as draw:
                        draw.text((28,  0), "SOL-IDER",                     fill="white")
                        draw.line((0, 12, 128, 12),                          fill="white")
                        draw.text(( 0, 15), f"T1:{t1:.1f}C  H1:{h1:.1f}%",  fill="white")
                        draw.text(( 0, 27), f"T2:{t2:.1f}C  H2:{h2:.1f}%",  fill="white")
                        draw.line((0, 39, 128, 39),                          fill="white")
                        draw.text(( 0, 42), f"WEIGHT: {weight:.3f} kg",     fill="white")
                        draw.text(( 0, 54), f"STATUS: {status}",            fill="white")
                except Exception as e:
                    print(f"[OLED] Update error: {e}")

            now = time.strftime("%H:%M:%S")
            print(f"{now:<10}  {t1:>7.1f}  {h1:>7.1f}  {t2:>7.1f}  {h2:>7.1f}  {weight:>9.3f}")

        except Exception as e:
            print(f"[LOOP ERROR] {e}")

        time.sleep(READ_INTERVAL)

# FLASK ROUTES

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
    if snap.get('session_start_time') and not isinstance(snap['session_start_time'], str):
        snap['session_start_time'] = snap['session_start_time'].strftime('%Y-%m-%d %H:%M:%S')
    snap.pop('_hum_sum',  None)
    snap.pop('_temp_sum', None)
    snap.pop('_readings', None)

    if snap['drying_in_progress'] and snap['session_start_weight']:
        sw = snap['session_start_weight']
        cw = snap['weight']
        tgt_w = snap.get('session_end_weight_target') or round(sw * 0.20, 3)
        removed = max(0, sw - cw)
        to_remove = max(0, sw - tgt_w)
        snap['weight_progress_pct'] = round((removed / to_remove * 100) if to_remove > 0 else 0, 1)
    else:
        snap['weight_progress_pct'] = 0.0

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


@app.route('/api/summary')
def api_summary():
    """Summary statistics for the Records tab — totals and averages."""
    days  = request.args.get('days', 30, type=int)
    since = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
    conn  = get_db()
    recs  = [dict(r) for r in conn.execute(
        'SELECT * FROM drying_records WHERE end_time >= ? AND initial_weight > 0',
        (since,)
    ).fetchall()]
    conn.close()

    if not recs:
        return jsonify({
            'total_batches': 0, 'total_kg_processed': 0,
            'total_kg_reduced': 0, 'avg_reduction_pct': 0,
            'avg_duration_hours': 0, 'avg_temperature': 0, 'avg_humidity': 0,
        })

    n = len(recs)
    return jsonify({
        'total_batches':      n,
        'total_kg_processed': round(sum(r['initial_weight']  for r in recs), 2),
        'total_kg_reduced':   round(sum(r['weight_reduced']  for r in recs), 2),
        'avg_reduction_pct':  round(sum(r['weight_reduced'] / r['initial_weight'] * 100 for r in recs) / n, 1),
        'avg_duration_hours': round(sum(r['duration_minutes'] for r in recs) / n / 60, 1),
        'avg_temperature':    round(sum(r['avg_temperature']  for r in recs) / n, 1),
        'avg_humidity':       round(sum(r['avg_humidity']     for r in recs) / n, 1),
    })


@app.route('/api/records/add', methods=['POST'])
def api_records_add():
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
    with lock:
        if state['drying_in_progress']:
            return jsonify({'ok': False, 'msg': 'Session already in progress.'}), 400
        w = state['weight']
        if w < SESSION_START_WEIGHT:
            return jsonify({'ok': False, 'msg': f'No food waste detected on scale (weight: {w:.3f} kg). Please load the tray first.'}), 400
        start_session(w, trigger='manual')
        tgt_w = state['session_end_weight_target']
        tgt_h = state['session_end_humidity_target']
    return jsonify({
        'ok': True,
        'msg': f'Drying session started. Target: ≤{tgt_w:.3f} kg & ≤{tgt_h:.0f}% RH.',
        'initial_weight': w,
        'target_weight':  tgt_w,
        'target_humidity': tgt_h,
    })


@app.route('/api/end_session', methods=['POST'])
def api_end_session():
    with lock:
        if not state['drying_in_progress']:
            return jsonify({'ok': False, 'msg': 'No active session.'}), 400
        conn = get_db()
        end_session(state['weight'], conn)
        conn.commit()
        conn.close()
    return jsonify({'ok': True, 'msg': 'Session ended and saved.'})

@app.route('/api/shutdown', methods=['POST'])
def api_shutdown():
    """Shut down the Raspberry Pi safely."""
    def do_shutdown():
        time.sleep(2)  
        subprocess.call(['sudo', 'shutdown', '-h', 'now'])
    threading.Thread(target=do_shutdown, daemon=True).start()
    return jsonify({'ok': True, 'msg': 'Shutting down in 2 seconds...'})


@app.route('/api/reboot', methods=['POST'])
def api_reboot():
    """Reboot the Raspberry Pi."""
    def do_reboot():
        time.sleep(2)
        subprocess.call(['sudo', 'reboot'])
    threading.Thread(target=do_reboot, daemon=True).start()
    return jsonify({'ok': True, 'msg': 'Rebooting in 2 seconds...'})


# MAIN

if __name__ == '__main__':
    print("")
    print("=" * 50)
    print("  SOL-IDER")
    print("  Solar Integrated Food Waste Dehydrator")
    print(f"  Mode: {'SIMULATION' if SIMULATE else 'HARDWARE'}")
    print("=" * 50)
    print("")
    init_db()
    print("")
    sensor_thread = threading.Thread(target=sensor_loop, daemon=True)
    sensor_thread.start()
    print("")
    print("=" * 50)
    print("  Web app running!")
    print("=" * 50)
    print(f"  This Pi       : http://localhost:5000")
    print(f"  Other devices : http://<your-pi-ip>:5000")
    print(f"  Find IP       : hostname -I")
    print(f"  Press Ctrl+C to stop.")
    print("")
    try:
        app.run(host='0.0.0.0', port=5000, debug=False)
    finally:
        try:
            from luma.core.interface.serial import i2c as luma_i2c
            from luma.oled.device import sh1106 as luma_sh1106
            serial = luma_i2c(port=1, address=0x3C)
            oled   = luma_sh1106(serial)
            oled.clear()
            print("OLED cleared.")
        except Exception as e:
            print(f"OLED could not clear: {e}")
