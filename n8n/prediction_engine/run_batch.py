#!/usr/bin/env python3
"""Read JSON from stdin, write to file, and run predict.py."""
import sys, json, subprocess

data = sys.stdin.buffer.read().decode('utf-8')
if not data.strip():
    print("Error: No input received", file=sys.stderr)
    sys.exit(1)

with open('/tmp/predict_input.json', 'w', encoding='utf-8') as f:
    f.write(data)

result = subprocess.run(
    ['python3', '/prediction-engine/predict.py', '/tmp/predict_input.json'],
    capture_output=True, timeout=120
)

sys.stdout.buffer.write(result.stdout)
sys.stderr.buffer.write(result.stderr)
sys.exit(result.returncode)
