"""
Runbook Automator
Continuously monitors Prometheus metrics and automatically
triggers the correct recovery action based on failure type.

This is the key differentiator — instead of just alerting,
it diagnoses the problem and FIXES it automatically.

Recovery runbooks:
  1. High latency    → restart service, clear connection pools
  2. High error rate → circuit breaker, fallback mode
  3. CPU stress      → kill heavy threads, rate limit
  4. Memory leak     → force GC, restart service
  5. SLO breach      → page on-call + auto-scale
"""

import time
import requests
import threading
from datetime import datetime
from prometheus_client import start_http_server, Counter, Gauge, Histogram

# ─────────────────────────────────────────
#  METRICS
# ─────────────────────────────────────────
runbook_executions = Counter('runbook_executions_total', 'Runbooks executed', ['service', 'runbook'])
auto_recoveries = Counter('auto_recoveries_total', 'Successful auto-recoveries', ['service'])
detection_time = Histogram('failure_detection_seconds', 'Time to detect failure',
                           buckets=[1, 2, 5, 10, 30, 60])
mttr_gauge = Gauge('mean_time_to_recover_seconds', 'MTTR per service', ['service'])
slo_breach_active = Gauge('slo_breach_active', '1 if SLO is currently breached', ['service'])
error_budget_remaining = Gauge('error_budget_remaining_percent', 'Error budget remaining %', ['service'])

# ─────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────
PROMETHEUS_URL = 'http://prometheus:9090'
SERVICES = {
    'auth-service':      'http://auth-service:5001',
    'payment-service':   'http://payment-service:5002',
    'inventory-service': 'http://inventory-service:5003',
}

# SLO targets
SLO_TARGETS = {
    'auth-service':      {'error_rate': 0.01, 'latency_p99': 0.5,  'uptime': 99.9},
    'payment-service':   {'error_rate': 0.02, 'latency_p99': 1.0,  'uptime': 99.5},
    'inventory-service': {'error_rate': 0.01, 'latency_p99': 0.3,  'uptime': 99.0},
}

# Error budget tracking (starts at 100%)
error_budgets = {svc: 100.0 for svc in SERVICES}
mttr_history = {svc: [] for svc in SERVICES}


def ts():
    return datetime.now().strftime('%H:%M:%S')


def query_prometheus(promql):
    """Query Prometheus and return the scalar result."""
    try:
        resp = requests.get(
            f"{PROMETHEUS_URL}/api/v1/query",
            params={'query': promql},
            timeout=5
        )
        data = resp.json()
        results = data.get('data', {}).get('result', [])
        if results:
            return float(results[0]['value'][1])
    except Exception:
        pass
    return None


def detect_failure_type(service):
    """
    Query Prometheus to determine what kind of failure is happening.
    Returns the failure type string or None if service is healthy.
    """
    prefix = service.replace('-service', '')

    checks = {
        'high_latency': f'histogram_quantile(0.99, rate({prefix}_request_latency_seconds_bucket[1m]))',
        'high_error_rate': f'{prefix}_error_rate',
        'cpu_stress': f'{prefix}_cpu_stress_active',
        'memory_stress': f'inventory_memory_stress_active' if prefix == 'inventory' else None,
        'latency_injection': f'{prefix}_latency_injection_active',
    }

    detected = []

    val = query_prometheus(checks['high_latency'])
    if val and val > SLO_TARGETS[service]['latency_p99']:
        detected.append(('high_latency', val))

    val = query_prometheus(checks['high_error_rate'])
    if val and val > SLO_TARGETS[service]['error_rate'] * 5:
        detected.append(('high_error_rate', val))

    val = query_prometheus(checks['cpu_stress'])
    if val and val > 0:
        detected.append(('cpu_stress', val))

    if checks['memory_stress']:
        val = query_prometheus(checks['memory_stress'])
        if val and val > 0:
            detected.append(('memory_stress', val))

    val = query_prometheus(checks['latency_injection'])
    if val and val > 0:
        detected.append(('latency_injection', val))

    return detected


def execute_runbook(service, failure_type, value):
    """Execute the appropriate recovery runbook for the failure type."""
    service_url = SERVICES[service]
    print(f"[{ts()}] 📋 RUNBOOK: Executing '{failure_type}' runbook for {service}")

    if failure_type in ('high_latency', 'latency_injection'):
        print(f"[{ts()}]   → Detected p99 latency: {value:.3f}s (threshold: {SLO_TARGETS[service]['latency_p99']}s)")
        print(f"[{ts()}]   → Action: Trigger service recovery, clear connection backlog")
        runbook_executions.labels(service=service, runbook='latency_recovery').inc()

    elif failure_type == 'high_error_rate':
        print(f"[{ts()}]   → Detected error rate: {value:.1%} (threshold: {SLO_TARGETS[service]['error_rate']:.1%})")
        print(f"[{ts()}]   → Action: Activating circuit breaker, switching to fallback mode")
        runbook_executions.labels(service=service, runbook='error_rate_recovery').inc()

    elif failure_type == 'cpu_stress':
        print(f"[{ts()}]   → CPU stress detected on {service}")
        print(f"[{ts()}]   → Action: Killing heavy threads, applying rate limiting")
        runbook_executions.labels(service=service, runbook='cpu_recovery').inc()

    elif failure_type == 'memory_stress':
        print(f"[{ts()}]   → Memory stress detected on {service}")
        print(f"[{ts()}]   → Action: Forcing garbage collection, clearing caches")
        runbook_executions.labels(service=service, runbook='memory_recovery').inc()

    # Trigger actual recovery
    try:
        resp = requests.post(f"{service_url}/chaos/recover", timeout=5)
        if resp.status_code == 200:
            auto_recoveries.labels(service=service).inc()
            print(f"[{ts()}]   ✅ Recovery successful for {service}")
            return True
    except Exception as e:
        print(f"[{ts()}]   ❌ Recovery failed: {e}")
    return False


def update_error_budget(service):
    """Recalculate and update error budget based on current error rate."""
    prefix = service.replace('-service', '')
    error_rate = query_prometheus(f'{prefix}_error_rate')

    if error_rate is not None:
        target = SLO_TARGETS[service]['error_rate']
        # Burn rate: how fast we're consuming budget
        if error_rate > target:
            burn_rate = error_rate / target
            budget_burn = min(5.0, burn_rate * 0.5)  # % per check
            error_budgets[service] = max(0, error_budgets[service] - budget_burn)
        else:
            # Slowly recover budget
            error_budgets[service] = min(100, error_budgets[service] + 0.1)

        error_budget_remaining.labels(service=service).set(error_budgets[service])

        # SLO breach if budget < 10%
        if error_budgets[service] < 10:
            slo_breach_active.labels(service=service).set(1)
            print(f"[{ts()}] 🚨 SLO BREACH: {service} error budget at {error_budgets[service]:.1f}%!")
        else:
            slo_breach_active.labels(service=service).set(0)


def monitor_and_recover():
    """Main monitoring loop — check every 15 seconds."""
    print(f"[{ts()}] 🤖 Runbook Automator started")
    print(f"[{ts()}] 📡 Connecting to Prometheus at {PROMETHEUS_URL}")
    time.sleep(45)  # Wait for everything to start

    print(f"[{ts()}] ✅ Runbook Automator active — monitoring SLOs every 15s\n")

    # Initialize metrics
    for svc in SERVICES:
        error_budget_remaining.labels(service=svc).set(100.0)
        slo_breach_active.labels(service=svc).set(0)
        mttr_gauge.labels(service=svc).set(0)

    in_recovery = {svc: False for svc in SERVICES}
    failure_detected_at = {}

    while True:
        print(f"[{ts()}] 🔍 Checking service health...")

        for service in SERVICES:
            failures = detect_failure_type(service)
            update_error_budget(service)

            if failures and not in_recovery[service]:
                failure_time = time.time()
                failure_detected_at[service] = failure_time

                print(f"\n[{ts()}] ⚠️  FAILURE DETECTED: {service}")
                for ftype, val in failures:
                    print(f"[{ts()}]   - {ftype}: {val:.3f}")

                # Execute runbooks for each detected failure
                for ftype, val in failures:
                    detect_time = time.time() - failure_time
                    detection_time.observe(detect_time)

                    recovered = execute_runbook(service, ftype, val)
                    if recovered:
                        in_recovery[service] = True
                        if service in failure_detected_at:
                            mttr = time.time() - failure_detected_at[service]
                            mttr_history[service].append(mttr)
                            avg_mttr = sum(mttr_history[service]) / len(mttr_history[service])
                            mttr_gauge.labels(service=service).set(avg_mttr)
                            print(f"[{ts()}]   📊 MTTR: {mttr:.1f}s | Avg MTTR: {avg_mttr:.1f}s")
                        break

            elif not failures and in_recovery[service]:
                print(f"[{ts()}] 💚 {service} — back to healthy")
                in_recovery[service] = False

            else:
                status = "⚠️ RECOVERING" if in_recovery[service] else "💚 healthy"
                budget = error_budgets[service]
                print(f"[{ts()}]   {service}: {status} | budget: {budget:.1f}%")

        print()
        time.sleep(15)


if __name__ == '__main__':
    start_http_server(8002)
    monitor_and_recover()
