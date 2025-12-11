# license_server.py - VERSION OPTIMISÉE POUR RENDER.COM
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from datetime import datetime, timedelta
import sqlite3
import hashlib
import json
import os
import requests
from typing import Optional

# Configuration Render
RENDER_SERVICE_URL = "https://pharmagest-license.onrender.com"

# Chemin de la base de données (Render utilise /tmp pour SQLite)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_PATH = os.path.join(BASE_DIR, "pharmagest_licenses.db")

# Application FastAPI
app = FastAPI(
    title="PharmaGest License Server",
    description="API de gestion des licences à distance",
    version="2.0.0",
    docs_url="/docs",  # Documentation automatique
    redoc_url="/redoc"
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
    
    conn.commit()
    conn.close()
    print(f"✅ Base de données initialisée: {DATABASE_PATH}")

# Initialiser au démarrage
if not os.path.exists(DATABASE_PATH):
    init_database()

# --- PING INTERNE POUR ÉVITER L'ENDORMISSEMENT ---
async def keep_alive_ping():
    """Ping interne pour garder le service actif"""
    try:
        # Se ping soi-même
        response = requests.get(f"{RENDER_SERVICE_URL}/health", timeout=5)
        print(f"🔄 Ping auto: {response.status_code} - {datetime.now().strftime('%H:%M:%S')}")
    except Exception as e:
        print(f"⚠️ Ping échoué: {e}")

# Tâche en arrière-plan pour ping toutes les 10 minutes
from fastapi_utils.tasks import repeat_every

@app.on_event("startup")
@repeat_every(seconds=600)  # 10 minutes
async def startup_ping_task():
    await keep_alive_ping()

# --- UTILITAIRES ---
def get_db_connection():
    """Connexion à la base de données"""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def verify_admin_password(password: str) -> bool:
    """Vérifie le mot de passe admin (SHA256)"""
    # CHANGE CE MOT DE PASSE EN PRODUCTION !
    expected_hash = "8c6976e5b5410415bde908bd4dee15dfb167a9c873fc4bb8a81f6f2ab448a918"  # "admin123"
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
        "endpoints": {
            "validate_license": "POST /api/v1/validate",
            "health_check": "GET /health",
            "admin_list": "GET /admin/licenses (X-Admin-Password required)",
            "admin_block": "POST /admin/block",
            "admin_renew": "POST /admin/renew"
        },
        "render_service": RENDER_SERVICE_URL,
        "timestamp": datetime.now().isoformat()
    }

@app.get("/health")
async def health_check():
    """Endpoint de santé pour les pings"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as count FROM licenses")
    license_count = cursor.fetchone()["count"]
    conn.close()
    
    return {
        "status": "healthy",
        "service": "PharmaGest License Server",
        "license_count": license_count,
        "timestamp": datetime.now().isoformat(),
        "uptime": "active",
        "auto_ping": "enabled"
    }

@app.post("/api/v1/validate")
async def validate_license(request: LicenseValidationRequest):
    """Valide une licence (appelé par les clients PharmaGest)"""
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
        
        # 2. Vérifier blocage administratif
        if license_data['is_blocked']:
            return {
                "valid": False,
                "code": "ADMIN_BLOCKED",
                "message": f"Licence bloquée par l'administrateur: {license_data.get('block_reason', 'Non spécifié')}",
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
        
        # 4. Mettre à jour les statistiques
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
                request.client_info.get('user_agent', 'PharmaGest Desktop') if request.client_info else ''
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
            "server": "Render.com"
        }
        
    except Exception as e:
        print(f"❌ Erreur validation: {e}")
        return {
            "valid": False,
            "code": "SERVER_ERROR",
            "message": "Erreur interne du serveur",
            "timestamp": datetime.now().isoformat()
        }
    finally:
        conn.close()

# --- ENDPOINTS ADMIN (PROTÉGÉS) ---
def admin_required(password: str):
    """Middleware pour vérifier l'admin"""
    if not verify_admin_password(password):
        raise HTTPException(status_code=403, detail="Accès administrateur refusé")
    return True

@app.get("/admin/licenses")
async def get_all_licenses(x_admin_password: str = ""):
    """Liste toutes les licences (admin seulement)"""
    admin_required(x_admin_password)
    
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
    """Bloque une licence à distance"""
    admin_required(request.admin_password)
    
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
        
        # Log l'action admin
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
            "message": f"✅ Licence {request.license_id} BLOQUÉE avec succès",
            "client_name": dict(license)['client_name'],
            "reason": request.reason,
            "timestamp": datetime.now().isoformat(),
            "effect": "Le blocage sera effectif dès la prochaine vérification du client"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur: {str(e)}")
    finally:
        conn.close()

@app.post("/admin/renew")
async def renew_license(request: AdminRenewRequest):
    """Renouvelle une licence (ajoute des jours)"""
    admin_required(request.admin_password)
    
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
        
        # Mettre à jour (et débloquer si nécessaire)
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
            "message": f"✅ Licence renouvelée avec succès",
            "license_id": request.license_id,
            "client_name": license_data['client_name'],
            "old_expiry": license_data['expiry_date'],
            "new_expiry": new_expiry.isoformat(),
            "extra_days": request.extra_days,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur: {str(e)}")
    finally:
        conn.close()

@app.post("/admin/create")
async def create_license(request: CreateLicenseRequest):
    """Crée une nouvelle licence"""
    admin_required(request.admin_password)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Générer ID unique
        import uuid
        license_id = f"PHG-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"
        
        # Générer clé
        import secrets
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
            "message": "✅ Licence créée avec succès",
            "license_id": license_id,
            "license_key": license_key,
            "client_name": request.client_name,
            "client_email": request.client_email,
            "expiry_date": expiry_date.isoformat(),
            "duration_days": request.duration_days,
            "max_users": request.max_users,
            "instructions": "Envoyez cette clé au client pour activation dans PharmaGest",
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur création: {str(e)}")
    finally:
        conn.close()

# --- NE RIEN AJOUTER APRÈS ---
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)