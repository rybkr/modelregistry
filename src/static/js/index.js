/**
 * Package listing page functionality
 */

let currentOffset = 0;
let currentLimit = 25;
let currentQuery = '';
let currentRegex = false;
let currentVersion = '';
let currentSortField = '';
let currentSortOrder = '';

/**
 * Initialize the page
 */
document.addEventListener('DOMContentLoaded', async () => {
    // Load initial parameters from URL
    const urlOffset = getUrlParameter('offset');
    const urlLimit = getUrlParameter('limit');
    const urlQuery = getUrlParameter('query');
    const urlRegex = getUrlParameter('regex');
    const urlVersion = getUrlParameter('version');
    const urlSortField = getUrlParameter('sort-field');
    const urlSortOrder = getUrlParameter('sort-order');

    if (urlOffset) currentOffset = parseInt(urlOffset, 10);
    if (urlLimit) {
        currentLimit = parseInt(urlLimit, 10);
        document.getElementById('search-limit').value = currentLimit;
    }
    if (urlQuery) {
        currentQuery = urlQuery;
        document.getElementById('search-query').value = urlQuery;
    }
    if (urlVersion) {
        currentVersion = urlVersion;
        document.getElementById('search-version').value = urlVersion;
    }
    if (urlSortField) {
      currentSortField = urlSortField;
      document.getElementById('sort-field').value = urlSortField;
    }
    if (urlSortOrder) {
      currentSortOrder = urlSortOrder;
      document.getElementById('sort-order').value = urlSortOrder;
    }
    if (urlRegex === 'true') {
        currentRegex = true;
        document.getElementById('use-regex').checked = true;
    }

    // Set up event listeners
    document.getElementById('search-form').addEventListener('submit', handleSearch);
    document.getElementById('clear-search').addEventListener('click', handleClearSearch);

    // Load packages
    await loadPackages();
});

/**
 * Handle search form submission
 */
async function handleSearch(event) {
    event.preventDefault();
    currentQuery = document.getElementById('search-query').value.trim();
    currentRegex = document.getElementById('use-regex').checked;
    currentVersion = document.getElementById('search-version').value.trim();
    currentSortField = document.getElementById('sort-field').value.trim();
    currentSortOrder = document.getElementById('sort-order').value.trim();
    currentOffset = 0;
    currentLimit = parseInt(document.getElementById('search-limit').value, 10);

    // Update URL
    setUrlParameter('offset', currentOffset);
    setUrlParameter('limit', currentLimit);
    setUrlParameter('version', currentVersion);
    if (currentQuery) {
        setUrlParameter('query', currentQuery);
    } else {
        removeUrlParameter('query');
    }
    if (currentSortField) {
        setUrlParameter('sort-field', currentSortField);
    } else {
        removeUrlParameter('sort-field');
    }
    if (currentSortOrder) {
        setUrlParameter('sort-order', currentSortOrder);
    } else {
        removeUrlParameter('sort-order');
    }
    if (currentRegex) {
        setUrlParameter('regex', 'true');
    } else {
        removeUrlParameter('regex');
    }

    await loadPackages();
}

/**
 * Handle clear search
 */
async function handleClearSearch() {
    document.getElementById('search-query').value = '';
    document.getElementById('use-regex').checked = false;
    document.getElementById('search-version').value = '';
    document.getElementById('sort-field').value = '';
    document.getElementById('sort-order').value = '';

    currentQuery = '';
    currentRegex = false;
    currentOffset = 0;
    currentVersion = '';
    currentSortField = '';
    currentSortOrder = '';

    // Clear URL parameters
    removeUrlParameter('query');
    removeUrlParameter('regex');
    removeUrlParameter('offset');
    removeUrlParameter('version');
    removeUrlParamter('sort-field');
    removeUrlParameter('sort-order');

    await loadPackages();
}

/**
 * Load packages from API
 */
async function loadPackages() {
    const loadingIndicator = document.getElementById('loading-indicator');
    const packagesContainer = document.getElementById('packages-container');
    const paginationContainer = document.getElementById('pagination-container');

    loadingIndicator.style.display = 'block';
    packagesContainer.innerHTML = '';

    try {
        const response = await apiClient.listPackages({
            offset: currentOffset,
            limit: currentLimit,
            query: currentQuery,
            regex: currentRegex,
            version: currentVersion,
            sortField: currentSortField,
            sortOrder: currentSortOrder,
        });

        loadingIndicator.style.display = 'none';

        if (response.packages && response.packages.length > 0) {
            renderPackages(response.packages);
            renderPagination(response.total, response.offset, response.limit);
        } else {
            packagesContainer.innerHTML = `
                <div class="card">
                    <div class="card-body">
                        <p class="text-muted text-center py-5">
                            ${currentQuery ? 'No packages found matching your search.' : 'No packages found. Upload or ingest a model to get started.'}
                        </p>
                    </div>
                </div>
            `;
            paginationContainer.style.display = 'none';
        }
    } catch (error) {
        loadingIndicator.style.display = 'none';
        showAlert(`Failed to load packages: ${error.message}`, 'danger');
        packagesContainer.innerHTML = `
            <div class="card">
                <div class="card-body">
                    <p class="text-danger text-center py-5">Error loading packages. Please try again.</p>
                </div>
            </div>
        `;
    }
}

/**
 * Render packages list
 */
function renderPackages(packages) {
    const container = document.getElementById('packages-container');

    const packagesHtml = packages.map(pkg => {
        const uploadDate = formatDate(pkg.upload_timestamp);
        const size = formatBytes(pkg.size_bytes);
        const url = pkg.metadata?.url || '#';
        const hasUrl = pkg.metadata?.url;

        return `
            <div class="card mb-3">
                <div class="card-body">
                    <div class="d-flex justify-content-between align-items-start">
                        <div class="flex-grow-1">
                            <h5 class="card-title">
                                <a href="/packages/${pkg.id}" class="text-decoration-none">${escapeHtml(pkg.name)}</a>
                            </h5>
                            <p class="card-text text-muted mb-2">
                                <small>
                                    <strong>Version:</strong> ${escapeHtml(pkg.version)} |
                                    <strong>Size:</strong> ${size} |
                                    <strong>Uploaded:</strong> ${uploadDate}
                                </small>
                            </p>
                            ${hasUrl ? `
                                <p class="card-text mb-0">
                                    <a href="${url}" target="_blank" rel="noopener noreferrer" class="text-decoration-none">
                                        <i class="bi bi-box-arrow-up-right me-1" aria-hidden="true"></i>View Source
                                    </a>
                                </p>
                            ` : ''}
                        </div>
                        <div class="ms-3">
                            <a href="/packages/${pkg.id}" class="btn btn-sm btn-outline-primary" aria-label="View details for ${escapeHtml(pkg.name)}">
                                <i class="bi bi-eye me-1" aria-hidden="true"></i>View
                            </a>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }).join('');

    container.innerHTML = packagesHtml;
}

/**
 * Render pagination controls
 */
function renderPagination(total, offset, limit) {
    const container = document.getElementById('pagination-container');
    if (total <= limit) {
        container.style.display = 'none';
        return;
    }

    container.style.display = 'block';
    const totalPages = Math.ceil(total / limit);
    const currentPage = Math.floor(offset / limit) + 1;

    let paginationHtml = '';

    // Previous button
    if (currentPage > 1) {
        const prevOffset = offset - limit;
        paginationHtml += `
            <li class="page-item">
                <a class="page-link" href="#" data-offset="${prevOffset}" aria-label="Previous page">
                    <span aria-hidden="true">&laquo;</span>
                </a>
            </li>
        `;
    } else {
        paginationHtml += `
            <li class="page-item disabled">
                <span class="page-link" aria-hidden="true">&laquo;</span>
            </li>
        `;
    }

    // Page numbers
    const maxPagesToShow = 5;
    let startPage = Math.max(1, currentPage - Math.floor(maxPagesToShow / 2));
    let endPage = Math.min(totalPages, startPage + maxPagesToShow - 1);
    if (endPage - startPage < maxPagesToShow - 1) {
        startPage = Math.max(1, endPage - maxPagesToShow + 1);
    }

    for (let i = startPage; i <= endPage; i++) {
        const pageOffset = (i - 1) * limit;
        if (i === currentPage) {
            paginationHtml += `
                <li class="page-item active" aria-current="page">
                    <span class="page-link">${i}</span>
                </li>
            `;
        } else {
            paginationHtml += `
                <li class="page-item">
                    <a class="page-link" href="#" data-offset="${pageOffset}">${i}</a>
                </li>
            `;
        }
    }

    // Next button
    if (currentPage < totalPages) {
        const nextOffset = offset + limit;
        paginationHtml += `
            <li class="page-item">
                <a class="page-link" href="#" data-offset="${nextOffset}" aria-label="Next page">
                    <span aria-hidden="true">&raquo;</span>
                </a>
            </li>
        `;
    } else {
        paginationHtml += `
            <li class="page-item disabled">
                <span class="page-link" aria-hidden="true">&raquo;</span>
            </li>
        `;
    }

    container.querySelector('.pagination').innerHTML = paginationHtml;

    // Add event listeners to pagination links
    container.querySelectorAll('.page-link[data-offset]').forEach(link => {
        link.addEventListener('click', async (e) => {
            e.preventDefault();
            currentOffset = parseInt(link.dataset.offset, 10);
            setUrlParameter('offset', currentOffset);
            await loadPackages();
            window.scrollTo({ top: 0, behavior: 'smooth' });
        });
    });
}

/**
 * Escape HTML to prevent XSS
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
