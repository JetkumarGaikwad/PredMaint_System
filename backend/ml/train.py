import os
import csv
import sys
import pickle
import random
import math
from datetime import datetime

# Fallback: if scikit-learn is not installed, print a clean error message.
try:
    import numpy as np
    from sklearn.model_selection import train_test_split
    from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import classification_report, accuracy_score
    HAS_ML_LIBS = True
except ImportError as e:
    HAS_ML_LIBS = False
    MISSING_LIB = str(e)

# Target model directory
MODEL_DIR = os.path.join(os.path.dirname(__file__), "models")
MODEL_PATH = os.path.join(MODEL_DIR, "anomaly_detector.pkl")
SCALER_PATH = os.path.join(MODEL_DIR, "scaler.pkl")

# Constants matching live simulator
WINDOW_SIZE = 30

def load_data(csv_path):
    """
    Loads and cleans the sensor fault detection CSV.
    Delimited by ';'. Columns: Timestamp, SensorId, Value
    """
    print(f"Loading dataset from: {csv_path}")
    data = []
    
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"Dataset file not found at {csv_path}")

    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.reader(f, delimiter=';')
        header = next(reader)
        
        for row in reader:
            if not row or len(row) < 3:
                continue
            ts_str, _, val_str = row[0], row[1], row[2]
            try:
                # Try parsing timestamp
                try:
                    # e.g., 2017-03-01T23:20:00+03:00
                    # Remove timezone offset if present for standard parsing
                    clean_ts = ts_str.split('+')[0].split('-')[0:3]
                    ts = datetime.fromisoformat(ts_str.split('+')[0])
                except Exception:
                    ts = datetime.utcnow()
                
                val = float(val_str)
                data.append((ts, val))
            except ValueError:
                continue

    # Sort chronologically
    data.sort(key=lambda x: x[0])
    print(f"Loaded {len(data)} valid data points.")
    return data

def augment_and_label_data(data):
    """
    Performs data augmentation by segmenting the time series
    and injecting synthetic anomalies (Overheating, Bearing Wear, Electrical Fault, Pressure Leak)
    to create a balanced training set for classification.
    
    Labels:
      0: Normal
      1: Overheating (Drift Upward)
      2: Bearing Wear (High Noise/StdDev)
      3: Electrical Fault (High Amplitude Spikes)
      4: Pressure Leak (Drift Downward)
    """
    print("Performing data augmentation and labeling...")
    augmented_data = []
    labels = []
    
    # We will split data into segments of size 120 points (~2 minutes of data per segment)
    segment_size = 120
    num_segments = len(data) // segment_size
    
    anomaly_types = ["Normal", "Overheating", "Bearing Wear", "Electrical Fault", "Pressure Leak"]
    
    for i in range(num_segments):
        start_idx = i * segment_size
        end_idx = start_idx + segment_size
        segment = [val for _, val in data[start_idx:end_idx]]
        
        # Determine segment label
        # 50% chance of normal, 50% split among the 4 anomalies
        choice = random.random()
        if choice < 0.5:
            label = 0  # Normal
        elif choice < 0.625:
            label = 1  # Overheating (Drift Upwards)
        elif choice < 0.75:
            label = 2  # Bearing Wear (High Noise)
        elif choice < 0.875:
            label = 3  # Electrical Fault (Spikes)
        else:
            label = 4  # Pressure Leak (Drift Downwards)
            
        # Apply augmentation based on label
        augmented_segment = []
        for idx, val in enumerate(segment):
            modified_val = val
            if label == 1:
                # Overheating: gradual drift upwards up to +25 units at the end of the segment
                drift = (idx / segment_size) * 25.0
                modified_val += drift
            elif label == 2:
                # Bearing Wear: inject high frequency zero-mean noise
                noise = random.normalvariate(0, 8.0)
                modified_val += noise
            elif label == 3:
                # Electrical Fault: 5% chance per point of a high amplitude spike
                if random.random() < 0.05:
                    spike = random.choice([-50.0, 50.0]) + random.uniform(-10.0, 10.0)
                    modified_val += spike
            elif label == 4:
                # Pressure Leak: gradual drift downwards up to -15 units
                drift = (idx / segment_size) * 15.0
                modified_val -= drift
                
            augmented_segment.append(modified_val)
            
        augmented_data.append(augmented_segment)
        labels.append(label)
        
    print(f"Generated {len(augmented_data)} augmented segments of length {segment_size}.")
    label_counts = {anomaly_types[lbl]: labels.count(lbl) for lbl in range(5)}
    print("Class Distribution:", label_counts)
    
    return augmented_data, labels

def extract_features(augmented_segments):
    """
    Computes rolling features for each segment.
    To capture the temporal dynamics, we calculate the features over the last 30 points of the segment.
    Features: Mean, StdDev, Kurtosis, Rate of Change.
    """
    print("Extracting features from segments...")
    features_list = []
    
    for segment in augmented_segments:
        # Take the window of size WINDOW_SIZE at the end of the segment
        window = segment[-WINDOW_SIZE:]
        arr = np.array(window)
        
        mean = np.mean(arr)
        std = np.std(arr) + 1e-6
        
        # Kurtosis
        diff = arr - mean
        m4 = np.mean(diff ** 4)
        m2 = np.mean(diff ** 2) + 1e-6
        kurt = (m4 / (m2 ** 2)) - 3.0
        
        # Rate of change
        diff_first = np.diff(arr)
        rate_of_change = np.mean(np.abs(diff_first)) if len(diff_first) > 0 else 0.0
        
        features_list.append([
            float(mean),
            float(std),
            float(kurt),
            float(rate_of_change)
        ])
        
    return np.array(features_list)

def train_model():
    if not HAS_ML_LIBS:
        print("\n[ERROR] Missing required machine learning libraries!")
        print(f"Details: {MISSING_LIB}")
        print("Please ensure scikit-learn, numpy, and fastapi dependencies are fully installed.")
        print("You can run 'pip install numpy scikit-learn' first.")
        sys.exit(1)
        
    # Find dataset path
    possible_paths = [
        os.path.join(os.path.dirname(__file__), "..", "..", "sensor-fault-detection.csv"),
        os.path.join(os.path.dirname(__file__), "..", "sensor-fault-detection.csv"),
        "sensor-fault-detection.csv"
    ]
    
    csv_path = None
    for p in possible_paths:
        if os.path.exists(p):
            csv_path = p
            break
            
    if not csv_path:
        print("\n[ERROR] Could not find sensor-fault-detection.csv in any of the expected paths:")
        for p in possible_paths:
            print(f"  - {os.path.abspath(p)}")
        sys.exit(1)
        
    # 1. Load Data
    raw_data = load_data(csv_path)
    
    # 2. Augment and Label
    segments, labels = augment_and_label_data(raw_data)
    
    # 3. Extract Features
    X = extract_features(segments)
    y = np.array(labels)
    
    # 4. Train-Test Split
    # Since it is augmented segments, we do a stratified split to keep class ratios
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    
    # 5. Scaling
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)
    
    # 6. Train Models
    print("\nTraining Random Forest Classifier...")
    rf_model = RandomForestClassifier(n_estimators=100, random_state=42)
    rf_model.fit(X_train_scaled, y_train)
    
    # Evaluate Random Forest
    rf_preds = rf_model.predict(X_test_scaled)
    rf_acc = accuracy_score(y_test, rf_preds)
    print(f"Random Forest Accuracy: {rf_acc * 100:.2f}%")
    
    print("\nTraining Gradient Boosting Classifier...")
    gb_model = GradientBoostingClassifier(n_estimators=100, random_state=42)
    gb_model.fit(X_train_scaled, y_train)
    
    # Evaluate Gradient Boosting
    gb_preds = gb_model.predict(X_test_scaled)
    gb_acc = accuracy_score(y_test, gb_preds)
    print(f"Gradient Boosting Accuracy: {gb_acc * 100:.2f}%")
    
    # Compare and choose best model
    best_model = rf_model if rf_acc >= gb_acc else gb_model
    best_name = "Random Forest" if rf_acc >= gb_acc else "Gradient Boosting"
    best_acc = max(rf_acc, gb_acc)
    best_preds = rf_preds if rf_acc >= gb_acc else gb_preds
    
    print(f"\nSelecting {best_name} as the final model (Accuracy: {best_acc * 100:.2f}%).")
    
    # Classification Report
    anomaly_names = ["Normal", "Overheating", "Bearing Wear", "Electrical Fault", "Pressure Leak"]
    print("\nClassification Report:")
    print(classification_report(y_test, best_preds, target_names=anomaly_names))
    
    # Create models folder if not exist
    if not os.path.exists(MODEL_DIR):
        os.makedirs(MODEL_DIR)
        
    # Save Model and Scaler
    print(f"Saving final model to: {MODEL_PATH}")
    with open(MODEL_PATH, "wb") as f:
        pickle.dump(best_model, f)
        
    print(f"Saving scaler to: {SCALER_PATH}")
    with open(SCALER_PATH, "wb") as f:
        pickle.dump(scaler, f)
        
    print("\nML training pipeline completed successfully!")

if __name__ == "__main__":
    train_model()
