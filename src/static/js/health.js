/**
 * Health dashboard page functionality
 */

/**
 * Initialize the page
 */
document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('refresh-health').addEventListener('click', () => loadHealthData(true));
    document.getElementById('reset-registry').addEventListener('click', handleReset);

    const refreshActivityBtn = document.getElementById('refresh-activity');
    if (refreshActivityBtn) {
        refreshActivityBtn.addEventListener('click', () => loadActivityData(true));
    }

    const refreshLogsBtn = document.getElementById('refresh-logs');
    if (refreshLogsBtn) {
        refreshLogsBtn.addEventListener('click', () => loadLogData(true));
    }

    // Initial load
    loadHealthData(true);
    loadActivityData(true);
    loadLogData(true);

    // Auto-refresh cadence
    setInterval(() => loadHealthData(false), 30000);
    setInterval(() => {
        loadActivityData(false);
        loadLogData(false);
    }, 60000);
});

/**
 * Load health data from API
 */
async function loadHealthData(showSpinner = false) {
    const refreshBtn = document.getElementById('refresh-health');
    let originalText = '';

    if (showSpinner) {
        originalText = refreshBtn.innerHTML;
        refreshBtn.disabled = true;
        refreshBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span>Refreshing...';
    }

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
        if (showSpinner) {
            refreshBtn.disabled = false;
            refreshBtn.innerHTML = originalText;
        }
    }
}

/**
 * Load activity summary and timeline
 */
async function loadActivityData(showSpinner = false) {
    const refreshBtn = document.getElementById('refresh-activity');
    const summaryContainer = document.getElementById('activity-summary');
    const eventsBody = document.getElementById('activity-events-body');
    const windowLabel = document.getElementById('activity-window-label');

    if (!summaryContainer || !eventsBody) {
        return;
    }

    let originalText = '';
    if (showSpinner && refreshBtn) {
        originalText = refreshBtn.innerHTML;
        refreshBtn.disabled = true;
        refreshBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span>Refreshing...';
    }

    try {
        const activity = await apiClient.getHealthActivity({ window: 60, limit: 25 });

        windowLabel.textContent = `Window: ${formatDate(activity.window_start)} – ${formatDate(activity.window_end)}`;

        const counts = activity.counts || {};
        const summaryHtml = Object.entries(counts)
            .map(([key, value]) => {
                const label = key === 'other' ? 'Other' : key.replace(/_/g, ' ');
                return `
                    <div class="col-md-6 col-lg-4 mb-3">
                        <div class="border rounded p-3 bg-light h-100">
                            <p class="text-muted mb-1 text-uppercase small">${label}</p>
                            <p class="h4 mb-0">${value}</p>
                        </div>
                    </div>
                `;
            })
            .join('');
        summaryContainer.innerHTML = summaryHtml || '<p class="text-muted mb-0">No activity recorded in the last hour.</p>';

        const events = activity.events || [];
        if (events.length === 0) {
            eventsBody.innerHTML = `
                <tr>
                    <td colspan="4" class="text-muted text-center">No recent activity to display.</td>
                </tr>
            `;
        } else {
            eventsBody.innerHTML = events
                .map((event) => {
                    const packageLabel = event.package
                        ? `${event.package.name || 'unknown'} (${event.package.version || 'n/a'})`
                        : '—';
                    return `
                        <tr>
                            <td class="text-nowrap">${formatDate(event.timestamp)}</td>
                            <td><span class="badge bg-secondary text-uppercase">${event.type.replace(/_/g, ' ')}</span></td>
                            <td>${packageLabel}</td>
                            <td>${event.message}</td>
                        </tr>
                    `;
                })
                .join('');
        }
    } catch (error) {
        showAlert(`Failed to load activity data: ${error.message}`, 'danger');
    } finally {
        if (showSpinner && refreshBtn) {
            refreshBtn.disabled = false;
            refreshBtn.innerHTML = originalText;
        }
    }
}

/**
 * Load recent log entries
 */
async function loadLogData(showSpinner = false) {
    const refreshBtn = document.getElementById('refresh-logs');
    const logsContainer = document.getElementById('logs-body');

    if (!logsContainer) {
        return;
    }

    let originalText = '';
    if (showSpinner && refreshBtn) {
        originalText = refreshBtn.innerHTML;
        refreshBtn.disabled = true;
        refreshBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span>Refreshing...';
    }

    try {
        const { entries } = await apiClient.getHealthLogs({ limit: 100 });

        if (!entries || entries.length === 0) {
            logsContainer.innerHTML = '<p class="text-muted mb-0">No log entries available.</p>';
        } else {
            logsContainer.innerHTML = entries
                .map((entry) => {
                    const levelBadgeClass = entry.level === 'ERROR' ? 'bg-danger' :
                        entry.level === 'WARNING' ? 'bg-warning text-dark' : 'bg-secondary';
                    return `
                        <div class="log-entry border-bottom py-2">
                            <div class="d-flex justify-content-between align-items-center">
                                <span class="text-muted small">${formatDate(entry.timestamp)}</span>
                                <span class="badge ${levelBadgeClass}">${entry.level}</span>
                            </div>
                            <div class="mt-1">
                                <code class="text-wrap">${entry.message}</code>
                            </div>
                        </div>
                    `;
                })
                .join('');
        }
    } catch (error) {
        showAlert(`Failed to load system logs: ${error.message}`, 'danger');
    } finally {
        if (showSpinner && refreshBtn) {
            refreshBtn.disabled = false;
            refreshBtn.innerHTML = originalText;
        }
    }
}

/**
 * Handle reset registry button click
 */
async function handleReset() {
    const firstConfirm = await showConfirmDialog(
        'Are you sure you want to reset the registry? This will delete ALL packages and cannot be undone.',
        'Reset Registry - Warning'
    );
    
    if (!firstConfirm) {
        return;
    }

    const secondConfirm = await showConfirmDialog(
        'This is your last chance. Are you absolutely sure you want to delete ALL packages?',
        'Reset Registry - Final Confirmation'
    );
    
    if (!secondConfirm) {
        return;
    }

    const resetBtn = document.getElementById('reset-registry');
    const originalText = resetBtn.innerHTML;
    
    resetBtn.disabled = true;
    resetBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span>Resetting...';
    resetBtn.setAttribute('aria-busy', 'true');

    try {
        await apiClient.resetRegistry();
        showAlert('Registry reset successfully!', 'success');
        
        // Reload health data and redirect to home
        setTimeout(() => {
            loadHealthData(true);
            loadActivityData(true);
            loadLogData(true);
            window.location.href = '/';
        }, 1500);
    } catch (error) {
        showAlert(`Failed to reset registry: ${error.message}`, 'danger');
        resetBtn.disabled = false;
        resetBtn.innerHTML = originalText;
        resetBtn.removeAttribute('aria-busy');
    }
}

