"""
WSGI entry point for Elastic Beanstalk.

This file makes the Flask app discoverable by Elastic Beanstalk.
"""

import os

# Import from the actual API server
from api_server import app

# Make the app object available for WSGI
application = app

# Health check endpoint (EB checks this)
if __name__ == "__main__":
    # Read port from environment variable (AWS EB sets this) or default to 8000
    port = int(os.environ.get("PORT", 8000))
    application.run(debug=False, host="0.0.0.0", port=port)
