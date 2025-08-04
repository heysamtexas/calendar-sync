// Dark Mode Functionality
function initializeDarkMode() {
    const darkModeToggle = document.getElementById('darkModeToggle');
    const darkModeIcon = document.getElementById('darkModeIcon');
    const html = document.documentElement;
    
    // Check for saved theme preference or default to system preference
    const savedTheme = localStorage.getItem('darkMode');
    const systemPrefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    
    let isDarkMode = savedTheme === 'enabled' || (savedTheme === null && systemPrefersDark);
    
    // Apply initial theme
    updateDarkMode(isDarkMode);
    
    // Toggle dark mode on button click
    if (darkModeToggle) {
        darkModeToggle.addEventListener('click', function() {
            isDarkMode = !isDarkMode;
            updateDarkMode(isDarkMode);
            localStorage.setItem('darkMode', isDarkMode ? 'enabled' : 'disabled');
        });
    }
    
    // Listen for system theme changes
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function(e) {
        if (localStorage.getItem('darkMode') === null) {
            isDarkMode = e.matches;
            updateDarkMode(isDarkMode);
        }
    });
    
    function updateDarkMode(isDark) {
        if (isDark) {
            html.classList.add('dark-mode');
            if (darkModeIcon) {
                darkModeIcon.className = 'dark-mode-icon dark';
            }
        } else {
            html.classList.remove('dark-mode');
            if (darkModeIcon) {
                darkModeIcon.className = 'dark-mode-icon light';
            }
        }
        
        // Update the global isDarkMode variable
        window.isDarkModeActive = isDark;
    }
}

// HTMX Configuration and Event Handlers
document.addEventListener('DOMContentLoaded', function() {
    
    // Initialize dark mode
    initializeDarkMode();
    
    // Set dynamic calendar colors using CSS custom properties
    document.querySelectorAll('.calendar-color-badge[data-color]').forEach(function(badge) {
        const color = badge.getAttribute('data-color');
        if (color) {
            badge.style.setProperty('--calendar-color', color);
        }
    });
    
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

// Copy to clipboard function for Google Calendar IDs
function copyToClipboard(text) {
    if (navigator.clipboard && window.isSecureContext) {
        // Use modern clipboard API
        navigator.clipboard.writeText(text).then(function() {
            showCopyNotification('Copied to clipboard!');
        }).catch(function(err) {
            console.error('Failed to copy to clipboard:', err);
            showCopyNotification('Failed to copy', true);
        });
    } else {
        // Fallback for older browsers
        const textArea = document.createElement('textarea');
        textArea.value = text;
        textArea.style.position = 'fixed';
        textArea.style.opacity = '0';
        document.body.appendChild(textArea);
        textArea.focus();
        textArea.select();
        
        try {
            const successful = document.execCommand('copy');
            showCopyNotification(successful ? 'Copied to clipboard!' : 'Failed to copy', !successful);
        } catch (err) {
            console.error('Failed to copy to clipboard:', err);
            showCopyNotification('Failed to copy', true);
        }
        
        document.body.removeChild(textArea);
    }
}

// Show copy notification
function showCopyNotification(message, isError = false) {
    // Remove any existing notifications
    const existingNotification = document.querySelector('.copy-notification');
    if (existingNotification) {
        existingNotification.remove();
    }
    
    // Create notification element
    const notification = document.createElement('div');
    notification.className = `copy-notification ${isError ? 'error' : 'success'}`;
    notification.textContent = message;
    notification.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        background: ${isError ? '#dc3545' : '#28a745'};
        color: white;
        padding: 12px 20px;
        border-radius: 4px;
        font-size: 14px;
        font-weight: 500;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        z-index: 1000;
        transform: translateX(100%);
        transition: transform 0.3s ease;
    `;
    
    document.body.appendChild(notification);
    
    // Animate in
    setTimeout(() => {
        notification.style.transform = 'translateX(0)';
    }, 10);
    
    // Animate out and remove
    setTimeout(() => {
        notification.style.transform = 'translateX(100%)';
        setTimeout(() => {
            if (notification.parentNode) {
                notification.parentNode.removeChild(notification);
            }
        }, 300);
    }, 2000);
}