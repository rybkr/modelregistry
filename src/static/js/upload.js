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

    // Get form data
    const name = document.getElementById('package-name').value.trim();
    const version = document.getElementById('package-version').value.trim();
    const url = document.getElementById('package-url').value.trim();
    const content = document.getElementById('package-content').value.trim();
    const metadataJson = document.getElementById('package-metadata').value.trim();

    // Validate required fields
    if (!name || !version) {
        showAlert('Package name and version are required', 'danger');
        return;
    }

    // Validate JSON metadata if provided
    let metadata = {};
    if (metadataJson) {
        const parsed = validateJSON(metadataJson);
        if (parsed === null) {
            showAlert('Invalid JSON in metadata field', 'danger');
            return;
        }
        metadata = parsed;
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
    }
}

