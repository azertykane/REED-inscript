import React, {useEffect, useState} from "react";
import axios from "axios";

export default function Dashboard({token, onLogout, user}){
  const [machines, setMachines] = useState([]);
  const [logs, setLogs] = useState([]);

  useEffect(()=>{ fetchMachines(); fetchLogs(); }, []);

  const fetchMachines = async ()=>{
    const res = await axios.get("/api/machines/", { headers: { Authorization: `Bearer ${token}` } });
    setMachines(res.data);
  };

  const fetchLogs = async ()=>{
    const res = await axios.get("/api/logs/", { headers: { Authorization: `Bearer ${token}` } });
    setLogs(res.data);
  };

  const block = async (id)=>{
    await axios.post(`/api/machines/block/${id}`, {}, { headers: { Authorization: `Bearer ${token}` } });
    fetchMachines(); fetchLogs();
  };
  const unblock = async (id)=>{
    await axios.post(`/api/machines/unblock/${id}`, {}, { headers: { Authorization: `Bearer ${token}` } });
    fetchMachines(); fetchLogs();
  };

  return (
    <div className="layout">
      <aside className="sidebar">
        <h3>Admin Pharma</h3>
        <div>Utilisateur: {user?.username || "—"}</div>
        <button onClick={onLogout}>Logout</button>
      </aside>
      <main className="main">
        <h2>Machines</h2>
        <div className="grid">
          {machines.map(m=>(
            <div key={m.id} className="card">
              <h4>{m.device_name}</h4>
              <div>MAC: {m.mac_address}</div>
              <div>Status: {m.status}</div>
              {m.status !== "blocked" ? <button onClick={()=>block(m.id)}>Bloquer</button> : <button onClick={()=>unblock(m.id)}>Débloquer</button>}
            </div>
          ))}
        </div>

        <h2>Historique des blocages</h2>
        <div>
          {logs.map(l=>(
            <div key={l.id} className="log">{l.timestamp} — Machine {l.machine_id} — {l.action} par {l.by_user}</div>
          ))}
        </div>
      </main>
    </div>
  );
}
