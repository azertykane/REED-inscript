import os
import time
import json
from flask import Flask, render_template, request, redirect, url_for, flash, send_file, jsonify, session, Response
from flask_mail import Mail, Message
from werkzeug.utils import secure_filename
from datetime import datetime
import io
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor
import sqlite3
from flask_sqlalchemy import SQLAlchemy
import logging

# Configuration du logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
class Config:
    # Security
    SECRET_KEY = os.environ.get('SECRET_KEY', 'production-secret-key-change-this-in-production')
    
    # Database configuration for Render
    basedir = os.path.abspath(os.path.dirname(__file__))
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', '').replace('postgres://', 'postgresql://', 1) if os.environ.get('DATABASE_URL', '').startswith('postgres://') else os.environ.get('DATABASE_URL', 'sqlite:///' + os.path.join(basedir, 'instance', 'amicale.db'))
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Upload configuration
    UPLOAD_FOLDER = 'static/uploads'
    ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg'}
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    
    # Mail configuration - with fallback for Render
    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'True').lower() == 'true'
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME', 'commissionsociale.reed@gmail.com')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD', '')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER', 'commissionsociale.reed@gmail.com')
    
    # If no mail password, disable email functionality
    MAIL_ENABLED = bool(os.environ.get('MAIL_PASSWORD', ''))
    
    # Admin credentials
    ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'admin')
    ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin123')
    
    # Session
    from datetime import timedelta
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=30)

# Initialisation
app = Flask(__name__)
app.config.from_object(Config)

# Initialize database
db = SQLAlchemy(app)

# Initialize mail only if enabled
if app.config['MAIL_ENABLED']:
    mail = Mail(app)
    logger.info("Mail functionality ENABLED")
else:
    mail = None
    logger.warning("Mail functionality DISABLED - No MAIL_PASSWORD set")

# Modèle de base de données
class StudentRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(100), nullable=False)
    prenom = db.Column(db.String(100), nullable=False)
    adresse = db.Column(db.Text, nullable=False)
    telephone = db.Column(db.String(20), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    
    # Fichiers
    certificat_inscription = db.Column(db.String(200))
    certificat_residence = db.Column(db.String(200))
    demande_manuscrite = db.Column(db.String(200))
    carte_membre_reed = db.Column(db.String(200))
    copie_cni = db.Column(db.String(200))
    
    # Statut
    status = db.Column(db.String(20), default='pending')  # pending, approved, rejected
    admin_notes = db.Column(db.Text)
    
    # Dates
    date_submitted = db.Column(db.DateTime, default=datetime.utcnow)
    date_processed = db.Column(db.DateTime)
    
    def to_dict(self):
        return {
            'id': self.id,
            'nom': self.nom,
            'prenom': self.prenom,
            'email': self.email,
            'telephone': self.telephone,
            'adresse': self.adresse,
            'status': self.status,
            'date_submitted': self.date_submitted.strftime('%Y-%m-%d %H:%M:%S') if self.date_submitted else None,
            'date_processed': self.date_processed.strftime('%Y-%m-%d %H:%M:%S') if self.date_processed else None
        }

# Création des dossiers nécessaires
def create_directories():
    os.makedirs('static/uploads', exist_ok=True)
    os.makedirs('instance', exist_ok=True)

# Fonction utilitaire
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def init_database():
    """Initialiser la base de données"""
    with app.app_context():
        db.create_all()
        logger.info("Base de données initialisée")

def send_confirmation_email(to_email, nom, prenom, request_id):
    """Envoyer un email de confirmation"""
    if not app.config['MAIL_ENABLED']:
        logger.warning(f"Email non envoyé à {to_email} - MAIL désactivé")
        return
    
    try:
        subject = "Confirmation de réception de votre demande"
        message = f"""Cher(e) {prenom} {nom},

Nous accusons réception de votre demande d'adhésion à l'Amicale des Étudiants (N°{request_id}).

Votre dossier est en cours de traitement et vous serez notifié(e) par email dès qu'une décision sera prise.

Nous vous remercions pour votre confiance.

Cordialement,
La Commission Sociale REED
Amicale des Étudiants
"""
        
        msg = Message(
            subject=subject,
            recipients=[to_email],
            body=message,
            sender=app.config['MAIL_DEFAULT_SENDER']
        )
        
        mail.send(msg)
        logger.info(f"Email de confirmation envoyé à {to_email}")
    except Exception as e:
        logger.error(f"Erreur d'envoi d'email à {to_email}: {e}")

def send_status_email(student, status, notes):
    """Envoyer un email à l'étudiant concernant le statut de sa demande"""
    if not app.config['MAIL_ENABLED'] or not student.email:
        return
    
    try:
        if status == 'approved':
            subject = "Félicitations ! Votre demande d'adhésion a été acceptée"
            message = f"""Cher(e) {student.prenom} {student.nom},

Nous avons le plaisir de vous informer que votre demande d'adhésion à l'Amicale des Étudiants (ID: {student.id}) a été approuvée.

Bienvenue dans notre communauté !
"""
        elif status == 'rejected':
            subject = "Décision concernant votre demande d'adhésion"
            message = f"""Cher(e) {student.prenom} {student.nom},

Après examen de votre demande d'adhésion (ID: {student.id}), nous regrettons de vous informer qu'elle n'a pas pu être acceptée pour le moment.
"""
        else:
            subject = "Mise à jour sur votre demande d'adhésion"
            message = f"""Cher(e) {student.prenom} {student.nom},

Votre demande d'adhésion (ID: {student.id}) est actuellement en cours de traitement par notre équipe.

Nous vous contacterons dès que nous aurons une décision.
"""
        
        if notes:
            message += f"\nNote: {notes}\n"
        
        message += """
Merci pour votre compréhension.

Cordialement,
La Commission Sociale REED
Amicale des Étudiants
"""
        
        msg = Message(
            subject=subject,
            recipients=[student.email],
            body=message,
            sender=app.config['MAIL_DEFAULT_SENDER']
        )
        
        mail.send(msg)
        logger.info(f"Email de statut envoyé à {student.email}")
    except Exception as e:
        logger.error(f"Erreur d'envoi d'email de statut à {student.email}: {e}")

# Middleware pour vérifier le Content-Type JSON
@app.before_request
def check_json():
    if request.method == 'POST' and request.path.startswith('/admin/'):
        if request.is_json:
            try:
                request.get_json()
            except Exception as e:
                return jsonify({'error': 'Invalid JSON format'}), 400

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/formulaire', methods=['GET', 'POST'])
def formulaire():
    if request.method == 'POST':
        try:
            # Get form data
            nom = request.form.get('nom', '').strip()
            prenom = request.form.get('prenom', '').strip()
            adresse = request.form.get('adresse', '').strip()
            telephone = request.form.get('telephone', '').strip()
            email = request.form.get('email', '').strip().lower()
            
            # Validate required fields
            if not all([nom, prenom, adresse, telephone, email]):
                flash('Tous les champs sont obligatoires', 'error')
                return redirect(url_for('formulaire'))
            
            # Validate email
            if '@' not in email or '.' not in email:
                flash('Email invalide', 'error')
                return redirect(url_for('formulaire'))
            
            # Create new student request
            new_request = StudentRequest(
                nom=nom,
                prenom=prenom,
                adresse=adresse,
                telephone=telephone,
                email=email,
                status='pending'
            )
            
            # Handle file uploads
            files_required = {
                'certificat_inscription': 'certificat_inscription',
                'certificat_residence': 'certificat_residence', 
                'demande_manuscrite': 'demande_manuscrite',
                'carte_membre_reed': 'carte_membre_reed',
                'copie_cni': 'copie_cni'
            }
            
            # Vérifier d'abord tous les fichiers
            for field, file_key in files_required.items():
                file = request.files.get(file_key)
                if not file or file.filename == '':
                    flash(f'Le fichier {field.replace("_", " ")} est requis', 'error')
                    return redirect(url_for('formulaire'))
                
                if not allowed_file(file.filename):
                    flash(f'Le fichier {field.replace("_", " ")} doit être au format PDF, PNG ou JPG', 'error')
                    return redirect(url_for('formulaire'))
            
            # Sauvegarder la demande d'abord
            db.session.add(new_request)
            db.session.flush()  # Get the ID without committing
            
            # Ensuite sauvegarder les fichiers
            for field, file_key in files_required.items():
                file = request.files.get(file_key)
                if file and file.filename:
                    ext = file.filename.rsplit('.', 1)[1].lower()
                    filename = f"{new_request.id}_{field}.{ext}"
                    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    
                    try:
                        file.save(filepath)
                        setattr(new_request, field, filename)
                    except Exception as e:
                        logger.error(f"Erreur sauvegarde fichier {field}: {e}")
                        flash('Erreur lors de la sauvegarde des fichiers', 'error')
                        return redirect(url_for('formulaire'))
            
            # Commit toutes les données
            db.session.commit()
            logger.info(f"Nouvelle demande créée: ID {new_request.id} - {prenom} {nom}")
            
            # Envoyer l'email de confirmation
            send_confirmation_email(email, nom, prenom, new_request.id)
            
            flash('Votre demande a été soumise avec succès! Vous recevrez un email de confirmation.', 'success')
            return redirect(url_for('index'))
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Erreur formulaire: {e}")
            flash('Une erreur est survenue lors de la soumission. Veuillez réessayer.', 'error')
            return redirect(url_for('formulaire'))
    
    return render_template('form.html')

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        
        if username == app.config['ADMIN_USERNAME'] and password == app.config['ADMIN_PASSWORD']:
            session['admin_logged_in'] = True
            session.permanent = True
            flash('Connexion réussie!', 'success')
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Identifiants incorrects', 'error')
    
    return render_template('admin_login.html')

@app.route('/admin/dashboard')
def admin_dashboard():
    if not session.get('admin_logged_in'):
        flash('Veuillez vous connecter', 'error')
        return redirect(url_for('admin_login'))
    
    requests = StudentRequest.query.order_by(StudentRequest.date_submitted.desc()).all()
    pending_count = StudentRequest.query.filter_by(status='pending').count()
    approved_count = StudentRequest.query.filter_by(status='approved').count()
    rejected_count = StudentRequest.query.filter_by(status='rejected').count()
    
    return render_template('admin_dashboard.html', 
                         requests=requests,
                         pending_count=pending_count,
                         approved_count=approved_count,
                         rejected_count=rejected_count)

@app.route('/admin/view/<int:request_id>')
def view_request(request_id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    
    student_request = StudentRequest.query.get_or_404(request_id)
    return render_template('view_request.html', request=student_request)

@app.route('/admin/update_status/<int:request_id>', methods=['POST'])
def update_status(request_id):
    if not session.get('admin_logged_in'):
        return jsonify({'error': 'Non autorisé'}), 401
    
    try:
        # Récupérer les données JSON
        if not request.is_json:
            return jsonify({'error': 'Content-Type must be application/json'}), 400
        
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Données JSON requises'}), 400
        
        student_request = StudentRequest.query.get_or_404(request_id)
        
        status = data.get('status')
        notes = data.get('notes', '')
        
        if status not in ['pending', 'approved', 'rejected']:
            return jsonify({'error': 'Statut invalide'}), 400
        
        old_status = student_request.status
        student_request.status = status
        student_request.admin_notes = notes
        student_request.date_processed = datetime.utcnow()
        
        db.session.commit()
        logger.info(f"Statut mis à jour: ID {request_id} -> {status}")
        
        # Envoyer un email à l'étudiant si le statut change
        if old_status != status:
            send_status_email(student_request, status, notes)
        
        # Retourner les données mises à jour
        return jsonify({
            'success': True, 
            'message': 'Statut mis à jour',
            'request': student_request.to_dict()
        })
    
    except Exception as e:
        db.session.rollback()
        logger.error(f"Erreur update_status: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/admin/send_email', methods=['POST'])
def send_email():
    if not session.get('admin_logged_in'):
        return jsonify({'error': 'Non autorisé'}), 401
    
    try:
        # Vérifier que c'est du JSON
        if not request.is_json:
            return jsonify({'error': 'Content-Type must be application/json'}), 400
        
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Données JSON requises'}), 400
        
        recipient_type = data.get('recipient_type', 'all')
        subject = data.get('subject', '')
        message = data.get('message', '')
        custom_emails = data.get('custom_emails', [])
        selected_ids = data.get('selected_ids', [])
        
        if not subject or not message:
            return jsonify({'error': 'Sujet et message sont requis'}), 400
        
        # Vérifier si l'email est activé
        if not app.config['MAIL_ENABLED']:
            return jsonify({
                'warning': 'Fonctionnalité email désactivée sur le serveur',
                'email_preview': {
                    'subject': subject,
                    'message': message,
                    'recipient_type': recipient_type,
                    'recipient_count': 0
                }
            })
        
        # Récupérer les destinataires
        recipients = []
        
        if recipient_type == 'approved':
            recipients = StudentRequest.query.filter_by(status='approved').all()
        elif recipient_type == 'rejected':
            recipients = StudentRequest.query.filter_by(status='rejected').all()
        elif recipient_type == 'pending':
            recipients = StudentRequest.query.filter_by(status='pending').all()
        elif recipient_type == 'selected' and selected_ids:
            recipients = StudentRequest.query.filter(StudentRequest.id.in_(selected_ids)).all()
        elif recipient_type == 'custom' and custom_emails:
            # Pour les emails custom, créer des objets factices
            recipients = [type('obj', (object,), {'email': email.strip()})() 
                         for email in custom_emails if email.strip()]
        else:  # 'all' ou défaut
            recipients = StudentRequest.query.all()
        
        # Filtrer les emails valides
        valid_emails = []
        for recipient in recipients:
            if hasattr(recipient, 'email') and recipient.email and '@' in recipient.email:
                valid_emails.append(recipient.email)
        
        if not valid_emails:
            return jsonify({'error': 'Aucun destinataire valide trouvé'}), 400
        
        # Envoyer les emails
        sent_count = 0
        failed_emails = []
        
        for i, email in enumerate(valid_emails):
            try:
                # Personnaliser le message
                personalized_message = message
                if recipient_type in ['approved', 'rejected', 'pending', 'selected', 'all']:
                    student = next((s for s in recipients if hasattr(s, 'email') and s.email == email), None)
                    if student:
                        personalized_message = message.replace('{nom}', student.nom or '')
                        personalized_message = personalized_message.replace('{prenom}', student.prenom or '')
                        personalized_message = personalized_message.replace('{id}', str(student.id))
                        if student.date_submitted:
                            personalized_message = personalized_message.replace('{date}', student.date_submitted.strftime('%d/%m/%Y'))
                
                msg = Message(
                    subject=subject,
                    recipients=[email],
                    body=personalized_message,
                    sender=app.config['MAIL_DEFAULT_SENDER']
                )
                
                mail.send(msg)
                sent_count += 1
                logger.info(f"Email envoyé à {email}")
                
                # Pause pour éviter les limites
                if i % 5 == 0 and i > 0:
                    time.sleep(0.5)
                    
            except Exception as e:
                failed_emails.append({'email': email, 'error': str(e)})
                logger.error(f"Erreur envoi email à {email}: {e}")
        
        # Préparer la réponse
        response_data = {
            'success': True, 
            'message': f'{sent_count} email(s) envoyé(s) avec succès sur {len(valid_emails)} destinataire(s)',
            'sent_count': sent_count,
            'total_count': len(valid_emails)
        }
        
        if failed_emails:
            response_data['failed_emails'] = failed_emails[:5]
            response_data['warning'] = f"{len(failed_emails)} email(s) n'ont pas pu être envoyés"
        
        return jsonify(response_data)
    
    except Exception as e:
        logger.error(f"Erreur send_email: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/admin/download_report')
def download_report():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    
    try:
        buffer = io.BytesIO()
        p = canvas.Canvas(buffer, pagesize=letter)
        width, height = letter
        
        # Title
        p.setFont("Helvetica-Bold", 16)
        p.setFillColor(HexColor("#1E3A8A"))
        p.drawString(1*inch, height - 1*inch, "Rapport des Demandes - Amicale des Étudiants")
        
        # Date
        p.setFont("Helvetica", 10)
        p.setFillColor(HexColor("#666666"))
        p.drawString(1*inch, height - 1.2*inch, f"Généré le: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
        
        # Statistics
        y_position = height - 2*inch
        
        p.setFont("Helvetica-Bold", 12)
        p.setFillColor(HexColor("#1E3A8A"))
        p.drawString(1*inch, y_position, "Statistiques:")
        
        y_position -= 0.25*inch
        p.setFont("Helvetica", 10)
        p.setFillColor(HexColor("#000000"))
        
        # Get counts
        total = StudentRequest.query.count()
        pending = StudentRequest.query.filter_by(status='pending').count()
        approved = StudentRequest.query.filter_by(status='approved').count()
        rejected = StudentRequest.query.filter_by(status='rejected').count()
        
        stats = [
            f"Total des demandes: {total}",
            f"En attente: {pending}",
            f"Approuvées: {approved}",
            f"Rejetées: {rejected}"
        ]
        
        for stat in stats:
            p.drawString(1.2*inch, y_position, stat)
            y_position -= 0.2*inch
        
        # List of requests
        y_position -= 0.3*inch
        p.setFont("Helvetica-Bold", 12)
        p.setFillColor(HexColor("#1E3A8A"))
        p.drawString(1*inch, y_position, "Liste des Demandes:")
        
        y_position -= 0.3*inch
        p.setFont("Helvetica", 8)
        
        # Table header
        p.setFillColor(HexColor("#FBBF24"))
        p.rect(1*inch, y_position - 0.1*inch, 6.5*inch, 0.25*inch, fill=1, stroke=0)
        p.setFillColor(HexColor("#000000"))
        headers = ["ID", "Nom", "Prénom", "Email", "Statut", "Date"]
        col_widths = [0.5, 1.5, 1.5, 2, 1, 1]
        
        x_position = 1*inch
        for header, width in zip(headers, col_widths):
            p.drawString(x_position + 0.1*inch, y_position, header)
            x_position += width*inch
        
        y_position -= 0.3*inch
        
        # Table rows
        requests = StudentRequest.query.order_by(StudentRequest.date_submitted.desc()).all()
        for req in requests:
            if y_position < 1*inch:
                p.showPage()
                p.setFont("Helvetica", 8)
                y_position = height - 1*inch
            
            row_data = [
                str(req.id),
                req.nom,
                req.prenom,
                req.email[:20] + "..." if len(req.email) > 20 else req.email,
                req.status,
                req.date_submitted.strftime('%d/%m/%y') if req.date_submitted else ''
            ]
            
            x_position = 1*inch
            for data, width in zip(row_data, col_widths):
                p.drawString(x_position + 0.1*inch, y_position, str(data))
                x_position += width*inch
            
            y_position -= 0.2*inch
        
        p.save()
        buffer.seek(0)
        
        return send_file(buffer, 
                        as_attachment=True, 
                        download_name=f"rapport_amicale_{datetime.now().strftime('%Y%m%d')}.pdf", 
                        mimetype='application/pdf')
    
    except Exception as e:
        logger.error(f"Erreur download_report: {e}")
        flash(f'Erreur lors de la génération du rapport: {str(e)}', 'error')
        return redirect(url_for('admin_dashboard'))

@app.route('/admin/email_compose')
def email_compose():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    
    return render_template('email_compose.html')

@app.route('/admin/api/students')
def api_students():
    if not session.get('admin_logged_in'):
        return jsonify({'error': 'Non autorisé'}), 401
    
    try:
        students = StudentRequest.query.all()
        students_data = []
        for student in students:
            students_data.append({
                'id': student.id,
                'nom': student.nom,
                'prenom': student.prenom,
                'email': student.email,
                'telephone': student.telephone,
                'adresse': student.adresse,
                'status': student.status,
                'date_submitted': student.date_submitted.strftime('%Y-%m-%d') if student.date_submitted else None
            })
        return jsonify(students_data)
    except Exception as e:
        logger.error(f"Erreur api_students: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/admin/api/stats')
def api_stats():
    if not session.get('admin_logged_in'):
        return jsonify({'error': 'Non autorisé'}), 401
    
    try:
        stats = {
            'total': StudentRequest.query.count(),
            'approved': StudentRequest.query.filter_by(status='approved').count(),
            'rejected': StudentRequest.query.filter_by(status='rejected').count(),
            'pending': StudentRequest.query.filter_by(status='pending').count()
        }
        return jsonify(stats)
    except Exception as e:
        logger.error(f"Erreur api_stats: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    flash('Déconnexion réussie', 'success')
    return redirect(url_for('admin_login'))

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_server_error(e):
    logger.error(f"Erreur 500: {e}")
    return render_template('500.html'), 500

@app.errorhandler(Exception)
def handle_exception(e):
    logger.error(f"Exception non gérée: {e}")
    return jsonify({'error': 'Une erreur interne est survenue'}), 500

if __name__ == '__main__':
    create_directories()
    init_database()
    print("\n" + "="*60)
    print("APPLICATION PRÊTE POUR LA PRODUCTION")
    print("="*60)
    print("URL: http://localhost:5000")
    print("Login admin: http://localhost:5000/admin/login")
    print(f"Mail enabled: {app.config['MAIL_ENABLED']}")
    print("="*60 + "\n")
    app.run(host='0.0.0.0', port=5000, debug=False)