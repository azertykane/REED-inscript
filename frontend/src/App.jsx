import React, {useState, useEffect} from "react";
import axios from "axios";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";

export default function App(){
  const [token, setToken] = useState(localStorage.getItem("token"));
  const [user, setUser] = useState(null);

  useEffect(()=>{
    if(token){
      axios.get("/api/users/me", { headers: { Authorization: `Bearer ${token}` } })
        .then(r => setUser(r.data))
        .catch(()=> { setUser(null); setToken(null); localStorage.removeItem("token"); });
    }
  }, [token]);

  if(!token) return <Login onLogin={(t)=>{ setToken(t); localStorage.setItem("token", t); }} />;
  return <Dashboard token={token} user={user} onLogout={()=>{ setToken(null); localStorage.removeItem("token"); }} />;
}
