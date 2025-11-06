/**
 * Health dashboard page functionality
 */

/**
 * Initialize the page
 */
document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('refresh-health').addEventListener('click', loadHealthData);
    document.getElementById('reset-registry').addEventListener('click', handleReset);

    // Load health data
    loadHealthData();

    // Auto-refresh every 30 seconds
    setInterval(loadHealthData, 30000);
});

/**
 * Load health data from API
 */
async function loadHealthData() {
    const refreshBtn = document.getElementById('refresh-health');
    const originalText = refreshBtn.innerHTML;
    
    refreshBtn.disabled = true;
    refreshBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span>Refreshing...';

    try {
        const health = await apiClient.getHealth();

        // Update status card
        const statusCard = document.getElementById('status-card');
        const healthStatus = document.getElementById('health-status');
        
        if (health.status === 'healthy') {
            statusCard.className = 'card text-white bg-success';
            healthStatus.textContent = 'Healthy';
        } else {
            statusCard.className = 'card text-white bg-danger';
            healthStatus.textContent = 'Unhealthy';
        }

        // Update packages count
        document.getElementById('packages-count').textContent = health.packages_count || 0;

        // Update last updated
        document.getElementById('last-updated').textContent = formatDate(health.timestamp);

        // Update health details
        const healthDetails = document.getElementById('health-details');
        healthDetails.innerHTML = `
            <dl class="row mb-0">
                <dt class="col-sm-3">Status:</dt>
                <dd class="col-sm-9">
                    <span class="badge bg-${health.status === 'healthy' ? 'success' : 'danger'}">${health.status}</span>
                </dd>
                
                <dt class="col-sm-3">Timestamp:</dt>
                <dd class="col-sm-9">${formatDate(health.timestamp)}</dd>
                
                <dt class="col-sm-3">Packages Count:</dt>
                <dd class="col-sm-9">${health.packages_count || 0}</dd>
            </dl>
        `;
    } catch (error) {
        showAlert(`Failed to load health data: ${error.message}`, 'danger');
    } finally {
        refreshBtn.disabled = false;
        refreshBtn.innerHTML = originalText;
    }
}

/**
 * Handle reset registry button click
 */
async function handleReset() {
    if (!confirm('Are you sure you want to reset the registry? This will delete ALL packages and cannot be undone.')) {
        return;
    }

    if (!confirm('This is your last chance. Are you absolutely sure?')) {
        return;
    }

    const resetBtn = document.getElementById('reset-registry');
    const originalText = resetBtn.innerHTML;
    
    resetBtn.disabled = true;
    resetBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span>Resetting...';

    try {
        await apiClient.resetRegistry();
        showAlert('Registry reset successfully!', 'success');
        
        // Reload health data and redirect to home
        setTimeout(() => {
            loadHealthData();
            window.location.href = '/';
        }, 1500);
    } catch (error) {
        showAlert(`Failed to reset registry: ${error.message}`, 'danger');
        resetBtn.disabled = false;
        resetBtn.innerHTML = originalText;
    }
}

