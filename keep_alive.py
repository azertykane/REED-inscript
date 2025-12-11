# keep_alive.py - Ping automatique pour garder le service actif
import requests
import time
from datetime import datetime
import os

# URL de ton service Render
SERVICE_URL = os.getenv("RENDER_SERVICE_URL", "https://pharmagest-license.onrender.com")

def ping_service():
    """Ping le service pour éviter l'endormissement"""
    try:
        print(f"🔄 Ping envoyé à {SERVICE_URL} - {datetime.now().strftime('%H:%M:%S')}")
        
        # Ping l'endpoint health
        response = requests.get(f"{SERVICE_URL}/health", timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Service actif: {data.get('license_count', 0)} licences")
            return True
        else:
            print(f"⚠️ Service répond mais avec code {response.status_code}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Erreur de ping: {e}")
        return False
    except Exception as e:
        print(f"❌ Erreur inattendue: {e}")
        return False

if __name__ == "__main__":
    print("=" * 50)
    print("   🚀 DÉMARREUR DE PING AUTOMATIQUE")
    print(f"   Service: {SERVICE_URL}")
    print(f"   Heure: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)
    
    success = ping_service()
    
    if success:
        print("✅ Ping réussi - Le service restera actif")
    else:
        print("❌ Ping échoué - Vérifie l'URL du service")
    
    print("=" * 50)