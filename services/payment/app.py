"""
Payment Service - Microservice 2
Handles payment processing
"""

import time
import random
import threading
from flask import Flask, jsonify, request
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST

app = Flask(__name__)

REQUEST_COUNT = Counter('payment_requests_total', 'Total requests', ['method', 'endpoint', 'status'])
REQUEST_LATENCY = Histogram('payment_request_latency_seconds', 'Request latency',
                            buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0])
ERROR_RATE = Gauge('payment_error_rate', 'Current error rate 0-1')
SERVICE_UP = Gauge('payment_service_up', '1 if service is healthy')
TRANSACTIONS = Counter('payment_transactions_total', 'Total transactions', ['status'])
LATENCY_INJECT = Gauge('payment_latency_injection_active', '1 if latency injection active')
CPU_STRESS = Gauge('payment_cpu_stress_active', '1 if CPU stress active')

chaos_state = {
    'latency_injection': False,
    'error_injection': False,
    'cpu_stress': False,
    'injected_latency_ms': 0,
    'injected_error_rate': 0.0,
}

SERVICE_UP.set(1)


@app.route('/health')
def health():
    SERVICE_UP.set(1)
    return jsonify({'status': 'healthy', 'service': 'payment-service'}), 200


@app.route('/pay', methods=['GET', 'POST'])
def pay():
    start = time.time()

    if chaos_state['latency_injection']:
        time.sleep(chaos_state['injected_latency_ms'] / 1000.0)

    if chaos_state['error_injection'] and random.random() < chaos_state['injected_error_rate']:
        REQUEST_COUNT.labels(method='POST', endpoint='/pay', status='500').inc()
        TRANSACTIONS.labels(status='failed').inc()
        REQUEST_LATENCY.observe(time.time() - start)
        ERROR_RATE.set(chaos_state['injected_error_rate'])
        return jsonify({'error': 'Payment processing failed'}), 500

    time.sleep(random.uniform(0.05, 0.15))
    REQUEST_COUNT.labels(method='POST', endpoint='/pay', status='200').inc()
    TRANSACTIONS.labels(status='success').inc()
    REQUEST_LATENCY.observe(time.time() - start)
    ERROR_RATE.set(0.02)
    return jsonify({'status': 'payment_processed', 'transaction_id': f'TXN-{random.randint(10000,99999)}'}), 200


@app.route('/refund', methods=['GET', 'POST'])
def refund():
    start = time.time()
    time.sleep(random.uniform(0.1, 0.3))
    REQUEST_COUNT.labels(method='POST', endpoint='/refund', status='200').inc()
    TRANSACTIONS.labels(status='refunded').inc()
    REQUEST_LATENCY.observe(time.time() - start)
    return jsonify({'status': 'refund_processed'}), 200


@app.route('/chaos/inject', methods=['POST'])
def inject_chaos():
    data = request.get_json()
    chaos_type = data.get('type')

    if chaos_type == 'latency':
        chaos_state['latency_injection'] = True
        chaos_state['injected_latency_ms'] = data.get('latency_ms', 3000)
        LATENCY_INJECT.set(1)
        return jsonify({'injected': 'latency'}), 200
    elif chaos_type == 'error':
        chaos_state['error_injection'] = True
        chaos_state['injected_error_rate'] = data.get('error_rate', 0.6)
        return jsonify({'injected': 'error'}), 200
    elif chaos_type == 'cpu':
        chaos_state['cpu_stress'] = True
        CPU_STRESS.set(1)
        threading.Thread(target=cpu_stress_worker, daemon=True).start()
        return jsonify({'injected': 'cpu_stress'}), 200
    return jsonify({'error': 'unknown type'}), 400


@app.route('/chaos/recover', methods=['POST'])
def recover():
    chaos_state.update({'latency_injection': False, 'error_injection': False,
                        'cpu_stress': False, 'injected_latency_ms': 0, 'injected_error_rate': 0.0})
    LATENCY_INJECT.set(0)
    CPU_STRESS.set(0)
    ERROR_RATE.set(0.02)
    SERVICE_UP.set(1)
    return jsonify({'status': 'recovered', 'service': 'payment-service'}), 200


@app.route('/metrics')
def metrics():
    return generate_latest(), 200, {'Content-Type': CONTENT_TYPE_LATEST}


@app.route('/status')
def status():
    return jsonify({'service': 'payment-service', 'chaos_state': chaos_state}), 200


def cpu_stress_worker():
    end = time.time() + 30
    while time.time() < end and chaos_state['cpu_stress']:
        _ = sum(i * i for i in range(10000))
    chaos_state['cpu_stress'] = False
    CPU_STRESS.set(0)


def simulate_traffic():
    while True:
        # simulate baseline transactions
        TRANSACTIONS.labels(status='success').inc(random.randint(1, 5))
        time.sleep(random.uniform(3, 8))


if __name__ == '__main__':
    threading.Thread(target=simulate_traffic, daemon=True).start()
    app.run(host='0.0.0.0', port=5002, threaded=True)
