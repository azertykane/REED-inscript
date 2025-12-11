# license_server.py - VERSION CORRIGÉE POUR TON SERVEUR
from fastapi import FastAPI, HTTPException, BackgroundTasks, Header
from pydantic import BaseModel
from datetime import datetime, timedelta
import sqlite3
import hashlib
import json
import os
import requests
import uuid
import secrets
from typing import Optional
from fastapi.middleware.cors import CORSMiddleware

# Configuration Render - METS TON URL ICI
RENDER_SERVICE_URL = "https://pharma-1-7g7e.onrender.com"

# Chemin de la base de données
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_PATH = os.path.join(BASE_DIR, "pharmagest_licenses.db")

# Application FastAPI
app = FastAPI(
    title="PharmaGest License Server",
    description="API de gestion des licences à distance",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Autoriser CORS pour l'interface web
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- INITIALISATION BASE DE DONNÉES ---
def init_database():
    """Initialise la base de données SQLite"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    # Table des licences
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS licenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            license_key TEXT UNIQUE NOT NULL,
            license_id TEXT UNIQUE NOT NULL,
            client_name TEXT NOT NULL,
            client_email TEXT NOT NULL,
            system_fingerprint TEXT,
            issue_date TEXT NOT NULL,
            expiry_date TEXT NOT NULL,
            max_users INTEGER DEFAULT 1,
            is_active BOOLEAN DEFAULT 1,
            is_blocked BOOLEAN DEFAULT 0,
            block_reason TEXT,
            last_check TEXT,
            total_checks INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            notes TEXT
        )
    ''')
    
    # Table des vérifications
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS license_checks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            license_id TEXT NOT NULL,
            check_time TEXT NOT NULL,
            client_ip TEXT,
            was_valid BOOLEAN,
            user_agent TEXT
        )
    ''')
    
    # Table admin
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS admin_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action_type TEXT NOT NULL,
            license_id TEXT,
            admin_user TEXT,
            details TEXT,
            action_time TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()
    print(f"✅ Base de données initialisée: {DATABASE_PATH}")

# Initialiser au démarrage
init_database()

# --- UTILITAIRES ---
def get_db_connection():
    """Connexion à la base de données"""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def verify_admin_password(password: str) -> bool:
    """Vérifie le mot de passe admin"""
    # Mot de passe: "admin123"
    expected_hash = "8c6976e5b5410415bde908bd4dee15dfb167a9c873fc4bb8a81f6f2ab448a918"
    return hashlib.sha256(password.encode()).hexdigest() == expected_hash

# --- MODÈLES PYDANTIC ---
class LicenseValidationRequest(BaseModel):
    license_key: str
    system_fingerprint: str
    client_info: Optional[dict] = None

class AdminBlockRequest(BaseModel):
    license_id: str
    reason: str = "Non-paiement"
    admin_password: str

class AdminRenewRequest(BaseModel):
    license_id: str
    extra_days: int = 30
    admin_password: str
    notes: Optional[str] = None

class CreateLicenseRequest(BaseModel):
    client_name: str
    client_email: str
    duration_days: int = 30
    max_users: int = 1
    admin_password: str

# --- ENDPOINTS PUBLICS ---
@app.get("/")
async def root():
    return {
        "service": "PharmaGest License Server",
        "version": "2.0.0",
        "status": "online",
        "docs": "/docs",
        "admin_panel": "/admin_panel.html",
        "timestamp": datetime.now().isoformat()
    }

@app.get("/health")
async def health_check():
    """Endpoint de santé"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as count FROM licenses")
    license_count = cursor.fetchone()["count"]
    conn.close()
    
    return {
        "status": "healthy",
        "license_count": license_count,
        "timestamp": datetime.now().isoformat()
    }

@app.post("/api/v1/validate")
async def validate_license(request: LicenseValidationRequest):
    """Valide une licence"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # 1. Rechercher la licence
        cursor.execute(
            "SELECT * FROM licenses WHERE license_key = ?",
            (request.license_key,)
        )
        license = cursor.fetchone()
        
        if not license:
            return {
                "valid": False,
                "code": "LICENSE_NOT_FOUND",
                "message": "Clé de licence introuvable",
                "timestamp": datetime.now().isoformat()
            }
        
        license_data = dict(license)
        
        # 2. Vérifier blocage
        if license_data['is_blocked']:
            return {
                "valid": False,
                "code": "ADMIN_BLOCKED",
                "message": f"Licence bloquée: {license_data.get('block_reason', 'Non spécifié')}",
                "license_id": license_data['license_id'],
                "client_name": license_data['client_name'],
                "timestamp": datetime.now().isoformat()
            }
        
        # 3. Vérifier expiration
        expiry_date = datetime.fromisoformat(license_data['expiry_date'])
        if datetime.now() > expiry_date:
            return {
                "valid": False,
                "code": "LICENSE_EXPIRED",
                "message": "Licence expirée",
                "license_id": license_data['license_id'],
                "expiry_date": license_data['expiry_date'],
                "timestamp": datetime.now().isoformat()
            }
        
        # 4. Mettre à jour les stats
        now = datetime.now().isoformat()
        cursor.execute(
            """UPDATE licenses 
               SET last_check = ?, total_checks = total_checks + 1 
               WHERE license_key = ?""",
            (now, request.license_key)
        )
        
        # 5. Enregistrer la vérification
        cursor.execute(
            """INSERT INTO license_checks 
               (license_id, check_time, client_ip, was_valid, user_agent)
               VALUES (?, ?, ?, ?, ?)""",
            (
                license_data['license_id'],
                now,
                request.client_info.get('ip', '') if request.client_info else '',
                True,
                request.client_info.get('user_agent', 'PharmaGest') if request.client_info else ''
            )
        )
        
        conn.commit()
        
        # 6. Calculer jours restants
        days_remaining = max(0, (expiry_date - datetime.now()).days)
        
        return {
            "valid": True,
            "code": "LICENSE_VALID",
            "message": "Licence valide",
            "license_id": license_data['license_id'],
            "client_name": license_data['client_name'],
            "expiry_date": license_data['expiry_date'],
            "days_remaining": days_remaining,
            "max_users": license_data['max_users'],
            "timestamp": now,
            "server": RENDER_SERVICE_URL
        }
        
    except Exception as e:
        print(f"❌ Erreur validation: {e}")
        return {
            "valid": False,
            "code": "SERVER_ERROR",
            "message": f"Erreur interne: {str(e)}",
            "timestamp": datetime.now().isoformat()
        }
    finally:
        conn.close()

# --- ENDPOINTS ADMIN ---
@app.get("/admin/licenses")
async def get_all_licenses(x_admin_password: str = Header(None, alias="X-Admin-Password")):
    """Liste toutes les licences"""
    if not x_admin_password or not verify_admin_password(x_admin_password):
        raise HTTPException(status_code=403, detail="Accès administrateur refusé")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT l.*,
               (SELECT COUNT(*) FROM license_checks lc WHERE lc.license_id = l.license_id) as total_checks,
               (SELECT MAX(check_time) FROM license_checks lc WHERE lc.license_id = l.license_id) as last_seen
        FROM licenses l
        ORDER BY l.created_at DESC
    ''')
    
    licenses = []
    for row in cursor.fetchall():
        license_dict = dict(row)
        
        # Déterminer statut
        if license_dict['is_blocked']:
            status = "blocked"
        elif datetime.fromisoformat(license_dict['expiry_date']) < datetime.now():
            status = "expired"
        else:
            status = "active"
        
        license_dict['status'] = status
        license_dict['days_remaining'] = max(0, (
            datetime.fromisoformat(license_dict['expiry_date']) - datetime.now()
        ).days)
        
        licenses.append(license_dict)
    
    conn.close()
    
    return {
        "success": True,
        "count": len(licenses),
        "licenses": licenses,
        "timestamp": datetime.now().isoformat()
    }

@app.post("/admin/block")
async def block_license(request: AdminBlockRequest):
    """Bloque une licence"""
    if not verify_admin_password(request.admin_password):
        raise HTTPException(status_code=403, detail="Accès administrateur refusé")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Vérifier si la licence existe
        cursor.execute(
            "SELECT client_name FROM licenses WHERE license_id = ?",
            (request.license_id,)
        )
        license = cursor.fetchone()
        
        if not license:
            raise HTTPException(status_code=404, detail="Licence non trouvée")
        
        # Bloquer la licence
        cursor.execute(
            """UPDATE licenses 
               SET is_blocked = 1, block_reason = ?, last_check = ?
               WHERE license_id = ?""",
            (request.reason, datetime.now().isoformat(), request.license_id)
        )
        
        # Log l'action
        cursor.execute(
            """INSERT INTO admin_actions 
               (action_type, license_id, admin_user, details)
               VALUES (?, ?, ?, ?)""",
            ("BLOCK", request.license_id, "admin", 
             json.dumps({"reason": request.reason, "time": datetime.now().isoformat()}))
        )
        
        conn.commit()
        
        return {
            "success": True,
            "message": f"✅ Licence {request.license_id} bloquée",
            "client_name": dict(license)['client_name'],
            "reason": request.reason
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur: {str(e)}")
    finally:
        conn.close()

@app.post("/admin/renew")
async def renew_license(request: AdminRenewRequest):
    """Renouvelle une licence"""
    if not verify_admin_password(request.admin_password):
        raise HTTPException(status_code=403, detail="Accès administrateur refusé")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Récupérer la licence
        cursor.execute(
            "SELECT expiry_date, client_name FROM licenses WHERE license_id = ?",
            (request.license_id,)
        )
        license = cursor.fetchone()
        
        if not license:
            raise HTTPException(status_code=404, detail="Licence non trouvée")
        
        license_data = dict(license)
        
        # Calculer nouvelle date
        old_expiry = datetime.fromisoformat(license_data['expiry_date'])
        new_expiry = old_expiry + timedelta(days=request.extra_days)
        
        # Mettre à jour
        cursor.execute(
            """UPDATE licenses 
               SET expiry_date = ?, is_blocked = 0, block_reason = NULL,
                   last_check = ?, notes = COALESCE(notes || '\n', '') || ?
               WHERE license_id = ?""",
            (
                new_expiry.isoformat(),
                datetime.now().isoformat(),
                f"[{datetime.now().strftime('%Y-%m-%d')}] Renouvellement +{request.extra_days}j. {request.notes or ''}",
                request.license_id
            )
        )
        
        # Log l'action
        cursor.execute(
            """INSERT INTO admin_actions 
               (action_type, license_id, admin_user, details)
               VALUES (?, ?, ?, ?)""",
            ("RENEW", request.license_id, "admin",
             json.dumps({"extra_days": request.extra_days, "new_expiry": new_expiry.isoformat()}))
        )
        
        conn.commit()
        
        return {
            "success": True,
            "message": "✅ Licence renouvelée",
            "license_id": request.license_id,
            "client_name": license_data['client_name'],
            "new_expiry": new_expiry.isoformat(),
            "extra_days": request.extra_days
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur: {str(e)}")
    finally:
        conn.close()

@app.post("/admin/create")
async def create_license(request: CreateLicenseRequest):
    """Crée une nouvelle licence"""
    if not verify_admin_password(request.admin_password):
        raise HTTPException(status_code=403, detail="Accès administrateur refusé")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Générer ID unique
        license_id = f"PHG-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"
        
        # Générer clé
        license_key = secrets.token_urlsafe(32)
        
        # Dates
        issue_date = datetime.now()
        expiry_date = issue_date + timedelta(days=request.duration_days)
        
        # Insérer
        cursor.execute(
            """INSERT INTO licenses 
               (license_key, license_id, client_name, client_email,
                issue_date, expiry_date, max_users, is_active)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                license_key,
                license_id,
                request.client_name,
                request.client_email,
                issue_date.isoformat(),
                expiry_date.isoformat(),
                request.max_users,
                True
            )
        )
        
        # Log
        cursor.execute(
            """INSERT INTO admin_actions 
               (action_type, license_id, admin_user, details)
               VALUES (?, ?, ?, ?)""",
            ("CREATE", license_id, "admin",
             json.dumps({
                 "client_name": request.client_name,
                 "duration_days": request.duration_days,
                 "max_users": request.max_users
             }))
        )
        
        conn.commit()
        
        return {
            "success": True,
            "message": "✅ Licence créée",
            "license_id": license_id,
            "license_key": license_key,
            "client_name": request.client_name,
            "client_email": request.client_email,
            "expiry_date": expiry_date.isoformat(),
            "duration_days": request.duration_days,
            "max_users": request.max_users,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur création: {str(e)}")
    finally:
        conn.close()

# --- PAGE ADMIN HTML ---
from fastapi.responses import HTMLResponse

@app.get("/admin_panel.html", response_class=HTMLResponse)
async def admin_panel():
    """Retourne le panneau admin HTML"""
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Admin PharmaGest</title>
        <style>
            body { font-family: Arial; padding: 20px; background: #f5f5f5; }
            .container { max-width: 1200px; margin: 0 auto; }
            .license { border: 1px solid #ddd; padding: 15px; margin: 10px 0; border-radius: 5px; }
            .active { background: #d4edda; border-left: 5px solid #28a745; }
            .blocked { background: #f8d7da; border-left: 5px solid #dc3545; }
            .expired { background: #fff3cd; border-left: 5px solid #ffc107; }
            button { margin: 5px; padding: 8px 15px; cursor: pointer; border: none; border-radius: 3px; }
            .btn-success { background: #28a745; color: white; }
            .btn-danger { background: #dc3545; color: white; }
            .btn-warning { background: #ffc107; color: black; }
            .btn-info { background: #17a2b8; color: white; }
            input, select { padding: 8px; margin: 5px; width: 200px; }
            .stats { display: flex; gap: 20px; margin: 20px 0; }
            .stat-box { background: white; padding: 15px; border-radius: 5px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🔐 Admin Panel PharmaGest</h1>
            
            <div class="stats">
                <div class="stat-box">
                    <h3>📊 Statistiques</h3>
                    <p id="stats">Chargement...</p>
                </div>
                <div class="stat-box">
                    <h3>🔑 Nouvelle Licence</h3>
                    <input type="password" id="adminPass" placeholder="Mot de passe admin" />
                    <input type="text" id="clientName" placeholder="Nom client" />
                    <input type="email" id="clientEmail" placeholder="Email client" />
                    <select id="duration">
                        <option value="30">1 mois</option>
                        <option value="90">3 mois</option>
                        <option value="180">6 mois</option>
                        <option value="365">1 an</option>
                    </select>
                    <button class="btn-success" onclick="createLicense()">➕ Créer Licence</button>
                </div>
            </div>
            
            <div>
                <h2>📋 Licences Actives</h2>
                <button class="btn-info" onclick="loadLicenses()">🔄 Rafraîchir</button>
                <input type="text" id="search" placeholder="Rechercher..." onkeyup="filterLicenses()" />
            </div>
            
            <div id="licenses"></div>
        </div>
        
        <script>
            const SERVER_URL = window.location.origin;
            
            async function loadStats() {
                try {
                    const response = await fetch(`${SERVER_URL}/health`);
                    const data = await response.json();
                    document.getElementById('stats').innerHTML = 
                        `Licences: ${data.license_count}<br>Statut: ${data.status}`;
                } catch (e) {
                    document.getElementById('stats').innerHTML = 'Erreur chargement stats';
                }
            }
            
            async function loadLicenses() {
                const password = document.getElementById('adminPass').value;
                if (!password) {
                    alert('Veuillez entrer le mot de passe admin');
                    return;
                }
                
                try {
                    const response = await fetch(`${SERVER_URL}/admin/licenses`, {
                        headers: { 'X-Admin-Password': password }
                    });
                    
                    if (response.ok) {
                        const data = await response.json();
                        displayLicenses(data.licenses);
                        loadStats();
                    } else {
                        alert('Accès refusé - Mot de passe incorrect');
                    }
                } catch (e) {
                    alert('Erreur de connexion au serveur');
                }
            }
            
            function displayLicenses(licenses) {
                const container = document.getElementById('licenses');
                container.innerHTML = '';
                
                if (licenses.length === 0) {
                    container.innerHTML = '<p>Aucune licence trouvée</p>';
                    return;
                }
                
                licenses.forEach(license => {
                    const div = document.createElement('div');
                    div.className = `license ${license.status}`;
                    div.id = `license-${license.id}`;
                    
                    const days = license.days_remaining;
                    let statusBadge = '';
                    if (license.status === 'active') {
                        statusBadge = `<span style="background:#28a745;color:white;padding:3px 8px;border-radius:3px;">ACTIF (${days}j)</span>`;
                    } else if (license.status === 'blocked') {
                        statusBadge = `<span style="background:#dc3545;color:white;padding:3px 8px;border-radius:3px;">BLOQUÉ</span>`;
                    } else {
                        statusBadge = `<span style="background:#ffc107;color:black;padding:3px 8px;border-radius:3px;">EXPIRÉ</span>`;
                    }
                    
                    div.innerHTML = `
                        <h3>${license.client_name} (${license.license_id})</h3>
                        <p>📧 ${license.client_email} | ${statusBadge} | 👥 ${license.max_users} utilisateurs</p>
                        <p>📅 Créée: ${license.created_at} | Expire: ${license.expiry_date}</p>
                        <p>🔄 Vérifications: ${license.total_checks || 0} | Dernière: ${license.last_seen || 'Jamais'}</p>
                        ${license.is_blocked ? `<p><strong>🚫 Raison: ${license.block_reason}</strong></p>` : ''}
                        
                        <div>
                            <input type="text" id="reason-${license.id}" placeholder="Raison du blocage" />
                            <button class="btn-danger" onclick="blockLicense('${license.license_id}')">🚫 Bloquer</button>
                            <button class="btn-warning" onclick="unblockLicense('${license.license_id}')">✅ Débloquer</button>
                            <button class="btn-success" onclick="renewLicense('${license.license_id}', 30)">🔄 +1 mois</button>
                            <button class="btn-success" onclick="renewLicense('${license.license_id}', 90)">🔄 +3 mois</button>
                            <button class="btn-success" onclick="renewLicense('${license.license_id}', 365)">🔄 +1 an</button>
                        </div>
                        <hr>
                    `;
                    
                    container.appendChild(div);
                });
            }
            
            async function blockLicense(licenseId) {
                const password = document.getElementById('adminPass').value;
                const reason = document.getElementById(`reason-${licenseId}`)?.value || 'Non-paiement';
                
                const response = await fetch(`${SERVER_URL}/admin/block`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        license_id: licenseId,
                        reason: reason,
                        admin_password: password
                    })
                });
                
                if (response.ok) {
                    alert('✅ Licence bloquée!');
                    loadLicenses();
                } else {
                    alert('❌ Erreur lors du blocage');
                }
            }
            
            async function unblockLicense(licenseId) {
                const password = document.getElementById('adminPass').value;
                
                // Pour débloquer, on utilise renew avec 0 jours
                const response = await fetch(`${SERVER_URL}/admin/renew`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        license_id: licenseId,
                        extra_days: 0,
                        admin_password: password,
                        notes: "Licence débloquée"
                    })
                });
                
                if (response.ok) {
                    alert('✅ Licence débloquée!');
                    loadLicenses();
                } else {
                    alert('❌ Erreur lors du déblocage');
                }
            }
            
            async function renewLicense(licenseId, extraDays) {
                const password = document.getElementById('adminPass').value;
                
                const response = await fetch(`${SERVER_URL}/admin/renew`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        license_id: licenseId,
                        extra_days: extraDays,
                        admin_password: password
                    })
                });
                
                if (response.ok) {
                    alert(\`✅ Licence renouvelée de \${extraDays} jours!\`);
                    loadLicenses();
                } else {
                    alert('❌ Erreur lors du renouvellement');
                }
            }
            
            async function createLicense() {
                const password = document.getElementById('adminPass').value;
                const clientName = document.getElementById('clientName').value;
                const clientEmail = document.getElementById('clientEmail').value;
                const duration = parseInt(document.getElementById('duration').value);
                
                if (!clientName || !clientEmail) {
                    alert('Veuillez remplir tous les champs');
                    return;
                }
                
                const response = await fetch(\`\${SERVER_URL}/admin/create\`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        client_name: clientName,
                        client_email: clientEmail,
                        duration_days: duration,
                        max_users: 1,
                        admin_password: password
                    })
                });
                
                if (response.ok) {
                    const data = await response.json();
                    alert(\`✅ Licence créée!\\nID: \${data.license_id}\\nClé: \${data.license_key}\`);
                    loadLicenses();
                } else {
                    alert('❌ Erreur création licence');
                }
            }
            
            function filterLicenses() {
                const search = document.getElementById('search').value.toLowerCase();
                const licenses = document.querySelectorAll('.license');
                
                licenses.forEach(license => {
                    const text = license.textContent.toLowerCase();
                    if (text.includes(search)) {
                        license.style.display = 'block';
                    } else {
                        license.style.display = 'none';
                    }
                });
            }
            
            // Charger les stats au démarrage
            loadStats();
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)