"""
Inventory Service - Microservice 3
Handles product inventory lookups
"""

import time
import random
import threading
from flask import Flask, jsonify, request
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST

app = Flask(__name__)

REQUEST_COUNT = Counter('inventory_requests_total', 'Total requests', ['method', 'endpoint', 'status'])
REQUEST_LATENCY = Histogram('inventory_request_latency_seconds', 'Request latency',
                            buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0])
ERROR_RATE = Gauge('inventory_error_rate', 'Current error rate 0-1')
SERVICE_UP = Gauge('inventory_service_up', '1 if service is healthy')
STOCK_QUERIES = Counter('inventory_stock_queries_total', 'Stock queries', ['result'])
LATENCY_INJECT = Gauge('inventory_latency_injection_active', '1 if latency injection active')
MEMORY_STRESS = Gauge('inventory_memory_stress_active', '1 if memory stress active')

chaos_state = {
    'latency_injection': False,
    'error_injection': False,
    'memory_stress': False,
    'injected_latency_ms': 0,
    'injected_error_rate': 0.0,
}

SERVICE_UP.set(1)
memory_hog = []  # for memory stress simulation


@app.route('/health')
def health():
    SERVICE_UP.set(1)
    return jsonify({'status': 'healthy', 'service': 'inventory-service'}), 200


@app.route('/stock/<item_id>', methods=['GET'])
def get_stock(item_id):
    start = time.time()

    if chaos_state['latency_injection']:
        time.sleep(chaos_state['injected_latency_ms'] / 1000.0)

    if chaos_state['error_injection'] and random.random() < chaos_state['injected_error_rate']:
        REQUEST_COUNT.labels(method='GET', endpoint='/stock', status='500').inc()
        STOCK_QUERIES.labels(result='error').inc()
        REQUEST_LATENCY.observe(time.time() - start)
        ERROR_RATE.set(chaos_state['injected_error_rate'])
        return jsonify({'error': 'Database connection failed'}), 500

    time.sleep(random.uniform(0.02, 0.08))
    stock = random.randint(0, 500)
    REQUEST_COUNT.labels(method='GET', endpoint='/stock', status='200').inc()
    STOCK_QUERIES.labels(result='found' if stock > 0 else 'out_of_stock').inc()
    REQUEST_LATENCY.observe(time.time() - start)
    ERROR_RATE.set(0.01)
    return jsonify({'item_id': item_id, 'stock': stock, 'warehouse': 'US-EAST-1'}), 200


@app.route('/update', methods=['POST'])
def update_stock():
    start = time.time()
    time.sleep(random.uniform(0.03, 0.1))
    REQUEST_COUNT.labels(method='POST', endpoint='/update', status='200').inc()
    REQUEST_LATENCY.observe(time.time() - start)
    return jsonify({'status': 'updated'}), 200


@app.route('/chaos/inject', methods=['POST'])
def inject_chaos():
    data = request.get_json()
    chaos_type = data.get('type')

    if chaos_type == 'latency':
        chaos_state['latency_injection'] = True
        chaos_state['injected_latency_ms'] = data.get('latency_ms', 2500)
        LATENCY_INJECT.set(1)
        return jsonify({'injected': 'latency'}), 200
    elif chaos_type == 'error':
        chaos_state['error_injection'] = True
        chaos_state['injected_error_rate'] = data.get('error_rate', 0.4)
        return jsonify({'injected': 'error'}), 200
    elif chaos_type == 'memory':
        chaos_state['memory_stress'] = True
        MEMORY_STRESS.set(1)
        threading.Thread(target=memory_stress_worker, daemon=True).start()
        return jsonify({'injected': 'memory_stress'}), 200
    return jsonify({'error': 'unknown type'}), 400


@app.route('/chaos/recover', methods=['POST'])
def recover():
    global memory_hog
    chaos_state.update({'latency_injection': False, 'error_injection': False,
                        'memory_stress': False, 'injected_latency_ms': 0, 'injected_error_rate': 0.0})
    memory_hog = []
    LATENCY_INJECT.set(0)
    MEMORY_STRESS.set(0)
    ERROR_RATE.set(0.01)
    SERVICE_UP.set(1)
    return jsonify({'status': 'recovered', 'service': 'inventory-service'}), 200


@app.route('/metrics')
def metrics():
    return generate_latest(), 200, {'Content-Type': CONTENT_TYPE_LATEST}


@app.route('/status')
def status():
    return jsonify({'service': 'inventory-service', 'chaos_state': chaos_state}), 200


def memory_stress_worker():
    global memory_hog
    # Allocate ~50MB of memory for 30 seconds
    for _ in range(50):
        if not chaos_state['memory_stress']:
            break
        memory_hog.append(' ' * 1024 * 1024)
        time.sleep(0.5)
    time.sleep(20)
    memory_hog = []
    chaos_state['memory_stress'] = False
    MEMORY_STRESS.set(0)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5003, threaded=True)
