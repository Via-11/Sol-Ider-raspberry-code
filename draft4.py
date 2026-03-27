import time
import board
import adafruit_dht
from luma.core.interface.serial import i2c
from luma.core.render import canvas
from luma.oled.device import sh1106
import RPi.GPIO as GPIO
from hx711 import HX711

def get_median_reading(hx, samples=15):
    """Takes multiple readings, sorts them, and returns the middle one."""
    readings = []
    for _ in range(samples):
        readings.append(hx.get_data_mean(1))
    readings.sort()
    return readings[len(readings) // 2]

def main():
    # --- UPDATE THIS AFTER YOUR TEST ---
    REFERENCE_UNIT = 443800.0  # Put your new calculated number here
    
    dht_device = adafruit_dht.DHT22(board.D4)
    hx = HX711(dout_pin=6, pd_sck_pin=5)
    
    try:
        serial = i2c(port=1, address=0x3C)
        device = sh1106(serial)
    except Exception as e:
        print(f"OLED Error: {e}")
        return

    print("Taring scale... Keep it empty.")
    # Use median for tare to ensure a clean baseline
    offset_val = get_median_reading(hx, 20)
    print(f"Tare complete. Offset: {offset_val}")

    try:
        while True:
            try:
                # Read Sensors with a tiny gap to prevent CPU jitter
                temp = dht_device.temperature
                humid = dht_device.humidity
                time.sleep(0.1) 
                
                # Get a stable raw reading using the median filter
                raw_reading = get_median_reading(hx, 15)

                # Calculate Weight
                weight_kg = (raw_reading - offset_val) / REFERENCE_UNIT

                # "Zero out" noise (anything less than 10 grams is ignored)
                if abs(weight_kg) < 0.010:
                    weight_kg = 0.0

                print(f"Weight: {weight_kg:.3f} kg | Raw: {raw_reading}")

                with canvas(device) as draw:
                    draw.text((32, 2), "LIVE MONITOR", fill="white")
                    draw.line((0, 15, 128, 15), fill="white")

                    if temp is not None:
                        draw.text((5, 22), f"TEMP:    {temp:.1f} C", fill="white")
                        draw.text((5, 36), f"HUMID:   {humid:.1f} %", fill="white")
                    else:
                        draw.text((5, 22), "DHT Reading...", fill="white")

                    draw.text((5, 50), f"WEIGHT:  {weight_kg:.3f} kg", fill="white")

            except RuntimeError: # DHT22 often fails to read; just skip that loop
                pass
            except Exception as e:
                print(f"Loop Error: {e}")

            time.sleep(1)

    except KeyboardInterrupt:
        print("\nCleaning up...")
        dht_device.exit()
        GPIO.cleanup()

if __name__ == "__main__":
    main()
