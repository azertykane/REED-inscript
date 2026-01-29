import os
import time
import traceback
from flask import Flask, render_template, request, redirect, url_for, flash, send_file, jsonify, session
from flask_mail import Mail, Message
from werkzeug.utils import secure_filename
from datetime import datetime
import io
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor
import secrets
from pathlib import Path

from config import Config
from database import db, StudentRequest

app = Flask(__name__)

# Chemin absolu pour les uploads
BASE_DIR = Path(__file__).parent

# Configuration pour Render
class RenderConfig(Config):
    # Utiliser PostgreSQL sur Render, SQLite en local
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', f'sqlite:///{BASE_DIR}/amicale.db')
    
    # Si c'est PostgreSQL, ajuster l'URL
    if SQLALCHEMY_DATABASE_URI and SQLALCHEMY_DATABASE_URI.startswith("postgres://"):
        SQLALCHEMY_DATABASE_URI = SQLALCHEMY_DATABASE_URI.replace("postgres://", "postgresql://", 1)
    
    # Clé secrète sécurisée
    SECRET_KEY = os.environ.get('SECRET_KEY', secrets.token_hex(32))
    
    # Configuration mail avec valeurs par défaut
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME','rashidtoure730@gmail.com')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_USERNAME', 'rashidtoure730@gmail.com')

        # Augmenter les timeouts pour Render
    MAIL_SERVER = 'smtp.gmail.com'
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_USE_SSL = False
    MAIL_TIMEOUT = 30  # Augmenter à 30 secondes
    MAIL_DEBUG = True  # Activer le debug pour voir les erreurs
    
    # Chemin absolu pour les uploads
    UPLOAD_FOLDER = str(BASE_DIR / 'static' / 'uploads')
    
    # Admin credentials from environment
    ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'admin')
    ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin123')

app.config.from_object(RenderConfig)

# Initialize extensions
db.init_app(app)
mail = Mail(app)

# Create upload folder if it doesn't exist
upload_folder = app.config['UPLOAD_FOLDER']
os.makedirs(upload_folder, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def get_mail_sender():
    """Retourne l'expéditeur de l'email ou une valeur par défaut"""
    sender = app.config.get('MAIL_DEFAULT_SENDER')
    if not sender:
        sender = app.config.get('MAIL_USERNAME')
    if not sender:
        sender = 'noreply@amicale.com'
    return sender

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/formulaire', methods=['GET', 'POST'])
def formulaire():
    if request.method == 'POST':
        try:
            # Get form data
            nom = request.form.get('nom')
            prenom = request.form.get('prenom')
            adresse = request.form.get('adresse')
            telephone = request.form.get('telephone')
            email = request.form.get('email')
            
            # Validate required fields
            if not all([nom, prenom, adresse, telephone, email]):
                flash('Tous les champs sont obligatoires', 'error')
                return redirect(url_for('formulaire'))
            
            # Create new student request
            new_request = StudentRequest(
                nom=nom,
                prenom=prenom,
                adresse=adresse,
                telephone=telephone,
                email=email
            )
            
            # Handle file uploads
            files_required = {
                'certificat_inscription': 'certificat_inscription',
                'certificat_residence': 'certificat_residence', 
                'demande_manuscrite': 'demande_manuscrite',
                'carte_membre_reed': 'carte_membre_reed',
                'copie_cni': 'copie_cni'
            }
            
            files_uploaded = True
            for field, file_key in files_required.items():
                file = request.files.get(file_key)
                if file and file.filename and allowed_file(file.filename):
                    filename = secure_filename(f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{field}_{file.filename}")
                    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    file.save(filepath)
                    setattr(new_request, field, filename)
                else:
                    flash(f'Le fichier {field.replace("_", " ")} est requis et doit être au format PDF, PNG ou JPG', 'error')
                    files_uploaded = False
            
            if not files_uploaded:
                return redirect(url_for('formulaire'))
            
            # Save to database
            db.session.add(new_request)
            db.session.commit()
            
            # Envoyer un email de confirmation à l'étudiant
            try:
                send_confirmation_email(email, nom, prenom, new_request.id)
            except Exception as email_error:
                print(f"Erreur d'envoi d'email: {email_error}")
                # Ne pas bloquer l'enregistrement si l'email échoue
            
            flash('Votre demande a été soumise avec succès!', 'success')
            return redirect(url_for('index'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Une erreur est survenue: {str(e)}', 'error')
            return redirect(url_for('formulaire'))
    
    return render_template('form.html')

def send_confirmation_email(to_email, nom, prenom, request_id):
    """Envoyer un email de confirmation à l'étudiant"""
    subject = "Confirmation de réception de votre demande"
    message = f"""Cher(e) {prenom} {nom},

Nous accusons réception de votre demande d'adhésion à l'Amicale des Étudiants (N°{request_id}).

Votre dossier est en cours de traitement et vous serez notifié(e) par email dès qu'une décision sera prise.

Nous vous remercions pour votre confiance.

Cordialement,
La Commission Sociale REED
Amicale des Étudiants
"""
    
    try:
        msg = Message(
            subject=subject,
            recipients=[to_email],
            body=message,
            sender=get_mail_sender()
        )
        
        mail.send(msg)
        print(f"✓ Email de confirmation envoyé à {to_email}")
    except Exception as e:
        print(f"✗ Erreur d'envoi d'email à {to_email}: {e}")

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        
        print(f"\n=== TENTATIVE DE CONNEXION ===")
        print(f"Username: '{username}'")
        print(f"Password: '{password}'")
        print(f"Attendu: '{app.config['ADMIN_USERNAME']}' / '{app.config['ADMIN_PASSWORD']}'")
        
        if username == app.config['ADMIN_USERNAME'] and password == app.config['ADMIN_PASSWORD']:
            session['admin_logged_in'] = True
            session.permanent = True
            flash('Connexion réussie!', 'success')
            print("✓ Connexion réussie")
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Identifiants incorrects', 'error')
            print("✗ Identifiants incorrects")
    
    return render_template('admin_login.html')

@app.route('/admin/dashboard')
def admin_dashboard():
    if not session.get('admin_logged_in'):
        flash('Veuillez vous connecter', 'error')
        return redirect(url_for('admin_login'))
    
    try:
        requests = StudentRequest.query.order_by(StudentRequest.date_submitted.desc()).all()
        pending_count = StudentRequest.query.filter_by(status='pending').count()
        approved_count = StudentRequest.query.filter_by(status='approved').count()
        rejected_count = StudentRequest.query.filter_by(status='rejected').count()
        
        return render_template('admin_dashboard.html', 
                             requests=requests,
                             pending_count=pending_count,
                             approved_count=approved_count,
                             rejected_count=rejected_count)
    except Exception as e:
        print(f"Erreur dans admin_dashboard: {e}")
        traceback.print_exc()
        flash(f'Erreur lors du chargement du tableau de bord: {str(e)}', 'error')
        return redirect(url_for('admin_login'))

@app.route('/admin/view/<int:request_id>')
def view_request(request_id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    
    try:
        student_request = StudentRequest.query.get_or_404(request_id)
        return render_template('view_request.html', request=student_request)
    except Exception as e:
        print(f"Erreur dans view_request: {e}")
        flash(f'Erreur lors du chargement de la demande: {str(e)}', 'error')
        return redirect(url_for('admin_dashboard'))

@app.route('/admin/update_status/<int:request_id>', methods=['POST'])
def update_status(request_id):
    if not session.get('admin_logged_in'):
        return jsonify({'error': 'Non autorisé'}), 401
    
    try:
        student_request = StudentRequest.query.get_or_404(request_id)
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'Données JSON requises'}), 400
        
        status = data.get('status')
        notes = data.get('notes', '')
        
        if status in ['pending', 'approved', 'rejected']:
            old_status = student_request.status
            student_request.status = status
            student_request.admin_notes = notes
            student_request.date_processed = datetime.utcnow()
            db.session.commit()
            
            # Envoyer un email à l'étudiant si le statut change
            if old_status != status:
                send_status_email(student_request, status, notes)
            
            return jsonify({'success': True, 'message': 'Statut mis à jour'})
        else:
            return jsonify({'error': 'Statut invalide'}), 400
    
    except Exception as e:
        db.session.rollback()
        print(f"Erreur dans update_status: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

def send_status_email(student, status, notes):
    """Envoyer un email à l'étudiant concernant le statut de sa demande"""
    if not student.email:
        return
    
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
    else:  # pending
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
    
    try:
        msg = Message(
            subject=subject,
            recipients=[student.email],
            body=message,
            sender=get_mail_sender()
        )
        mail.send(msg)
        print(f"✓ Email de statut envoyé à {student.email}")
    except Exception as e:
        print(f"✗ Erreur d'envoi d'email de statut à {student.email}: {e}")

@app.route('/admin/send_email', methods=['POST'])
def send_email():
    if not session.get('admin_logged_in'):
        return jsonify({'error': 'Non autorisé'}), 401
    
    try:
        # Vérifier si les données JSON sont valides
        if not request.is_json:
            print("✗ Données JSON manquantes")
            return jsonify({'error': 'Données JSON requises'}), 400
        
        data = request.get_json(silent=True)  # silent=True pour éviter les erreurs
        
        if not data:
            print("✗ Données JSON invalides ou vides")
            return jsonify({'error': 'Données JSON invalides'}), 400
        
        print(f"✓ Données reçues: {data.keys() if data else 'Aucune'}")
        
        recipient_type = data.get('recipient_type', 'all')
        subject = data.get('subject', '')
        message = data.get('message', '')
        custom_emails = data.get('custom_emails', [])
        selected_ids = data.get('selected_ids', [])
        
        print(f"Type: {recipient_type}, Sujet: {subject[:50]}...")
        
        if not subject or not message:
            return jsonify({'error': 'Sujet et message sont requis'}), 400
        
        # Récupérer les destinataires
        recipients = []
        emails_list = []
        
        try:
            if recipient_type == 'approved':
                approved_students = StudentRequest.query.filter_by(status='approved').all()
                recipients = approved_students
                emails_list = [student.email for student in approved_students if student.email]
            elif recipient_type == 'rejected':
                rejected_students = StudentRequest.query.filter_by(status='rejected').all()
                recipients = rejected_students
                emails_list = [student.email for student in rejected_students if student.email]
            elif recipient_type == 'pending':
                pending_students = StudentRequest.query.filter_by(status='pending').all()
                recipients = pending_students
                emails_list = [student.email for student in pending_students if student.email]
            elif recipient_type == 'selected' and selected_ids:
                selected_students = StudentRequest.query.filter(StudentRequest.id.in_(selected_ids)).all()
                recipients = selected_students
                emails_list = [student.email for student in selected_students if student.email]
            elif recipient_type == 'custom' and custom_emails:
                if isinstance(custom_emails, str):
                    custom_emails = [email.strip() for email in custom_emails.split(',') if email.strip()]
                emails_list = [email.strip() for email in custom_emails if email.strip()]
            else:
                # Tous les étudiants
                all_students = StudentRequest.query.all()
                recipients = all_students
                emails_list = [student.email for student in all_students if student.email]
        except Exception as e:
            print(f"Erreur lors de la récupération des destinataires: {e}")
            traceback.print_exc()
            return jsonify({'error': f'Erreur base de données: {str(e)}'}), 500
        
        # Filtrer les emails valides
        valid_emails = [email for email in emails_list if email and '@' in email]
        
        if not valid_emails:
            return jsonify({'error': 'Aucun destinataire valide trouvé'}), 400
        
        print(f"✓ {len(valid_emails)} email(s) valide(s) trouvé(s)")
        
        # Si aucun email configuré, retourner une réponse mais ne pas envoyer
        sender = get_mail_sender()
        if not app.config['MAIL_USERNAME'] or not app.config['MAIL_PASSWORD']:
            print("⚠ Email non configuré, simulation d'envoi")
            return jsonify({
                'success': True, 
                'message': f'Email non envoyé (configuration manquante) - {len(valid_emails)} destinataire(s)',
                'sent_count': 0,
                'total_count': len(valid_emails),
                'warning': 'Email non configuré sur le serveur'
            })
        
        # Envoyer les emails
        sent_count = 0
        failed_emails = []
        
        for i, email in enumerate(valid_emails):
            try:
                # Personnaliser le message avec les variables
                personalized_message = message
                if recipient_type in ['approved', 'rejected', 'pending', 'selected', 'all']:
                    # Chercher l'étudiant correspondant
                    student = next((s for s in recipients if s.email == email), None)
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
                    sender=sender
                )
                
                mail.send(msg)
                sent_count += 1
                print(f"✓ Email envoyé à {email}")
                
                # Petite pause pour éviter les limites
                if i % 5 == 0 and i > 0:
                    time.sleep(0.5)
                    
            except Exception as e:
                failed_emails.append({'email': email, 'error': str(e)})
                print(f"✗ Erreur d'envoi à {email}: {e}")
        
        # Préparer la réponse
        response_data = {
            'success': True, 
            'message': f'{sent_count} email(s) envoyé(s) avec succès sur {len(valid_emails)} destinataire(s)',
            'sent_count': sent_count,
            'total_count': len(valid_emails)
        }
        
        if failed_emails:
            response_data['failed_emails'] = failed_emails[:5]  # Limiter pour ne pas surcharger
            response_data['warning'] = f"{len(failed_emails)} email(s) n'ont pas pu être envoyés"
        
        print(f"✓ Réponse: {response_data}")
        return jsonify(response_data)
    
    except Exception as e:
        print(f"✗ Erreur dans send_email: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    
@app.route('/admin/download_report')
def download_report():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    
    try:
        # Create PDF report
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
            if y_position < 1*inch:  # New page if needed
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
        print(f"Erreur dans download_report: {e}")
        traceback.print_exc()
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
        print(f"Erreur dans api_students: {e}")
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
        print(f"Erreur dans api_stats: {e}")
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
    print(f"Erreur 500: {e}")
    traceback.print_exc()
    return render_template('500.html'), 500

# Ajoutez cette fonction avant le démarrage de l'application
def init_database():
    """Initialiser la base de données"""
    with app.app_context():
        try:
            db.create_all()
            print("✓ Base de données initialisée")
            
            # Vérifier si la table existe
            from sqlalchemy import inspect
            inspector = inspect(db.engine)
            tables = inspector.get_table_names()
            print(f"Tables existantes: {tables}")
            
        except Exception as e:
            print(f"✗ Erreur d'initialisation: {e}")
            traceback.print_exc()



def initialize_database():
    """Crée les tables si elles n'existent pas"""
    with app.app_context():
        try:
            db.create_all()
            print("✓ Tables de base de données créées/vérifiées")
            
            # Vérifiez si la table existe
            from sqlalchemy import inspect
            inspector = inspect(db.engine)
            tables = inspector.get_table_names()
            print(f"Tables disponibles: {tables}")
            
        except Exception as e:
            print(f"✗ Erreur lors de l'initialisation de la base de données: {e}")
            traceback.print_exc()

# Appelez cette fonction avant le démarrage du serveur
initialize_database()

# Route de santé pour Render
@app.route('/health')
def health_check():
    return 'OK', 200

if __name__ == '__main__':
    with app.app_context():
        try:
            db.create_all()
            print("\n" + "="*60)
            print("APPLICATION DÉMARRÉE")
            print("="*60)
            print(f"Environment: {'Production' if not app.debug else 'Development'}")
            print(f"Database: {app.config['SQLALCHEMY_DATABASE_URI'].split('://')[0]}")
            print(f"Upload folder: {app.config['UPLOAD_FOLDER']}")
            print(f"Admin username: {app.config['ADMIN_USERNAME']}")
            print(f"Mail sender: {get_mail_sender()}")
            print(f"Mail configured: {bool(app.config['MAIL_USERNAME'] and app.config['MAIL_PASSWORD'])}")
            print("="*60 + "\n")
        except Exception as e:
            print(f"Erreur lors de l'initialisation: {e}")
            traceback.print_exc()
    
    port = int(os.environ.get('PORT', 5000))
    init_database()
    app.run(host='0.0.0.0', port=port, debug=False)