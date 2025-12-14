# End-to-End Selenium Tests

This directory contains comprehensive Selenium-based end-to-end tests for the Model Registry web interface.

## Test Files

### `test_packages_page.py`
Tests for the main packages listing page:
- Package listing and display
- Search functionality
- Filtering by name and version
- Regex search
- Sorting functionality
- Pagination
- Clear search functionality
- Accessibility features

### `test_upload_page.py`
Tests for the package upload page:
- Page loading
- Form field presence and validation
- Required field validation
- Form submission
- Cancel button navigation
- JSON metadata validation
- Accessibility features (ARIA labels, error messages)

### `test_ingest_page.py`
Tests for the HuggingFace model ingestion page:
- Page loading
- Form validation
- URL format validation
- Evaluation progress section
- Cancel button navigation
- Accessibility features

### `test_package_detail_page.py`
Tests for the package detail page:
- Page loading and package information display
- Action buttons (Rate, Delete)
- Metadata display
- Breadcrumb navigation
- Metrics section
- Accessibility features

### `test_health_dashboard.py`
Tests for the health dashboard:
- Status cards display
- Health details section
- Activity section and timeline
- System logs display
- Refresh buttons functionality
- Reset registry button (with warning)
- Accessibility features

### `test_navigation.py`
Tests for site-wide navigation and accessibility:
- Navbar presence on all pages
- Navbar link navigation
- Footer presence
- Skip to main content link
- Main content landmark
- Alert container
- Keyboard navigation
- Page titles
- ARIA labels on icons
- Form label associations

## Running the Tests

### Prerequisites
- Python 3.9+
- Chrome browser installed
- ChromeDriver (automatically managed by webdriver-manager)

### Run All E2E Tests
```bash
pytest test/e2e/ -v -m e2e
```

### Run Specific Test File
```bash
pytest test/e2e/test_upload_page.py -v
```

### Run with Coverage
```bash
pytest test/e2e/ -v --cov=src --cov-report=html
```

## Test Structure

All tests use the following fixtures (defined in `conftest.py`):
- `api_server`: Starts the Flask API server for testing
- `browser`: Provides a headless Chrome WebDriver instance

## Test Markers

Tests are marked with `@pytest.mark.e2e` to allow selective running:
```bash
pytest -m e2e
```

## CI/CD Integration

These tests are designed to run in CI/CD environments:
- Headless Chrome browser
- Automatic ChromeDriver management
- Server startup and teardown
- Clean registry state between tests

## Accessibility Testing

Many tests include accessibility checks:
- ARIA labels and roles
- Form label associations
- Keyboard navigation
- Screen reader compatibility
- WCAG 2.1 AA compliance features

## Notes

- Tests reset the registry state before running to ensure clean test environment
- Some tests may take longer due to waiting for JavaScript to execute
- Tests use explicit waits to handle dynamic content loading
- All tests are designed to be independent and can run in any order
