from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class StudentRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(100), nullable=False)
    prenom = db.Column(db.String(100), nullable=False)
    adresse = db.Column(db.String(200), nullable=False)
    telephone = db.Column(db.String(20), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    
    # File paths for uploaded documents
    certificat_inscription = db.Column(db.String(300))
    certificat_residence = db.Column(db.String(300))
    demande_manuscrite = db.Column(db.String(300))
    carte_membre_reed = db.Column(db.String(300))
    copie_cni = db.Column(db.String(300))  # NOUVEAU: Copie de la CNI
    
    # Status: pending, approved, rejected
    status = db.Column(db.String(20), default='pending')
    
    # Timestamps
    date_submitted = db.Column(db.DateTime, default=datetime.utcnow)
    date_processed = db.Column(db.DateTime)
    
    # Admin notes
    admin_notes = db.Column(db.Text)
    
    def __repr__(self):
        return f'<StudentRequest {self.nom} {self.prenom}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'nom': self.nom,
            'prenom': self.prenom,
            'adresse': self.adresse,
            'telephone': self.telephone,
            'email': self.email,
            'status': self.status,
            'date_submitted': self.date_submitted.strftime('%Y-%m-%d %H:%M') if self.date_submitted else None,
            'admin_notes': self.admin_notes
        }