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
    const progressBar = progressCard.querySelector('.progress-bar');
    const statusText = document.getElementById('evaluation-status');

    // Get URL
    const url = document.getElementById('model-url').value.trim();

    // Validate URL
    if (!url) {
        showAlert('HuggingFace model URL is required', 'danger');
        return;
    }

    if (!url.startsWith('https://huggingface.co/')) {
        showAlert('URL must be a HuggingFace model URL (must start with https://huggingface.co/)', 'danger');
        return;
    }

    // Disable submit button and show progress
    submitBtn.disabled = true;
    submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span>Ingesting...';
    progressCard.style.display = 'block';
    progressBar.style.width = '0%';
    statusText.textContent = 'Evaluating model metrics...';

    try {
        // Simulate progress updates
        const progressInterval = setInterval(() => {
            const currentWidth = parseInt(progressBar.style.width) || 0;
            if (currentWidth < 90) {
                progressBar.style.width = `${currentWidth + 10}%`;
            }
        }, 500);

        const response = await apiClient.ingestModel(url);

        clearInterval(progressInterval);
        progressBar.style.width = '100%';
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
    }
}

