import random
import math
from datetime import datetime

class SensorSimulator:
    def __init__(self):
        # Dictionary tracking active anomalies per machine: {machine_id: anomaly_type}
        # Failure types: 'Bearing Wear', 'Overheating', 'Pressure Leak', 'Motor Fault'
        self.active_anomalies = {}
        # Progress of anomaly (from 0.0 to 1.0, increases every second when active)
        self.anomaly_progress = {}

    def trigger_anomaly(self, machine_id: int, anomaly_type: str):
        self.active_anomalies[machine_id] = anomaly_type
        self.anomaly_progress[machine_id] = 0.0

    def clear_anomaly(self, machine_id: int):
        if machine_id in self.active_anomalies:
            del self.active_anomalies[machine_id]
        if machine_id in self.anomaly_progress:
            del self.anomaly_progress[machine_id]

    def generate_next_readings(self, machine_id: int, machine_type: str):
        """
        Generates a 1-second interval reading for all 4 sensor types.
        Calculates normal distributions and adds drift/variance if an anomaly is active.
        """
        now = datetime.utcnow().isoformat() + "Z"
        
        # Base values depending on machine type
        # Default Pump: Vibration=10, Temp=65, Pressure=80, Voltage=220
        # Default Lathe: Vibration=12, Temp=55, Pressure=30, Voltage=220
        # Default Compressor: Vibration=8, Temp=70, Pressure=110, Voltage=220
        
        base_vib = 10.0 if machine_type == "Pump" else (12.0 if machine_type == "Lathe" else 8.0)
        base_temp = 65.0 if machine_type == "Pump" else (55.0 if machine_type == "Lathe" else 70.0)
        base_press = 80.0 if machine_type == "Pump" else (30.0 if machine_type == "Lathe" else 110.0)
        base_volt = 220.0

        # Normal standard deviations
        vib_std = 1.0
        temp_std = 2.0
        press_std = 3.0
        volt_std = 4.0

        # Apply anomaly effects if active
        anomaly = self.active_anomalies.get(machine_id)
        if anomaly:
            # Progress goes from 0.0 to 1.0 over ~45 steps (seconds)
            self.anomaly_progress[machine_id] = min(1.0, self.anomaly_progress[machine_id] + 0.02)
            progress = self.anomaly_progress[machine_id]

            if anomaly == "Bearing Wear":
                # Increase vibration standard deviation significantly (up to 15x)
                vib_std = 1.0 + (14.0 * progress)
                # Introduce high frequency vibrations
                base_vib = base_vib + (5.0 * progress * math.sin(datetime.now().timestamp() * 5.0))
                # Slight temp increase as friction heats up bearing
                base_temp = base_temp + (15.0 * progress)
                
            elif anomaly == "Overheating":
                # Temperature ramps up to over 105 degrees C (Rule limit is 100)
                base_temp = base_temp + (45.0 * progress)
                # Slight vibration increase due to thermal expansion/strain
                vib_std = 1.0 + (2.0 * progress)
                
            elif anomaly == "Pressure Leak":
                # Pressure drops significantly (e.g. from 80 to 25)
                if machine_type == "Compressor":
                    base_press = base_press - (75.0 * progress)
                else:
                    base_press = base_press - (55.0 * progress)
                # Temp might drop or spike depending on system
                base_temp = base_temp - (10.0 * progress)
                # Slight vibration spike from cavitation/fluid turbulence
                vib_std = 1.0 + (3.0 * progress)
                
            elif anomaly == "Motor Fault":
                # Voltage variance increases, kurtosis spikes, random voltage drops/surges
                volt_std = 4.0 + (25.0 * progress)
                # Inject a periodic surge/drop
                base_volt = base_volt + (30.0 * progress * math.cos(datetime.now().timestamp() * 2.0))
                # Slight temp increase
                base_temp = base_temp + (8.0 * progress)

        # Generate actual readings with Gaussian noise
        vib_val = random.gauss(base_vib, vib_std)
        temp_val = random.gauss(base_temp, temp_std)
        press_val = random.gauss(base_press, press_std)
        volt_val = random.gauss(base_volt, volt_std)

        # Ensure values don't go below physical limits
        vib_val = max(0.1, vib_val)
        temp_val = max(10.0, temp_val)
        press_val = max(0.5, press_val)
        volt_val = max(50.0, volt_val)

        return [
            {"time": now, "machine_id": machine_id, "sensor_type": "vibration", "value": round(vib_val, 2), "unit": "g"},
            {"time": now, "machine_id": machine_id, "sensor_type": "temp", "value": round(temp_val, 2), "unit": "C"},
            {"time": now, "machine_id": machine_id, "sensor_type": "pressure", "value": round(press_val, 2), "unit": "PSI"},
            {"time": now, "machine_id": machine_id, "sensor_type": "voltage", "value": round(volt_val, 2), "unit": "V"}
        ]
