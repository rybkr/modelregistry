"""
WSGI entry point for Elastic Beanstalk.

This file makes the Flask app discoverable by Elastic Beanstalk.
"""

# Import from the actual API server
from api_server import app

# Make the app object available for WSGI
application = app

# Health check endpoint (EB checks this)
if __name__ == "__main__":
    application.run(debug=False, host="0.0.0.0", port=8000)



