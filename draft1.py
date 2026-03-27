import time
import sys
from luma.core.interface.serial import i2c
from luma.core.render import canvas
from luma.oled.device import sh1106
import luma.core.error

def main():
    try:
        # Initialize the port
        serial = i2c(port=1, address=0x3C)
        device = sh1106(serial)
        print("Display found and initialized!")
    except luma.core.error.DeviceNotFoundError:
        print("Error: Display not found at 0x3C.")
        print("Try: Running 'sudo i2cdetect -y 1' to check the address.")
        return
    except Exception as e:
        print(f"Unexpected error: {e}")
        return

    try:
        while True:
            with canvas(device) as draw:
                # Header
                draw.text((30, 0), "MONITOR V1", fill="white")
                draw.line((0, 12, 128, 12), fill="white")
                
                # Hardcoded Data
                draw.text((5, 20), "TEMP:   24.5 C", fill="white")
                draw.text((5, 35), "HUMID:  55 %", fill="white")
                draw.text((5, 50), "WGT:    1.25 kg", fill="white")
            
            time.sleep(1)
            
    except KeyboardInterrupt:
        device.clear()
        print("\nStopping...")

if __name__ == "__main__":
    main()
