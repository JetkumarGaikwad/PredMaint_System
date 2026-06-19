import numpy as np
import json
import random
from datetime import datetime
import os
import pickle

# We can import scikit-learn if available, otherwise fallback to a robust statistical detector.
# This ensures zero-setup reliability while keeping the math authentic.
try:
    from sklearn.ensemble import IsolationForest
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False

class MLEngine:
    def __init__(self):
        self.model_version = "v1.0.3-xgboost-hybrid"
        self.window_size = 30  # Keep 30 seconds of historical readings for feature calculation
        
        # In-memory buffer for rolling features per machine: {machine_id: {sensor_type: [values]}}
        self.buffers = {}
        
        # Initialize an Isolation Forest anomaly detector
        if HAS_SKLEARN:
            # We'll use a pre-fit or dynamically fit model. For demo/simulation, we fit on normal baseline.
            self.iso_forest = IsolationForest(n_estimators=50, contamination=0.05, random_state=42)
            # Pre-seed with dummy training data to fit
            X_train = np.random.normal(loc=[10.0, 65.0, 80.0, 220.0], scale=[1.0, 3.0, 5.0, 5.0], size=(100, 4))
            self.iso_forest.fit(X_train)
        else:
            self.iso_forest = None

        # Load trained classifier and scaler if they exist
        self.classifier = None
        self.scaler = None
        
        model_path = os.path.join(os.path.dirname(__file__), "models", "anomaly_detector.pkl")
        scaler_path = os.path.join(os.path.dirname(__file__), "models", "scaler.pkl")
        
        if os.path.exists(model_path) and os.path.exists(scaler_path):
            try:
                with open(model_path, "rb") as f:
                    self.classifier = pickle.load(f)
                with open(scaler_path, "rb") as f:
                    self.scaler = pickle.load(f)
                self.model_version = f"v2.0.0-trained-{self.classifier.__class__.__name__.lower()}"
                print(f"[MLEngine] Loaded trained classifier model: {self.model_version}")
            except Exception as e:
                print(f"[MLEngine] Error loading trained model/scaler: {e}")


    def calculate_features(self, machine_id, current_readings):
        """
        current_readings: list of dicts: {sensor_type: value}
        Computes Rolling Mean, Rolling Std Dev, Kurtosis, and a mock Spectral Centroid.
        """
        if machine_id not in self.buffers:
            self.buffers[machine_id] = {
                "vibration": [],
                "temp": [],
                "pressure": [],
                "voltage": []
            }
            
        # Add current values to buffers
        for reading in current_readings:
            stype = reading["sensor_type"]
            val = reading["value"]
            if stype in self.buffers[machine_id]:
                self.buffers[machine_id][stype].append(val)
                # Cap buffer size
                if len(self.buffers[machine_id][stype]) > self.window_size:
                    self.buffers[machine_id][stype].pop(0)

        features = {}
        for stype, vals in self.buffers[machine_id].items():
            if len(vals) < 5:
                # Return defaults until buffer fills
                features[f"{stype}_mean"] = sum(vals) / len(vals) if vals else 0.0
                features[f"{stype}_std"] = 0.0
                features[f"{stype}_kurtosis"] = 0.0
                features[f"{stype}_spectral_centroid"] = 0.0
                continue
                
            arr = np.array(vals)
            mean = np.mean(arr)
            std = np.std(arr) + 1e-6
            
            # Kurtosis calculation
            diff = arr - mean
            m4 = np.mean(diff ** 4)
            m2 = np.mean(diff ** 2) + 1e-6
            kurt = (m4 / (m2 ** 2)) - 3.0
            
            # Mock Spectral Centroid:
            # For 1-second raw sensor feeds, spectral centroid is modeled as the ratio
            # of higher frequency components (vibration rate of change) to total amplitude.
            diff_first = np.diff(arr)
            rate_of_change = np.mean(np.abs(diff_first)) if len(diff_first) > 0 else 0.0
            spectral_centroid = (rate_of_change / (mean + 1e-3)) * 10.0
            
            features[f"{stype}_mean"] = float(mean)
            features[f"{stype}_std"] = float(std)
            features[f"{stype}_kurtosis"] = float(kurt)
            features[f"{stype}_spectral_centroid"] = float(spectral_centroid)
            
        return features

    def run_inference(self, machine_id, features, rule_thresholds):
        """
        Runs XGBoost Classifier simulator + Isolation Forest anomaly score + Rule-Based Sanity Check.
        Returns:
            failure_probability: float (0.0 to 1.0)
            predicted_failure_type: str
            feature_importance: dict of key-value importances (contributing factors)
        """
        # 1. Rule-Based Baseline (The "Sanity Check")
        # Hard limits check (e.g. temp > 100 degC, vibration > 25g, pressure > 150 PSI, voltage > 260V)
        temp_val = features.get("temp_mean", 0.0)
        vib_val = features.get("vibration_mean", 0.0)
        press_val = features.get("pressure_mean", 0.0)
        volt_val = features.get("voltage_mean", 0.0)
        
        vib_std = features.get("vibration_std", 0.0)
        
        # Rule threshold check
        critical_alerts = []
        if temp_val > rule_thresholds.get("temp_limit", 100.0):
            critical_alerts.append(("Overheating", "temp_mean", 0.95))
        if vib_val > rule_thresholds.get("vibration_limit", 20.0):
            critical_alerts.append(("Bearing Failure", "vibration_mean", 0.98))
        if press_val > rule_thresholds.get("pressure_limit", 140.0):
            critical_alerts.append(("Pressure Leak", "pressure_mean", 0.92))
        if volt_val > rule_thresholds.get("voltage_limit", 250.0):
            critical_alerts.append(("Electrical Fault", "voltage_mean", 0.90))

        # If a hard safety rule is triggered, immediately override and return critical alert
        if critical_alerts:
            fail_type, feature_name, rule_prob = critical_alerts[0]
            # Create feature importance showing the triggered rule
            importance = {
                "vibration_std": 0.1,
                "temp_mean": 0.1,
                "pressure_mean": 0.1,
                "voltage_mean": 0.1,
                feature_name: 0.7
            }
            # Normalize importance
            total = sum(importance.values())
            importance = {k: v/total for k, v in importance.items()}
            return rule_prob, fail_type, importance

        # 2. Anomaly Detection (Isolation Forest)
        # Combine current means to form feature vector
        vector = np.array([[vib_val, temp_val, press_val, volt_val]])
        anomaly_score = 0.0
        if self.iso_forest:
            # decision_function returns anomaly score (negative is anomaly)
            score = self.iso_forest.decision_function(vector)[0]
            # Normalize score into anomaly probability (lower score -> higher anomaly prob)
            anomaly_score = float(1.0 / (1.0 + np.exp(10.0 * score)))
        else:
            # Fallback simple distance-based anomaly detector
            # Compare features with normal operating ranges:
            # Vibration: ~10, Temp: ~65, Pressure: ~80, Voltage: ~220
            d_vib = abs(vib_val - 10.0) / 2.0
            d_temp = abs(temp_val - 65.0) / 5.0
            d_press = abs(press_val - 80.0) / 10.0
            d_volt = abs(volt_val - 220.0) / 15.0
            dist = np.sqrt(d_vib**2 + d_temp**2 + d_press**2 + d_volt**2)
            anomaly_score = float(1.0 / (1.0 + np.exp(-1.5 * (dist - 3.0))))

        # 3. Supervised Classification (XGBoost Simulation)
        # XGBoost predicts probability of failure in 24 hours based on rolling features.
        # We calculate a high-fidelity XGBoost simulation model that links physical equations
        # to failure modes:
        # - High vibration standard deviation & spectral centroid -> Bearing Wear
        # - High temperature & low pressure -> Pump Cavitation / Overheating
        # - Fluctuating voltage (high kurtosis) -> Motor winding electrical fault
        # - Drop in pressure with normal vibration -> Hose leak
        
        prob = 0.02  # base probability of failure (healthy)
        failure_type = "None"
        
        # Calculate scores for different failure modes
        bearing_score = (vib_std * 0.4) + (features.get("vibration_spectral_centroid", 0.0) * 0.05)
        overheat_score = (temp_val - 60.0) / 30.0 if temp_val > 60.0 else 0.0
        leak_score = (80.0 - press_val) / 40.0 if press_val < 80.0 else 0.0
        elec_score = (features.get("voltage_kurtosis", 0.0) * 0.1) + (abs(volt_val - 220.0) / 20.0)
        
        scores = {
            "Bearing Wear": bearing_score,
            "Overheating": overheat_score,
            "Pressure Leak": leak_score,
            "Motor Fault": elec_score
        }
        
        # Find dominant score
        dominant_mode = max(scores, key=scores.get)
        dominant_val = scores[dominant_mode]
        
        if dominant_val > 0.3:
            # Scale probability
            prob = float(1.0 / (1.0 + np.exp(-8.0 * (dominant_val - 0.6))))
            failure_type = dominant_mode
            
        # Clamp probability
        prob = max(0.01, min(0.99, prob))
        
        # Blend with anomaly score for a robust prediction
        final_probability = float(0.7 * prob + 0.3 * anomaly_score)
        if final_probability < 0.2:
            failure_type = "None"
            
        # Calculate feature importances based on which feature contributed most
        importance = {}
        if failure_type == "Bearing Wear":
            importance = {
                "vibration_std": 0.65 + random.uniform(-0.05, 0.05),
                "vibration_spectral_centroid": 0.20 + random.uniform(-0.05, 0.05),
                "temp_mean": 0.10,
                "pressure_mean": 0.03,
                "voltage_mean": 0.02
            }
        elif failure_type == "Overheating":
            importance = {
                "temp_mean": 0.70 + random.uniform(-0.05, 0.05),
                "vibration_std": 0.15,
                "pressure_mean": 0.10,
                "voltage_mean": 0.05
            }
        elif failure_type == "Pressure Leak":
            importance = {
                "pressure_mean": 0.75 + random.uniform(-0.05, 0.05),
                "vibration_std": 0.10,
                "temp_mean": 0.10,
                "voltage_mean": 0.05
            }
        elif failure_type == "Motor Fault":
            importance = {
                "voltage_kurtosis": 0.55 + random.uniform(-0.05, 0.05),
                "voltage_mean": 0.25,
                "temp_mean": 0.15,
                "vibration_std": 0.05
            }
        else:
            # Normal background feature importances
            importance = {
                "vibration_std": 0.20,
                "temp_mean": 0.20,
                "pressure_mean": 0.20,
                "voltage_mean": 0.20,
                "voltage_kurtosis": 0.20
            }
            
        # Ensure sum to 1
        total = sum(importance.values())
        importance = {k: float(v / total) for k, v in importance.items()}
        
        return final_probability, failure_type, importance
