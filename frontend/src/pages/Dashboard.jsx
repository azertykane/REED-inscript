import React, { useEffect, useState } from "react";
import api from "../api";

export default function Dashboard() {
  const [machines, setMachines] = useState([]);
  const [logs, setLogs] = useState([]);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  // Rafraîchissement automatique toutes les 10s
  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 10000); // 10s
    return () => clearInterval(interval);
  }, []);

  const loadData = async () => {
    try {
      const [mRes, lRes] = await Promise.all([
        api.get("/machines"),
        api.get("/logs"),
      ]);
      setMachines(mRes.data);
      setLogs(lRes.data);
      setLoading(false);
      setError(null);
    } catch (err) {
      console.error("API ERROR", err);
      setError("Impossible de charger les données.");
      setLoading(false);
    }
  };

  const block = async (id) => {
    try {
      await api.post(`/machines/${id}/block`);
      loadData();
    } catch {
      setError("Erreur blocage machine");
    }
  };

  const unblock = async (id) => {
    try {
      await api.post(`/machines/${id}/unblock`);
      loadData();
    } catch {
      setError("Erreur déblocage machine");
    }
  };

  if (loading) return <div style={{ padding: 40 }}>Chargement des données…</div>;
  if (error) return <div style={{ padding: 40 }}>{error}</div>;

  return (
    <div className="layout">
      <aside className="sidebar">
        <h3>Pharma Dashboard</h3>
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
        <div className="logs">
          {logs.map((l) => (
            <div key={l.id}>
              {new Date(l.timestamp).toLocaleString()} — Machine {l.machine_id} — {l.action}
            </div>
          ))}
        </div>
      </main>
    </div>
  );
}
