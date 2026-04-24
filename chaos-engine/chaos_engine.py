"""
Chaos Engine
Automatically injects failures into microservices every ~2 minutes.
Simulates real-world failure scenarios:
  - Latency injection
  - Error rate injection
  - CPU stress
  - Memory leak
  - Service cascading failures

Exposes its own metrics so Prometheus can track chaos events.
"""

import time
import random
import requests
import threading
from datetime import datetime
from prometheus_client import start_http_server, Counter, Gauge, Info

# ─────────────────────────────────────────
#  METRICS
# ─────────────────────────────────────────
chaos_events_total = Counter('chaos_events_total', 'Total chaos events injected', ['service', 'chaos_type'])
chaos_active = Gauge('chaos_active', 'Whether chaos is currently active', ['service'])
chaos_duration_seconds = Gauge('chaos_duration_seconds', 'Duration of last chaos event', ['service'])
recovery_time_seconds = Gauge('recovery_time_seconds', 'Time to recover from chaos', ['service'])
chaos_engine_info = Info('chaos_engine', 'Chaos engine metadata')

# ─────────────────────────────────────────
#  SERVICE REGISTRY
# ─────────────────────────────────────────
SERVICES = {
    'auth-service':      'http://auth-service:5001',
    'payment-service':   'http://payment-service:5002',
    'inventory-service': 'http://inventory-service:5003',
}

# ─────────────────────────────────────────
#  CHAOS SCENARIOS
# ─────────────────────────────────────────
CHAOS_SCENARIOS = [
    {
        'name': 'High Latency Injection',
        'type': 'latency',
        'payload': {'type': 'latency', 'latency_ms': 2000},
        'duration': 40,
        'description': 'Injects 2s latency — simulates slow database or network'
    },
    {
        'name': 'Error Rate Injection',
        'type': 'error',
        'payload': {'type': 'error', 'error_rate': 0.5},
        'duration': 35,
        'description': 'Injects 50% error rate — simulates downstream dependency failure'
    },
    {
        'name': 'CPU Stress',
        'type': 'cpu',
        'payload': {'type': 'cpu'},
        'duration': 30,
        'description': 'Maxes out CPU — simulates runaway process or crypto mining attack'
    },
    {
        'name': 'Memory Leak',
        'type': 'memory',
        'payload': {'type': 'memory'},
        'duration': 45,
        'description': 'Allocates memory continuously — simulates memory leak'
    },
    {
        'name': 'Cascading Failure',
        'type': 'error',
        'payload': {'type': 'error', 'error_rate': 0.8},
        'duration': 30,
        'description': 'High error rate on payment — simulates cascading failure across services'
    },
]

# ─────────────────────────────────────────
#  CHAOS ENGINE CORE
# ─────────────────────────────────────────

def inject_chaos(service_name, service_url, scenario):
    """Inject a chaos scenario into a service."""
    try:
        resp = requests.post(
            f"{service_url}/chaos/inject",
            json=scenario['payload'],
            timeout=5
        )
        if resp.status_code == 200:
            chaos_events_total.labels(service=service_name, chaos_type=scenario['type']).inc()
            chaos_active.labels(service=service_name).set(1)
            print(f"[{ts()}] ⚡ CHAOS INJECTED: {scenario['name']} → {service_name}")
            print(f"         {scenario['description']}")
            return True
    except Exception as e:
        print(f"[{ts()}] ❌ Failed to inject chaos into {service_name}: {e}")
    return False


def recover_service(service_name, service_url):
    """Tell a service to recover from chaos."""
    try:
        resp = requests.post(f"{service_url}/chaos/recover", timeout=5)
        if resp.status_code == 200:
            chaos_active.labels(service=service_name).set(0)
            print(f"[{ts()}] ✅ RECOVERED: {service_name}")
            return True
    except Exception as e:
        print(f"[{ts()}] ❌ Failed to recover {service_name}: {e}")
    return False


def run_chaos_cycle():
    """Main chaos loop — runs forever, triggering events every 90-150 seconds."""
    print(f"[{ts()}] 🔥 Chaos Engine started — waiting for services to be ready...")
    time.sleep(30)  # Wait for services to start

    print(f"[{ts()}] 🎯 Chaos Engine active — injecting failures every ~2 minutes")
    print(f"[{ts()}] 📊 Metrics available at :8001/metrics\n")

    while True:
        # Pick a random service and scenario
        service_name = random.choice(list(SERVICES.keys()))
        service_url = SERVICES[service_name]

        # Filter scenarios by what the service supports
        # inventory supports memory, auth/payment support cpu
        if service_name == 'inventory-service':
            available = [s for s in CHAOS_SCENARIOS if s['type'] != 'cpu']
        else:
            available = [s for s in CHAOS_SCENARIOS if s['type'] != 'memory']

        scenario = random.choice(available)
        duration = scenario['duration']

        print(f"\n[{ts()}] ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print(f"[{ts()}] 🎯 Target: {service_name}")
        print(f"[{ts()}] 💥 Scenario: {scenario['name']}")
        print(f"[{ts()}] ⏱️  Duration: {duration}s")

        # Inject chaos
        chaos_start = time.time()
        if inject_chaos(service_name, service_url, scenario):
            chaos_duration_seconds.labels(service=service_name).set(duration)

            # Wait for chaos duration
            time.sleep(duration)

            # Recover
            recovery_start = time.time()
            recover_service(service_name, service_url)
            recovery_time = time.time() - recovery_start
            recovery_time_seconds.labels(service=service_name).set(recovery_time)

            total = time.time() - chaos_start
            print(f"[{ts()}] 📈 Chaos cycle complete — total: {total:.1f}s, recovery: {recovery_time:.2f}s")

        # Wait before next chaos event
        wait = random.uniform(90, 150)
        print(f"[{ts()}] 😴 Next chaos event in {wait:.0f}s...\n")
        time.sleep(wait)


def generate_continuous_traffic():
    """
    Generate continuous background traffic to all services
    so metrics are always flowing and SLOs can be measured.
    """
    time.sleep(15)  # Wait for services
    print(f"[{ts()}] 🌊 Traffic generator started")

    endpoints = {
        'auth-service':      [('http://auth-service:5001/login', 'POST'),
                               ('http://auth-service:5001/validate', 'GET')],
        'payment-service':   [('http://payment-service:5002/pay', 'POST'),
                               ('http://payment-service:5002/refund', 'POST')],
        'inventory-service': [('http://inventory-service:5003/stock/item-001', 'GET'),
                               ('http://inventory-service:5003/stock/item-002', 'GET')],
    }

    while True:
        for service, eps in endpoints.items():
            for url, method in eps:
                try:
                    if method == 'GET':
                        requests.get(url, timeout=8)
                    else:
                        requests.post(url, json={}, timeout=8)
                except Exception:
                    pass  # Chaos is expected — just keep going
        time.sleep(random.uniform(1, 3))


def ts():
    return datetime.now().strftime('%H:%M:%S')


if __name__ == '__main__':
    chaos_engine_info.info({
        'version': '1.0.0',
        'project': 'Chaos Resilience Framework',
        'services': str(list(SERVICES.keys()))
    })

    # Start metrics server
    start_http_server(8001)

    # Start traffic generator in background
    threading.Thread(target=generate_continuous_traffic, daemon=True).start()

    # Start chaos engine
    run_chaos_cycle()
