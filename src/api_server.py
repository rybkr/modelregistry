from flask import Flask, jsonify, request
from flask_cors import CORS
from datetime import datetime
import uuid
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from registry_models import Package
from storage import storage
from model_audit_cli.metrics_engine import compute_all_metrics
from model_audit_cli.models import Model
from model_audit_cli.resources.model_resource import ModelResource

app = Flask(__name__)
CORS(app)

DEFAULT_USERNAME = "ece30861defaultadminuser"
DEFAULT_PASSWORD = "'correcthorsebatterystaple123(!__+@**(A;DROP TABLE packages'"


@app.route('/health', methods=['GET'])
def health():
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


@app.route('/upload', methods=['POST'])
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
            uploaded_by=DEFAULT_USERNAME,
            upload_timestamp=datetime.utcnow(),
            size_bytes=len(data.get('content', '')),
            metadata=data.get('metadata', {}),
            s3_key=None
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
        query = request.args.get('query', '')
        regex = request.args.get('regex', 'false').lower() == 'true'
        
        if query:
            packages = storage.search_packages(query, use_regex=regex)
            packages = packages[offset:offset + limit]
        else:
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


@app.route('/packages/<package_id>/rate', methods=['GET'])
def rate_package(package_id):
    try:
        package = storage.get_package(package_id)
        if not package:
            return jsonify({'error': 'Package not found'}), 404
        
        url = package.metadata.get('url')
        if not url:
            return jsonify({'error': 'No URL in package metadata'}), 400
        
        model = Model(model=ModelResource(url=url))
        results = compute_all_metrics(model)
        
        scores = {}
        for name, metric in results.items():
            scores[name] = {
                'score': metric.value,
                'latency_ms': metric.latency_ms
            }
        
        return jsonify(scores), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/ingest', methods=['POST'])
def ingest_model():
    try:
        data = request.get_json()
        if not data or 'url' not in data:
            return jsonify({'error': 'URL required'}), 400
        
        url = data['url']
        
        if not url.startswith('https://huggingface.co/'):
            return jsonify({'error': 'URL must be a HuggingFace model URL'}), 400
        
        try:
            model = Model(model=ModelResource(url=url))
            results = compute_all_metrics(model)
        except Exception as e:
            return jsonify({'error': f'Failed to evaluate model: {str(e)}'}), 500
        
        non_latency_metrics = ['license', 'ramp_up_time', 'bus_factor', 
                               'dataset_and_code', 'dataset_quality', 
                               'code_quality', 'performance']
        
        for metric_name in non_latency_metrics:
            if metric_name in results:
                metric = results[metric_name]
                score = metric.value if isinstance(metric.value, (int, float)) else 0
                if score < 0.5:
                    return jsonify({
                        'error': f'Model failed threshold: {metric_name} score {score} < 0.5'
                    }), 400
        
        parts = url.rstrip('/').split('/')
        model_name = parts[-1] if parts else 'unknown'
        
        scores = {}
        for name, metric in results.items():
            scores[name] = {
                'score': metric.value,
                'latency_ms': metric.latency_ms
            }
        
        package_id = str(uuid.uuid4())
        package = Package(
            id=package_id,
            name=model_name,
            version='1.0.0',
            uploaded_by=DEFAULT_USERNAME,
            upload_timestamp=datetime.utcnow(),
            size_bytes=0,
            metadata={'url': url, 'scores': scores},
            s3_key=None
        )
        
        storage.create_package(package)
        
        return jsonify({
            'message': 'Model ingested successfully',
            'package': package.to_dict()
        }), 201
        
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
