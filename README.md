# PredMaint System

PredMaint is a real-time Predictive Maintenance cockpit and ingestion pipeline. It monitors complex machinery by simulating high-frequency sensor telemetry, writing observations to a persistent SQLite database, performing machine learning-based failure predictions, and managing standard operational maintenance workflows.

---

## 🛠️ Architecture & Tech Stack

### Backend
* **FastAPI**: Core REST endpoints and real-time WebSocket communication framework.
* **ML Inference Engine**: Predicts failure probability and outlines feature importance using pre-defined operational boundaries and models.
* **Sensor Simulator**: Generates realistic telemetry streams for different machine types (e.g., Compressors, Turbines) and supports interactive anomaly injection.
* **SQLite & Database Layer**: Stores historical telemetry logs, predictions, alerts, and work orders.

### Frontend
* **React 18 & Vite**: High-performance, low-latency UI.
* **TypeScript**: Strict compile-time typing.
* **TailwindCSS**: Premium dark-themed user interface matching a modern technical cockpit.
* **Recharts**: Responsive multi-sensor history and ML forecasting charts.
* **Lucide React**: Clean iconography.

---


## 🤖 Machine Learning Model Training

The system supports offline model training using the `sensor-fault-detection.csv` dataset. This pipeline performs cleaning, time-series feature engineering, data augmentation (anomaly injection), classifier training, and serialization.

### 1. Dataset Details
* **File**: `sensor-fault-detection.csv` (placed in the root directory)
* **Format**: Semicolon-delimited, containing `Timestamp`, `SensorId`, and `Value`.

### 2. Training the Model
To run the ML training pipeline:
1. Open a terminal and activate your virtual environment:
   ```bash
   cd backend
   call venv\Scripts\activate
   ```
2. Run the training script:
   ```bash
   python ml/train.py
   ```
The script will:
* Clean the CSV and parse timestamps.
* Extract temporal rolling statistics (Mean, StdDev, Kurtosis, Rate of Change) over a sliding window.
* Augment the dataset by injecting synthetic anomaly profiles (Overheating, Bearing Wear, Electrical Fault, Pressure Leak) to create labels.
* Train and compare `RandomForest` and `GradientBoosting` classifiers.
* Save the best model (`anomaly_detector.pkl`) and scaler (`scaler.pkl`) inside the `backend/ml/models/` folder.

### 3. Testing and Evaluating the Model
To evaluate the trained model on the test split:
1. Activate your virtual environment and run the test script:
   ```bash
   python ml/test.py
   ```
2. The script will output an evaluation report containing the overall accuracy, classification report (precision, recall, F1-score), and a text-based Confusion Matrix.

#### 📊 Model Performance Metrics
The trained model (`RandomForestClassifier`) achieves the following results on the test partition:

* **Overall Accuracy**: **95.24%**

| Class | Precision | Recall | F1-Score | Support |
| :--- | :---: | :---: | :---: | :---: |
| **Normal** | 0.93 | 0.98 | 0.95 | 51 |
| **Overheating** | 1.00 | 1.00 | 1.00 | 12 |
| **Bearing Wear** | 1.00 | 1.00 | 1.00 | 14 |
| **Electrical Fault** | 0.92 | 0.73 | 0.81 | 15 |
| **Pressure Leak** | 1.00 | 1.00 | 1.00 | 13 |

#### 🎛️ Confusion Matrix
| Actual \ Predicted | Normal | Overheating | Bearing Wear | Electrical Fault | Pressure Leak |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Normal** | **50** | 0 | 0 | 1 | 0 |
| **Overheating** | 0 | **12** | 0 | 0 | 0 |
| **Bearing Wear** | 0 | 0 | **14** | 0 | 0 |
| **Electrical Fault** | 4 | 0 | 0 | **11** | 0 |
| **Pressure Leak** | 0 | 0 | 0 | 0 | **13** |

### 4. Live System Integration
Once the training script completes, the FastAPI backend will automatically detect the presence of the serialized model on startup and load it. The live system will then transition from simulated boundaries to actual ML inference on the incoming telemetry streams.

---


## 🚀 Getting Started

### Quick Start (Windows)
The easiest way to start the system is by running the batch script at the root of the project:
```bash
.\start_servers.bat
```
This script automatically:
1. Creates a Python virtual environment in the `backend` directory if one does not exist.
2. Installs backend dependencies from `requirements.txt`.
3. Launches the FastAPI server at `http://localhost:8000`.
4. Starts the Vite development server in the `frontend` directory.

---

### Manual Setup

#### 1. Backend Server
Navigate to the `backend` directory, create a virtual environment, install dependencies, and run the API:
```bash
cd backend
python -m venv venv

# Activate virtual environment
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the server
uvicorn main:app --port 8000 --reload
```
The FastAPI documentation will be available at `http://localhost:8000/docs`.

#### 2. Frontend Development Server
Navigate to the `frontend` directory, install Node dependencies, and start Vite:
```bash
cd frontend
npm install
npm run dev
```
The frontend application will be hosted at `http://localhost:5173`.

---

## 🔌 API Reference

### REST Endpoints

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/machines` | Retrieve all machines and their current state. |
| `GET` | `/api/machines/{id}` | Fetch detailed metadata for a specific machine. |
| `POST` | `/api/machines/{id}/threshold` | Update failure probability alert threshold sensitivity (0.0 to 1.0). |
| `POST` | `/api/machines/{id}/acknowledge` | Acknowledge a failure warning, set status to `maintenance`, and create a work order. |
| `POST` | `/api/machines/{id}/feedback` | Close work order with root cause details and return machine to `operational` status. |
| `POST` | `/api/machines/{id}/trigger_anomaly` | Inject specific simulation anomalies (`Bearing Wear`, `Overheating`, `Pressure Leak`, `Motor Fault`). |
| `GET` | `/api/machines/{id}/history` | Retrieve historical sensor telemetry aligned for visualization. |
| `GET` | `/api/machines/{id}/export` | Export the last 24 hours of raw sensor telemetry to a downloadable CSV. |
| `GET` | `/api/alerts` | Get the list of recent cached alerts. |
| `GET` | `/api/work_orders` | List all active maintenance work orders. |

### WebSocket Endpoint
* **`WS /api/ws`**: Broadcasts real-time JSON telemetry frames every 1 second, containing refreshed sensor parameters, health scores, and ML feature weights.

---

## 📁 Repository Structure
```text
Project 2/
├── backend/
│   ├── database/         # SQLite schema and DB access functions
│   ├── ml/               # Feature calculation and ML inference pipeline
│   ├── main.py           # FastAPI server and background scheduler
│   ├── simulator.py      # Telemetry signal simulator
│   └── requirements.txt  # Python package list
├── frontend/
│   ├── src/              # React, Recharts, and Tailwind views
│   ├── package.json      # Node scripts and dependencies
│   ├── tailwind.config.js# Custom styling tokens
│   └── vite.config.ts    # Build configurations
├── start_servers.bat     # Windows automated startup script
├── .gitignore            # Git exclusion patterns
├── .ignore               # File/directory search exclusion patterns
└── README.md             # Project documentation
```
