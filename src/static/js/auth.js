/**
 * Authentication state management
 * Handles token storage, retrieval, and validation
 */

const AUTH_TOKEN_KEY = 'model_registry_auth_token';
const AUTH_USER_KEY = 'model_registry_auth_user';

class AuthManager {
    /**
     * Store authentication token and user info
     * @param {string} token - Authentication token
     * @param {object} userInfo - User information (optional)
     */
    setAuth(token, userInfo = null) {
        if (!token || typeof token !== 'string' || token.trim() === '') {
            console.error('Invalid token provided to setAuth');
            return;
        }

        const trimmedToken = token.trim();
        console.log('Setting auth token:', trimmedToken.substring(0, 20) + '...');

        localStorage.setItem(AUTH_TOKEN_KEY, trimmedToken);
        if (userInfo) {
            localStorage.setItem(AUTH_USER_KEY, JSON.stringify(userInfo));
        }
        this.onAuthChange();
    }

    /**
     * Get stored authentication token
     * @returns {string|null} Token or null if not set
     */
    getToken() {
        return localStorage.getItem(AUTH_TOKEN_KEY);
    }

    /**
     * Get stored user information
     * @returns {object|null} User info or null if not set
     */
    getUserInfo() {
        const userStr = localStorage.getItem(AUTH_USER_KEY);
        return userStr ? JSON.parse(userStr) : null;
    }

    /**
     * Check if user is authenticated
     * @returns {boolean} True if token exists
     */
    isAuthenticated() {
        return this.getToken() !== null;
    }

    /**
     * Check if user has specific permission
     * @param {string} permission - Permission to check
     * @returns {boolean} True if user has permission
     */
    hasPermission(permission) {
        const userInfo = this.getUserInfo();
        if (!userInfo) return false;
        if (userInfo.is_admin) return true;
        return userInfo.permissions && userInfo.permissions.includes(permission);
    }

    /**
     * Clear authentication data
     */
    clearAuth() {
        localStorage.removeItem(AUTH_TOKEN_KEY);
        localStorage.removeItem(AUTH_USER_KEY);
        this.onAuthChange();
    }

    /**
     * Notify listeners of auth state change
     */
    onAuthChange() {
        // Dispatch custom event for other components to listen
        window.dispatchEvent(new CustomEvent('authStateChange', {
            detail: {
                isAuthenticated: this.isAuthenticated(),
                userInfo: this.getUserInfo()
            }
        }));
    }
}

// Create and export singleton instance
const authManager = new AuthManager();

/**
 * Initialize login modal and handlers
 */
function initLoginModal() {
    const loginModal = document.getElementById('login-modal');
    const loginForm = document.getElementById('login-form');
    const loginSubmit = document.getElementById('login-submit');
    const loginError = document.getElementById('login-error');

    if (!loginModal || !loginForm) return;

    // Handle form submission
    loginSubmit.addEventListener('click', async () => {
        const username = document.getElementById('login-username').value.trim();
        const password = document.getElementById('login-password').value;

        if (!username || !password) {
            showLoginError('Please enter both username and password');
            return;
        }

        loginSubmit.disabled = true;
        loginSubmit.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Logging in...';

        try {
            console.log('Attempting login for user:', username);
            const result = await apiClient.authenticate(username, password);
            console.log('Login successful, token received');

            // Verify token was stored
            if (typeof authManager !== 'undefined') {
                const storedToken = authManager.getToken();
                if (!storedToken) {
                    throw new Error('Token was not stored properly');
                }
                console.log('Token stored successfully');
            }

            const bsModal = bootstrap.Modal.getInstance(loginModal);
            bsModal.hide();
            loginForm.reset();
            showAlert('Login successful!', 'success');

            // Reload page to update UI
            setTimeout(() => {
                window.location.reload();
            }, 500);
        } catch (error) {
            console.error('Login error:', error);
            showLoginError(error.message || 'Login failed. Please check your credentials.');
        } finally {
            loginSubmit.disabled = false;
            loginSubmit.innerHTML = 'Login';
        }
    });

    function showLoginError(message) {
        if (loginError) {
            loginError.textContent = message;
            loginError.style.display = 'block';
        }
    }

    // Clear error when modal is hidden
    loginModal.addEventListener('hidden.bs.modal', () => {
        if (loginError) {
            loginError.style.display = 'none';
        }
        if (loginForm) {
            loginForm.reset();
        }
    });

    // Add default credentials helper
    const useDefaultBtn = document.getElementById('use-default-credentials');
    if (useDefaultBtn) {
        useDefaultBtn.addEventListener('click', () => {
            document.getElementById('login-username').value = 'ece30861defaultadminuser';
            document.getElementById('login-password').value = 'correcthorsebatterystaple123(!__+@**(A\'"`;DROP TABLE packages;';
        });
    }
}

/**
 * Update navigation based on auth state
 */
function updateNavigation() {
    const loginBtn = document.getElementById('login-btn');
    const logoutBtn = document.getElementById('logout-btn');
    const userInfo = document.getElementById('user-info');
    const usernameDisplay = document.getElementById('username-display');

    if (!loginBtn || !logoutBtn || !userInfo) return;

    if (authManager.isAuthenticated()) {
        loginBtn.style.display = 'none';
        userInfo.style.display = 'block';
        const user = authManager.getUserInfo();
        if (user && user.username) {
            usernameDisplay.textContent = user.username;
        }

        // Remove existing listeners by cloning
        const newLogoutBtn = logoutBtn.cloneNode(true);
        logoutBtn.parentNode.replaceChild(newLogoutBtn, logoutBtn);

        newLogoutBtn.addEventListener('click', () => {
            authManager.clearAuth();
            showAlert('Logged out successfully', 'info');
            window.location.reload();
        });
    } else {
        loginBtn.style.display = 'block';
        userInfo.style.display = 'none';

        // Remove existing listeners by cloning
        const newLoginBtn = loginBtn.cloneNode(true);
        loginBtn.parentNode.replaceChild(newLoginBtn, loginBtn);

        newLoginBtn.addEventListener('click', () => {
            const loginModal = new bootstrap.Modal(document.getElementById('login-modal'));
            loginModal.show();
        });
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    initLoginModal();
    updateNavigation();

    // Listen for auth state changes
    window.addEventListener('authStateChange', updateNavigation);
});
