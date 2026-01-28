import os
from datetime import timedelta

class Config:
    # Clé secrète - sera remplacée par RenderConfig
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-key-change-in-production')
    
    # Base de données - sera remplacée par RenderConfig
    SQLALCHEMY_DATABASE_URI = 'sqlite:///amicale.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Upload configuration
    UPLOAD_FOLDER = 'static/uploads'
    ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg'}
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    
    # Mail configuration - sera remplacée par RenderConfig
    MAIL_SERVER = 'smtp.gmail.com'
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_USERNAME = None
    MAIL_PASSWORD = None
    MAIL_DEFAULT_SENDER = None
    
    # Admin credentials (change these in production!)
    ADMIN_USERNAME = 'admin'
    ADMIN_PASSWORD = 'admin123'
    
    # Session
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=30)