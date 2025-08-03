// HTMX Configuration and Event Handlers
document.addEventListener('DOMContentLoaded', function() {
    
    // Configure HTMX CSRF protection
    document.body.addEventListener('htmx:configRequest', function(evt) {
        const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
        if (csrfToken) {
            evt.detail.headers['X-CSRFToken'] = csrfToken;
        }
    });
    
    // Global error handling for HTMX requests
    document.body.addEventListener('htmx:responseError', function(evt) {
        console.error('HTMX request error:', evt.detail);
        
        // Find the closest error container
        const errorContainer = evt.target.closest('.calendar-sync-toggle')?.querySelector('.error-container');
        if (errorContainer) {
            errorContainer.innerHTML = '<div class="alert alert-danger">An error occurred. Please try again.</div>';
            errorContainer.style.display = 'block';
            
            // Hide error after 5 seconds
            setTimeout(() => {
                errorContainer.style.display = 'none';
                errorContainer.innerHTML = '';
            }, 5000);
        }
    });
    
    // Handle successful HTMX responses
    document.body.addEventListener('htmx:afterSwap', function(evt) {
        // Hide any visible error containers on successful swap
        const errorContainers = document.querySelectorAll('.error-container');
        errorContainers.forEach(container => {
            container.style.display = 'none';
            container.innerHTML = '';
        });
    });
    
    // Handle loading states
    document.body.addEventListener('htmx:beforeRequest', function(evt) {
        // Disable the button that triggered the request
        if (evt.target.matches('button')) {
            evt.target.disabled = true;
        }
    });
    
    document.body.addEventListener('htmx:afterRequest', function(evt) {
        // Re-enable buttons after request completes
        if (evt.target.matches('button')) {
            evt.target.disabled = false;
        }
    });
    
});