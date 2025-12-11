# license_server.py - VERSION AVEC RÉCEPTION PHARMAGEST
from fastapi import FastAPI, HTTPException, BackgroundTasks, Header, Depends
from pydantic import BaseModel
from datetime import datetime, timedelta
import sqlite3
import hashlib
import json
import os
import requests
import uuid
import secrets
from typing import Optional, Dict, Any
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

# Configuration Render
RENDER_SERVICE_URL = "https://pharma-1-7g7e.onrender.com"

# Chemin de la base de données
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_PATH = os.path.join(BASE_DIR, "pharmagest_licenses.db")

# Application FastAPI
app = FastAPI(
    title="PharmaGest License Server",
    description="API de gestion des licences à distance",
    version="3.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS pour autoriser PharmaGest
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Autorise toutes les origines (à restreindre en prod)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- INITIALISATION BASE DE DONNÉES AVEC NOUVELLES TABLES ---
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
            mac_address TEXT,
            ip_address TEXT,
            computer_name TEXT,
            windows_version TEXT,
            issue_date TEXT NOT NULL,
            expiry_date TEXT NOT NULL,
            max_users INTEGER DEFAULT 1,
            is_active BOOLEAN DEFAULT 1,
            is_blocked BOOLEAN DEFAULT 0,
            block_reason TEXT,
            last_check TEXT,
            last_seen TEXT,
            total_checks INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            notes TEXT,
            app_version TEXT,
            user_agent TEXT
        )
    ''')
    
    # Table des vérifications détaillées
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS license_checks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            license_id TEXT NOT NULL,
            check_time TEXT NOT NULL,
            client_ip TEXT,
            mac_address TEXT,
            system_fingerprint TEXT,
            computer_name TEXT,
            was_valid BOOLEAN,
            user_agent TEXT,
            response_code TEXT,
            details TEXT
        )
    ''')
    
    # Table admin (logs des actions)
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
    
    # Table des clients actifs
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS active_clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            license_id TEXT NOT NULL,
            client_name TEXT,
            last_seen TEXT,
            ip_address TEXT,
            mac_address TEXT,
            computer_name TEXT,
            app_version TEXT,
            is_online BOOLEAN DEFAULT 0,
            session_start TEXT,
            session_end TEXT,
            FOREIGN KEY (license_id) REFERENCES licenses (license_id)
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
    expected_hash = "8c6976e5b5410415bde908bd4dee15dfb167a9c873fc4bb8a81f6f2ab448a918"  # "admin123"
    return hashlib.sha256(password.encode()).hexdigest() == expected_hash

# --- MODÈLES PYDANTIC ---
class SystemInfo(BaseModel):
    mac_address: Optional[str] = None
    ip_address: Optional[str] = None
    computer_name: Optional[str] = None
    windows_version: Optional[str] = None
    user_profile: Optional[str] = None

class ClientInfo(BaseModel):
    ip: Optional[str] = None
    user_agent: Optional[str] = None
    app_version: Optional[str] = None
    system_info: Optional[SystemInfo] = None

class LicenseValidationRequest(BaseModel):
    license_key: str
    system_fingerprint: str
    client_info: Optional[ClientInfo] = None

class PharmaGestRegisterRequest(BaseModel):
    """Pour l'enregistrement depuis PharmaGest"""
    license_key: str
    client_name: str
    client_email: str
    system_fingerprint: str
    system_info: SystemInfo
    app_version: str = "2.0.0"

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

# --- ENDPOINTS POUR PHARMAGEST ---
@app.get("/")
async def root():
    return {
        "service": "PharmaGest License Server",
        "version": "3.0.0",
        "status": "online",
        "pharmagest_api": "POST /api/v1/register pour enregistrer PharmaGest",
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
    
    cursor.execute("SELECT COUNT(*) as count FROM active_clients WHERE is_online = 1")
    online_clients = cursor.fetchone()["count"]
    
    conn.close()
    
    return {
        "status": "healthy",
        "license_count": license_count,
        "online_clients": online_clients,
        "timestamp": datetime.now().isoformat(),
        "pharmagest_compatible": True
    }

@app.post("/api/v1/register")
async def register_pharmagest(request: PharmaGestRegisterRequest):
    """
    Endpoint appelé par PharmaGest pour s'enregistrer
    C'est ici que PharmaGest envoie ses infos (MAC, etc.)
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        now = datetime.now().isoformat()
        
        # 1. Vérifier si la licence existe déjà
        cursor.execute(
            "SELECT * FROM licenses WHERE license_key = ?",
            (request.license_key,)
        )
        existing = cursor.fetchone()
        
        if existing:
            # Mettre à jour les informations existantes
            license_data = dict(existing)
            cursor.execute('''
                UPDATE licenses SET
                    last_seen = ?,
                    last_check = ?,
                    total_checks = total_checks + 1,
                    mac_address = COALESCE(?, mac_address),
                    ip_address = COALESCE(?, ip_address),
                    computer_name = COALESCE(?, computer_name),
                    windows_version = COALESCE(?, windows_version),
                    app_version = ?,
                    user_agent = ?
                WHERE license_key = ?
            ''', (
                now, now,
                request.system_info.mac_address,
                request.system_info.ip_address,
                request.system_info.computer_name,
                request.system_info.windows_version,
                request.app_version,
                f"PharmaGest v{request.app_version}",
                request.license_key
            ))
            
            # Mettre à jour la table active_clients
            cursor.execute('''
                INSERT OR REPLACE INTO active_clients 
                (license_id, client_name, last_seen, ip_address, mac_address, 
                 computer_name, app_version, is_online, session_start)
                VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)
            ''', (
                license_data['license_id'],
                request.client_name,
                now,
                request.system_info.ip_address,
                request.system_info.mac_address,
                request.system_info.computer_name,
                request.app_version,
                now
            ))
            
        else:
            # 2. Générer une nouvelle licence
            license_id = f"PHG-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"
            expiry_date = (datetime.now() + timedelta(days=365)).isoformat()
            
            # Insérer la nouvelle licence
            cursor.execute('''
                INSERT INTO licenses 
                (license_key, license_id, client_name, client_email,
                 system_fingerprint, mac_address, ip_address, computer_name,
                 windows_version, issue_date, expiry_date, max_users,
                 is_active, last_check, last_seen, app_version, user_agent)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                request.license_key,
                license_id,
                request.client_name,
                request.client_email,
                request.system_fingerprint,
                request.system_info.mac_address,
                request.system_info.ip_address,
                request.system_info.computer_name,
                request.system_info.windows_version,
                now,
                expiry_date,
                1,  # max_users
                True,
                now,
                now,
                request.app_version,
                f"PharmaGest v{request.app_version}"
            ))
            
            # Ajouter au tableau des clients actifs
            cursor.execute('''
                INSERT INTO active_clients 
                (license_id, client_name, last_seen, ip_address, mac_address,
                 computer_name, app_version, is_online, session_start)
                VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)
            ''', (
                license_id,
                request.client_name,
                now,
                request.system_info.ip_address,
                request.system_info.mac_address,
                request.system_info.computer_name,
                request.app_version,
                now
            ))
        
        # 3. Enregistrer la vérification
        cursor.execute('''
            INSERT INTO license_checks 
            (license_id, check_time, client_ip, mac_address, system_fingerprint,
             computer_name, was_valid, user_agent, response_code, details)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            license_id if not existing else existing['license_id'],
            now,
            request.system_info.ip_address,
            request.system_info.mac_address,
            request.system_fingerprint,
            request.system_info.computer_name,
            True,
            f"PharmaGest v{request.app_version}",
            "REGISTERED",
            json.dumps({
                "action": "registration",
                "client_name": request.client_name,
                "email": request.client_email
            })
        ))
        
        conn.commit()
        
        return {
            "success": True,
            "message": "✅ PharmaGest enregistré avec succès",
            "license_id": license_id if not existing else existing['license_id'],
            "client_name": request.client_name,
            "timestamp": now,
            "server": RENDER_SERVICE_URL,
            "instructions": "Votre installation est maintenant surveillée par le serveur"
        }
        
    except Exception as e:
        print(f"❌ Erreur enregistrement PharmaGest: {e}")
        return {
            "success": False,
            "message": f"Erreur d'enregistrement: {str(e)}",
            "timestamp": datetime.now().isoformat()
        }
    finally:
        conn.close()

@app.post("/api/v1/validate")
async def validate_license(request: LicenseValidationRequest):
    """Valide une licence (appelé régulièrement par PharmaGest)"""
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
                "timestamp": datetime.now().isoformat(),
                "block_reason": license_data.get('block_reason')
            }
        
        # 3. Vérifier expiration
        expiry_date = datetime.fromisoformat(license_data['expiry_date'])
        if datetime.now() > expiry_date:
            return {
                "valid": False,
                "code": "LICENSE_EXPIRED",
                "message": "Licence expirée",
                "license_id": license_data['license_id'],
                "client_name": license_data['client_name'],
                "expiry_date": license_data['expiry_date'],
                "timestamp": datetime.now().isoformat()
            }
        
        # 4. Mettre à jour les stats et informations client
        now = datetime.now().isoformat()
        cursor.execute('''
            UPDATE licenses SET
                last_check = ?,
                last_seen = ?,
                total_checks = total_checks + 1,
                ip_address = COALESCE(?, ip_address),
                user_agent = COALESCE(?, user_agent)
            WHERE license_key = ?
        ''', (
            now,
            now,
            request.client_info.ip if request.client_info else None,
            request.client_info.user_agent if request.client_info else None,
            request.license_key
        ))
        
        # 5. Mettre à jour active_clients
        cursor.execute('''
            UPDATE active_clients SET
                last_seen = ?,
                ip_address = COALESCE(?, ip_address),
                is_online = 1
            WHERE license_id = ?
        ''', (
            now,
            request.client_info.ip if request.client_info else None,
            license_data['license_id']
        ))
        
        # 6. Enregistrer la vérification
        cursor.execute('''
            INSERT INTO license_checks 
            (license_id, check_time, client_ip, mac_address, system_fingerprint,
             computer_name, was_valid, user_agent, response_code)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            license_data['license_id'],
            now,
            request.client_info.ip if request.client_info else '',
            license_data.get('mac_address', ''),
            request.system_fingerprint,
            license_data.get('computer_name', ''),
            True,
            request.client_info.user_agent if request.client_info else 'PharmaGest',
            "VALID"
        ))
        
        conn.commit()
        
        # 7. Calculer jours restants
        days_remaining = max(0, (expiry_date - datetime.now()).days)
        
        return {
            "valid": True,
            "code": "LICENSE_VALID",
            "message": "Licence valide",
            "license_id": license_data['license_id'],
            "client_name": license_data['client_name'],
            "client_email": license_data['client_email'],
            "expiry_date": license_data['expiry_date'],
            "days_remaining": days_remaining,
            "max_users": license_data['max_users'],
            "mac_address": license_data.get('mac_address'),
            "computer_name": license_data.get('computer_name'),
            "ip_address": license_data.get('ip_address'),
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

# --- ENDPOINTS ADMIN AMÉLIORÉS ---
@app.get("/admin/licenses")
async def get_all_licenses(x_admin_password: str = Header(None, alias="X-Admin-Password")):
    """Liste toutes les licences avec infos détaillées"""
    if not x_admin_password or not verify_admin_password(x_admin_password):
        raise HTTPException(status_code=403, detail="Accès administrateur refusé")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT l.*,
               (SELECT COUNT(*) FROM license_checks lc WHERE lc.license_id = l.license_id) as total_checks,
               (SELECT MAX(check_time) FROM license_checks lc WHERE lc.license_id = l.license_id) as last_check_time,
               ac.is_online,
               ac.last_seen as client_last_seen,
               ac.session_start
        FROM licenses l
        LEFT JOIN active_clients ac ON l.license_id = ac.license_id
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
        
        # Vérifier si en ligne (vu il y a moins de 5 minutes)
        last_seen = license_dict.get('client_last_seen')
        if last_seen:
            last_seen_time = datetime.fromisoformat(last_seen)
            license_dict['is_online_now'] = (datetime.now() - last_seen_time).seconds < 300  # 5 minutes
        else:
            license_dict['is_online_now'] = False
        
        licenses.append(license_dict)
    
    conn.close()
    
    return {
        "success": True,
        "count": len(licenses),
        "licenses": licenses,
        "timestamp": datetime.now().isoformat()
    }

@app.get("/admin/active-clients")
async def get_active_clients(x_admin_password: str = Header(None, alias="X-Admin-Password")):
    """Liste des clients actuellement en ligne"""
    if not x_admin_password or not verify_admin_password(x_admin_password):
        raise HTTPException(status_code=403, detail="Accès administrateur refusé")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT ac.*, l.client_email, l.expiry_date, l.is_blocked, l.block_reason
        FROM active_clients ac
        JOIN licenses l ON ac.license_id = l.license_id
        WHERE ac.is_online = 1
        ORDER BY ac.last_seen DESC
    ''')
    
    clients = []
    for row in cursor.fetchall():
        client_dict = dict(row)
        
        # Calculer le temps en ligne
        if client_dict.get('session_start'):
            start_time = datetime.fromisoformat(client_dict['session_start'])
            online_time = datetime.now() - start_time
            client_dict['online_duration'] = str(online_time).split('.')[0]  # Enlever microsecondes
        else:
            client_dict['online_duration'] = "Inconnu"
        
        clients.append(client_dict)
    
    conn.close()
    
    return {
        "success": True,
        "online_count": len(clients),
        "clients": clients,
        "timestamp": datetime.now().isoformat()
    }

@app.get("/admin/license/{license_id}/history")
async def get_license_history(license_id: str, x_admin_password: str = Header(None, alias="X-Admin-Password")):
    """Historique complet d'une licence"""
    if not x_admin_password or not verify_admin_password(x_admin_password):
        raise HTTPException(status_code=403, detail="Accès administrateur refusé")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Infos de la licence
    cursor.execute("SELECT * FROM licenses WHERE license_id = ?", (license_id,))
    license_info = cursor.fetchone()
    
    if not license_info:
        raise HTTPException(status_code=404, detail="Licence non trouvée")
    
    # Historique des vérifications
    cursor.execute('''
        SELECT * FROM license_checks 
        WHERE license_id = ? 
        ORDER BY check_time DESC 
        LIMIT 100
    ''', (license_id,))
    
    checks = [dict(row) for row in cursor.fetchall()]
    
    # Actions admin
    cursor.execute('''
        SELECT * FROM admin_actions 
        WHERE license_id = ? 
        ORDER BY action_time DESC
    ''', (license_id,))
    
    actions = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    
    return {
        "success": True,
        "license": dict(license_info),
        "check_history": checks,
        "admin_actions": actions,
        "check_count": len(checks),
        "timestamp": datetime.now().isoformat()
    }

# ... [Les autres fonctions admin restent les mêmes que précédemment] ...

# --- PAGE ADMIN HTML AMÉLIORÉE ---
@app.get("/admin_panel.html", response_class=HTMLResponse)
async def admin_panel():
    """Panneau admin avec infos PharmaGest en temps réel"""
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Admin PharmaGest - Surveillance Clients</title>
        <style>
            body { font-family: Arial; padding: 20px; background: #f5f5f5; }
            .container { max-width: 1400px; margin: 0 auto; }
            .tab { overflow: hidden; border: 1px solid #ccc; background: #f1f1f1; }
            .tab button { background: inherit; float: left; border: none; outline: none; cursor: pointer; padding: 14px 16px; transition: 0.3s; }
            .tab button:hover { background: #ddd; }
            .tab button.active { background: #007bff; color: white; }
            .tabcontent { display: none; padding: 20px; border: 1px solid #ccc; border-top: none; background: white; }
            
            .license { border: 1px solid #ddd; padding: 15px; margin: 10px 0; border-radius: 5px; }
            .active { border-left: 5px solid #28a745; }
            .blocked { border-left: 5px solid #dc3545; }
            .expired { border-left: 5px solid #ffc107; }
            
            .online-badge { background: #28a745; color: white; padding: 2px 8px; border-radius: 10px; font-size: 12px; }
            .offline-badge { background: #6c757d; color: white; padding: 2px 8px; border-radius: 10px; font-size: 12px; }
            
            button { margin: 5px; padding: 8px 15px; cursor: pointer; border: none; border-radius: 3px; }
            .btn-success { background: #28a745; color: white; }
            .btn-danger { background: #dc3545; color: white; }
            .btn-warning { background: #ffc107; color: black; }
            .btn-info { background: #17a2b8; color: white; }
            
            .system-info { background: #e9ecef; padding: 10px; border-radius: 5px; margin: 5px 0; font-size: 12px; }
            .stats-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; margin: 20px 0; }
            .stat-card { background: white; padding: 15px; border-radius: 5px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); text-align: center; }
            
            table { width: 100%; border-collapse: collapse; margin: 15px 0; }
            th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
            th { background: #f8f9fa; }
            tr:hover { background: #f5f5f5; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🔐 Admin PharmaGest - Surveillance Clients</h1>
            <p>Serveur: <span id="server-url"></span> | <button onclick="loadStats()" class="btn-info">🔄 Rafraîchir</button></p>
            
            <div class="tab">
                <button class="tablinks active" onclick="openTab(event, 'licenses')">📋 Licences</button>
                <button class="tablinks" onclick="openTab(event, 'online')">🟢 Clients en ligne</button>
                <button class="tablinks" onclick="openTab(event, 'create')">➕ Nouvelle Licence</button>
                <button class="tablinks" onclick="openTab(event, 'stats')">📊 Statistiques</button>
            </div>
            
            <!-- Onglet Licences -->
            <div id="licenses" class="tabcontent" style="display: block;">
                <h2>📋 Toutes les licences</h2>
                <div style="margin: 15px 0;">
                    <input type="password" id="adminPass" placeholder="Mot de passe admin" />
                    <button onclick="loadLicenses()" class="btn-info">Charger Licences</button>
                    <input type="text" id="search" placeholder="Rechercher..." onkeyup="filterLicenses()" style="float: right; width: 300px;" />
                </div>
                <div id="licenses-list"></div>
            </div>
            
            <!-- Onglet Clients en ligne -->
            <div id="online" class="tabcontent">
                <h2>🟢 Clients actuellement en ligne</h2>
                <div id="online-clients"></div>
            </div>
            
            <!-- Onglet Création -->
            <div id="create" class="tabcontent">
                <h2>➕ Générer une nouvelle licence</h2>
                <div style="background: #e9f7fe; padding: 20px; border-radius: 5px;">
                    <input type="password" id="create-pass" placeholder="Mot de passe admin" /><br><br>
                    <input type="text" id="client-name" placeholder="Nom du client" /><br>
                    <input type="email" id="client-email" placeholder="Email du client" /><br>
                    <select id="duration">
                        <option value="30">1 mois</option>
                        <option value="90">3 mois</option>
                        <option value="180">6 mois</option>
                        <option value="365">1 an</option>
                        <option value="730">2 ans</option>
                    </select>
                    <input type="number" id="max-users" placeholder="Utilisateurs max" value="1" min="1" max="50" /><br><br>
                    <button onclick="createLicense()" class="btn-success">Créer la licence</button>
                </div>
                <div id="create-result" style="margin-top: 20px;"></div>
            </div>
            
            <!-- Onglet Statistiques -->
            <div id="stats" class="tabcontent">
                <h2>📊 Statistiques du serveur</h2>
                <div class="stats-grid">
                    <div class="stat-card" id="stat-total">Total: ...</div>
                    <div class="stat-card" id="stat-active">Actives: ...</div>
                    <div class="stat-card" id="stat-online">En ligne: ...</div>
                    <div class="stat-card" id="stat-expired">Expirées: ...</div>
                </div>
                <div id="detailed-stats"></div>
            </div>
        </div>

        <script>
            const SERVER_URL = window.location.origin;
            document.getElementById('server-url').textContent = SERVER_URL;
            
            function openTab(evt, tabName) {
                const tabcontent = document.getElementsByClassName("tabcontent");
                for (let i = 0; i < tabcontent.length; i++) {
                    tabcontent[i].style.display = "none";
                }
                
                const tablinks = document.getElementsByClassName("tablinks");
                for (let i = 0; i < tablinks.length; i++) {
                    tablinks[i].className = tablinks[i].className.replace(" active", "");
                }
                
                document.getElementById(tabName).style.display = "block";
                evt.currentTarget.className += " active";
            }
            
            async function loadStats() {
                try {
                    const response = await fetch(`${SERVER_URL}/health`);
                    const data = await response.json();
                    
                    document.getElementById('stat-total').innerHTML = `<h3>${data.license_count}</h3><small>Licences totales</small>`;
                    document.getElementById('stat-online').innerHTML = `<h3>${data.online_clients}</h3><small>Clients en ligne</small>`;
                    
                    // Charger les détails
                    await loadLicensesStats();
                    await loadOnlineClients();
                } catch (e) {
                    console.error('Erreur stats:', e);
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
                        updateStats(data.licenses);
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
                    div.id = `license-${license.id}`;
                    
                    // Badge statut
                    let statusBadge = '';
                    if (license.status === 'active') {
                        statusBadge = `<span class="online-badge">ACTIF (${license.days_remaining}j)</span>`;
                    } else if (license.status === 'blocked') {
                        statusBadge = `<span style="background:#dc3545;color:white;padding:3px 8px;border-radius:3px;">BLOQUÉ</span>`;
                    } else {
                        statusBadge = `<span style="background:#ffc107;color:black;padding:3px 8px;border-radius:3px;">EXPIRÉ</span>`;
                    }
                    
                    // Badge en ligne
                    const onlineBadge = license.is_online_now ? 
                        `<span class="online-badge">🟢 EN LIGNE</span>` : 
                        `<span class="offline-badge">⚫ HORS LIGNE</span>`;
                    
                    // Informations système
                    const systemInfo = `
                        <div class="system-info">
                            <strong>Système client:</strong><br>
                            ${license.mac_address ? `MAC: ${license.mac_address}<br>` : ''}
                            ${license.computer_name ? `Ordinateur: ${license.computer_name}<br>` : ''}
                            ${license.ip_address ? `IP: ${license.ip_address}<br>` : ''}
                            ${license.windows_version ? `Windows: ${license.windows_version}<br>` : ''}
                            Version app: ${license.app_version || 'Inconnue'}<br>
                            Dernière connexion: ${license.last_seen || 'Jamais'}
                        </div>
                    `;
                    
                    div.innerHTML = `
                        <h3>${license.client_name} (${license.license_id}) ${onlineBadge}</h3>
                        <p>📧 ${license.client_email} | ${statusBadge} | 👥 ${license.max_users} utilisateurs</p>
                        <p>📅 Créée: ${license.created_at} | Expire: ${license.expiry_date}</p>
                        <p>🔄 Vérifications: ${license.total_checks || 0} | Dernière: ${license.last_check_time || 'Jamais'}</p>
                        ${license.is_blocked ? `<p><strong>🚫 Raison: ${license.block_reason}</strong></p>` : ''}
                        
                        ${systemInfo}
                        
                        <div style="margin-top: 10px;">
                            <input type="text" id="reason-${license.id}" placeholder="Raison du blocage" />
                            <button class="btn-danger" onclick="blockLicense('${license.license_id}')">🚫 Bloquer</button>
                            <button class="btn-warning" onclick="unblockLicense('${license.license_id}')">✅ Débloquer</button>
                            <button class="btn-success" onclick="renewLicense('${license.license_id}', 30)">🔄 +1 mois</button>
                            <button class="btn-success" onclick="renewLicense('${license.license_id}', 365)">🔄 +1 an</button>
                            <button class="btn-info" onclick="showHistory('${license.license_id}')">📜 Historique</button>
                        </div>
                        <hr>
                    `;
                    
                    container.appendChild(div);
                });
            }
            
            async function loadOnlineClients() {
                const password = document.getElementById('adminPass').value;
                if (!password) return;
                
                try {
                    const response = await fetch(`${SERVER_URL}/admin/active-clients`, {
                        headers: { 'X-Admin-Password': password }
                    });
                    
                    if (response.ok) {
                        const data = await response.json();
                        displayOnlineClients(data.clients);
                    }
                } catch (e) {
                    console.error('Erreur clients en ligne:', e);
                }
            }
            
            function displayOnlineClients(clients) {
                const container = document.getElementById('online-clients');
                
                if (!clients || clients.length === 0) {
                    container.innerHTML = '<p>Aucun client en ligne</p>';
                    return;
                }
                
                let html = '<table>';
                html += '<tr><th>Client</th><th>Adresse MAC</th><th>IP</th><th>En ligne depuis</th><th>Actions</th></tr>';
                
                clients.forEach(client => {
                    html += `
                        <tr>
                            <td><strong>${client.client_name}</strong><br>${client.license_id}</td>
                            <td>${client.mac_address || 'Non renseigné'}</td>
                            <td>${client.ip_address || 'Non renseigné'}</td>
                            <td>${client.online_duration || 'Inconnu'}</td>
                            <td>
                                <button class="btn-danger" onclick="forceLogout('${client.license_id}')">👋 Forcer déconnexion</button>
                                <button class="btn-info" onclick="sendMessage('${client.license_id}')">✉️ Envoyer message</button>
                            </td>
                        </tr>
                    `;
                });
                
                html += '</table>';
                container.innerHTML = html;
            }
            
            function updateStats(licenses) {
                let active = 0, expired = 0, blocked = 0, online = 0;
                
                licenses.forEach(license => {
                    if (license.status === 'active') active++;
                    if (license.status === 'expired') expired++;
                    if (license.status === 'blocked') blocked++;
                    if (license.is_online_now) online++;
                });
                
                document.getElementById('stat-active').innerHTML = `<h3>${active}</h3><small>Licences actives</small>`;
                document.getElementById('stat-expired').innerHTML = `<h3>${expired}</h3><small>Licences expirées</small>`;
                
                const statsDiv = document.getElementById('detailed-stats');
                statsDiv.innerHTML = `
                    <h3>Répartition des licences</h3>
                    <p>Actives: ${active} | Expirées: ${expired} | Bloquées: ${blocked}</p>
                    <p>Clients en ligne: ${online}</p>
                `;
            }
            
            async function blockLicense(licenseId) {
                const password = document.getElementById('adminPass').value;
                const reason = document.getElementById(\`reason-\${licenseId}\`)?.value || 'Non-paiement';
                
                const response = await fetch(\`\${SERVER_URL}/admin/block\`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        license_id: licenseId,
                        reason: reason,
                        admin_password: password
                    })
                });
                
                if (response.ok) {
                    alert('✅ Licence bloquée! Le client sera déconnecté.');
                    loadLicenses();
                    loadOnlineClients();
                }
            }
            
            async function forceLogout(licenseId) {
                const password = document.getElementById('adminPass').value;
                if (!confirm('Forcer la déconnexion de ce client?')) return;
                
                // Marquer comme hors ligne
                const response = await fetch(\`\${SERVER_URL}/admin/force-logout\`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        license_id: licenseId,
                        admin_password: password
                    })
                });
                
                if (response.ok) {
                    alert('✅ Client déconnecté');
                    loadOnlineClients();
                    loadLicenses();
                }
            }
            
            async function showHistory(licenseId) {
                const password = document.getElementById('adminPass').value;
                const response = await fetch(\`\${SERVER_URL}/admin/license/\${licenseId}/history\`, {
                    headers: { 'X-Admin-Password': password }
                });
                
                if (response.ok) {
                    const data = await response.json();
                    alert(\`Historique de \${licenseId}\\n\\nVérifications: \${data.check_count}\\nDernière action: \${data.admin_actions[0]?.action_type || 'Aucune'}\`);
                }
            }
            
            async function createLicense() {
                const password = document.getElementById('create-pass').value;
                const clientName = document.getElementById('client-name').value;
                const clientEmail = document.getElementById('client-email').value;
                const duration = parseInt(document.getElementById('duration').value);
                const maxUsers = parseInt(document.getElementById('max-users').value);
                
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
                        max_users: maxUsers,
                        admin_password: password
                    })
                });
                
                const resultDiv = document.getElementById('create-result');
                
                if (response.ok) {
                    const data = await response.json();
                    resultDiv.innerHTML = \`
                        <div style="background:#d4edda;padding:15px;border-radius:5px;">
                            <h4>✅ Licence créée avec succès!</h4>
                            <p><strong>ID Licence:</strong> \${data.license_id}</p>
                            <p><strong>Clé de licence:</strong> <code style="background:#eee;padding:5px;">\${data.license_key}</code></p>
                            <p><strong>Instructions pour le client:</strong></p>
                            <ol>
                                <li>Envoyez cette clé au client</li>
                                <li>Le client doit lancer PharmaGest</li>
                                <li>Dans PharmaGest, aller dans Aide > Activer licence</li>
                                <li>Entrer la clé, son nom et email</li>
                                <li>PharmaGest s'enregistrera automatiquement sur ce serveur</li>
                            </ol>
                            <p><strong>Le client apparaîtra ici dès qu'il se connectera!</strong></p>
                        </div>
                    \`;
                    
                    // Réinitialiser le formulaire
                    document.getElementById('client-name').value = '';
                    document.getElementById('client-email').value = '';
                    
                    // Recharger la liste
                    setTimeout(() => loadLicenses(), 1000);
                    
                } else {
                    resultDiv.innerHTML = \`
                        <div style="background:#f8d7da;padding:15px;border-radius:5px;">
                            ❌ Erreur lors de la création de la licence
                        </div>
                    \`;
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
            
            // Auto-refresh toutes les 30 secondes
            setInterval(() => {
                loadStats();
                const activeTab = document.querySelector('.tabcontent[style*="block"]').id;
                if (activeTab === 'online') {
                    loadOnlineClients();
                }
            }, 30000);
            
            // Initial load
            loadStats();
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

# --- Endpoint supplémentaire pour forcer la déconnexion ---
class ForceLogoutRequest(BaseModel):
    license_id: str
    admin_password: str

@app.post("/admin/force-logout")
async def force_logout(request: ForceLogoutRequest):
    """Force la déconnexion d'un client"""
    if not verify_admin_password(request.admin_password):
        raise HTTPException(status_code=403, detail="Accès administrateur refusé")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            UPDATE active_clients 
            SET is_online = 0, session_end = ?
            WHERE license_id = ?
        ''', (datetime.now().isoformat(), request.license_id))
        
        conn.commit()
        
        return {
            "success": True,
            "message": f"Client {request.license_id} déconnecté avec succès",
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur: {str(e)}")
    finally:
        conn.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)