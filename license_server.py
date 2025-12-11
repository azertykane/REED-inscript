# license_server.py - VERSION SIMPLIFIÉE ET FONCTIONNELLE
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel
from datetime import datetime, timedelta
import sqlite3
import hashlib
import json
import os
import uuid
import secrets
from typing import Optional
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

# Application FastAPI
app = FastAPI(
    title="PharmaGest License Server",
    description="API de gestion des licences à distance",
    version="1.0.0"
)

# Autoriser toutes les origines
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Chemin de la base de données
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_PATH = os.path.join(BASE_DIR, "pharmagest_licenses.db")

# --- INITIALISATION BASE DE DONNÉES ---
def init_database():
    """Initialise la base de données SQLite"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS licenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            license_key TEXT UNIQUE NOT NULL,
            license_id TEXT UNIQUE NOT NULL,
            client_name TEXT NOT NULL,
            client_email TEXT NOT NULL,
            system_fingerprint TEXT,
            mac_address TEXT,
            computer_name TEXT,
            ip_address TEXT,
            windows_version TEXT,
            issue_date TEXT NOT NULL,
            expiry_date TEXT NOT NULL,
            max_users INTEGER DEFAULT 1,
            is_active BOOLEAN DEFAULT 1,
            is_blocked BOOLEAN DEFAULT 0,
            block_reason TEXT,
            last_check TEXT,
            total_checks INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS license_checks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            license_id TEXT NOT NULL,
            check_time TEXT NOT NULL,
            client_ip TEXT,
            mac_address TEXT,
            was_valid BOOLEAN,
            response_code TEXT
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
    """Vérifie le mot de passe admin (SHA256 de 'admin123')"""
    expected_hash = "8c6976e5b5410415bde908bd4dee15dfb167a9c873fc4bb8a81f6f2ab448a918"
    return hashlib.sha256(password.encode()).hexdigest() == expected_hash

# --- MODÈLES PYDANTIC ---
class LicenseValidationRequest(BaseModel):
    license_key: str
    system_fingerprint: str
    client_name: Optional[str] = None
    client_email: Optional[str] = None
    mac_address: Optional[str] = None
    computer_name: Optional[str] = None
    ip_address: Optional[str] = None
    windows_version: Optional[str] = None

class AdminBlockRequest(BaseModel):
    license_id: str
    reason: str = "Non-paiement"
    admin_password: str

class AdminRenewRequest(BaseModel):
    license_id: str
    extra_days: int = 30
    admin_password: str

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
        "version": "1.0.0",
        "status": "online",
        "endpoints": {
            "validate": "POST /api/v1/validate",
            "health": "GET /health",
            "admin_panel": "GET /admin_panel.html"
        }
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
    """Valide une licence - Appelé par PharmaGest"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Chercher la licence
        cursor.execute(
            "SELECT * FROM licenses WHERE license_key = ?",
            (request.license_key,)
        )
        license = cursor.fetchone()
        
        now = datetime.now().isoformat()
        
        # Si licence non trouvée
        if not license:
            # Créer une nouvelle licence (première activation)
            if request.client_name and request.client_email:
                license_id = f"PHG-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"
                expiry_date = (datetime.now() + timedelta(days=365)).isoformat()
                
                cursor.execute('''
                    INSERT INTO licenses 
                    (license_key, license_id, client_name, client_email,
                     system_fingerprint, mac_address, computer_name, ip_address,
                     windows_version, issue_date, expiry_date, max_users,
                     is_active, last_check)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    request.license_key,
                    license_id,
                    request.client_name,
                    request.client_email,
                    request.system_fingerprint,
                    request.mac_address,
                    request.computer_name,
                    request.ip_address,
                    request.windows_version,
                    now,
                    expiry_date,
                    1,
                    True,
                    now
                ))
                
                license_data = {
                    'license_id': license_id,
                    'client_name': request.client_name,
                    'client_email': request.client_email,
                    'expiry_date': expiry_date,
                    'is_blocked': False
                }
            else:
                return JSONResponse(
                    status_code=404,
                    content={
                        "valid": False,
                        "code": "LICENSE_NOT_FOUND",
                        "message": "Licence non trouvée"
                    }
                )
        else:
            license_data = dict(license)
        
        # Enregistrer la vérification
        cursor.execute('''
            INSERT INTO license_checks 
            (license_id, check_time, client_ip, mac_address, was_valid, response_code)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            license_data['license_id'],
            now,
            request.ip_address or "127.0.0.1",
            request.mac_address or "00:00:00:00:00:00",
            True,
            "VALID"
        ))
        
        # Mettre à jour les stats
        cursor.execute('''
            UPDATE licenses 
            SET last_check = ?, total_checks = total_checks + 1,
                mac_address = COALESCE(?, mac_address),
                computer_name = COALESCE(?, computer_name),
                ip_address = COALESCE(?, ip_address)
            WHERE license_id = ?
        ''', (
            now,
            request.mac_address,
            request.computer_name,
            request.ip_address,
            license_data['license_id']
        ))
        
        conn.commit()
        
        # Vérifier blocage
        if license_data.get('is_blocked', False):
            return JSONResponse(
                status_code=403,
                content={
                    "valid": False,
                    "code": "ADMIN_BLOCKED",
                    "message": f"Licence bloquée: {license_data.get('block_reason', 'Non spécifié')}",
                    "license_id": license_data['license_id']
                }
            )
        
        # Vérifier expiration
        expiry_date = datetime.fromisoformat(license_data['expiry_date'])
        if datetime.now() > expiry_date:
            return JSONResponse(
                status_code=403,
                content={
                    "valid": False,
                    "code": "LICENSE_EXPIRED",
                    "message": "Licence expirée",
                    "license_id": license_data['license_id'],
                    "expiry_date": license_data['expiry_date']
                }
            )
        
        # Calculer jours restants
        days_remaining = max(0, (expiry_date - datetime.now()).days)
        
        return {
            "valid": True,
            "code": "LICENSE_VALID",
            "message": "Licence valide",
            "license_id": license_data['license_id'],
            "client_name": license_data['client_name'],
            "client_email": license_data.get('client_email'),
            "expiry_date": license_data['expiry_date'],
            "days_remaining": days_remaining,
            "max_users": license_data.get('max_users', 1),
            "mac_address": request.mac_address,
            "computer_name": request.computer_name,
            "timestamp": now
        }
        
    except Exception as e:
        print(f"❌ Erreur validation: {e}")
        return JSONResponse(
            status_code=500,
            content={
                "valid": False,
                "code": "SERVER_ERROR",
                "message": f"Erreur interne: {str(e)}"
            }
        )
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
               (SELECT MAX(check_time) FROM license_checks lc WHERE lc.license_id = l.license_id) as last_check_time
        FROM licenses l
        ORDER BY l.created_at DESC
    ''')
    
    licenses = []
    for row in cursor.fetchall():
        license_dict = dict(row)
        
        # Statut
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
        "licenses": licenses
    }

@app.post("/admin/block")
async def block_license(request: AdminBlockRequest):
    """Bloque une licence"""
    if not verify_admin_password(request.admin_password):
        raise HTTPException(status_code=403, detail="Accès administrateur refusé")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            "SELECT client_name FROM licenses WHERE license_id = ?",
            (request.license_id,)
        )
        license = cursor.fetchone()
        
        if not license:
            raise HTTPException(status_code=404, detail="Licence non trouvée")
        
        cursor.execute(
            "UPDATE licenses SET is_blocked = 1, block_reason = ? WHERE license_id = ?",
            (request.reason, request.license_id)
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
        cursor.execute(
            "SELECT expiry_date, client_name FROM licenses WHERE license_id = ?",
            (request.license_id,)
        )
        license = cursor.fetchone()
        
        if not license:
            raise HTTPException(status_code=404, detail="Licence non trouvée")
        
        license_data = dict(license)
        old_expiry = datetime.fromisoformat(license_data['expiry_date'])
        new_expiry = old_expiry + timedelta(days=request.extra_days)
        
        cursor.execute(
            "UPDATE licenses SET expiry_date = ?, is_blocked = 0 WHERE license_id = ?",
            (new_expiry.isoformat(), request.license_id)
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
        license_id = f"PHG-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"
        license_key = secrets.token_urlsafe(32)
        
        issue_date = datetime.now()
        expiry_date = issue_date + timedelta(days=request.duration_days)
        
        cursor.execute('''
            INSERT INTO licenses 
            (license_key, license_id, client_name, client_email,
             issue_date, expiry_date, max_users, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            license_key,
            license_id,
            request.client_name,
            request.client_email,
            issue_date.isoformat(),
            expiry_date.isoformat(),
            request.max_users,
            True
        ))
        
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
            "max_users": request.max_users
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur création: {str(e)}")
    finally:
        conn.close()

# --- PAGE ADMIN SIMPLE ET FONCTIONNELLE ---
@app.get("/admin_panel.html", response_class=HTMLResponse)
async def admin_panel():
    return HTMLResponse(content="""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Admin PharmaGest</title>
        <style>
            body { font-family: Arial, sans-serif; padding: 20px; background: #f5f5f5; }
            .container { max-width: 1200px; margin: 0 auto; }
            .tab { overflow: hidden; border: 1px solid #ccc; background: #f1f1f1; }
            .tab button { padding: 14px 16px; border: none; cursor: pointer; }
            .tab button.active { background: #007bff; color: white; }
            .tabcontent { padding: 20px; border: 1px solid #ccc; border-top: none; background: white; display: none; }
            .tabcontent.active { display: block; }
            
            .license { border: 1px solid #ddd; padding: 15px; margin: 10px 0; border-radius: 5px; }
            .active { border-left: 5px solid #28a745; }
            .blocked { border-left: 5px solid #dc3545; }
            .expired { border-left: 5px solid #ffc107; }
            
            button { padding: 8px 15px; margin: 5px; cursor: pointer; border: none; border-radius: 4px; }
            .btn-success { background: #28a745; color: white; }
            .btn-danger { background: #dc3545; color: white; }
            .btn-info { background: #17a2b8; color: white; }
            
            input, select { padding: 8px; margin: 5px; width: 250px; }
            .system-info { background: #e9ecef; padding: 10px; border-radius: 5px; margin: 5px 0; font-size: 12px; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🔐 Admin PharmaGest</h1>
            
            <div class="tab">
                <button class="tablinks active" onclick="openTab(event, 'licenses')">📋 Licences</button>
                <button class="tablinks" onclick="openTab(event, 'create')">➕ Créer Licence</button>
            </div>
            
            <!-- Onglet Licences -->
            <div id="licenses" class="tabcontent active">
                <h2>Licences Actives</h2>
                <div>
                    <input type="password" id="adminPass" placeholder="Mot de passe admin (admin123)" />
                    <button onclick="loadLicenses()" class="btn-info">Charger Licences</button>
                </div>
                <div id="licenses-list"></div>
            </div>
            
            <!-- Onglet Création -->
            <div id="create" class="tabcontent">
                <h2>Créer une nouvelle licence</h2>
                <div>
                    <input type="password" id="create-pass" placeholder="Mot de passe admin" /><br>
                    <input type="text" id="client-name" placeholder="Nom du client" /><br>
                    <input type="email" id="client-email" placeholder="Email du client" /><br>
                    <select id="duration">
                        <option value="30">1 mois</option>
                        <option value="90">3 mois</option>
                        <option value="180">6 mois</option>
                        <option value="365">1 an</option>
                    </select>
                    <br><br>
                    <button onclick="createLicense()" class="btn-success">Créer Licence</button>
                </div>
                <div id="create-result" style="margin-top: 20px;"></div>
            </div>
        </div>

        <script>
            const SERVER_URL = window.location.origin;
            
            function openTab(evt, tabName) {
                document.querySelectorAll('.tabcontent').forEach(tab => tab.classList.remove('active'));
                document.querySelectorAll('.tablinks').forEach(btn => btn.classList.remove('active'));
                
                document.getElementById(tabName).classList.add('active');
                evt.currentTarget.classList.add('active');
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
                    } else {
                        alert('Accès refusé - Mot de passe incorrect');
                    }
                } catch (e) {
                    alert('Erreur de connexion au serveur');
                }
            }
            
            function displayLicenses(licenses) {
                const container = document.getElementById('licenses-list');
                container.innerHTML = '';
                
                if (licenses.length === 0) {
                    container.innerHTML = '<p>Aucune licence trouvée</p>';
                    return;
                }
                
                licenses.forEach(license => {
                    const div = document.createElement('div');
                    div.className = `license ${license.status}`;
                    
                    let statusBadge = '';
                    if (license.status === 'active') {
                        statusBadge = `<span style="background:#28a745;color:white;padding:3px 8px;border-radius:3px;">ACTIF (${license.days_remaining}j)</span>`;
                    } else if (license.status === 'blocked') {
                        statusBadge = `<span style="background:#dc3545;color:white;padding:3px 8px;border-radius:3px;">BLOQUÉ</span>`;
                    } else {
                        statusBadge = `<span style="background:#ffc107;color:black;padding:3px 8px;border-radius:3px;">EXPIRÉ</span>`;
                    }
                    
                    const systemInfo = `
                        <div class="system-info">
                            ${license.mac_address ? `MAC: ${license.mac_address}<br>` : ''}
                            ${license.computer_name ? `Ordinateur: ${license.computer_name}<br>` : ''}
                            ${license.ip_address ? `IP: ${license.ip_address}<br>` : ''}
                            Dernière vérification: ${license.last_check_time || 'Jamais'}<br>
                            Total vérifications: ${license.total_checks || 0}
                        </div>
                    `;
                    
                    div.innerHTML = `
                        <h3>${license.client_name} (${license.license_id})</h3>
                        <p>📧 ${license.client_email} | ${statusBadge}</p>
                        <p>📅 Expire: ${license.expiry_date}</p>
                        ${license.is_blocked ? `<p><strong>🚫 Raison: ${license.block_reason}</strong></p>` : ''}
                        
                        ${systemInfo}
                        
                        <div style="margin-top: 10px;">
                            <input type="text" id="reason-${license.id}" placeholder="Raison du blocage" />
                            <button class="btn-danger" onclick="blockLicense('${license.license_id}')">🚫 Bloquer</button>
                            <button class="btn-success" onclick="renewLicense('${license.license_id}', 30)">🔄 +1 mois</button>
                            <button class="btn-success" onclick="renewLicense('${license.license_id}', 365)">🔄 +1 an</button>
                        </div>
                        <hr>
                    `;
                    
                    container.appendChild(div);
                });
            }
            
            async function blockLicense(licenseId) {
                const password = document.getElementById('adminPass').value;
                const reason = document.querySelector(`#reason-${licenseId}`)?.value || 'Non-paiement';
                
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
                    alert('❌ Erreur');
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
                    alert('❌ Erreur');
                }
            }
            
            async function createLicense() {
                const password = document.getElementById('create-pass').value;
                const clientName = document.getElementById('client-name').value;
                const clientEmail = document.getElementById('client-email').value;
                const duration = parseInt(document.getElementById('duration').value);
                
                if (!clientName || !clientEmail) {
                    alert('Veuillez remplir tous les champs');
                    return;
                }
                
                const response = await fetch(`${SERVER_URL}/admin/create`, {
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
                
                const resultDiv = document.getElementById('create-result');
                
                if (response.ok) {
                    const data = await response.json();
                    resultDiv.innerHTML = \`
                        <div style="background:#d4edda;padding:15px;border-radius:5px;">
                            <h4>✅ Licence créée!</h4>
                            <p><strong>Clé de licence:</strong> <code style="background:#eee;padding:5px;">\${data.license_key}</code></p>
                            <p>Envoyez cette clé au client pour activation dans PharmaGest</p>
                        </div>
                    \`;
                    
                    document.getElementById('client-name').value = '';
                    document.getElementById('client-email').value = '';
                } else {
                    resultDiv.innerHTML = '<div style="background:#f8d7da;padding:15px;border-radius:5px;">❌ Erreur création licence</div>';
                }
            }
        </script>
    </body>
    </html>
    """)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)