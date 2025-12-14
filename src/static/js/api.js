/**
 * API Client for Model Registry
 * Handles all communication with the backend REST API
 */

const API_BASE_URL = window.location.origin;

class ApiClient {
    /**
     * Make an API request
     * @param {string} endpoint - API endpoint
     * @param {object} options - Fetch options
     * @returns {Promise<Response>}
     */
    async request(endpoint, options = {}) {
        const url = `${API_BASE_URL}${endpoint}`;

        // Get auth token if available
        const token = typeof authManager !== 'undefined' ? authManager.getToken() : null;

        const config = {
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                ...(token && { 'X-Authorization': token }),
                ...options.headers,
            },
            ...options,
        };

        if (config.body && typeof config.body === 'object') {
            config.body = JSON.stringify(config.body);
        }

        try {
            const response = await fetch(url, config);
            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.error || `HTTP error! status: ${response.status}`);
            }

            return data;
        } catch (error) {
            console.error('API request failed:', error);
            throw error;
        }
    }

    /**
     * Get health status
     * @returns {Promise<object>}
     */
    async getHealth() {
        return this.request('/api/health');
    }

    /**
     * Get activity summary for the health dashboard
     * @param {object} params - Query parameters (window, limit)
     * @returns {Promise<object>}
     */
    async getHealthActivity(params = {}) {
        const queryParams = new URLSearchParams();
        if (params.window !== undefined) queryParams.append('window', params.window);
        if (params.limit !== undefined) queryParams.append('limit', params.limit);
        const queryString = queryParams.toString();
        const endpoint = `/api/health/activity${queryString ? `?${queryString}` : ''}`;
        return this.request(endpoint);
    }

    /**
     * Get recent log entries for the health dashboard
     * @param {object} params - Query parameters (limit, level)
     * @returns {Promise<object>}
     */
    async getHealthLogs(params = {}) {
        const queryParams = new URLSearchParams();
        if (params.limit !== undefined) queryParams.append('limit', params.limit);
        if (params.level) queryParams.append('level', params.level);
        const queryString = queryParams.toString();
        const endpoint = `/api/health/logs${queryString ? `?${queryString}` : ''}`;
        return this.request(endpoint);
    }

    /**
     * List packages with optional search and pagination
     * @param {object} params - Query parameters
     * @returns {Promise<object>}
     */
    async listPackages(params = {}) {
        const queryParams = new URLSearchParams();
        if (params.offset !== undefined) queryParams.append('offset', params.offset);
        if (params.limit !== undefined) queryParams.append('limit', params.limit);
        if (params.query) queryParams.append('query', params.query);
        if (params.regex) queryParams.append('regex', params.regex);
        if (params.version) queryParams.append('version', params.version)
        if (params.sortField) queryParams.append('sort-field', params.sortField)
        if (params.sortOrder) queryParams.append('sort-order', params.sortOrder)

        const queryString = queryParams.toString();
        const endpoint = `/api/packages${queryString ? `?${queryString}` : ''}`;
        return this.request(endpoint);
    }

    /**
     * Get a specific package by ID
     * @param {string} packageId - Package ID
     * @returns {Promise<object>}
     */
    async getPackage(packageId) {
        return this.request(`/api/packages/${packageId}`);
    }

    /**
     * Upload a new package
     * @param {object} packageData - Package data
     * @returns {Promise<object>}
     */
    async uploadPackage(packageData) {
        return this.request('/api/packages', {
            method: 'POST',
            body: packageData,
        });
    }

    /**
     * Delete a package
     * @param {string} packageId - Package ID
     * @returns {Promise<object>}
     */
    async deletePackage(packageId) {
        return this.request(`/api/packages/${packageId}`, {
            method: 'DELETE',
        });
    }

    /**
     * Rate a package (get metrics)
     * @param {string} packageId - Package ID
     * @returns {Promise<object>}
     */
    async ratePackage(packageId) {
        return this.request(`/api/packages/${packageId}/rate`);
    }

    /**
     * Ingest a model from HuggingFace
     * @param {string} url - HuggingFace model URL
     * @returns {Promise<object>}
     */
    async ingestModel(url) {
        return this.request('/api/ingest', {
            method: 'POST',
            body: { url },
        });
    }

    /**
     * Reset the registry
     * @returns {Promise<object>}
     */
    async resetRegistry() {
        return this.request('/api/reset', {
            method: 'DELETE',
        });
    }

    /**
     * Authenticate user and store token
     * @param {string} username - Username
     * @param {string} password - Password
     * @returns {Promise<object>} User info
     */
    async authenticate(username, password) {
        const url = `${API_BASE_URL}/api/authenticate`;

        try {
            const response = await fetch(url, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                    'Accept': 'application/json',
                },
                body: JSON.stringify({
                    user: { name: username },
                    secret: { password: password }
                })
            });

            // Handle non-JSON responses
            let data;
            const contentType = response.headers.get('content-type');
            if (contentType && contentType.includes('application/json')) {
                data = await response.json();
            } else {
                const text = await response.text();
                // Try to parse as JSON if it looks like JSON
                try {
                    data = JSON.parse(text);
                } catch {
                    // If not JSON, treat the text as the token
                    data = text;
                }
            }

            if (!response.ok) {
                const errorMsg = data.error || data.message || `HTTP error! status: ${response.status}`;
                throw new Error(errorMsg);
            }

            // Token extraction - handle various formats
            let authToken;
            if (typeof data === 'string') {
                // Token is returned as JSON string (e.g., "bearer abc123...")
                authToken = data;
            } else if (data.token) {
                authToken = data.token;
            } else if (data && typeof data === 'object') {
                // If it's an object, try to extract token
                authToken = JSON.stringify(data);
            } else {
                authToken = data;
            }

            // Remove quotes if token is wrapped in quotes
            if (typeof authToken === 'string') {
                authToken = authToken.trim().replace(/^["']|["']$/g, '');
            }

            // Store token
            if (typeof authManager !== 'undefined') {
                authManager.setAuth(authToken, { username: username });
            }

            return { token: authToken, username };
        } catch (error) {
            console.error('Authentication error:', error);
            throw error;
        }
    }
}

// Create and export a singleton instance
const apiClient = new ApiClient();
