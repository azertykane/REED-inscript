import React, { useEffect, useState } from "react";
import api from "../api";

export default function Dashboard({ token, onLogout, user }) {
  const [machines, setMachines] = useState([]);
  const [logs, setLogs] = useState([]);
  const [error, setError] = useState(null);

  const auth = {
    headers: { Authorization: `Bearer ${token}` },
  };

  // 🔄 Chargement machines et logs
  useEffect(() => {
    if (!token) return;
    loadData();
  }, [token]);

  const loadData = async () => {
    try {
      const [m, l] = await Promise.all([
        api.get("/machines", auth),
        api.get("/logs", auth),
      ]);
      setMachines(m.data);
      setLogs(l.data);
    } catch (err) {
      console.error("API ERROR", err);
      setError("Session expirée ou erreur serveur");
      onLogout(); // déconnexion automatique si token invalide
    }
  };

  const block = async (id) => {
    try {
      await api.post(`/machines/${id}/block`, {}, auth);
      loadData();
    } catch {
      setError("Erreur blocage");
    }
  };

  const unblock = async (id) => {
    try {
      await api.post(`/machines/${id}/unblock`, {}, auth);
      loadData();
    } catch {
      setError("Erreur déblocage");
    }
  };

  if (error) return <div style={{ padding: 40 }}>{error}</div>;

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
            {new Date(l.timestamp).toLocaleString()} — Machine {l.machine_id} — {l.action}
          </div>
        ))}
      </main>
    </div>
  );
}
