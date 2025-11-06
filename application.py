"""
WSGI entry point for Elastic Beanstalk.

This file makes the Flask app discoverable by Elastic Beanstalk.
It imports from the src directory.
"""

import sys
import os

# Add src directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Import from the actual API server
from api_server import app

# Make the app object available for WSGI
application = app

# Health check endpoint (EB checks this)
if __name__ == "__main__":
    application.run(debug=False, host="0.0.0.0", port=8000)

