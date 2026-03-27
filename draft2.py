import time
import board
import adafruit_dht
from luma.core.interface.serial import i2c
from luma.core.render import canvas
from luma.oled.device import sh1106

def main():
    # 1. Initialize DHT22 (on GPIO 4)
    dht_device = adafruit_dht.DHT22(board.D4)

    # 2. Initialize OLED
    serial = i2c(port=1, address=0x3C)
    device = sh1106(serial)

    print("Reading DHT22... Press Ctrl+C to stop.")

    try:
        while True:
            try:
                # Read actual sensor values
                temperature = dht_device.temperature
                humidity = dht_device.humidity
                weight = 5.210  # Placeholder for next step

                with canvas(device) as draw:
                    draw.text((32, 2), "LIVE MONITOR", fill="white")
                    draw.line((0, 15, 128, 15), fill="white")

                    if temperature is not None and humidity is not None:
                        draw.text((5, 22), f"TEMP:    {temperature:.1f} C", fill="white")
                        draw.text((5, 38), f"HUMID:   {humidity:.1f} %", fill="white")
                    else:
                        draw.text((5, 22), "TEMP:    Error", fill="white")

                    draw.text((5, 54), f"WEIGHT:  {weight} kg", fill="white")

            except RuntimeError as error:
                # DHT sensors are finicky; they often fail a single reading.
                # We just print the error and try again.
                print(f"Sensor error: {error.args[0]}")
                time.sleep(2.0)
                continue
            
            time.sleep(2.0)  # DHT22 needs at least 2 seconds between reads

    except KeyboardInterrupt:
        dht_device.exit()
        device.clear()
        print("Clean exit.")

if __name__ == "__main__":
    main()
