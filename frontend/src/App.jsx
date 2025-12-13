import React, { useState, useEffect, useRef } from "react";
import api from "./api";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";

export default function App() {
  const [token, setToken] = useState(localStorage.getItem("token"));
  const [user, setUser] = useState(null);
  const loaded = useRef(false);

  useEffect(() => {
    if (!token || loaded.current) return;

    loaded.current = true;

    api
      .get("/users/me", {
        headers: { Authorization: `Bearer ${token}` },
      })
      .then((res) => setUser(res.data))
      .catch(() => {
        setToken(null);
        setUser(null);
        localStorage.removeItem("token");
      });
  }, [token]);

  if (!token) {
    return (
      <Login
        onLogin={(t) => {
          localStorage.setItem("token", t);
          setToken(t);
          loaded.current = false;
        }}
      />
    );
  }

  return (
    <Dashboard
      token={token}
      user={user}
      onLogout={() => {
        setToken(null);
        setUser(null);
        localStorage.removeItem("token");
      }}
    />
  );
}
