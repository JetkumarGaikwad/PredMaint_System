import os
import sys
import pickle
import numpy as np

# Ensure the current directory is in the path for importing train
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import classification_report, accuracy_score, confusion_matrix
    from train import load_data, augment_and_label_data, extract_features, MODEL_PATH, SCALER_PATH
    HAS_ML_LIBS = True
except ImportError as e:
    HAS_ML_LIBS = False
    MISSING_LIB = str(e)

def print_confusion_matrix(cm, class_names):
    """
    Prints a beautiful text-based confusion matrix table.
    """
    header = f"{'Actual \\ Predicted':<20}" + "".join([f"{name:>15}" for name in class_names])
    print(header)
    print("-" * len(header))
    
    for idx, row in enumerate(cm):
        actual_name = class_names[idx]
        row_str = f"{actual_name:<20}" + "".join([f"{val:>15}" for val in row])
        print(row_str)

def run_evaluation():
    if not HAS_ML_LIBS:
        print("\n[ERROR] Missing required machine learning libraries!")
        print(f"Details: {MISSING_LIB}")
        sys.exit(1)

    # 1. Verify saved model exists
    if not os.path.exists(MODEL_PATH) or not os.path.exists(SCALER_PATH):
        print("\n[ERROR] No trained model/scaler files found!")
        print("Please train the model first by running: python ml/train.py")
        sys.exit(1)

    # 2. Find dataset path
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
        print("\n[ERROR] Could not find sensor-fault-detection.csv")
        sys.exit(1)

    # 3. Load and prepare test split
    raw_data = load_data(csv_path)
    segments, labels = augment_and_label_data(raw_data)
    X = extract_features(segments)
    y = np.array(labels)

    # Split (using same test size and random state to evaluate on the test split)
    _, X_test, _, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    # 4. Load Saved Artifacts
    print(f"\nLoading trained model from: {MODEL_PATH}")
    with open(MODEL_PATH, "rb") as f:
        model = pickle.load(f)

    print(f"Loading scaler from: {SCALER_PATH}")
    with open(SCALER_PATH, "rb") as f:
        scaler = pickle.load(f)

    # 5. Transform and Predict
    X_test_scaled = scaler.transform(X_test)
    preds = model.predict(X_test_scaled)

    # 6. Metrics Calculation
    accuracy = accuracy_score(y_test, preds)
    anomaly_names = ["Normal", "Overheating", "Bearing Wear", "Electrical Fault", "Pressure Leak"]

    print("\n" + "="*50)
    print(f"MODEL EVALUATION REPORT ({model.__class__.__name__})")
    print("="*50)
    print(f"Overall Accuracy: {accuracy * 100:.2f}%")
    
    print("\nClassification Report:")
    print(classification_report(y_test, preds, target_names=anomaly_names))
    
    print("\nConfusion Matrix:")
    cm = confusion_matrix(y_test, preds)
    print_confusion_matrix(cm, anomaly_names)
    print("="*50 + "\n")

if __name__ == "__main__":
    run_evaluation()
