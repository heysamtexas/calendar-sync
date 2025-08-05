// Bootstrap 5 Theme Toggle Implementation
function initializeThemeToggle() {
    const themeToggle = document.getElementById('darkModeToggle');
    const themeIcon = document.getElementById('darkModeIcon');
    
    // Get stored theme or default to 'auto'
    const getStoredTheme = () => localStorage.getItem('theme');
    const setStoredTheme = theme => localStorage.setItem('theme', theme);
    
    // Get preferred theme
    const getPreferredTheme = () => {
        const storedTheme = getStoredTheme();
        if (storedTheme) {
            return storedTheme;
        }
        return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    };
    
    // Set theme on document
    const setTheme = theme => {
        if (theme === 'auto') {
            document.documentElement.setAttribute('data-bs-theme', 
                window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
        } else {
            document.documentElement.setAttribute('data-bs-theme', theme);
        }
        
        // Update icon and button attributes
        updateThemeIcon(theme);
    };
    
    // Update icon based on theme
    const updateThemeIcon = (theme) => {
        if (!themeIcon || !themeToggle) return;
        
        const isDark = theme === 'dark' || 
            (theme === 'auto' && window.matchMedia('(prefers-color-scheme: dark)').matches);
        
        // Add animation class
        themeIcon.classList.add('changing');
        
        setTimeout(() => {
            if (isDark) {
                themeIcon.className = 'bi bi-moon-stars-fill theme-icon';
                themeToggle.setAttribute('title', 'Switch to light theme');
                themeToggle.setAttribute('aria-label', 'Switch to light theme');
            } else {
                themeIcon.className = 'bi bi-sun-fill theme-icon';
                themeToggle.setAttribute('title', 'Switch to dark theme');
                themeToggle.setAttribute('aria-label', 'Switch to dark theme');
            }
            
            // Remove animation class
            setTimeout(() => {
                themeIcon.classList.remove('changing');
            }, 150);
        }, 150);
    };
    
    // Set initial theme
    setTheme(getPreferredTheme());
    
    // Listen for system theme changes
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
        const storedTheme = getStoredTheme();
        if (storedTheme !== 'light' && storedTheme !== 'dark') {
            setTheme(getPreferredTheme());
        }
    });
    
    // Toggle theme on button click
    if (themeToggle) {
        themeToggle.addEventListener('click', () => {
            const currentTheme = getStoredTheme() || 'light';
            const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
            
            setStoredTheme(newTheme);
            setTheme(newTheme);
        });
    }
}

// HTMX Configuration and Event Handlers
document.addEventListener('DOMContentLoaded', function() {
    
    // Initialize theme toggle
    initializeThemeToggle();
    
    // Copy to clipboard functionality
    document.addEventListener('click', function(e) {
        if (e.target.matches('.copy-id-btn')) {
            const calendarId = e.target.getAttribute('data-calendar-id');
            if (calendarId) {
                navigator.clipboard.writeText(calendarId).then(function() {
                    // Show temporary success feedback
                    const originalText = e.target.textContent;
                    e.target.textContent = '✓';
                    e.target.style.color = '#28a745';
                    
                    setTimeout(function() {
                        e.target.textContent = originalText;
                        e.target.style.color = '';
                    }, 1000);
                }).catch(function(err) {
                    console.error('Failed to copy: ', err);
                });
            }
        }
    });
    
    // Disconnect account confirmation
    document.addEventListener('click', function(e) {
        if (e.target.matches('.disconnect-account-btn')) {
            const confirmMessage = e.target.getAttribute('data-confirm-message');
            if (confirmMessage && !confirm(confirmMessage)) {
                e.preventDefault();
            }
        }
    });
    
    // HTMX loading indicators
    document.body.addEventListener('htmx:beforeRequest', function(e) {
        const indicator = e.target.closest('td')?.querySelector('.htmx-indicator');
        if (indicator) {
            indicator.classList.remove('d-none');
            indicator.classList.add('d-flex');
        }
    });
    
    document.body.addEventListener('htmx:afterRequest', function(e) {
        const indicator = e.target.closest('td')?.querySelector('.htmx-indicator');
        if (indicator) {
            indicator.classList.add('d-none');
            indicator.classList.remove('d-flex');
        }
    });
});