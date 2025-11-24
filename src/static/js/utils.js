/**
 * Utility functions for the frontend
 */

/**
 * Show an alert message to the user
 * @param {string} message - Alert message
 * @param {string} type - Alert type (success, danger, warning, info)
 * @param {number} duration - Duration in milliseconds (0 = no auto-dismiss)
 */
function showAlert(message, type = 'info', duration = 5000) {
    const alertContainer = document.getElementById('alert-container');
    if (!alertContainer) return;

    const alertId = `alert-${Date.now()}`;
    // Escape HTML to prevent XSS
    const escapedMessage = escapeHtml(message);
    const alertHtml = `
        <div class="alert alert-${type} alert-dismissible fade show" role="alert" id="${alertId}">
            ${escapedMessage}
            <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close alert"></button>
        </div>
    `;
    
    alertContainer.insertAdjacentHTML('beforeend', alertHtml);

    if (duration > 0) {
        setTimeout(() => {
            const alertElement = document.getElementById(alertId);
            if (alertElement) {
                const bsAlert = new bootstrap.Alert(alertElement);
                bsAlert.close();
            }
        }, duration);
    }
}

/**
 * Show an accessible confirmation dialog
 * @param {string} message - Confirmation message
 * @param {string} title - Dialog title (optional)
 * @returns {Promise<boolean>} Promise that resolves to true if confirmed, false if cancelled
 */
function showConfirmDialog(message, title = 'Confirm Action') {
    return new Promise((resolve) => {
        const modal = document.getElementById('accessible-modal');
        if (!modal) {
            // Fallback to browser confirm if modal doesn't exist
            resolve(confirm(message));
            return;
        }

        const modalTitle = document.getElementById('modal-title');
        const modalBody = document.getElementById('modal-body');
        const confirmBtn = document.getElementById('modal-confirm');
        const cancelBtn = document.getElementById('modal-cancel');
        const bsModal = new bootstrap.Modal(modal);

        // Set content
        modalTitle.textContent = title;
        modalBody.textContent = message;

        // Remove existing event listeners by cloning
        const newConfirmBtn = confirmBtn.cloneNode(true);
        const newCancelBtn = cancelBtn.cloneNode(true);
        confirmBtn.parentNode.replaceChild(newConfirmBtn, confirmBtn);
        cancelBtn.parentNode.replaceChild(newCancelBtn, cancelBtn);

        // Add new event listeners
        newConfirmBtn.addEventListener('click', () => {
            bsModal.hide();
            resolve(true);
        });

        newCancelBtn.addEventListener('click', () => {
            bsModal.hide();
            resolve(false);
        });

        // Handle ESC key and backdrop click
        modal.addEventListener('hidden.bs.modal', () => {
            resolve(false);
        }, { once: true });

        // Show modal and focus on confirm button
        bsModal.show();
        setTimeout(() => {
            newConfirmBtn.focus();
        }, 100);
    });
}

/**
 * Escape HTML to prevent XSS
 * @param {string} text - Text to escape
 * @returns {string} Escaped HTML
 */
function escapeHtml(text) {
    if (typeof text !== 'string') return text;
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * Format bytes to human-readable size
 * @param {number} bytes - Size in bytes
 * @returns {string} Formatted size string
 */
function formatBytes(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
}

/**
 * Format ISO date string to readable format
 * @param {string} isoString - ISO date string
 * @returns {string} Formatted date string
 */
function formatDate(isoString) {
    if (!isoString) return 'N/A';
    const date = new Date(isoString);
    return date.toLocaleString();
}

/**
 * Format a score to percentage with color coding
 * @param {number} score - Score value (0-1)
 * @returns {object} Object with formatted string and color class
 */
function formatScore(score) {
    if (score === null || score === undefined) return { text: 'N/A', class: 'text-muted' };
    const percentage = (score * 100).toFixed(1);
    let colorClass = 'text-danger';
    if (score >= 0.7) colorClass = 'text-success';
    else if (score >= 0.5) colorClass = 'text-warning';
    return { text: `${percentage}%`, class: colorClass };
}

/**
 * Get URL parameter value
 * @param {string} name - Parameter name
 * @returns {string|null} Parameter value
 */
function getUrlParameter(name) {
    const urlParams = new URLSearchParams(window.location.search);
    return urlParams.get(name);
}

/**
 * Set URL parameter
 * @param {string} name - Parameter name
 * @param {string} value - Parameter value
 */
function setUrlParameter(name, value) {
    const url = new URL(window.location);
    url.searchParams.set(name, value);
    window.history.pushState({}, '', url);
}

/**
 * Remove URL parameter
 * @param {string} name - Parameter name
 */
function removeUrlParameter(name) {
    const url = new URL(window.location);
    url.searchParams.delete(name);
    window.history.pushState({}, '', url);
}

/**
 * Debounce function
 * @param {Function} func - Function to debounce
 * @param {number} wait - Wait time in milliseconds
 * @returns {Function} Debounced function
 */
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

/**
 * Validate JSON string
 * @param {string} jsonString - JSON string to validate
 * @returns {object|null} Parsed JSON or null if invalid
 */
function validateJSON(jsonString) {
    if (!jsonString || jsonString.trim() === '') return {};
    try {
        return JSON.parse(jsonString);
    } catch (e) {
        return null;
    }
}

/**
 * Copy text to clipboard
 * @param {string} text - Text to copy
 * @returns {Promise<boolean>} Success status
 */
async function copyToClipboard(text) {
    try {
        await navigator.clipboard.writeText(text);
        return true;
    } catch (err) {
        console.error('Failed to copy text:', err);
        return false;
    }
}

