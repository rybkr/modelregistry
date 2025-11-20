/**
 * Ingest model page functionality
 */

/**
 * Initialize the page
 */
document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('ingest-form').addEventListener('submit', handleIngest);
});

/**
 * Handle ingest form submission
 */
async function handleIngest(event) {
    event.preventDefault();

    const form = event.target;
    const submitBtn = form.querySelector('button[type="submit"]');
    const originalText = submitBtn.innerHTML;
    const progressCard = document.getElementById('evaluation-progress');
    const progressBarContainer = progressCard.querySelector('.progress');
    const progressBar = progressCard.querySelector('.progress-bar');
    const statusText = document.getElementById('evaluation-status');
    const urlInput = document.getElementById('model-url');

    // Clear previous errors
    clearIngestErrors();

    // Get URL
    const url = urlInput.value.trim();

    let hasErrors = false;

    // Validate URL
    if (!url) {
        showFieldError('model-url', 'HuggingFace model URL is required');
        hasErrors = true;
    } else if (!url.startsWith('https://huggingface.co/')) {
        showFieldError('model-url', 'URL must be a HuggingFace model URL (must start with https://huggingface.co/)');
        hasErrors = true;
    }

    if (hasErrors) {
        urlInput.focus();
        return;
    }

    // Disable submit button and show progress
    submitBtn.disabled = true;
    submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span>Ingesting...';
    submitBtn.setAttribute('aria-busy', 'true');
    progressCard.style.display = 'block';
    progressBar.style.width = '0%';
    progressBarContainer.setAttribute('aria-valuenow', '0');
    statusText.textContent = 'Evaluating model metrics...';

    try {
        // Simulate progress updates
        const progressInterval = setInterval(() => {
            const currentWidth = parseInt(progressBar.style.width) || 0;
            if (currentWidth < 90) {
                const newWidth = currentWidth + 10;
                progressBar.style.width = `${newWidth}%`;
                progressBarContainer.setAttribute('aria-valuenow', newWidth.toString());
            }
        }, 500);

        const response = await apiClient.ingestModel(url);

        clearInterval(progressInterval);
        progressBar.style.width = '100%';
        progressBarContainer.setAttribute('aria-valuenow', '100');
        statusText.textContent = 'Model ingested successfully!';

        showAlert('Model ingested successfully!', 'success');
        
        // Redirect to package detail page
        setTimeout(() => {
            window.location.href = `/packages/${response.package.id}`;
        }, 1500);
    } catch (error) {
        progressCard.style.display = 'none';
        showAlert(`Failed to ingest model: ${error.message}`, 'danger');
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
function clearIngestErrors() {
    const form = document.getElementById('ingest-form');
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

