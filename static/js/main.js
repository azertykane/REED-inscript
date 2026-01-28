// static/js/main.js - Version corrigée
document.addEventListener('DOMContentLoaded', function() {
    console.log('Application REED chargée');
    
    // Formattage des numéros de téléphone
    const phoneInputs = document.querySelectorAll('input[type="tel"]');
    phoneInputs.forEach(input => {
        input.addEventListener('input', function() {
            let value = this.value.replace(/\D/g, '');
            if (value.length > 0) {
                let formatted = '';
                if (value.length <= 2) {
                    formatted = value;
                } else if (value.length <= 4) {
                    formatted = value.replace(/(\d{2})/, '$1 ');
                } else if (value.length <= 6) {
                    formatted = value.replace(/(\d{2})(\d{2})/, '$1 $2 ');
                } else {
                    formatted = value.replace(/(\d{2})(\d{2})(\d{2})(\d{2})/, '$1 $2 $3 $4');
                }
                this.value = formatted;
            }
        });
    });
    
    // Prévisualisation d'images
    const imageInputs = document.querySelectorAll('input[type="file"][accept*="image"]');
    imageInputs.forEach(input => {
        input.addEventListener('change', function() {
            const previewId = this.getAttribute('data-preview');
            if (previewId) {
                const preview = document.getElementById(previewId);
                if (preview && this.files && this.files[0]) {
                    const reader = new FileReader();
                    reader.onload = function(e) {
                        preview.src = e.target.result;
                        preview.style.display = 'block';
                    };
                    reader.readAsDataURL(this.files[0]);
                }
            }
        });
    });
    
    // Validation des formulaires
    const forms = document.querySelectorAll('form');
    forms.forEach(form => {
        form.addEventListener('submit', function(e) {
            const requiredFields = this.querySelectorAll('[required]');
            let valid = true;
            
            requiredFields.forEach(field => {
                if (!field.value.trim()) {
                    valid = false;
                    field.classList.add('is-invalid');
                } else {
                    field.classList.remove('is-invalid');
                }
            });
            
            if (!valid) {
                e.preventDefault();
                alert('Veuillez remplir tous les champs obligatoires');
            }
        });
    });
});