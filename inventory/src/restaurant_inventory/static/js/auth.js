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

    // Handle authentication errors - redirect to login
    if (response.status === 401 || response.status === 403) {
        console.warn('Authentication error, redirecting to login...');
        // Clear stored credentials
        localStorage.removeItem('access_token');
        localStorage.removeItem('user');
        localStorage.removeItem('user_name');
        localStorage.removeItem('user_role');
        // Redirect to login
        window.location.href = '/login';
        // Return null to prevent further processing
        return null;
    }

    if (!response.ok) {
        // Log the response body for debugging
        const errorText = await response.text();
        console.error(`API Error ${response.status}:`, errorText);
        throw new Error(`HTTP error! status: ${response.status}`);
    }

    // Handle 204 No Content responses (from DELETE operations)
    if (response.status === 204) {
        return { success: true };
    }

    // Check if response is actually JSON before trying to parse it
    // This handles cases where server redirects to login page (HTML) with 200 status
    const contentType = response.headers.get('content-type');
    if (contentType && contentType.includes('application/json')) {
        return response.json();
    } else if (!contentType || contentType.length === 0) {
        // No content-type header - assume successful empty response (like 204)
        return { success: true };
    } else {
        // Response is not JSON (likely HTML from a redirect to login page)
        console.warn('Non-JSON response received, likely redirected to login. Clearing auth and redirecting...');
        localStorage.removeItem('access_token');
        localStorage.removeItem('user');
        localStorage.removeItem('user_name');
        localStorage.removeItem('user_role');
        window.location.href = '/login';
        return null;
    }
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
                'Admin': 'Admin',
                'admin': 'Admin',
                'MANAGER': 'Manager',
                'Manager': 'Manager',
                'manager': 'Manager',
                'STAFF': 'User',
                'Staff': 'User',
                'staff': 'User'
            };
            userRole.textContent = roleMap[user.role] || user.role;
        }

        // Show Settings link and dropdown admin options only to admins
        // Support all case variations for backwards compatibility
        const isAdmin = user.role === 'Admin' || user.role === 'ADMIN' || user.role === 'admin';

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
