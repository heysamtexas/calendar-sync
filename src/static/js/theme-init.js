// Initialize theme immediately to prevent flash
(function() {
    const savedTheme = localStorage.getItem('theme');
    const systemPrefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    
    let currentTheme;
    if (savedTheme) {
        currentTheme = savedTheme; // Use saved preference
    } else if (systemPrefersDark) {
        currentTheme = 'dark'; // Use system preference
    } else {
        currentTheme = 'light'; // Default to light
    }
    
    document.documentElement.setAttribute('data-theme', currentTheme);
})();