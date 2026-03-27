import time
import board
import adafruit_dht
from luma.core.interface.serial import i2c
from luma.core.render import canvas
from luma.oled.device import sh1106
import RPi.GPIO as GPIO
from hx711 import HX711

def main():
    # --- CALIBRATION SETTING ---
    # Based on your raw data (181,958 net raw / 0.410 kg)
    REFERENCE_UNIT = 443800.0 
    
    dht_device = adafruit_dht.DHT22(board.D4)
    hx = HX711(dout_pin=6, pd_sck_pin=5)
    
    try:
        serial = i2c(port=1, address=0x3C)
        device = sh1106(serial)
    except Exception as e:
        print(f"OLED Error: {e}")
        return

    print("Taring scale... Keep it empty.")
    # We use the offset you found: 3090
    offset_val = hx.get_data_mean(20)
    print(f"Tare complete. Offset: {offset_val}")

    try:
        while True:
            try:
                temp = dht_device.temperature
                humid = dht_device.humidity
                
                # Using 30 samples for better stability on the Pi 4
                raw_reading = hx.get_data_mean(30)
                
                # Calculate Weight
                weight_kg = (raw_reading - offset_val) / REFERENCE_UNIT
                
                # Small jump protection (removes ghost weight when empty)
                if abs(weight_kg) < 0.005:
                    weight_kg = 0.0

                print(f"Weight: {weight_kg:.3f} kg")

                with canvas(device) as draw:
                    draw.text((32, 2), "LIVE MONITOR", fill="white")
                    draw.line((0, 15, 128, 15), fill="white")
                    
                    if temp is not None:
                        draw.text((5, 22), f"TEMP:    {temp:.1f} C", fill="white")
                        draw.text((5, 36), f"HUMID:   {humid:.1f} %", fill="white")
                    else:
                        draw.text((5, 22), "DHT Reading...", fill="white")
                    
                    draw.text((5, 50), f"WEIGHT:  {weight_kg:.3f} kg", fill="white")

            except RuntimeError:
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
