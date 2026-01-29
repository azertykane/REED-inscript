import os
import time
import threading
import smtplib
from flask import Flask, render_template, request, redirect, url_for, flash, send_file, jsonify, session, current_app
from flask_mail import Mail, Message
from werkzeug.utils import secure_filename
from datetime import datetime
import io
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor

from config import Config
from database import db, StudentRequest
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import sendgrid
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail as SendGridMail, Email, Content, To
import ssl

app = Flask(__name__)
app.config.from_object(Config)

# Initialize extensions
db.init_app(app)
mail = Mail(app)

# Initialize SendGrid client
sg_client = SendGridAPIClient(app.config['MAIL_PASSWORD'])

# Create upload folder if it doesn't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

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
            if not telephone.replace(' ', '').isdigit():
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
                    filename = f"{new_request.id}_{field}.{file.filename.rsplit('.', 1)[1].lower()}"
                    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    
                    # Sauvegarder le fichier
                    file.save(filepath)
                    setattr(new_request, field, filename)
            
            # Commit toutes les données
            db.session.commit()
            
            # Envoyer l'email de confirmation
            send_confirmation_email(email, nom, prenom, new_request.id)
            
            flash('Votre demande a été soumise avec succès! Vous recevrez un email de confirmation.', 'success')
            return redirect(url_for('index'))
            
        except Exception as e:
            db.session.rollback()
            app.logger.error(f'Erreur lors de la soumission: {str(e)}')
            flash('Une erreur est survenue lors de la soumission. Veuillez réessayer.', 'error')
            return redirect(url_for('formulaire'))
    
    return render_template('form.html')

# Fonction pour envoyer des emails avec SendGrid (version corrigée)
def send_email_sendgrid(to_email, subject, body, from_email=None):
    """Envoyer un email via SendGrid API"""
    try:
        if from_email is None:
            from_email = app.config['MAIL_DEFAULT_SENDER']
        
        # Créer le message SendGrid avec la nouvelle API
        message = SendGridMail(
            from_email=Email(from_email),
            to_emails=To(to_email),
            subject=subject,
            plain_text_content=Content("text/plain", body)
        )
        
        # Envoyer l'email
        response = sg_client.send(message)
        
        print(f"✓ Email envoyé à {to_email} - Status: {response.status_code}")
        return True
        
    except Exception as e:
        print(f"✗ Erreur d'envoi d'email à {to_email}: {str(e)}")
        return False

# Fonction pour envoyer des emails en arrière-plan
def send_email_async(to_email, subject, body):
    """Envoyer un email en arrière-plan"""
    try:
        success = send_email_sendgrid(to_email, subject, body)
        if not success:
            print(f"Échec de l'envoi à {to_email}")
    except Exception as e:
        print(f"Erreur dans send_email_async: {str(e)}")

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
        # Envoyer en arrière-plan
        thread = threading.Thread(
            target=send_email_async,
            args=(to_email, subject, message)
        )
        thread.daemon = True
        thread.start()
        print(f"✓ Email de confirmation programmé pour {to_email}")
        
    except Exception as email_error:
        print(f"✗ Erreur d'envoi d'email: {email_error}")

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        
        if username == 'admin' and password == 'admin123':
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
        # Envoyer en arrière-plan
        thread = threading.Thread(
            target=send_email_async,
            args=(student.email, subject, message)
        )
        thread.daemon = True
        thread.start()
        print(f"✓ Email de statut programmé pour {student.email}")
    except Exception as e:
        print(f"✗ Erreur d'envoi d'email de statut: {e}")

@app.route('/admin/send_email', methods=['POST'])
def send_email():
    if not session.get('admin_logged_in'):
        return jsonify({'error': 'Non autorisé'}), 401
    
    try:
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
        
        # Limiter à 20 emails pour éviter les limites
        valid_emails = valid_emails[:20]
        
        # Envoyer les emails en arrière-plan
        sent_count = 0
        
        for email in valid_emails:
            try:
                # Personnaliser le message
                personalized_message = message
                if recipient_type in ['approved', 'rejected', 'pending', 'selected', 'all']:
                    student = next((s for s in recipients if s.email == email), None)
                    if student:
                        personalized_message = message.replace('{nom}', student.nom or '')
                        personalized_message = personalized_message.replace('{prenom}', student.prenom or '')
                        personalized_message = personalized_message.replace('{id}', str(student.id))
                        if student.date_submitted:
                            personalized_message = personalized_message.replace('{date}', student.date_submitted.strftime('%d/%m/%Y'))
                
                # Envoyer en arrière-plan
                thread = threading.Thread(
                    target=send_email_async,
                    args=(email, subject, personalized_message)
                )
                thread.daemon = True  # Thread démon pour ne pas bloquer l'arrêt
                thread.start()
                sent_count += 1
                
                # Petite pause pour éviter le rate limiting
                time.sleep(0.5)
                    
            except Exception as e:
                print(f"Erreur pour {email}: {str(e)}")
        
        # Préparer la réponse IMMÉDIATE
        response_data = {
            'success': True, 
            'message': f'Envoi d\'emails lancé en arrière-plan. {sent_count} email(s) seront envoyés.',
            'sent_count': sent_count,
            'total_count': len(valid_emails)
        }
        
        return jsonify(response_data)
    
    except Exception as e:
        print(f"Erreur générale dans send_email: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/test-sendgrid')
def test_sendgrid():
    """Route pour tester SendGrid"""
    try:
        # Tester l'envoi à votre propre email
        test_email = "commissionsociale.reed@gmail.com"
        subject = "Test SendGrid depuis Render"
        message = "Ceci est un test d'envoi d'email depuis votre application sur Render."
        
        success = send_email_sendgrid(test_email, subject, message)
        
        if success:
            return f"✓ Email de test envoyé à {test_email}"
        else:
            return "✗ Échec de l'envoi de l'email de test"
    
    except Exception as e:
        return f"Erreur: {str(e)}"

@app.route('/admin/test-email')
def admin_test_email():
    """Page admin pour tester les emails"""
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    
    return '''
    <div style="padding: 20px; max-width: 600px; margin: 0 auto;">
        <h2>📧 Tester l'envoi d'emails avec SendGrid</h2>
        <form method="POST" action="/admin/send-test-email">
            <div style="margin-bottom: 15px;">
                <label style="display: block; margin-bottom: 5px;">Email de test:</label>
                <input type="email" name="email" value="commissionsociale.reed@gmail.com" required 
                       style="width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 4px;">
            </div>
            <button type="submit" style="background: #007bff; color: white; padding: 10px 20px; border: none; border-radius: 4px; cursor: pointer;">
                Envoyer un test
            </button>
        </form>
        <p style="margin-top: 20px; color: #666;">
            <small>Vérifiez votre boîte de réception et vos spams après l'envoi.</small>
        </p>
    </div>
    '''

@app.route('/admin/send-test-email', methods=['POST'])
def send_test_email():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    
    email = request.form.get('email')
    if email:
        success = send_email_sendgrid(
            email, 
            "Test d'email - Amicale des Étudiants", 
            "Ceci est un email de test depuis votre application sur Render."
        )
        
        if success:
            flash(f'✓ Email de test envoyé à {email}', 'success')
        else:
            flash(f'✗ Échec de l\'envoi à {email}', 'error')
    
    return redirect(url_for('admin_dashboard'))

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
    return render_template('500.html'), 500

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        print("\n" + "="*60)
        print("APPLICATION DÉMARRÉE")
        print("="*60)
        print("URL: http://127.0.0.1:5000")
        print("Login admin: http://127.0.0.1:5000/admin/login")
        print("Identifiants: admin / admin123")
        print("Email configuré: commissionsociale.reed@gmail.com")
        print("SendGrid API Key: " + ("✓ Configuré" if app.config['MAIL_PASSWORD'] else "✗ Non configuré"))
        print("="*60 + "\n")
    
    app.run(debug=True, port=5000)