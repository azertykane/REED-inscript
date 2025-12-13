import { useEffect, useState, useRef } from "react";
import api from "./api";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";

export default function App() {
  const [token, setToken] = useState(localStorage.getItem("token"));
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const fetched = useRef(false);

  useEffect(() => {
    if (!token) {
      setLoading(false);
      return;
    }

    if (fetched.current) return;
    fetched.current = true;

    api
      .get("/users/me", {
        headers: { Authorization: `Bearer ${token}` },
      })
      .then((res) => {
        setUser(res.data);
        setLoading(false);
      })
      .catch(() => {
        localStorage.removeItem("token");
        setToken(null);
        setUser(null);
        setLoading(false);
      });
  }, [token]);
  
  if (!user) {
  return <div style={{ padding: 40 }}>Chargement session…</div>;
}

  if (loading) {
    return <div style={{ padding: 40 }}>Chargement…</div>;
  }

  if (!token) {
    return (
      <Login
        onLogin={(t) => {
          localStorage.setItem("token", t);
          setToken(t);
          fetched.current = false;
          setLoading(true);
        }}
      />
    );
  }

  return (
    <Dashboard
      user={user}
      token={token}
      onLogout={() => {
        localStorage.removeItem("token");
        setToken(null);
        setUser(null);
      }}
    />
  );
}
