"""
WSGI entry point for Elastic Beanstalk.

This file makes the Flask app discoverable by Elastic Beanstalk.
It imports from the src directory.
"""

import sys
import os

# Get the directory where this file is located (project root)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(BASE_DIR, "src")

# Add src directory to Python path
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

# Import from the actual API server
# Note: We import after adding src to path, so imports in api_server.py will work
try:
    from api_server import app
except Exception as e:
    # Log the error to stderr so it appears in EB logs
    import traceback

    sys.stderr.write(f"ERROR: Failed to import application: {e}\n")
    sys.stderr.write(traceback.format_exc())
    raise

# Make the app object available for WSGI
application = app

# Health check endpoint (EB checks this)
if __name__ == "__main__":
    application.run(debug=False, host="0.0.0.0", port=8000)
