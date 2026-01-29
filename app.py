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
from functools import wraps

from config import Config
from database import db, StudentRequest

app = Flask(__name__)
app.config.from_object(Config)

# Initialize extensions
db.init_app(app)
mail = Mail(app)

# Create necessary directories
os.makedirs('static/uploads', exist_ok=True)
os.makedirs('instance', exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def init_database():
    """Initialiser la base de données si elle n'existe pas"""
    with app.app_context():
        db.create_all()
        print("Base de données initialisée")

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return jsonify({'error': 'Non autorisé'}), 401
        return f(*args, **kwargs)
    return decorated_function

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
            
            # Validate phone number
            if not telephone.replace(' ', '').replace('-', '').replace('+', '').isdigit():
                flash('Numéro de téléphone invalide', 'error')
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
                if file and file.filename and allowed_file(file.filename):
                    # Utiliser un nom de fichier simple
                    ext = file.filename.rsplit('.', 1)[1].lower()
                    filename = f"{new_request.id}_{field}.{ext}"
                    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    
                    # Sauvegarder le fichier
                    file.save(filepath)
                    setattr(new_request, field, filename)
            
            # Commit toutes les données
            db.session.commit()
            
            # Envoyer l'email de confirmation
            try:
                send_confirmation_email(email, nom, prenom, new_request.id)
                flash('Votre demande a été soumise avec succès! Un email de confirmation a été envoyé.', 'success')
            except Exception as email_error:
                app.logger.error(f"Erreur d'envoi d'email: {email_error}")
                flash('Votre demande a été soumise avec succès! (Note: Email de confirmation non envoyé)', 'success')
            
            return redirect(url_for('index'))
            
        except Exception as e:
            db.session.rollback()
            app.logger.error(f'Erreur lors de la soumission: {str(e)}')
            flash('Une erreur est survenue lors de la soumission. Veuillez réessayer.', 'error')
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
    
    msg = Message(
        subject=subject,
        recipients=[to_email],
        body=message,
        sender=app.config['MAIL_DEFAULT_SENDER']
    )
    
    mail.send(msg)
    app.logger.info(f"Email de confirmation envoyé à {to_email}")

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
@admin_required
def update_status(request_id):
    try:
        student_request = StudentRequest.query.get_or_404(request_id)
        
        # Vérifier si c'est JSON ou form data
        if request.is_json:
            data = request.get_json()
            if not data:
                return jsonify({'error': 'Données JSON requises'}), 400
            status = data.get('status')
            notes = data.get('notes', '')
        else:
            status = request.form.get('status')
            notes = request.form.get('notes', '')
        
        if status in ['pending', 'approved', 'rejected']:
            old_status = student_request.status
            student_request.status = status
            student_request.admin_notes = notes
            student_request.date_processed = datetime.utcnow()
            db.session.commit()
            
            # Envoyer un email à l'étudiant si le statut change
            if old_status != status:
                send_status_email(student_request, status, notes)
            
            return jsonify({
                'success': True, 
                'message': 'Statut mis à jour',
                'new_status': status
            })
        else:
            return jsonify({'error': 'Statut invalide'}), 400
    
    except Exception as e:
        db.session.rollback()
        app.logger.error(f'Erreur mise à jour statut: {str(e)}')
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
    
    try:
        msg = Message(
            subject=subject,
            recipients=[student.email],
            body=message,
            sender=app.config['MAIL_DEFAULT_SENDER']
        )
        mail.send(msg)
        app.logger.info(f"Email de statut envoyé à {student.email}")
    except Exception as e:
        app.logger.error(f"Erreur d'envoi d'email de statut: {e}")

@app.route('/admin/send_email', methods=['POST'])
@admin_required
def send_email():
    try:
        # Vérifier le Content-Type
        content_type = request.headers.get('Content-Type', '')
        if 'application/json' in content_type:
            try:
                data = request.get_json()
                if not data:
                    return jsonify({'error': 'Données JSON requises'}), 400
            except:
                return jsonify({'error': 'JSON invalide'}), 400
        else:
            # Fallback to form data
            data = {
                'recipient_type': request.form.get('recipient_type'),
                'subject': request.form.get('subject'),
                'message': request.form.get('message'),
                'custom_emails': request.form.get('custom_emails', '').split(',') if request.form.get('custom_emails') else [],
                'selected_ids': request.form.getlist('selected_ids[]')
            }
        
        recipient_type = data.get('recipient_type', 'all')
        subject = data.get('subject', '')
        message = data.get('message', '')
        custom_emails = data.get('custom_emails', [])
        selected_ids = data.get('selected_ids', [])
        
        if isinstance(custom_emails, str):
            custom_emails = [email.strip() for email in custom_emails.split(',') if email.strip()]
        
        if isinstance(selected_ids, str):
            try:
                selected_ids = json.loads(selected_ids)
            except:
                selected_ids = [int(id.strip()) for id in selected_ids.split(',') if id.strip().isdigit()]
        
        if not subject or not message:
            return jsonify({'error': 'Sujet et message sont requis'}), 400
        
        # Récupérer les destinataires
        recipients = []
        emails_list = []
        
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
            emails_list = [email.strip() for email in custom_emails if email.strip()]
        else:
            all_students = StudentRequest.query.all()
            recipients = all_students
            emails_list = [student.email for student in all_students if student.email]
        
        # Filtrer les emails valides
        valid_emails = [email for email in emails_list if email and '@' in email]
        
        if not valid_emails:
            return jsonify({'error': 'Aucun destinataire valide trouvé'}), 400
        
        # Envoyer les emails en batch
        sent_count = 0
        failed_emails = []
        
        try:
            # Pour Gmail, envoyer en un seul email avec tous les destinataires en BCC
            if len(valid_emails) <= 100:  # Limite de Gmail pour BCC
                msg = Message(
                    subject=subject,
                    recipients=[app.config['MAIL_DEFAULT_SENDER']],  # Envoyer à nous-mêmes
                    bcc=valid_emails,
                    body=message,
                    sender=app.config['MAIL_DEFAULT_SENDER']
                )
                mail.send(msg)
                sent_count = len(valid_emails)
                app.logger.info(f"Email groupé envoyé à {sent_count} destinataires")
            else:
                # Pour plus de 100 destinataires, envoyer par groupes de 100
                for i in range(0, len(valid_emails), 100):
                    batch = valid_emails[i:i+100]
                    msg = Message(
                        subject=subject,
                        recipients=[app.config['MAIL_DEFAULT_SENDER']],
                        bcc=batch,
                        body=message,
                        sender=app.config['MAIL_DEFAULT_SENDER']
                    )
                    mail.send(msg)
                    sent_count += len(batch)
                    app.logger.info(f"Batch {i//100 + 1} envoyé à {len(batch)} destinataires")
                    
                    # Pause pour éviter les limites
                    if i + 100 < len(valid_emails):
                        time.sleep(1)
                        
        except Exception as e:
            app.logger.error(f"Erreur d'envoi d'email: {e}")
            return jsonify({'error': f'Erreur SMTP: {str(e)}'}), 500
        
        # Préparer la réponse
        response_data = {
            'success': True, 
            'message': f'{sent_count} email(s) envoyé(s) avec succès',
            'sent_count': sent_count,
            'total_count': len(valid_emails)
        }
        
        return jsonify(response_data)
    
    except Exception as e:
        app.logger.error(f'Erreur générale send_email: {str(e)}')
        return jsonify({'error': str(e)}), 500

@app.route('/admin/download_report')
@admin_required
def download_report():
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
        app.logger.error(f'Erreur génération rapport: {str(e)}')
        flash(f'Erreur lors de la génération du rapport: {str(e)}', 'error')
        return redirect(url_for('admin_dashboard'))

@app.route('/admin/email_compose')
@admin_required
def email_compose():
    return render_template('email_compose.html')

@app.route('/admin/api/students')
@admin_required
def api_students():
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
        app.logger.error(f'Erreur api_students: {str(e)}')
        return jsonify({'error': str(e)}), 500

@app.route('/admin/api/stats')
@admin_required
def api_stats():
    try:
        stats = {
            'total': StudentRequest.query.count(),
            'approved': StudentRequest.query.filter_by(status='approved').count(),
            'rejected': StudentRequest.query.filter_by(status='rejected').count(),
            'pending': StudentRequest.query.filter_by(status='pending').count()
        }
        return jsonify(stats)
    except Exception as e:
        app.logger.error(f'Erreur api_stats: {str(e)}')
        return jsonify({'error': str(e)}), 500

@app.route('/admin/api/update_status_batch', methods=['POST'])
@admin_required
def update_status_batch():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Données JSON requises'}), 400
        
        ids = data.get('ids', [])
        status = data.get('status')
        notes = data.get('notes', '')
        
        if not ids or status not in ['pending', 'approved', 'rejected']:
            return jsonify({'error': 'Paramètres invalides'}), 400
        
        updated_count = 0
        for request_id in ids:
            try:
                student_request = StudentRequest.query.get(request_id)
                if student_request:
                    old_status = student_request.status
                    student_request.status = status
                    student_request.admin_notes = notes
                    student_request.date_processed = datetime.utcnow()
                    
                    if old_status != status:
                        send_status_email(student_request, status, notes)
                    
                    updated_count += 1
            except Exception as e:
                app.logger.error(f"Erreur mise à jour demande {request_id}: {e}")
                continue
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'{updated_count} demande(s) mise(s) à jour',
            'updated_count': updated_count
        })
        
    except Exception as e:
        db.session.rollback()
        app.logger.error(f'Erreur update_status_batch: {str(e)}')
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
    app.logger.error(f'Erreur 500: {str(e)}')
    return render_template('500.html'), 500

@app.errorhandler(413)
def request_entity_too_large(e):
    flash('Fichier trop volumineux (max 16MB)', 'error')
    return redirect(request.url)

if __name__ == '__main__':
    init_database()
    print("\n" + "="*60)
    print("APPLICATION PRÊTE POUR LA PRODUCTION")
    print("="*60)
    print("URL: http://localhost:5000")
    print("Login admin: http://localhost:5000/admin/login")
    print("="*60 + "\n")
    app.run(host='0.0.0.0', port=5000, debug=False)