/**
 * Upload package page functionality
 */

/**
 * Initialize the page
 */
document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('upload-form').addEventListener('submit', handleUpload);
});

/**
 * Handle upload form submission
 */
async function handleUpload(event) {
    event.preventDefault();

    const form = event.target;
    const submitBtn = form.querySelector('button[type="submit"]');
    const originalText = submitBtn.innerHTML;

    // Clear previous errors
    clearFormErrors();

    // Get form data
    const nameInput = document.getElementById('package-name');
    const versionInput = document.getElementById('package-version');
    const urlInput = document.getElementById('package-url');
    const contentInput = document.getElementById('package-content');
    const metadataInput = document.getElementById('package-metadata');

    const name = nameInput.value.trim();
    const version = versionInput.value.trim();
    const url = urlInput.value.trim();
    const content = contentInput.value.trim();
    const metadataJson = metadataInput.value.trim();

    let hasErrors = false;

    // Validate required fields
    if (!name) {
        showFieldError('package-name', 'Package name is required');
        hasErrors = true;
    }

    if (!version) {
        showFieldError('package-version', 'Version is required');
        hasErrors = true;
    }

    // Validate URL format if provided
    if (url && !isValidUrl(url)) {
        showFieldError('package-url', 'Please enter a valid URL');
        hasErrors = true;
    }

    // Validate JSON metadata if provided
    let metadata = {};
    if (metadataJson) {
        const parsed = validateJSON(metadataJson);
        if (parsed === null) {
            showFieldError('package-metadata', 'Invalid JSON format. Please check your JSON syntax.');
            hasErrors = true;
        } else {
            metadata = parsed;
        }
    }

    if (hasErrors) {
        // Focus on first error field
        const firstError = form.querySelector('.is-invalid');
        if (firstError) {
            firstError.focus();
        }
        return;
    }

    // Add URL to metadata if provided
    if (url) {
        metadata.url = url;
    }

    // Prepare package data
    const packageData = {
        name,
        version,
        content,
        metadata,
    };

    // Disable submit button
    submitBtn.disabled = true;
    submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span>Uploading...';
    submitBtn.setAttribute('aria-busy', 'true');

    try {
        const response = await apiClient.uploadPackage(packageData);
        showAlert('Package uploaded successfully!', 'success');
        
        // Redirect to package detail page
        setTimeout(() => {
            window.location.href = `/packages/${response.package.id}`;
        }, 1500);
    } catch (error) {
        showAlert(`Failed to upload package: ${error.message}`, 'danger');
        submitBtn.disabled = false;
        submitBtn.innerHTML = originalText;
        submitBtn.removeAttribute('aria-busy');
    }
}

/**
 * Show field error
 */
function showFieldError(fieldId, message) {
    const field = document.getElementById(fieldId);
    const errorDiv = document.getElementById(`${fieldId}-error`);
    
    if (field) {
        field.classList.add('is-invalid');
        field.setAttribute('aria-invalid', 'true');
    }
    
    if (errorDiv) {
        errorDiv.textContent = message;
        errorDiv.style.display = 'block';
    }
}

/**
 * Clear all form errors
 */
function clearFormErrors() {
    const form = document.getElementById('upload-form');
    if (!form) return;
    
    form.querySelectorAll('.is-invalid').forEach(field => {
        field.classList.remove('is-invalid');
        field.setAttribute('aria-invalid', 'false');
    });
    
    form.querySelectorAll('.invalid-feedback').forEach(errorDiv => {
        errorDiv.textContent = '';
        errorDiv.style.display = 'none';
    });
}

/**
 * Validate URL format
 */
function isValidUrl(string) {
    try {
        const url = new URL(string);
        return url.protocol === 'http:' || url.protocol === 'https:';
    } catch (_) {
        return false;
    }
}

