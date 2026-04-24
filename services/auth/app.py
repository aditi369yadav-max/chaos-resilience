"""
Auth Service - Microservice 1
Handles authentication requests
Exposes Prometheus metrics for SLO tracking
"""

import time
import random
import os
import threading
from flask import Flask, jsonify
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST

app = Flask(__name__)

# ─────────────────────────────────────────
#  PROMETHEUS METRICS
# ─────────────────────────────────────────
REQUEST_COUNT = Counter('auth_requests_total', 'Total requests', ['method', 'endpoint', 'status'])
REQUEST_LATENCY = Histogram('auth_request_latency_seconds', 'Request latency',
                            buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0])
ERROR_RATE = Gauge('auth_error_rate', 'Current error rate 0-1')
SERVICE_UP = Gauge('auth_service_up', '1 if service is healthy')
ACTIVE_USERS = Gauge('auth_active_users', 'Active authenticated users')
CPU_STRESS = Gauge('auth_cpu_stress_active', '1 if CPU stress is active')
LATENCY_INJECT = Gauge('auth_latency_injection_active', '1 if latency injection is active')

# ─────────────────────────────────────────
#  CHAOS STATE
# ─────────────────────────────────────────
chaos_state = {
    'cpu_stress': False,
    'latency_injection': False,
    'error_injection': False,
    'injected_latency_ms': 0,
    'injected_error_rate': 0.0,
}

SERVICE_UP.set(1)
ACTIVE_USERS.set(random.randint(80, 150))

# ─────────────────────────────────────────
#  ROUTES
# ─────────────────────────────────────────

@app.route('/health')
def health():
    SERVICE_UP.set(1)
    return jsonify({'status': 'healthy', 'service': 'auth-service'}), 200

@app.route('/login', methods=['GET', 'POST'])
def login():
    start = time.time()

    # Simulate injected latency
    if chaos_state['latency_injection']:
        time.sleep(chaos_state['injected_latency_ms'] / 1000.0)

    # Simulate injected errors
    if chaos_state['error_injection'] and random.random() < chaos_state['injected_error_rate']:
        REQUEST_COUNT.labels(method='POST', endpoint='/login', status='500').inc()
        REQUEST_LATENCY.observe(time.time() - start)
        ERROR_RATE.set(chaos_state['injected_error_rate'])
        return jsonify({'error': 'Internal Server Error'}), 500

    # Normal processing with small baseline noise
    time.sleep(random.uniform(0.01, 0.05))
    REQUEST_COUNT.labels(method='POST', endpoint='/login', status='200').inc()
    REQUEST_LATENCY.observe(time.time() - start)
    ERROR_RATE.set(0.01)
    return jsonify({'status': 'authenticated', 'token': 'mock-jwt-token'}), 200

@app.route('/validate', methods=['GET'])
def validate():
    start = time.time()
    if chaos_state['latency_injection']:
        time.sleep(chaos_state['injected_latency_ms'] / 1000.0)
    time.sleep(random.uniform(0.005, 0.02))
    REQUEST_COUNT.labels(method='GET', endpoint='/validate', status='200').inc()
    REQUEST_LATENCY.observe(time.time() - start)
    return jsonify({'valid': True}), 200

@app.route('/chaos/inject', methods=['POST'])
def inject_chaos():
    """Called by chaos engine to inject failures"""
    import json
    from flask import request
    data = request.get_json()
    chaos_type = data.get('type')

    if chaos_type == 'latency':
        chaos_state['latency_injection'] = True
        chaos_state['injected_latency_ms'] = data.get('latency_ms', 2000)
        LATENCY_INJECT.set(1)
        return jsonify({'injected': 'latency', 'ms': chaos_state['injected_latency_ms']}), 200

    elif chaos_type == 'error':
        chaos_state['error_injection'] = True
        chaos_state['injected_error_rate'] = data.get('error_rate', 0.5)
        return jsonify({'injected': 'error', 'rate': chaos_state['injected_error_rate']}), 200

    elif chaos_type == 'cpu':
        chaos_state['cpu_stress'] = True
        CPU_STRESS.set(1)
        threading.Thread(target=cpu_stress_worker, daemon=True).start()
        return jsonify({'injected': 'cpu_stress'}), 200

    return jsonify({'error': 'unknown chaos type'}), 400

@app.route('/chaos/recover', methods=['POST'])
def recover():
    """Called by runbook automator to recover from chaos"""
    chaos_state['latency_injection'] = False
    chaos_state['error_injection'] = False
    chaos_state['cpu_stress'] = False
    chaos_state['injected_latency_ms'] = 0
    chaos_state['injected_error_rate'] = 0.0
    LATENCY_INJECT.set(0)
    CPU_STRESS.set(0)
    ERROR_RATE.set(0.01)
    SERVICE_UP.set(1)
    return jsonify({'status': 'recovered', 'service': 'auth-service'}), 200

@app.route('/metrics')
def metrics():
    return generate_latest(), 200, {'Content-Type': CONTENT_TYPE_LATEST}

@app.route('/status')
def status():
    return jsonify({
        'service': 'auth-service',
        'chaos_active': any(chaos_state.values()),
        'chaos_state': chaos_state
    }), 200

# ─────────────────────────────────────────
#  BACKGROUND METRIC SIMULATOR
# ─────────────────────────────────────────

def simulate_traffic():
    """Continuously generate background traffic metrics"""
    while True:
        # Simulate varying active users
        current = ACTIVE_USERS._value.get()
        delta = random.randint(-5, 5)
        ACTIVE_USERS.set(max(10, min(300, current + delta)))
        time.sleep(5)

def cpu_stress_worker():
    """Burn CPU for 30 seconds to simulate CPU stress"""
    end = time.time() + 30
    while time.time() < end and chaos_state['cpu_stress']:
        _ = sum(i * i for i in range(10000))
    chaos_state['cpu_stress'] = False
    CPU_STRESS.set(0)

if __name__ == '__main__':
    threading.Thread(target=simulate_traffic, daemon=True).start()
    app.run(host='0.0.0.0', port=5001, threaded=True)
