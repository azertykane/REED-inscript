// Main JavaScript file
// Version simplifiée pour tester
document.addEventListener('DOMContentLoaded', function() {
    console.log('Page chargée');
    
    // Désactiver toutes les validations JS temporairement
    const forms = document.querySelectorAll('form');
    forms.forEach(form => {
        form.addEventListener('submit', function(e) {
            console.log('Formulaire soumis:', form.id || form.className);
            // Laisser le formulaire s'envoyer normalement
        });
    });
    
    // Afficher les messages flash
    const alerts = document.querySelectorAll('.alert');
    if (alerts.length > 0) {
        console.log(`${alerts.length} message(s) flash trouvé(s)`);
    }
});

// Utility function to format phone numbers
function formatPhoneNumber(input) {
    const phone = input.value.replace(/\D/g, '');
    if (phone.length <= 2) {
        input.value = phone;
    } else if (phone.length <= 4) {
        input.value = phone.replace(/(\d{2})/, '$1 ');
    } else if (phone.length <= 6) {
        input.value = phone.replace(/(\d{2})(\d{2})/, '$1 $2 ');
    } else if (phone.length <= 8) {
        input.value = phone.replace(/(\d{2})(\d{2})(\d{2})/, '$1 $2 $3 ');
    } else {
        input.value = phone.replace(/(\d{2})(\d{2})(\d{2})(\d{2})/, '$1 $2 $3 $4');
    }
}

// Utility function to preview images before upload
function previewImage(input, previewId) {
    const preview = document.getElementById(previewId);
    const file = input.files[0];
    const reader = new FileReader();
    
    reader.onloadend = function() {
        preview.src = reader.result;
        preview.style.display = 'block';
    };
    
    if (file) {
        reader.readAsDataURL(file);
    } else {
        preview.src = '';
        preview.style.display = 'none';
    }
}

// Export functions to global scope
window.formatPhoneNumber = formatPhoneNumber;
window.previewImage = previewImage;