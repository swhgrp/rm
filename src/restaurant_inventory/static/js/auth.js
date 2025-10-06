// Authentication utilities

function getToken() {
    return localStorage.getItem('access_token');
}

function getUser() {
    const userStr = localStorage.getItem('user');
    return userStr ? JSON.parse(userStr) : null;
}

function isAuthenticated() {
    return getToken() !== null;
}

function logout() {
    localStorage.removeItem('access_token');
    localStorage.removeItem('user');
    window.location.href = '/login';
}

// API request helper with authentication
async function apiRequest(url, options = {}) {
    const token = getToken();
    
    const defaultOptions = {
        headers: {
            'Content-Type': 'application/json',
        }
    };
    
    if (token) {
        defaultOptions.headers['Authorization'] = `Bearer ${token}`;
    }
    
    const mergedOptions = {
        ...defaultOptions,
        ...options,
        headers: {
            ...defaultOptions.headers,
            ...options.headers
        }
    };
    
    const response = await fetch(url, mergedOptions);
    
    if (response.status === 401) {
        // Token expired or invalid
        logout();
        return;
    }
    
    if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
    }
    
    return response.json();
}

// Update navigation based on auth status
function updateNavigation() {
    const user = getUser();
    const userMenu = document.getElementById('userMenu');
    const loginButton = document.getElementById('loginButton');
    const userFullName = document.getElementById('userFullName');
    const userRole = document.getElementById('userRole');
    const adminSettingsLink = document.getElementById('adminSettingsLink');

    if (user) {
        userMenu.style.display = 'block';
        loginButton.style.display = 'none';
        userFullName.textContent = user.full_name;

        // Show role in dropdown
        if (userRole) {
            const roleMap = {
                'ADMIN': 'Admin',
                'MANAGER': 'Manager',
                'STAFF': 'User'
            };
            userRole.textContent = roleMap[user.role] || user.role;
        }

        // Show Settings link and dropdown admin options only to admins
        const isAdmin = user.role === 'ADMIN' || user.role === 'admin';

        if (adminSettingsLink) {
            adminSettingsLink.style.display = isAdmin ? 'block' : 'none';
        }
    } else {
        userMenu.style.display = 'none';
        loginButton.style.display = 'block';
        if (adminSettingsLink) {
            adminSettingsLink.style.display = 'none';
        }
    }
}

// Navigate to user profile
function showUserProfile() {
    window.location.href = '/profile';
}

// Initialize navigation on page load
document.addEventListener('DOMContentLoaded', function() {
    updateNavigation();
});
