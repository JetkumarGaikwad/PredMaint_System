-- PredMaint System SQLite Database Schema

CREATE TABLE IF NOT EXISTS machines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    serial_number TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    machine_type TEXT NOT NULL, -- e.g., 'Pump', 'Lathe'
    install_date TEXT NOT NULL,
    operational_status TEXT DEFAULT 'operational', -- 'operational', 'maintenance', 'broken'
    location_zone TEXT NOT NULL,
    threshold_sensitivity REAL DEFAULT 0.85 -- engineer configurable, FR-04
);

CREATE TABLE IF NOT EXISTS sensor_readings (
    time TEXT NOT NULL, -- ISO8601 string
    machine_id INTEGER,
    sensor_type TEXT NOT NULL, -- 'vibration', 'temp', 'pressure', 'voltage'
    value REAL NOT NULL,
    unit TEXT NOT NULL,
    FOREIGN KEY(machine_id) REFERENCES machines(id)
);

CREATE TABLE IF NOT EXISTS predictions (
    time TEXT NOT NULL, -- ISO8601 string
    machine_id INTEGER,
    failure_probability REAL NOT NULL, -- 0.0 to 1.0
    predicted_failure_type TEXT,
    model_version TEXT NOT NULL,
    feature_importance_json TEXT, -- JSON string mapping features to importance
    FOREIGN KEY(machine_id) REFERENCES machines(id)
);

CREATE TABLE IF NOT EXISTS work_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    machine_id INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    issue_description TEXT,
    resolved_at TEXT,
    root_cause_verified TEXT, -- Engineer input: Was the prediction correct?
    parts_replaced TEXT,
    FOREIGN KEY(machine_id) REFERENCES machines(id)
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_sensor_readings_time ON sensor_readings(time);
CREATE INDEX IF NOT EXISTS idx_sensor_readings_machine_id ON sensor_readings(machine_id);
CREATE INDEX IF NOT EXISTS idx_predictions_time ON predictions(time);
CREATE INDEX IF NOT EXISTS idx_predictions_machine_id ON predictions(machine_id);
