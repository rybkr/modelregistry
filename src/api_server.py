"""
Flask REST API server for Model Registry Phase 2.
"""

from flask import Flask, jsonify, request
from flask_cors import CORS
from datetime import datetime
import uuid
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from registry_models import Package
from storage import storage

app = Flask(__name__)
CORS(app)

DEFAULT_USERNAME = "ece30861defaultadminuser"
DEFAULT_PASSWORD = "'correcthorsebatterystaple123(!__+@**(A;DROP TABLE packages'"

@app.route('/health', methods=['GET'])
def health():
    """System health endpoint for monitoring."""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.utcnow().isoformat(),
        'packages_count': len(storage.packages)
    }), 200


@app.route('/', methods=['GET'])
def root():
    return jsonify({
        'message': 'Model Registry API v1.0',
        'status': 'running'
    }), 200


@app.route('/packages', methods=['POST'])
def upload_package():
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        required_fields = ['name', 'version']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'Missing required field: {field}'}), 400
        
        package_id = str(uuid.uuid4())
        package = Package(
            id=package_id,
            name=data['name'],
            version=data['version'],
            uploaded_by=DEFAULT_USERNAME,  # TODO: Get from auth token
            upload_timestamp=datetime.utcnow(),
            size_bytes=len(data.get('content', '')),
            metadata=data.get('metadata', {}),
            s3_key=None  # TODO: Upload to S3
        )
        
        storage.create_package(package)
        
        return jsonify({
            'message': 'Package uploaded successfully',
            'package': package.to_dict()
        }), 201
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/packages', methods=['GET'])
def list_packages():
    try:
        offset = int(request.args.get('offset', 0))
        limit = int(request.args.get('limit', 100))
        
        packages = storage.list_packages(offset=offset, limit=limit)
        
        return jsonify({
            'packages': [p.to_dict() for p in packages],
            'offset': offset,
            'limit': limit,
            'total': len(storage.packages)
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/packages/<package_id>', methods=['GET'])
def get_package(package_id):
    try:
        package = storage.get_package(package_id)
        
        if not package:
            return jsonify({'error': 'Package not found'}), 404
        
        return jsonify(package.to_dict()), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/packages/<package_id>', methods=['DELETE'])
def delete_package(package_id):
    try:
        success = storage.delete_package(package_id)
        
        if not success:
            return jsonify({'error': 'Package not found'}), 404
        
        return jsonify({'message': 'Package deleted successfully'}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/reset', methods=['DELETE'])
def reset_registry():
    try:
        storage.reset()
        return jsonify({'message': 'Registry reset successfully'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=True)
