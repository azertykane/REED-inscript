import React, { useState } from "react";
import api from "../api";

export default function Login({ onLogin }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);

  const submit = async (e) => {
    e.preventDefault();
    setError(null);

    try {
      const res = await api.post("/users/login", {
        username,
        password,
      });
      onLogin(res.data.access_token);
    } catch (err) {
      setError("Identifiants incorrects");
      console.error("LOGIN ERROR", err.response?.data || err.message);
    }
  };

  return (
    <div className="center">
      <form className="card" onSubmit={submit}>
        <h2>Admin Pharma</h2>
        {error && <div className="error">{error}</div>}
        <input placeholder="Username" value={username} onChange={(e) => setUsername(e.target.value)} />
        <input type="password" placeholder="Password" value={password} onChange={(e) => setPassword(e.target.value)} />
        <button type="submit">Connexion</button>
      </form>
    </div>
  );
}
