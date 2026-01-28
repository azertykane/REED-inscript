import os
from datetime import timedelta

class Config:
    # Clé secrète
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
    
    # Base de données (PostgreSQL sur Render, SQLite en local)
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///amicale.db')
    if SQLALCHEMY_DATABASE_URI and SQLALCHEMY_DATABASE_URI.startswith("postgres://"):
        SQLALCHEMY_DATABASE_URI = SQLALCHEMY_DATABASE_URI.replace("postgres://", "postgresql://", 1)
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Upload configuration
    UPLOAD_FOLDER = 'static/uploads'
    ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg'}
    MAX_CONTENT_LENGTH = int(os.environ.get('MAX_CONTENT_LENGTH', 16 * 1024 * 1024))  # 16MB max
    
    # Mail configuration
    MAIL_SERVER = 'smtp.gmail.com'
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME', 'rashidtoure730@gmail.com')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD', '')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_USERNAME', 'rashidtoure730@gmail.com')
    
    # Admin credentials
    ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'admin')
    ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin123')
    
    # Session
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=30)
    
    # Production settings
    DEBUG = os.environ.get('DEBUG', 'False').lower() == 'true'
    
class ProductionConfig(Config):
    DEBUG = False
    PREFERRED_URL_SCHEME = 'https'  # Forcer HTTPS
    
class DevelopmentConfig(Config):
    DEBUG = True
    MAIL_SUPPRESS_SEND = True  # Ne pas envoyer d'emails en développement