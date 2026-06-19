import React, { useState, useEffect, useRef } from 'react';
import { 
  Activity, 
  Cpu, 
  AlertTriangle, 
  Wrench, 
  Settings, 
  Download, 
  Play, 
  CheckCircle, 
  RefreshCw, 
  Sliders, 
  X, 
  ChevronRight, 
  Info, 
  Clock, 
  Database,
  FileSpreadsheet
} from 'lucide-react';
import { 
  LineChart, 
  Line, 
  XAxis, 
  YAxis, 
  CartesianGrid, 
  Tooltip, 
  ResponsiveContainer, 
  BarChart, 
  Bar, 
  Cell
} from 'recharts';

// --- Types ---
interface Machine {
  id: number;
  serial_number: string;
  name: string;
  machine_type: string;
  install_date: string;
  operational_status: string; // 'operational', 'maintenance', 'broken'
  location_zone: string;
  threshold_sensitivity: number;
}

interface Reading {
  value: number;
  unit: string;
}

interface Telemetry {
  machine_id: number;
  name: string;
  machine_type: string;
  status: string;
  health_score: number;
  failure_probability: number;
  predicted_failure_type: string;
  feature_importance: Record<string, number>;
  readings: Record<string, Reading>;
  threshold: number;
  timestamp: string;
}

interface ToastMessage {
  id: string;
  machineName: string;
  type: string;
  probability: number;
  timestamp: string;
}

interface HistoricalPoint {
  time: string;
  vibration?: number;
  temp?: number;
  pressure?: number;
  voltage?: number;
}

// Play console chime via Web Audio API
const playAlertChime = () => {
  try {
    const AudioContextClass = window.AudioContext || (window as any).webkitAudioContext;
    if (!AudioContextClass) return;
    const ctx = new AudioContextClass();
    
    // Play dual tone chime
    const osc1 = ctx.createOscillator();
    const osc2 = ctx.createOscillator();
    const gainNode = ctx.createGain();
    
    osc1.type = 'sine';
    osc1.frequency.setValueAtTime(880, ctx.currentTime); // A5
    osc1.frequency.exponentialRampToValueAtTime(1200, ctx.currentTime + 0.15);
    
    osc2.type = 'square';
    osc2.frequency.setValueAtTime(440, ctx.currentTime); // A4
    osc2.frequency.exponentialRampToValueAtTime(600, ctx.currentTime + 0.15);
    
    gainNode.gain.setValueAtTime(0.08, ctx.currentTime);
    gainNode.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.3);
    
    osc1.connect(gainNode);
    osc2.connect(gainNode);
    gainNode.connect(ctx.destination);
    
    osc1.start();
    osc2.start();
    osc1.stop(ctx.currentTime + 0.3);
    osc2.stop(ctx.currentTime + 0.3);
  } catch (e) {
    console.warn("Audio Context failed to play chime:", e);
  }
};

export default function App() {
  const [activeTab, setActiveTab] = useState<'dashboard' | 'alerts' | 'retraining'>('dashboard');
  const [machines, setMachines] = useState<Machine[]>([]);
  const [telemetry, setTelemetry] = useState<Record<number, Telemetry>>({});
  const [selectedMachineId, setSelectedMachineId] = useState<number | null>(null);
  const [historyData, setHistoryData] = useState<HistoricalPoint[]>([]);
  const [isHistoryLoading, setIsHistoryLoading] = useState(false);
  
  // Modals & Forms State
  const [showAckModal, setShowAckModal] = useState(false);
  const [ackDescription, setAckDescription] = useState('Scheduled emergency bearing inspection');
  const [anomalyType, setAnomalyType] = useState('Bearing Wear');
  const [retrainCause, setRetrainCause] = useState('Bearing Wear');
  const [partsReplaced, setPartsReplaced] = useState('Inner cage assembly, grease pack');
  
  // Connection State
  const [wsConnected, setWsConnected] = useState(false);
  const [toasts, setToasts] = useState<ToastMessage[]>([]);
  
  // Slide out sidebar control
  const [sidebarExpanded, setSidebarExpanded] = useState(false);
  const [currentTime, setCurrentTime] = useState(new Date().toUTCString());
  
  // Vibration sparkline buffer
  const [sparklineBuffer, setSparklineBuffer] = useState<Record<number, number[]>>({});

  const wsRef = useRef<WebSocket | null>(null);

  // UTC clock update
  useEffect(() => {
    const timer = setInterval(() => {
      setCurrentTime(new Date().toUTCString());
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  // Fetch static machine listings initially
  const fetchMachinesList = async () => {
    try {
      const res = await fetch('/api/machines');
      if (res.ok) {
        const data = await res.json();
        setMachines(data);
      }
    } catch (err) {
      console.error("Error fetching machines list:", err);
    }
  };

  // Connect WebSockets
  useEffect(() => {
    fetchMachinesList();
    
    const connectWS = () => {
      const loc = window.location;
      const wsProto = loc.protocol === 'https:' ? 'wss:' : 'ws:';
      const wsUrl = `${wsProto}//${loc.host}/api/ws`;
      
      console.log(`Connecting WebSocket to: ${wsUrl}`);
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        setWsConnected(true);
      };

      ws.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        if (msg.type === 'telemetry') {
          const telemetryList: Telemetry[] = msg.data;
          
          setTelemetry(prev => {
            const next = { ...prev };
            telemetryList.forEach(item => {
              // Check if machine just entered critical state (status change to broken)
              const previousItem = prev[item.machine_id];
              if (
                item.status === 'broken' && 
                (!previousItem || previousItem.status !== 'broken')
              ) {
                // Trigger Toast & Audio Chime
                triggerToast(item.name, item.predicted_failure_type, item.failure_probability);
              }
              
              next[item.machine_id] = item;
            });
            return next;
          });

          // Update sparklines (keep last 15 seconds for grid UI)
          setSparklineBuffer(prev => {
            const next = { ...prev };
            telemetryList.forEach(item => {
              const currentVib = item.readings.vibration?.value || 0;
              const currentBuffer = prev[item.machine_id] || [];
              const updated = [...currentBuffer, currentVib].slice(-15);
              next[item.machine_id] = updated;
            });
            return next;
          });
        }
      };

      ws.onclose = () => {
        setWsConnected(false);
        setTimeout(connectWS, 3000); // Reconnect loop
      };

      ws.onerror = () => {
        setWsConnected(false);
      };
    };

    connectWS();

    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, []);

  // Fetch machine sensor historical data (last 4 hours)
  const fetchHistory = async (machineId: number) => {
    setIsHistoryLoading(true);
    try {
      const res = await fetch(`/api/machines/${machineId}/history?hours=4`);
      if (res.ok) {
        const rawHistory = await res.json();
        // Group raw readings by time
        const grouped: Record<string, HistoricalPoint> = {};
        rawHistory.forEach((row: any) => {
          const t = row.time;
          if (!grouped[t]) {
            grouped[t] = { time: t };
          }
          if (row.sensor_type === 'vibration') grouped[t].vibration = row.value;
          if (row.sensor_type === 'temp') grouped[t].temp = row.value;
          if (row.sensor_type === 'pressure') grouped[t].pressure = row.value;
          if (row.sensor_type === 'voltage') grouped[t].voltage = row.value;
        });
        
        const sorted = Object.values(grouped).sort(
          (a, b) => new Date(a.time).getTime() - new Date(b.time).getTime()
        );
        setHistoryData(sorted);
      }
    } catch (e) {
      console.error("Error loading history:", e);
    } finally {
      setIsHistoryLoading(false);
    }
  };

  // Poll history for selected machine if active
  useEffect(() => {
    if (selectedMachineId !== null) {
      fetchHistory(selectedMachineId);
      const historyPoll = setInterval(() => {
        fetchHistory(selectedMachineId);
      }, 5000);
      return () => clearInterval(historyPoll);
    }
  }, [selectedMachineId]);

  const triggerToast = (machineName: string, type: string, probability: number) => {
    playAlertChime();
    const newToast: ToastMessage = {
      id: Math.random().toString(36).substring(2, 9),
      machineName,
      type,
      probability,
      timestamp: new Date().toLocaleTimeString()
    };
    setToasts(prev => [newToast, ...prev]);
    setTimeout(() => {
      setToasts(prev => prev.filter(t => t.id !== newToast.id));
    }, 6000);
  };

  // Trigger simulated anomaly in backend
  const handleTriggerAnomaly = async () => {
    if (selectedMachineId === null) return;
    try {
      await fetch(`/api/machines/${selectedMachineId}/trigger_anomaly`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ anomaly_type: anomalyType })
      });
      // Refresh local configuration list
      fetchMachinesList();
    } catch (e) {
      console.error(e);
    }
  };

  // Acknowledge alert -> Schedule Maintenance
  const handleAcknowledge = async () => {
    if (selectedMachineId === null) return;
    try {
      const res = await fetch(`/api/machines/${selectedMachineId}/acknowledge`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ description: ackDescription })
      });
      if (res.ok) {
        setShowAckModal(false);
        fetchMachinesList();
      }
    } catch (e) {
      console.error(e);
    }
  };

  // Retraining feedback form submit
  const handleFeedbackSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (selectedMachineId === null) return;
    try {
      const res = await fetch(`/api/machines/${selectedMachineId}/feedback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          root_cause: retrainCause,
          parts_replaced: partsReplaced
        })
      });
      if (res.ok) {
        fetchMachinesList();
      }
    } catch (e) {
      console.error(e);
    }
  };

  // Modify threshold value
  const handleThresholdUpdate = async (val: number) => {
    if (selectedMachineId === null) return;
    try {
      const res = await fetch(`/api/machines/${selectedMachineId}/threshold`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ threshold: val })
      });
      if (res.ok) {
        fetchMachinesList();
      }
    } catch (e) {
      console.error(e);
    }
  };

  // Terminal Styled Tooltip
  const TerminalTooltip = ({ active, payload, label }: any) => {
    if (active && payload && payload.length) {
      return (
        <div className="bg-[#020617] border border-[#22C55E]/40 p-2 font-mono text-xs text-[#22C55E] rounded shadow-2xl">
          <p className="text-[#94A3B8] mb-1 font-semibold">{`TIMESTAMP: ${new Date(label).toLocaleTimeString()}`}</p>
          {payload.map((p: any) => (
            <p key={p.name} className="flex gap-2 justify-between">
              <span>{`> ${p.name.toUpperCase()}:`}</span>
              <span className="font-bold">{`${p.value.toFixed(2)} ${p.unit || ''}`}</span>
            </p>
          ))}
        </div>
      );
    }
    return null;
  };

  const activeTelemetry = selectedMachineId !== null ? telemetry[selectedMachineId] : null;
  const currentMachine = machines.find(m => m.id === selectedMachineId);

  // Group active incident alerts
  const activeAlerts = Object.values(telemetry).filter(t => t.status === 'broken');

  return (
    <div className="flex flex-col h-screen w-screen bg-[#0F172A] text-[#94A3B8] overflow-hidden select-none">
      
      {/* --- TOP HEADER (48px) --- */}
      <header className="h-12 border-b border-[#334155] flex items-center justify-between px-4 bg-[#0F172A] z-10">
        <div className="flex items-center gap-3">
          <div className="bg-[#EF4444] text-white p-1 rounded font-black text-xs tracking-widest flex items-center gap-1 animate-pulse">
            <Activity className="h-3 w-3" />
            <span>PREDMAINT</span>
          </div>
          <div className="h-4 w-px bg-[#334155]" />
          <div className="text-xs text-[#F8FAFC] font-semibold tracking-wider flex items-center gap-2">
            <span>SYS_LOC: EDGE_GATEWAY_A</span>
            <span className={`inline-block h-2 w-2 rounded-full ${wsConnected ? 'bg-[#22C55E]' : 'bg-[#EF4444]'}`} />
          </div>
        </div>

        <div className="flex items-center gap-4 text-xs font-mono">
          <div className="flex items-center gap-2 text-cyan-500">
            <Clock className="h-3.5 w-3.5" />
            <span>{currentTime}</span>
          </div>
          <div className="h-4 w-px bg-[#334155]" />
          <div className="bg-[#1E293B] border border-[#334155] px-2 py-0.5 rounded text-[#F8FAFC]">
            INCIDENTS: <span className="text-[#EF4444] font-bold">{activeAlerts.length}</span>
          </div>
        </div>
      </header>

      {/* --- MAIN PAGE CONTENT --- */}
      <div className="flex flex-1 overflow-hidden relative">
        
        {/* --- LEFT SIDEBAR (48px collapsed) --- */}
        <aside 
          className="border-r border-[#334155] bg-[#0F172A] flex flex-col justify-between items-center py-4 z-10 transition-all duration-300"
          style={{ width: sidebarExpanded ? '180px' : '48px' }}
        >
          <div className="flex flex-col gap-6 w-full px-2">
            <button 
              onClick={() => setActiveTab('dashboard')}
              className={`flex items-center gap-3 p-2 rounded transition-colors w-full ${activeTab === 'dashboard' ? 'bg-[#1E293B] text-cyan-500 border border-[#334155]' : 'hover:bg-[#1E293B]/50'}`}
              title="Dashboard Grid"
            >
              <Cpu className="h-5 w-5 min-w-5" />
              {sidebarExpanded && <span className="text-xs font-semibold">GRID</span>}
            </button>
            
            <button 
              onClick={() => setActiveTab('alerts')}
              className={`flex items-center gap-3 p-2 rounded transition-colors w-full relative ${activeTab === 'alerts' ? 'bg-[#1E293B] text-[#EF4444] border border-[#334155]' : 'hover:bg-[#1E293B]/50'}`}
              title="Active Incidents"
            >
              <AlertTriangle className="h-5 w-5 min-w-5" />
              {activeAlerts.length > 0 && (
                <span className="absolute top-1 right-1 h-2 w-2 rounded-full bg-[#EF4444] animate-ping" />
              )}
              {sidebarExpanded && <span className="text-xs font-semibold">ALERTS</span>}
            </button>

            <button 
              onClick={() => setActiveTab('retraining')}
              className={`flex items-center gap-3 p-2 rounded transition-colors w-full ${activeTab === 'retraining' ? 'bg-[#1E293B] text-green-500 border border-[#334155]' : 'hover:bg-[#1E293B]/50'}`}
              title="Feedback Loop Retraining"
            >
              <Wrench className="h-5 w-5 min-w-5" />
              {sidebarExpanded && <span className="text-xs font-semibold">FEEDBACK</span>}
            </button>
          </div>

          <button 
            onClick={() => setSidebarExpanded(!sidebarExpanded)}
            className="p-1 text-[#334155] hover:text-[#94A3B8] transition-colors"
          >
            <ChevronRight className={`h-4 w-4 transform transition-transform duration-300 ${sidebarExpanded ? 'rotate-180' : ''}`} />
          </button>
        </aside>

        {/* --- TOAST PANEL (Floating Top Right) --- */}
        <div className="absolute top-4 right-4 z-50 flex flex-col gap-2 pointer-events-none w-80">
          {toasts.map(toast => (
            <div 
              key={toast.id}
              className="pointer-events-auto bg-[#020617] border-l-4 border-[#EF4444] p-3 text-xs shadow-2xl rounded flex flex-col gap-1 slide-in-toast font-mono"
            >
              <div className="flex justify-between items-center font-bold text-[#EF4444]">
                <span className="flex items-center gap-1">
                  <AlertTriangle className="h-3.5 w-3.5 animate-bounce" />
                  CRITICAL PREDICTION
                </span>
                <span className="text-[10px] text-gray-500">{toast.timestamp}</span>
              </div>
              <p className="text-[#F8FAFC]">
                Machine <span className="font-bold underline">{toast.machineName}</span> predicted to fail within 24h.
              </p>
              <div className="text-[#94A3B8] text-[10px] flex justify-between mt-1">
                <span>EST_TYPE: {toast.type}</span>
                <span>CONFIDENCE: {(toast.probability * 100).toFixed(0)}%</span>
              </div>
            </div>
          ))}
        </div>

        {/* --- GRID DASHBOARD VIEW --- */}
        {activeTab === 'dashboard' && (
          <main className="flex-1 p-4 overflow-y-auto flex gap-4">
            <div className="flex-1 flex flex-col gap-4">
              <div className="flex justify-between items-center">
                <h2 className="text-sm tracking-widest font-black text-[#F8FAFC] flex items-center gap-2">
                  <Database className="h-4 w-4 text-cyan-500" />
                  MACHINE TELEMETRY COCKPIT [TRELLIS VIEW]
                </h2>
                <div className="text-[10px] text-[#334155]">
                  UPDATED EVERY 1000MS
                </div>
              </div>

              {/* Machine Trellis Grid */}
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                {machines.map(m => {
                  const data = telemetry[m.id];
                  const status = data ? data.status : m.operational_status;
                  const healthScore = data ? data.health_score : 100;
                  const failProb = data ? data.failure_probability : 0.02;
                  const type = data ? data.predicted_failure_type : 'None';
                  const sparkValues = sparklineBuffer[m.id] || [];

                  // Status configurations
                  let statusColor = 'border-[#22C55E]';
                  let statusBg = 'bg-[#22C55E]/10';
                  let statusLabel = 'HEALTHY';
                  let isBlinking = false;

                  if (status === 'broken') {
                    statusColor = 'border-[#EF4444]';
                    statusBg = 'bg-[#EF4444]/10';
                    statusLabel = 'CRITICAL';
                    isBlinking = true;
                  } else if (status === 'maintenance') {
                    statusColor = 'border-[#F59E0B]';
                    statusBg = 'bg-[#F59E0B]/10';
                    statusLabel = 'MAINTENANCE';
                  }

                  const isSelected = selectedMachineId === m.id;

                  return (
                    <div 
                      key={m.id}
                      onClick={() => setSelectedMachineId(m.id)}
                      className={`cursor-pointer transition-all duration-200 border border-[#334155] rounded-sm bg-[#1E293B] hover:bg-[#1E293B]/80 flex flex-col justify-between p-3 min-h-[140px] select-none ${isBlinking ? 'animate-alert-blink border-l-4' : `border-l-4 ${statusColor}`} ${isSelected ? 'ring-1 ring-cyan-500' : ''}`}
                    >
                      <div className="flex justify-between items-start">
                        <div>
                          <div className="text-[#F8FAFC] text-xs font-bold font-mono tracking-wider">{m.name}</div>
                          <div className="text-[10px] text-[#94A3B8]">{m.serial_number}</div>
                        </div>
                        <div className={`text-[10px] px-1.5 py-0.5 rounded font-black font-mono tracking-wider ${statusBg} ${isBlinking ? 'text-[#EF4444]' : status === 'maintenance' ? 'text-[#F59E0B]' : 'text-[#22C55E]'}`}>
                          {statusLabel}
                        </div>
                      </div>

                      {/* Sparkline & Score */}
                      <div className="flex items-end justify-between mt-3 gap-2">
                        {/* Tiny Sparkline */}
                        <div className="h-10 w-28 bg-[#0F172A] border border-[#334155]/60 rounded-sm overflow-hidden flex items-center justify-center relative">
                          {sparkValues.length > 1 ? (
                            <ResponsiveContainer width="100%" height="100%">
                              <LineChart data={sparkValues.map((v, i) => ({ idx: i, val: v }))}>
                                <Line 
                                  type="monotone" 
                                  dataKey="val" 
                                  stroke={status === 'broken' ? '#EF4444' : status === 'maintenance' ? '#F59E0B' : '#22C55E'} 
                                  strokeWidth={1.2} 
                                  dot={false} 
                                />
                              </LineChart>
                            </ResponsiveContainer>
                          ) : (
                            <div className="text-[8px] text-[#334155]">BUFFERING...</div>
                          )}
                        </div>

                        {/* Health Score display */}
                        <div className="text-right">
                          <div className="text-[9px] text-gray-500">HEALTH</div>
                          <div className={`text-2xl font-black font-mono leading-none tracking-tighter ${status === 'broken' ? 'text-[#EF4444]' : status === 'maintenance' ? 'text-[#F59E0B]' : 'text-[#22C55E]'}`}>
                            {healthScore}%
                          </div>
                        </div>
                      </div>

                      {/* Small diagnostics */}
                      <div className="border-t border-[#334155]/40 mt-2 pt-2 flex justify-between text-[9px] text-[#94A3B8] font-mono">
                        <span>ZONE: {m.location_zone}</span>
                        {status === 'broken' && <span className="text-[#EF4444] animate-pulse">FAIL: {type}</span>}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* --- DETAILED SLIDE-OUT PANEL --- */}
            {selectedMachineId !== null && currentMachine && (
              <div className="w-[480px] border-l border-[#334155] bg-[#1E293B] flex flex-col justify-between overflow-hidden shadow-2xl relative">
                
                {/* Panel Header */}
                <div className="h-12 border-b border-[#334155] flex items-center justify-between px-4 bg-[#0F172A]">
                  <div className="flex items-center gap-2">
                    <Sliders className="h-4 w-4 text-cyan-500" />
                    <span className="text-xs font-bold text-[#F8FAFC] tracking-widest">{currentMachine.name.toUpperCase()} ANALYTICS</span>
                  </div>
                  <button 
                    onClick={() => setSelectedMachineId(null)}
                    className="p-1 hover:bg-[#1E293B] rounded text-gray-400 hover:text-white"
                  >
                    <X className="h-4 w-4" />
                  </button>
                </div>

                {/* Panel Scrollable Content */}
                <div className="flex-1 overflow-y-auto p-4 flex flex-col gap-5">
                  
                  {/* Summary Details */}
                  <div className="grid grid-cols-2 gap-2 text-xs bg-[#0F172A] border border-[#334155] p-3 rounded-sm font-mono">
                    <div>
                      <span className="text-gray-500">SERIAL_NO:</span>
                      <p className="text-white font-bold">{currentMachine.serial_number}</p>
                    </div>
                    <div>
                      <span className="text-gray-500">ZONE_ZONE:</span>
                      <p className="text-white font-bold">{currentMachine.location_zone}</p>
                    </div>
                    <div>
                      <span className="text-gray-500">TYPE:</span>
                      <p className="text-white font-bold">{currentMachine.machine_type}</p>
                    </div>
                    <div>
                      <span className="text-gray-500">STATUS:</span>
                      <p className={`font-bold ${activeTelemetry?.status === 'broken' ? 'text-[#EF4444]' : activeTelemetry?.status === 'maintenance' ? 'text-[#F59E0B]' : 'text-[#22C55E]'}`}>
                        {activeTelemetry?.status?.toUpperCase() || currentMachine.operational_status.toUpperCase()}
                      </p>
                    </div>
                  </div>

                  {/* Real-Time Values */}
                  {activeTelemetry && (
                    <div className="grid grid-cols-4 gap-2 text-center">
                      <div className="border border-[#334155] p-2 bg-[#0F172A] rounded-sm">
                        <div className="text-[8px] text-gray-500">VIB (g)</div>
                        <div className="text-xs font-bold text-white font-mono mt-0.5">
                          {activeTelemetry.readings.vibration?.value.toFixed(1) || '0.0'}
                        </div>
                      </div>
                      <div className="border border-[#334155] p-2 bg-[#0F172A] rounded-sm">
                        <div className="text-[8px] text-gray-500">TEMP (°C)</div>
                        <div className="text-xs font-bold text-white font-mono mt-0.5">
                          {activeTelemetry.readings.temp?.value.toFixed(1) || '0.0'}
                        </div>
                      </div>
                      <div className="border border-[#334155] p-2 bg-[#0F172A] rounded-sm">
                        <div className="text-[8px] text-gray-500">PRESS (PSI)</div>
                        <div className="text-xs font-bold text-white font-mono mt-0.5">
                          {activeTelemetry.readings.pressure?.value.toFixed(0) || '0.0'}
                        </div>
                      </div>
                      <div className="border border-[#334155] p-2 bg-[#0F172A] rounded-sm">
                        <div className="text-[8px] text-gray-500">VOLT (V)</div>
                        <div className="text-xs font-bold text-white font-mono mt-0.5">
                          {activeTelemetry.readings.voltage?.value.toFixed(0) || '0.0'}
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Oscilloscope Plot */}
                  <div className="border border-[#334155] rounded-sm bg-[#0F172A] p-2 relative flex flex-col gap-2">
                    <div className="flex justify-between items-center text-[10px] px-1 font-bold">
                      <span className="text-cyan-500">VIBRATION WAVEFORM (LAST 4h)</span>
                      <span className="text-gray-500">UNIT: g</span>
                    </div>

                    <div className="h-40 w-full rounded-sm overflow-hidden oscilloscope-grid">
                      {isHistoryLoading ? (
                        <div className="absolute inset-0 flex items-center justify-center bg-[#0F172A]/70 text-xs font-bold">
                          LOADING OSCILLOSCOPE DATA...
                        </div>
                      ) : historyData.length > 0 ? (
                        <ResponsiveContainer width="100%" height="100%">
                          <LineChart 
                            data={historyData} 
                            margin={{ top: 10, right: 10, left: -25, bottom: 5 }}
                          >
                            <CartesianGrid strokeDasharray="3 3" stroke="rgba(51, 65, 85, 0.2)" />
                            <XAxis 
                              dataKey="time" 
                              tickFormatter={(t) => new Date(t).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} 
                              tick={{ fill: '#94A3B8', fontSize: 9 }}
                            />
                            <YAxis 
                              tick={{ fill: '#94A3B8', fontSize: 9, angle: -90, textAnchor: 'end' }} 
                            />
                            <Tooltip 
                              cursor={{ stroke: '#06B6D4', strokeWidth: 1, strokeDasharray: '3 3' }} 
                              content={<TerminalTooltip />} 
                            />
                            <Line 
                              type="monotone" 
                              dataKey="vibration" 
                              name="Vibration" 
                              unit="g"
                              stroke="#06B6D4" 
                              strokeWidth={1.5} 
                              dot={false} 
                              activeDot={{ r: 5 }} 
                            />
                          </LineChart>
                        </ResponsiveContainer>
                      ) : (
                        <div className="absolute inset-0 flex items-center justify-center text-[9px] text-[#334155]">
                          NO DATA POINTS RECORDED
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Feature Importance / Diagnostics */}
                  {activeTelemetry && (
                    <div className="border border-[#334155] rounded-sm bg-[#0F172A] p-3">
                      <h4 className="text-[10px] font-bold text-cyan-500 mb-2">
                        ML ROOT CAUSE ANALYSIS (XGBOOST FEATURE SHAP)
                      </h4>
                      <div className="flex flex-col gap-2">
                        {Object.entries(activeTelemetry.feature_importance)
                          .sort((a, b) => b[1] - a[1])
                          .map(([feat, importance]) => (
                            <div key={feat} className="text-[10px] font-mono">
                              <div className="flex justify-between mb-0.5">
                                <span className="text-white font-bold">{feat}</span>
                                <span className="text-cyan-500 font-bold">{(importance * 100).toFixed(0)}%</span>
                              </div>
                              <div className="w-full bg-[#1E293B] h-1.5 rounded-sm overflow-hidden">
                                <div 
                                  className="h-full bg-cyan-500 rounded-sm" 
                                  style={{ width: `${importance * 100}%` }}
                                />
                              </div>
                            </div>
                          ))
                        }
                      </div>
                    </div>
                  )}

                  {/* Alert Threshold Tuning */}
                  <div className="border border-[#334155] rounded-sm bg-[#0F172A] p-3 flex flex-col gap-2">
                    <h4 className="text-[10px] font-bold text-cyan-500 flex items-center gap-1.5">
                      <Sliders className="h-3.5 w-3.5" />
                      ALERT SENSITIVITY CALIBRATION
                    </h4>
                    <div className="flex items-center gap-3 mt-1">
                      <input 
                        type="range" 
                        min="0.5" 
                        max="0.99" 
                        step="0.01" 
                        value={currentMachine.threshold_sensitivity}
                        onChange={(e) => handleThresholdUpdate(parseFloat(e.target.value))}
                        className="flex-1 accent-cyan-500 bg-[#1E293B]"
                      />
                      <span className="text-xs font-bold font-mono text-white">
                        {(currentMachine.threshold_sensitivity * 100).toFixed(0)}%
                      </span>
                    </div>
                    <span className="text-[9px] text-gray-500 leading-snug">
                      Alert thresholds configured below 80% increase warning frequency. Standard default is 85%.
                    </span>
                  </div>

                  {/* Trigger Simulator Anomaly */}
                  <div className="border border-[#334155] rounded-sm bg-[#0F172A] p-3 flex flex-col gap-3">
                    <h4 className="text-[10px] font-bold text-[#EF4444] flex items-center gap-1.5">
                      <Play className="h-3.5 w-3.5 animate-pulse" />
                      EDGE SIMULATION TESTING INTERFACE
                    </h4>
                    <div className="flex gap-2">
                      <select 
                        value={anomalyType}
                        onChange={(e) => setAnomalyType(e.target.value)}
                        className="flex-1 bg-[#1E293B] border border-[#334155] px-2 py-1 text-xs text-white rounded-sm font-mono focus:outline-none"
                      >
                        <option value="Bearing Wear">Bearing Wear (Vibration)</option>
                        <option value="Overheating">Overheating (Temp)</option>
                        <option value="Pressure Leak">Pressure Leak (Pressure)</option>
                        <option value="Motor Fault">Motor Winding Fault (Voltage)</option>
                      </select>
                      <button 
                        onClick={handleTriggerAnomaly}
                        className="bg-[#EF4444]/20 hover:bg-[#EF4444]/30 text-[#EF4444] border border-[#EF4444]/40 font-bold px-3 py-1 rounded-sm text-xs font-mono btn-physical"
                      >
                        TRIGGER
                      </button>
                    </div>
                  </div>

                  {/* Feedback retrain Loop (FR-06) */}
                  {activeTelemetry?.status === 'maintenance' && (
                    <form onSubmit={handleFeedbackSubmit} className="border border-green-500/20 rounded-sm bg-green-500/5 p-3 flex flex-col gap-3">
                      <h4 className="text-[10px] font-bold text-green-500 flex items-center gap-1.5">
                        <CheckCircle className="h-3.5 w-3.5" />
                        MAINTENANCE CLOSURE FEEDBACK LOOP
                      </h4>
                      <div className="flex flex-col gap-2">
                        <div className="flex flex-col gap-1">
                          <label className="text-[9px] text-gray-400">VERIFIED ROOT CAUSE</label>
                          <select 
                            value={retrainCause}
                            onChange={(e) => setRetrainCause(e.target.value)}
                            className="bg-[#1E293B] border border-[#334155] px-2 py-1 text-xs text-white rounded-sm font-mono focus:outline-none"
                          >
                            <option value="Bearing Wear">Bearing Wear</option>
                            <option value="Overheating">Overheating</option>
                            <option value="Pressure Leak">Pressure Leak</option>
                            <option value="Motor Fault">Motor Winding Fault</option>
                            <option value="False Alarm">False Alarm / Normal Operation</option>
                          </select>
                        </div>
                        <div className="flex flex-col gap-1">
                          <label className="text-[9px] text-gray-400">REPLACEMENT DETAILS</label>
                          <input 
                            type="text" 
                            value={partsReplaced}
                            onChange={(e) => setPartsReplaced(e.target.value)}
                            className="bg-[#1E293B] border border-[#334155] px-2 py-1 text-xs text-white rounded-sm font-mono focus:outline-none"
                          />
                        </div>
                        <button 
                          type="submit"
                          className="bg-green-500/20 hover:bg-green-500/30 text-green-400 border border-green-500/40 font-bold py-1.5 rounded-sm text-xs font-mono btn-physical mt-1"
                        >
                          SUBMIT TRAINING LABEL & RUN RETRAIN
                        </button>
                      </div>
                    </form>
                  )}

                </div>

                {/* Panel Footer / Action buttons */}
                <div className="h-14 border-t border-[#334155] flex items-center justify-between px-4 bg-[#0F172A] gap-3">
                  <a 
                    href={`/api/machines/${currentMachine.id}/export`}
                    download
                    className="flex-1 bg-[#1E293B] hover:bg-[#1E293B]/80 text-[#94A3B8] border border-[#334155] font-bold py-2 rounded-sm text-xs font-mono text-center flex items-center justify-center gap-1.5 btn-physical"
                  >
                    <Download className="h-3.5 w-3.5" />
                    EXPORT CSV
                  </a>

                  {activeTelemetry?.status === 'broken' && (
                    <button 
                      onClick={() => setShowAckModal(true)}
                      className="flex-1 bg-[#EF4444] hover:bg-[#EF4444]/90 text-white font-bold py-2 rounded-sm text-xs font-mono flex items-center justify-center gap-1.5 btn-physical border border-[#EF4444]/40"
                    >
                      <AlertTriangle className="h-3.5 w-3.5 animate-pulse" />
                      ACKNOWLEDGE
                    </button>
                  )}
                </div>

              </div>
            )}
          </main>
        )}

        {/* --- ACTIVE INCIDENTS / ALERTS VIEW --- */}
        {activeTab === 'alerts' && (
          <main className="flex-1 p-4 overflow-y-auto flex flex-col gap-4">
            <h2 className="text-sm tracking-widest font-black text-[#F8FAFC] flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 text-[#EF4444]" />
              ACTIVE INCIDENT DISPATCH
            </h2>

            <div className="border border-[#334155] rounded-sm overflow-hidden bg-[#1E293B]">
              <div className="grid grid-cols-5 bg-[#0F172A] p-3 text-[10px] font-bold border-b border-[#334155] tracking-wider">
                <span>TIMESTAMP</span>
                <span>MACHINE</span>
                <span>FAIL PROBABILITY</span>
                <span>SUSPECTED ROOT CAUSE</span>
                <span className="text-right">DISPATCH</span>
              </div>

              {activeAlerts.length === 0 ? (
                <div className="p-10 text-center text-xs font-bold text-gray-500">
                  NO ACTIVE ALERTS. SYSTEM IS RUNNING HEALTHY.
                </div>
              ) : (
                <div className="divide-y divide-[#334155]/60">
                  {activeAlerts.map(alert => (
                    <div key={alert.machine_id} className="grid grid-cols-5 p-3 text-xs items-center font-mono">
                      <span className="text-cyan-500">{new Date(alert.timestamp).toLocaleTimeString()}</span>
                      <span className="text-white font-bold">{alert.name}</span>
                      <span className="text-[#EF4444] font-bold">{(alert.failure_probability * 100).toFixed(0)}%</span>
                      <span className="text-gray-400">{alert.predicted_failure_type}</span>
                      <div className="text-right">
                        <button 
                          onClick={() => {
                            setSelectedMachineId(alert.machine_id);
                            setShowAckModal(true);
                          }}
                          className="bg-[#EF4444]/20 hover:bg-[#EF4444]/30 text-[#EF4444] border border-[#EF4444]/40 font-bold px-3 py-1 rounded-sm text-xs btn-physical"
                        >
                          ACKNOWLEDGE
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </main>
        )}

        {/* --- RETRAINING FEEDBACK LOOP VIEW --- */}
        {activeTab === 'retraining' && (
          <main className="flex-1 p-4 overflow-y-auto flex flex-col gap-4">
            <h2 className="text-sm tracking-widest font-black text-[#F8FAFC] flex items-center gap-2">
              <Wrench className="h-4 w-4 text-green-500" />
              ML TRAINING PIPELINE FEEDBACK LOOP (FR-06)
            </h2>

            <div className="border border-[#334155] rounded-sm overflow-hidden bg-[#1E293B] max-w-4xl">
              <div className="p-4 border-b border-[#334155] bg-[#0F172A]">
                <h3 className="text-xs font-bold text-[#F8FAFC]">ACTIVE MAINTENANCE ORDERS PENDING Retraining LABEL</h3>
                <p className="text-[10px] text-gray-500 mt-1">
                  Once a machine repair is finished, submit details below. The labeled data is tagged directly in SQLite to trigger retrains.
                </p>
              </div>

              {Object.values(telemetry).filter(t => t.status === 'maintenance').length === 0 ? (
                <div className="p-10 text-center text-xs font-bold text-gray-500">
                  NO PENDING MAINTENANCE ORDERS REQUIRING LABELS.
                </div>
              ) : (
                <div className="divide-y divide-[#334155]/60">
                  {Object.values(telemetry)
                    .filter(t => t.status === 'maintenance')
                    .map(m => (
                      <div key={m.machine_id} className="p-4 flex flex-col gap-3">
                        <div className="flex justify-between items-center text-xs">
                          <span className="text-white font-bold">{m.name} ({m.machine_type})</span>
                          <span className="text-[#F59E0B] font-bold text-[10px] px-1.5 py-0.5 bg-[#F59E0B]/10 rounded border border-[#F59E0B]/30">
                            IN MAINTENANCE
                          </span>
                        </div>

                        {/* Inline retrain form */}
                        <div className="grid grid-cols-3 gap-3">
                          <div className="flex flex-col gap-1">
                            <label className="text-[9px] text-gray-400">VERIFIED INCIDENT</label>
                            <select 
                              value={retrainCause}
                              onChange={(e) => setRetrainCause(e.target.value)}
                              className="bg-[#0F172A] border border-[#334155] px-2 py-1.5 text-xs text-white rounded-sm font-mono focus:outline-none"
                            >
                              <option value="Bearing Wear">Bearing Wear</option>
                              <option value="Overheating">Overheating</option>
                              <option value="Pressure Leak">Pressure Leak</option>
                              <option value="Motor Fault">Motor Winding Fault</option>
                              <option value="False Alarm">False Alarm / Normal</option>
                            </select>
                          </div>
                          
                          <div className="flex flex-col gap-1">
                            <label className="text-[9px] text-gray-400">REPLACED HARDWARE</label>
                            <input 
                              type="text" 
                              value={partsReplaced}
                              onChange={(e) => setPartsReplaced(e.target.value)}
                              placeholder="e.g. Pump impeller"
                              className="bg-[#0F172A] border border-[#334155] px-2 py-1.5 text-xs text-white rounded-sm font-mono focus:outline-none"
                            />
                          </div>

                          <div className="flex items-end">
                            <button 
                              onClick={async () => {
                                try {
                                  await fetch(`/api/machines/${m.machine_id}/feedback`, {
                                    method: 'POST',
                                    headers: { 'Content-Type': 'application/json' },
                                    body: JSON.stringify({
                                      root_cause: retrainCause,
                                      parts_replaced: partsReplaced
                                    })
                                  });
                                  fetchMachinesList();
                                } catch(e) {
                                  console.error(e);
                                }
                              }}
                              className="w-full bg-green-500/20 hover:bg-green-500/30 text-green-400 border border-green-500/40 font-bold py-1.5 rounded-sm text-xs font-mono btn-physical"
                            >
                              RESOLVE & LABEL DATA
                            </button>
                          </div>
                        </div>
                      </div>
                    ))
                  }
                </div>
              )}
            </div>
          </main>
        )}

      </div>

      {/* --- ACKNOWLEDGE ALERT MODAL --- */}
      {showAckModal && selectedMachineId !== null && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="w-[400px] border border-[#334155] bg-[#1E293B] rounded shadow-2xl p-4 flex flex-col gap-4 font-mono">
            <div className="flex justify-between items-center border-b border-[#334155] pb-2">
              <h3 className="text-xs font-bold text-white tracking-widest flex items-center gap-1.5 text-[#EF4444]">
                <AlertTriangle className="h-4 w-4" />
                DISPATCH MAINTENANCE ORDER
              </h3>
              <button 
                onClick={() => setShowAckModal(false)}
                className="text-gray-400 hover:text-white"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <p className="text-[11px] text-[#94A3B8] leading-relaxed">
              You are acknowledging the ML anomaly warning for machine <span className="text-white font-bold underline">{currentMachine?.name}</span>. This will transition status to **PENDING MAINTENANCE** (Amber Alert) and suppress future sound triggers.
            </p>

            <div className="flex flex-col gap-1.5">
              <label className="text-[9px] text-gray-500">ENGINEER LOG DESCRIPTION</label>
              <textarea 
                value={ackDescription}
                onChange={(e) => setAckDescription(e.target.value)}
                rows={3}
                className="bg-[#0F172A] border border-[#334155] p-2 text-xs text-white rounded focus:outline-none resize-none font-mono"
              />
            </div>

            <div className="flex gap-2 justify-end border-t border-[#334155]/60 pt-3">
              <button 
                onClick={() => setShowAckModal(false)}
                className="bg-[#1E293B] hover:bg-[#1E293B]/80 text-[#94A3B8] border border-[#334155] px-4 py-1.5 rounded-sm text-xs btn-physical"
              >
                CANCEL
              </button>
              <button 
                onClick={handleAcknowledge}
                className="bg-[#EF4444] hover:bg-[#EF4444]/90 text-white font-bold px-4 py-1.5 rounded-sm text-xs btn-physical"
              >
                DISPATCH ORDER
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}
