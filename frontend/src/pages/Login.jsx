import React, { useState } from "react";
import api from "../api";

export default function Login({ onLogin }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);

  const submit = async (e) => {
    e.preventDefault();

    try {
      const res = await api.post("/users/login", {
        username,
        password,
      });
      onLogin(res.data.access_token);
    } catch {
      setError("Erreur de connexion");
    }
  };

  return (
    <div className="center">
      <form className="card" onSubmit={submit}>
        <h2>Admin Pharma</h2>
        {error && <div className="error">{error}</div>}
        <input value={username} onChange={(e) => setUsername(e.target.value)} />
        <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
        <button>Connexion</button>
      </form>
    </div>
  );
}
