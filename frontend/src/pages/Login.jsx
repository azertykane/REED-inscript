import React, {useState} from "react";
import axios from "axios";

export default function Login({onLogin}){
  const [username,setUsername]=useState("");
  const [password,setPassword]=useState("");
  const [error,setError]=useState(null);

  const submit = async (e)=>{
    e.preventDefault();
    const form = new FormData();
    form.append("username", username);
    form.append("password", password);
    try{
      const res = await axios.post("/api/users/login", form);
      onLogin(res.data.access_token);
    }catch(err){
      setError(err.response?.data?.detail || "Erreur de connexion");
    }
  };

  return (
    <div className="center">
      <form className="card" onSubmit={submit}>
        <h2>Admin Pharma - Login</h2>
        {error && <div className="error">{error}</div>}
        <input placeholder="username" value={username} onChange={e=>setUsername(e.target.value)} />
        <input placeholder="password" type="password" value={password} onChange={e=>setPassword(e.target.value)} />
        <button type="submit">Se connecter</button>
      </form>
    </div>
  );
}
