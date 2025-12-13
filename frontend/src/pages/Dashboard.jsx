import React, { useEffect, useState } from "react";
import api from "../api";

export default function Dashboard({ token, onLogout, user }) {
  const [machines, setMachines] = useState([]);
  const [logs, setLogs] = useState([]);

  const auth = {
    headers: { Authorization: `Bearer ${token}` },
  };

  useEffect(() => {
    fetchMachines();
    fetchLogs();
  }, []);

  const fetchMachines = async () => {
    const res = await api.get("/machines", auth);
    setMachines(res.data);
  };

  const fetchLogs = async () => {
    const res = await api.get("/logs", auth);
    setLogs(res.data);
  };

  const block = async (id) => {
    await api.post(`/machines/${id}/block`, {}, auth);
    fetchMachines();
    fetchLogs();
  };

  const unblock = async (id) => {
    await api.post(`/machines/${id}/unblock`, {}, auth);
    fetchMachines();
    fetchLogs();
  };

  return (
    <div className="layout">
      <aside className="sidebar">
        <h3>Admin Pharma</h3>
        <div>Utilisateur : {user?.username}</div>
        <button onClick={onLogout}>Logout</button>
      </aside>

      <main className="main">
        <h2>Machines</h2>

        <div className="grid">
          {machines.map((m) => (
            <div key={m.id} className="card">
              <h4>{m.device_name}</h4>
              <div>MAC: {m.mac_address}</div>
              <div>Status: {m.status}</div>

              {m.status === "blocked" ? (
                <button onClick={() => unblock(m.id)}>Débloquer</button>
              ) : (
                <button onClick={() => block(m.id)}>Bloquer</button>
              )}
            </div>
          ))}
        </div>

        <h2>Historique</h2>
        {logs.map((l) => (
          <div key={l.id}>
            {l.timestamp} — Machine {l.machine_id} — {l.action}
          </div>
        ))}
      </main>
    </div>
  );
}
