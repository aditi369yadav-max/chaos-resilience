# 🔥 SRE Chaos & Resilience Framework

![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python)
![Prometheus](https://img.shields.io/badge/Prometheus-2.51-orange?logo=prometheus)
![Grafana](https://img.shields.io/badge/Grafana-10.4-yellow?logo=grafana)
![Docker](https://img.shields.io/badge/Docker-Compose-blue?logo=docker)

A production-style **chaos engineering and SLO resilience framework** with 3 microservices, an automated chaos engine, and a runbook automator that detects failures and triggers recovery automatically.

---

## 🏗️ Architecture

```
┌──────────────┐  ┌─────────────────┐  ┌──────────────────┐
│ auth-service │  │ payment-service │  │inventory-service │
│   :5001      │  │    :5002        │  │     :5003        │
└──────┬───────┘  └────────┬────────┘  └────────┬─────────┘
       │                   │                     │
       └──────────┬────────┴─────────────────────┘
                  │  metrics + chaos inject/recover
       ┌──────────┴────────────────────┐
       │        chaos-engine           │  ← Auto-injects failures
       │  + runbook-automator          │  ← Auto-recovers from failures
       └──────────┬────────────────────┘
                  │ scrape
       ┌──────────▼──────────┐
       │     Prometheus      │  :9091
       └──────────┬──────────┘
                  │ query
       ┌──────────▼──────────┐
       │       Grafana       │  :3001
       └─────────────────────┘
```

---

## ⚡ Chaos Scenarios (Auto-triggered every ~2 min)

| Scenario | What happens | Recovery action |
|---|---|---|
| **Latency Injection** | 2-3s added to all requests | Clear connection pool, circuit break |
| **Error Rate Injection** | 40-80% requests return 500 | Activate fallback mode |
| **CPU Stress** | CPU maxed out for 30s | Kill heavy threads, rate limit |
| **Memory Leak** | 50MB allocated continuously | Force GC, clear caches |
| **Cascading Failure** | 80% errors on payment | Isolate service, reroute traffic |

---

## 🤖 Runbook Automator

The automator **queries Prometheus every 15s** and:
1. Detects the failure type from metric patterns
2. Executes the matching recovery runbook
3. Tracks MTTR (Mean Time to Recover)
4. Burns/recovers error budget

---

## 🚀 Quick Start

```bash
git clone https://github.com/YOUR_USERNAME/chaos-resilience.git
cd chaos-resilience
docker-compose up --build
```

| Service | URL |
|---|---|
| Grafana Dashboard | http://localhost:3001 (admin/securepassword123) |
| Prometheus | http://localhost:9091 |
| Auth Service | http://localhost:5001/health |
| Payment Service | http://localhost:5002/health |
| Inventory Service | http://localhost:5003/health |

---

## 📊 SLO Targets

| Service | p99 Latency | Error Rate | Uptime |
|---|---|---|---|
| auth-service | < 500ms | < 1% | 99.9% |
| payment-service | < 1s | < 2% | 99.5% |
| inventory-service | < 300ms | < 1% | 99.0% |

---

*Built as an InfoSec SRE intern project demonstrating chaos engineering, SLO tracking, and automated runbook execution.*
