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
        const config = {
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
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
        return this.request('/health');
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
        const endpoint = `/health/activity${queryString ? `?${queryString}` : ''}`;
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
        const endpoint = `/health/logs${queryString ? `?${queryString}` : ''}`;
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
        
        const queryString = queryParams.toString();
        const endpoint = `/packages${queryString ? `?${queryString}` : ''}`;
        return this.request(endpoint);
    }

    /**
     * Get a specific package by ID
     * @param {string} packageId - Package ID
     * @returns {Promise<object>}
     */
    async getPackage(packageId) {
        return this.request(`/packages/${packageId}`);
    }

    /**
     * Upload a new package
     * @param {object} packageData - Package data
     * @returns {Promise<object>}
     */
    async uploadPackage(packageData) {
        return this.request('/packages', {
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
        return this.request(`/packages/${packageId}`, {
            method: 'DELETE',
        });
    }

    /**
     * Rate a package (get metrics)
     * @param {string} packageId - Package ID
     * @returns {Promise<object>}
     */
    async ratePackage(packageId) {
        return this.request(`/packages/${packageId}/rate`);
    }

    /**
     * Ingest a model from HuggingFace
     * @param {string} url - HuggingFace model URL
     * @returns {Promise<object>}
     */
    async ingestModel(url) {
        return this.request('/ingest', {
            method: 'POST',
            body: { url },
        });
    }

    /**
     * Reset the registry
     * @returns {Promise<object>}
     */
    async resetRegistry() {
        return this.request('/reset', {
            method: 'DELETE',
        });
    }
}

// Create and export a singleton instance
const apiClient = new ApiClient();

