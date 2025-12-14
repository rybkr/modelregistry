/**
 * Package detail page functionality
 */

let currentPackageId = null;
let currentArtifactType = 'model'; // Default to 'model' for backward compatibility

/**
 * Initialize the page
 */
document.addEventListener('DOMContentLoaded', async () => {
    // Get package ID from data attribute or URL
    const rowElement = document.querySelector('.row[data-package-id]');
    if (rowElement && rowElement.dataset.packageId) {
        currentPackageId = rowElement.dataset.packageId;
    } else {
        // Fallback to URL parsing
        const pathParts = window.location.pathname.split('/');
        currentPackageId = pathParts[pathParts.length - 1];
    }

    if (!currentPackageId || currentPackageId === 'packages') {
        showAlert('Invalid package ID', 'danger');
        return;
    }

    // Set up event listeners
    document.getElementById('rate-btn').addEventListener('click', handleRate);
    document.getElementById('delete-btn').addEventListener('click', handleDelete);

    // Load package details
    await loadPackageDetails();
});

/**
 * Load package details from API
 */
async function loadPackageDetails() {
    const loadingIndicator = document.getElementById('loading-indicator');
    const packageDetails = document.getElementById('package-details');

    loadingIndicator.style.display = 'block';
    packageDetails.style.display = 'none';

    try {
        const pkg = await apiClient.getPackage(currentPackageId);

        loadingIndicator.style.display = 'none';
        packageDetails.style.display = 'block';

        // Store artifact type for deletion
        currentArtifactType = pkg.artifact_type || 'model';

        // Populate package information
        document.getElementById('package-name').textContent = pkg.name;
        document.getElementById('package-id').textContent = pkg.id;
        document.getElementById('package-version').textContent = pkg.version;
        document.getElementById('package-uploaded-by').textContent = pkg.uploaded_by;
        document.getElementById('package-upload-date').textContent = formatDate(pkg.upload_timestamp);
        document.getElementById('package-size').textContent = formatBytes(pkg.size_bytes);

        // URL
        const urlElement = document.getElementById('package-url');
        if (pkg.metadata?.url) {
            urlElement.href = pkg.metadata.url;
            urlElement.textContent = pkg.metadata.url;
        } else {
            urlElement.href = '#';
            urlElement.textContent = 'N/A';
        }

        // S3 Key
        document.getElementById('package-s3-key').textContent = pkg.s3_key || 'N/A';

        // Metadata
        document.getElementById('package-metadata').textContent = JSON.stringify(pkg.metadata, null, 2);

        // If package already has scores in metadata, display them
        if (pkg.metadata?.scores) {
            displayMetrics(pkg.metadata.scores);
        }
    } catch (error) {
        loadingIndicator.style.display = 'none';
        showAlert(`Failed to load package: ${error.message}`, 'danger');
    }
}

/**
 * Handle rate button click
 */
async function handleRate() {
    const rateBtn = document.getElementById('rate-btn');
    const originalText = rateBtn.innerHTML;

    rateBtn.disabled = true;
    rateBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span>Rating...';
    rateBtn.setAttribute('aria-busy', 'true');

    try {
        const metrics = await apiClient.ratePackage(currentPackageId);
        displayMetrics(metrics);
        showAlert('Package rated successfully!', 'success');
    } catch (error) {
        showAlert(`Failed to rate package: ${error.message}`, 'danger');
    } finally {
        rateBtn.disabled = false;
        rateBtn.innerHTML = originalText;
        rateBtn.removeAttribute('aria-busy');
    }
}

/**
 * Display metrics
 */
function displayMetrics(metrics) {
    const metricsCard = document.getElementById('metrics-card');
    const metricsContent = document.getElementById('metrics-content');

    if (!metrics || Object.keys(metrics).length === 0) {
        metricsCard.style.display = 'none';
        return;
    }

    metricsCard.style.display = 'block';

    // Sort metrics by name
    const sortedMetrics = Object.entries(metrics).sort((a, b) => a[0].localeCompare(b[0]));

    const metricsHtml = `
        <div class="row">
            ${sortedMetrics.map(([name, data]) => {
        const score = data.score !== undefined ? data.score : data;
        const latency = data.latency_ms !== undefined ? data.latency_ms : null;
        const scoreInfo = formatScore(score);

        return `
                    <div class="col-md-6 mb-3">
                        <div class="card h-100">
                            <div class="card-body">
                                <h6 class="card-title text-capitalize">${escapeHtml(name.replace(/_/g, ' '))}</h6>
                                <p class="card-text">
                                    <span class="h4 ${scoreInfo.class}">${scoreInfo.text}</span>
                                    ${latency !== null ? `<small class="text-muted d-block">Latency: ${latency.toFixed(2)}ms</small>` : ''}
                                </p>
                            </div>
                        </div>
                    </div>
                `;
    }).join('')}
        </div>
    `;

    metricsContent.innerHTML = metricsHtml;
}

/**
 * Handle delete button click
 */
async function handleDelete() {
    const confirmed = await showConfirmDialog(
        'Are you sure you want to delete this package? This action cannot be undone.',
        'Delete Package'
    );

    if (!confirmed) {
        return;
    }

    const deleteBtn = document.getElementById('delete-btn');
    const originalText = deleteBtn.innerHTML;

    deleteBtn.disabled = true;
    deleteBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span>Deleting...';
    deleteBtn.setAttribute('aria-busy', 'true');

    try {
        await apiClient.deletePackage(currentPackageId, currentArtifactType);
        showAlert('Package deleted successfully!', 'success');
        setTimeout(() => {
            window.location.href = '/';
        }, 1500);
    } catch (error) {
        showAlert(`Failed to delete package: ${error.message}`, 'danger');
        deleteBtn.disabled = false;
        deleteBtn.innerHTML = originalText;
        deleteBtn.removeAttribute('aria-busy');
    }
}

/**
 * Escape HTML to prevent XSS
 */
function escapeHtml(text) {
    if (typeof text !== 'string') return text;
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

