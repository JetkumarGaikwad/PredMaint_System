import os
import sqlite3
import json
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(__file__), "predmaint.db")
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    # Read and execute schema
    with open(SCHEMA_PATH, "r") as f:
        schema = f.read()
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.executescript(schema)
    
    # Check if we need to seed machines
    cursor.execute("SELECT COUNT(*) FROM machines")
    count = cursor.fetchone()[0]
    if count == 0:
        seed_machines(cursor)
        
    conn.commit()
    conn.close()

def seed_machines(cursor):
    machines_data = [
        ("SN-PUMP-001", "Pump-01", "Pump", "2024-01-15", "operational", "Zone A"),
        ("SN-PUMP-002", "Pump-02", "Pump", "2024-02-10", "operational", "Zone A"),
        ("SN-PUMP-003", "Pump-03", "Pump", "2023-11-05", "operational", "Zone B"),
        ("SN-PUMP-004", "Pump-04", "Pump", "2024-03-01", "operational", "Zone B"),
        ("SN-LATHE-001", "Lathe-01", "Lathe", "2023-08-20", "operational", "Zone C"),
        ("SN-LATHE-002", "Lathe-02", "Lathe", "2023-09-12", "operational", "Zone C"),
        ("SN-COMP-001", "Compressor-01", "Compressor", "2024-04-18", "operational", "Zone D"),
        ("SN-COMP-002", "Compressor-02", "Compressor", "2024-05-01", "operational", "Zone D")
    ]
    cursor.executemany(
        """
        INSERT INTO machines (serial_number, name, machine_type, install_date, operational_status, location_zone)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        machines_data
    )

def get_machines():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM machines")
    machines = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return machines

def get_machine(machine_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM machines WHERE id = ?", (machine_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def update_machine_status(machine_id, status):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE machines SET operational_status = ? WHERE id = ?", (status, machine_id))
    conn.commit()
    conn.close()

def update_machine_threshold(machine_id, threshold):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE machines SET threshold_sensitivity = ? WHERE id = ?", (threshold, machine_id))
    conn.commit()
    conn.close()

def insert_sensor_readings(readings):
    # readings is list of dicts: {time, machine_id, sensor_type, value, unit}
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.executemany(
        """
        INSERT INTO sensor_readings (time, machine_id, sensor_type, value, unit)
        VALUES (:time, :machine_id, :sensor_type, :value, :unit)
        """,
        readings
    )
    conn.commit()
    conn.close()

def insert_prediction(prediction):
    # prediction is dict: {time, machine_id, failure_probability, predicted_failure_type, model_version, feature_importance_json}
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO predictions (time, machine_id, failure_probability, predicted_failure_type, model_version, feature_importance_json)
        VALUES (:time, :machine_id, :failure_probability, :predicted_failure_type, :model_version, :feature_importance_json)
        """,
        prediction
    )
    conn.commit()
    conn.close()

def create_work_order(machine_id, issue_description):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO work_orders (machine_id, created_at, issue_description)
        VALUES (?, ?, ?)
        """,
        (machine_id, datetime.utcnow().isoformat() + "Z", issue_description)
    )
    work_order_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return work_order_id

def resolve_work_order(machine_id, root_cause, parts_replaced):
    conn = get_db_connection()
    cursor = conn.cursor()
    # Find active work order for this machine (one that hasn't been resolved yet)
    cursor.execute(
        """
        UPDATE work_orders 
        SET resolved_at = ?, root_cause_verified = ?, parts_replaced = ?
        WHERE machine_id = ? AND resolved_at IS NULL
        """,
        (datetime.utcnow().isoformat() + "Z", root_cause, parts_replaced, machine_id)
    )
    # Update machine status back to operational
    cursor.execute("UPDATE machines SET operational_status = 'operational' WHERE id = ?", (machine_id,))
    conn.commit()
    conn.close()

def get_sensor_history(machine_id, sensor_type=None, hours=4):
    conn = get_db_connection()
    cursor = conn.cursor()
    cutoff_time = (datetime.utcnow() - timedelta(hours=hours)).isoformat() + "Z"
    
    if sensor_type:
        cursor.execute(
            """
            SELECT * FROM sensor_readings 
            WHERE machine_id = ? AND sensor_type = ? AND time >= ?
            ORDER BY time ASC
            """,
            (machine_id, sensor_type, cutoff_time)
        )
    else:
        cursor.execute(
            """
            SELECT * FROM sensor_readings 
            WHERE machine_id = ? AND time >= ?
            ORDER BY time ASC
            """,
            (machine_id, cutoff_time)
        )
        
    readings = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return readings

def get_latest_predictions(machine_id=None, limit=10):
    conn = get_db_connection()
    cursor = conn.cursor()
    if machine_id:
        cursor.execute(
            """
            SELECT * FROM predictions 
            WHERE machine_id = ? 
            ORDER BY time DESC LIMIT ?
            """,
            (machine_id, limit)
        )
    else:
        cursor.execute(
            """
            SELECT p.*, m.name as machine_name 
            FROM predictions p
            JOIN machines m ON p.machine_id = m.id
            ORDER BY p.time DESC LIMIT ?
            """,
            (limit,)
        )
    predictions = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return predictions

def get_active_work_orders():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT w.*, m.name as machine_name 
        FROM work_orders w
        JOIN machines m ON w.machine_id = m.id
        WHERE w.resolved_at IS NULL
        """
    )
    orders = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return orders

def cleanup_old_data():
    conn = get_db_connection()
    cursor = conn.cursor()
    # Delete raw sensor data older than 30 days
    limit_time = (datetime.utcnow() - timedelta(days=30)).isoformat() + "Z"
    cursor.execute("DELETE FROM sensor_readings WHERE time < ?", (limit_time,))
    conn.commit()
    conn.close()
