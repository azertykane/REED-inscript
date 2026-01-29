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
import ssl

app = Flask(__name__)
app.config.from_object(Config)

# Initialize extensions
db.init_app(app)
mail = Mail(app)

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
            
            # Handle file uploads - SIMPLIFIÉ POUR ÉVITER LES TIMEOUT
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
            
            # Envoyer l'email en arrière-plan (ne pas bloquer la réponse)
            try:
                send_confirmation_email.delay(email, nom, prenom, new_request.id)
            except:
                # Si Celery n'est pas configuré, envoyer plus tard
                pass
            
            flash('Votre demande a été soumise avec succès! Vous recevrez un email de confirmation.', 'success')
            return redirect(url_for('index'))
            
        except Exception as e:
            db.session.rollback()
            app.logger.error(f'Erreur lors de la soumission: {str(e)}')
            flash('Une erreur est survenue lors de la soumission. Veuillez réessayer.', 'error')
            return redirect(url_for('formulaire'))
    
    return render_template('form.html')

def send_confirmation_email(to_email, nom, prenom, request_id):
    """Envoyer un email de confirmation à l'étudiant (version simplifiée)"""
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
            args=(app.app_context(), to_email, subject, message)
        )
        thread.start()
        print(f"Email de confirmation programmé pour {to_email}")
        
    except Exception as email_error:
        print(f"Erreur d'envoi d'email: {email_error}")
        # Ne pas bloquer l'utilisateur si l'email échoue

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        
        print(f"\n=== TENTATIVE DE CONNEXION ===")
        print(f"Username: '{username}'")
        print(f"Password: '{password}'")
        print(f"Attendu: 'admin' / 'admin123'")
        
        if username == 'admin' and password == 'admin123':
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


def send_email_async(app_context, to_email, subject, body):
    """Envoyer un email en arrière-plan"""
    with app_context:
        try:
            # Configuration SMTP pour Gmail
            context = ssl.create_default_context()
            
            # Créer le message
            msg = MIMEMultipart()
            msg['From'] = app.config['MAIL_DEFAULT_SENDER']
            msg['To'] = to_email
            msg['Subject'] = subject
            
            # Ajouter le corps du message
            msg.attach(MIMEText(body, 'plain'))
            
            # Envoyer l'email
            with smtplib.SMTP_SSL('smtp.gmail.com', 465, context=context) as server:
                server.login(app.config['MAIL_USERNAME'], app.config['MAIL_PASSWORD'])
                server.send_message(msg)
            
            print(f"Email envoyé à {to_email}")
            
        except Exception as e:
            print(f"Erreur d'envoi d'email à {to_email}: {str(e)}")
            # Log l'erreur mais ne pas bloquer l'utilisateur

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
        
        # Envoyer les emails en arrière-plan
        sent_count = 0
        failed_emails = []
        
        # Créer un thread pour chaque email (limité à 10 pour éviter le spam)
        threads = []
        max_threads = min(len(valid_emails), 10)  # Limiter à 10 threads max
        
        for i, email in enumerate(valid_emails[:50]):  # Limiter à 50 emails max
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
                
                # Créer un thread pour envoyer l'email
                thread = threading.Thread(
                    target=send_email_async,
                    args=(app.app_context(), email, subject, personalized_message)
                )
                threads.append(thread)
                thread.start()
                sent_count += 1
                
                # Pause pour éviter les limites de Gmail
                if i % 5 == 0 and i > 0:
                    time.sleep(1)
                    
            except Exception as e:
                failed_emails.append({'email': email, 'error': str(e)})
        
        # Attendre que tous les threads se terminent (avec timeout)
        for thread in threads:
            thread.join(timeout=30)  # Timeout de 30 secondes
        
        # Préparer la réponse IMMÉDIATE (ne pas attendre tous les emails)
        response_data = {
            'success': True, 
            'message': f'Envoi d\'emails lancé en arrière-plan. {sent_count} email(s) seront envoyés.',
            'sent_count': sent_count,
            'total_count': len(valid_emails[:50])  # Limité à 50
        }
        
        return jsonify(response_data)
    
    except Exception as e:
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
            args=(app.app_context(), student.email, subject, message)
        )
        thread.start()
        print(f"Email de statut programmé pour {student.email}")
    except Exception as e:
        print(f"Erreur d'envoi d'email de statut: {e}")

@app.route('/admin/test_email', methods=['GET', 'POST'])
def test_email():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        if email:
            try:
                # Tester l'envoi d'email
                subject = "Test d'email - Amicale des Étudiants"
                message = "Ceci est un email de test pour vérifier la configuration."
                
                send_email_async(app.app_context(), email, subject, message)
                
                flash(f'Email de test envoyé à {email}', 'success')
            except Exception as e:
                flash(f'Erreur: {str(e)}', 'error')
        
        return redirect(url_for('admin_dashboard'))
    
    return '''
    <form method="POST">
        <input type="email" name="email" placeholder="Email de test" required>
        <button type="submit">Tester l'email</button>
    </form>
    '''

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
        print("Email configuré: rashidtoure730@gmail.com")
        print("="*60 + "\n")
    
    app.run(debug=True, port=5000)