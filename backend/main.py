import asyncio
import json
import logging
from datetime import datetime
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import io
import csv

from database import db
from ml.ml_engine import MLEngine
from simulator import SensorSimulator

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("PredMaintBackend")

app = FastAPI(title="PredMaint Backend API", version="1.0")

# Enable CORS for frontend Vite development server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In development, allow all
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize engines
ml_engine = MLEngine()
simulator = SensorSimulator()

# In-memory WebSocket manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_text(json.dumps(message))
            except Exception:
                # Handle stale connections
                pass

manager = ConnectionManager()

# In-memory "Redis" cache for recent alerts and thresholds
alerts_cache = []

# Background tasks lifecycle
background_tasks = set()

async def pipeline_loop():
    """
    Continuous pipeline running every 1 second:
    1. Simulates sensor readings
    2. Writes readings to SQLite
    3. Computes rolling features & runs ML Inference
    4. Triggers alarm if ML failure probability > threshold
    5. Broadcasts telemetry via WebSocket
    """
    logger.info("Starting ingestion & inference pipeline loop.")
    db.init_db()
    
    while True:
        try:
            start_time = datetime.now()
            
            # Fetch current machines status
            machines = db.get_machines()
            telemetry_data = []
            
            for m in machines:
                mid = m["id"]
                mname = m["name"]
                mtype = m["machine_type"]
                status = m["operational_status"]
                threshold = m["threshold_sensitivity"]
                
                # 1. Sim sensor data
                # If machine is currently undergoing maintenance, keep sensors at normal baseline values
                is_maintenance = (status == "maintenance")
                if is_maintenance:
                    # Temporarily clear simulator anomalies for this machine
                    simulator.clear_anomaly(mid)
                    
                readings = simulator.generate_next_readings(mid, mtype)
                
                # 2. Write readings to SQLite
                db.insert_sensor_readings(readings)
                
                # 3. ML features and inference
                features = ml_engine.calculate_features(mid, readings)
                
                # Default safety limits for rule-based check
                rule_limits = {
                    "temp_limit": 100.0,
                    "vibration_limit": 22.0,
                    "pressure_limit": 140.0 if mtype == "Compressor" else 120.0,
                    "voltage_limit": 250.0
                }
                
                fail_prob, fail_type, importance = ml_engine.run_inference(mid, features, rule_limits)
                
                # Save predictions
                pred_time = datetime.utcnow().isoformat() + "Z"
                db.insert_prediction({
                    "time": pred_time,
                    "machine_id": mid,
                    "failure_probability": fail_prob,
                    "predicted_failure_type": fail_type,
                    "model_version": ml_engine.model_version,
                    "feature_importance_json": json.dumps(importance)
                })
                
                # Calculate health score (0-100)
                health_score = int(round((1.0 - fail_prob) * 100.0))
                
                # 4. Threshold Management & Alert triggering
                # If failure probability exceeds threshold and machine is operational
                if fail_prob >= threshold and status == "operational":
                    status = "broken"
                    db.update_machine_status(mid, "broken")
                    # Cache alert in our local Redis-like cache
                    alert_log = {
                        "time": pred_time,
                        "machine_id": mid,
                        "machine_name": mname,
                        "failure_probability": fail_prob,
                        "failure_type": fail_type,
                        "resolved": False
                    }
                    alerts_cache.insert(0, alert_log)
                    # Limit cache size
                    if len(alerts_cache) > 50:
                        alerts_cache.pop()
                        
                # Format current readings for websocket
                readings_dict = {r["sensor_type"]: {"value": r["value"], "unit": r["unit"]} for r in readings}
                
                telemetry_data.append({
                    "machine_id": mid,
                    "name": mname,
                    "machine_type": mtype,
                    "status": status,
                    "health_score": health_score,
                    "failure_probability": fail_prob,
                    "predicted_failure_type": fail_type,
                    "feature_importance": importance,
                    "readings": readings_dict,
                    "threshold": threshold,
                    "timestamp": pred_time
                })
            
            # 5. Broadcast to WebSockets
            await manager.broadcast({
                "type": "telemetry",
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "data": telemetry_data
            })
            
            # Maintain 1-second interval, accounting for processing time
            elapsed = (datetime.now() - start_time).total_seconds()
            sleep_time = max(0.1, 1.0 - elapsed)
            await asyncio.sleep(sleep_time)
            
        except Exception as e:
            logger.error(f"Error in pipeline loop: {e}", exc_info=True)
            await asyncio.sleep(2.0)

@app.on_event("startup")
async def startup_event():
    # Run the background pipeline
    task = asyncio.create_task(pipeline_loop())
    background_tasks.add(task)
    task.add_done_callback(background_tasks.discard)

@app.on_event("shutdown")
async def shutdown_event():
    for task in background_tasks:
        task.cancel()

# --- REST ENDPOINTS ---

@app.get("/api/machines")
def get_machines():
    try:
        machines = db.get_machines()
        # Enrich machines with latest status
        return machines
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/machines/{machine_id}")
def get_machine_detail(machine_id: int):
    m = db.get_machine(machine_id)
    if not m:
        raise HTTPException(status_code=404, detail="Machine not found")
    return m

@app.post("/api/machines/{machine_id}/threshold")
def update_threshold(machine_id: int, payload: dict):
    threshold = payload.get("threshold")
    if threshold is None or not (0.0 <= threshold <= 1.0):
        raise HTTPException(status_code=400, detail="Invalid threshold. Must be between 0.0 and 1.0")
    try:
        db.update_machine_threshold(machine_id, threshold)
        return {"success": True, "message": f"Threshold updated to {threshold}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/machines/{machine_id}/acknowledge")
def acknowledge_alert(machine_id: int, payload: dict):
    """
    Acknowledge the failure prediction, transition state to pending maintenance ('maintenance').
    """
    description = payload.get("description", "Scheduled Maintenance via Dashboard Alert")
    try:
        db.update_machine_status(machine_id, "maintenance")
        # Create work order
        wo_id = db.create_work_order(machine_id, description)
        
        # Clear simulator anomaly immediately
        simulator.clear_anomaly(machine_id)
        
        return {"success": True, "work_order_id": wo_id, "message": "Machine status set to maintenance."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/machines/{machine_id}/feedback")
def submit_feedback(machine_id: int, payload: dict):
    """
    Submit final feedback, completing the work order, and restoring the machine to 'operational'.
    """
    root_cause = payload.get("root_cause")
    parts_replaced = payload.get("parts_replaced", "")
    if not root_cause:
        raise HTTPException(status_code=400, detail="Root cause is required")
        
    try:
        db.resolve_work_order(machine_id, root_cause, parts_replaced)
        # Re-ensure simulator is normal
        simulator.clear_anomaly(machine_id)
        return {"success": True, "message": "Work order closed. Machine returned to normal operation."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/machines/{machine_id}/trigger_anomaly")
def trigger_anomaly(machine_id: int, payload: dict):
    anomaly_type = payload.get("anomaly_type")
    valid_anomalies = ["Bearing Wear", "Overheating", "Pressure Leak", "Motor Fault"]
    if anomaly_type not in valid_anomalies:
        raise HTTPException(status_code=400, detail=f"Invalid anomaly_type. Select from {valid_anomalies}")
        
    m = db.get_machine(machine_id)
    if not m:
        raise HTTPException(status_code=404, detail="Machine not found")
        
    simulator.trigger_anomaly(machine_id, anomaly_type)
    return {"success": True, "message": f"Triggered {anomaly_type} anomaly simulator on machine {machine_id}"}

@app.get("/api/machines/{machine_id}/history")
def get_machine_history(machine_id: int, sensor_type: str = None, hours: int = 4):
    try:
        history = db.get_sensor_history(machine_id, sensor_type, hours)
        # Parse timestamp string and group/align responses for frontend charts
        return history
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/machines/{machine_id}/export")
def export_raw_data(machine_id: int):
    """
    Export raw sensor data to CSV format for FR-05.
    """
    try:
        m = db.get_machine(machine_id)
        if not m:
            raise HTTPException(status_code=404, detail="Machine not found")
            
        history = db.get_sensor_history(machine_id, hours=24) # Last 24 hours of data
        
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["time", "sensor_type", "value", "unit"])
        for row in history:
            writer.writerow([row["time"], row["sensor_type"], row["value"], row["unit"]])
            
        output.seek(0)
        filename = f"{m['name']}_raw_sensor_data_{datetime.now().strftime('%Y%m%d%H%M')}.csv"
        
        return StreamingResponse(
            io.BytesIO(output.getvalue().encode("utf-8")),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/alerts")
def get_alerts():
    return alerts_cache

@app.get("/api/work_orders")
def get_active_orders():
    try:
        return db.get_active_work_orders()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- WEBSOCKET ENDPOINT ---

@app.websocket("/api/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        # Stream initial setup or status immediately
        machines = db.get_machines()
        await websocket.send_text(json.dumps({
            "type": "welcome",
            "message": "Connected to PredMaint Real-Time Telemetry Socket",
            "machines": machines
        }))
        
        # Listen for messages if needed (e.g. ping/pong)
        while True:
            data = await websocket.receive_text()
            # Echo back or parse message
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)
