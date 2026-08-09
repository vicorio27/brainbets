from flask import Flask, request, jsonify
import os
import json
from datetime import datetime

app = Flask(__name__)
STORAGE_PATH = "/storage"

@app.route('/api/v1/write-file', methods=['POST'])
def write_file():
    try:
        data = request.get_json()
        filepath = data.get('filepath')
        content = data.get('content')
        
        if not filepath or not content:
            return jsonify({'error': 'filepath and content required'}), 400
        
        # Ensure directory exists
        directory = os.path.dirname(filepath)
        os.makedirs(directory, exist_ok=True)
        
        # Write file
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        
        return jsonify({'success': True, 'filepath': filepath})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'healthy'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
