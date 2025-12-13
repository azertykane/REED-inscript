import React, { useEffect, useState } from "react";
import api from "../api";

export default function Dashboard() {
  const [machines, setMachines] = useState([]);
  const [logs, setLogs] = useState([]);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  const loadData = async () => {
    try {
      const [mRes, lRes] = await Promise.all([
        api.get("/machines"),
        api.get("/logs"),
      ]);

      setMachines(mRes.data || []);
      setLogs(lRes.data || []);
      setError(null);
    } catch (err) {
      console.error(err);
      setError("Impossible de charger les données");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
    const t = setInterval(loadData, 10000);
    return () => clearInterval(t);
  }, []);

  const block = async (id) => {
    await api.post(`/machines/${id}/block`);
    loadData();
  };

  const unblock = async (id) => {
    await api.post(`/machines/${id}/unblock`);
    loadData();
  };

  if (loading) return <div style={{ padding: 30 }}>Chargement…</div>;
  if (error) return <div style={{ padding: 30, color: "red" }}>{error}</div>;

  return (
    <div style={{ padding: 30 }}>
      <h2>Machines</h2>

      {machines.map((m) => (
        <div
          key={m.id}
          style={{
            border: "1px solid #ccc",
            marginBottom: 10,
            padding: 10,
          }}
        >
          <b>{m.device_name}</b><br />
          MAC: {m.mac_address}<br />
          Status: <b>{m.status}</b><br />

          {m.status === "blocked" ? (
            <button onClick={() => unblock(m.id)}>Débloquer</button>
          ) : (
            <button onClick={() => block(m.id)}>Bloquer</button>
          )}
        </div>
      ))}

      <h2>Historique</h2>

      {logs.map((l) => (
        <div key={l.id}>
          {new Date(l.timestamp).toLocaleString()} — Machine {l.machine_id} — {l.action}
        </div>
      ))}
    </div>
  );
}
