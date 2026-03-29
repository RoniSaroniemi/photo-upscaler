# GCP Cost Measurement Research

**Date:** 2026-03-29
**Service:** esrgan-poc (Cloud Run, us-central1)
**Project:** photo-upscaler-24h

## 1. Cloud Run Metrics (Monitoring API)

### Available Metrics Tested

| Metric | Kind | Granularity | Per-Request? | Notes |
|--------|------|------------|--------------|-------|
| `billable_instance_time` | DELTA, DOUBLE | 1-min buckets | ❌ Aggregate | Total seconds billed across all instances per minute |
| `cpu/allocation_time` | DELTA, DOUBLE | 1-min buckets | ❌ Aggregate | Total vCPU-seconds allocated per minute (e.g. 240s = 4 vCPU × 60s) |
| `memory/allocation_time` | DELTA, DOUBLE | 1-min buckets | ❌ Aggregate | Total GiB-seconds allocated per minute |
| `request_count` | DELTA, INT64 | 1-min buckets | ✅ Count only | Requests per minute, labeled by response_code |
| `request_latencies` | DELTA, DISTRIBUTION | 1-min buckets | ⚠️ Distribution | Latency distribution, not individual requests |
| `cpu/utilizations` | DELTA, DISTRIBUTION | 1-min buckets | ❌ Aggregate | CPU utilization % distribution |

### Actual Data Observed

```
# billable_instance_time (per minute, in seconds):
08:17-08:18: 55.8s
08:16-08:17: 60.0s
08:15-08:16: 60.0s

# cpu/allocation_time (per minute, in vCPU-seconds):
08:17-08:18: 223.2s  (= 4 vCPU × 55.8s)
08:16-08:17: 240.0s  (= 4 vCPU × 60.0s — full minute active)

# request_count (per minute, by status):
200: tracked ✓
500: tracked ✓
504: tracked ✓
```

### Verdict: Can We Get Per-Request Cost from Metrics?

**No — not directly.** All cost-related metrics (billable_instance_time, cpu/allocation_time, memory/allocation_time) are **aggregated per minute**, not per request. You can derive an **average cost per request** by dividing:

```
avg_cost_per_request = (allocation_time_in_period × price_per_unit) / request_count_in_period
```

But this is inaccurate when:
- Multiple requests overlap in the same minute (unlikely with concurrency=1, but possible)
- Instance stays warm between requests (idle time gets amortized)
- Mix of different image sizes processed in same minute

## 2. Cloud Run Logs (Logging API)

### Per-Request Data Available

```
gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="esrgan-poc" AND httpRequest.requestMethod="POST"'
```

Each request log entry contains:

| Field | Example | Useful? |
|-------|---------|---------|
| `httpRequest.latency` | `50.531037906s` | ✅ Total request duration |
| `httpRequest.status` | `200` | ✅ Success/failure |
| `httpRequest.requestSize` | `323034` | ✅ Input file size |
| `httpRequest.responseSize` | `26016791` | ✅ Output file size |
| `timestamp` | `2026-03-29T08:09:00.222147Z` | ✅ When |

### Actual Request Log Data

```
2026-03-29T08:12:21Z | POST status=504 latency=300.0s  reqSize=3,676,965  resSize=72
2026-03-29T08:11:08Z | POST status=500 latency=70.6s   reqSize=488,050    resSize=None
2026-03-29T08:10:00Z | POST status=500 latency=67.5s   reqSize=390,759    resSize=None
2026-03-29T08:09:00Z | POST status=200 latency=50.5s   reqSize=323,034    resSize=26,016,791
2026-03-29T08:08:38Z | POST status=200 latency=19.6s   reqSize=154,524    resSize=13,212,212
```

### Custom Application Headers

The service already emits `X-Processing-Time-Ms` in response headers. This is **not** captured in Cloud Run logs by default, but could be:
- Logged from the application to stdout (then queryable)
- Returned to the client for client-side tracking

### Verdict: Best Source for Per-Request Cost

**Yes — logs provide per-request latency.** Since Cloud Run bills per instance-second with concurrency=1, the request latency IS the billable time for that request. Formula:

```
per_request_cost = latency_seconds × (4 × $0.000024 + 8 × $0.0000025)
                 = latency_seconds × $0.000116
```

## 3. Cloud Billing Export (BigQuery)

### Current State

```
$ bq ls --project_id=photo-upscaler-24h
# No datasets found
```

**Billing export is NOT enabled** for this project. No BigQuery datasets exist.

### What It Would Provide (If Enabled)

- **Standard export**: Daily cost by SKU (Cloud Run vCPU, Memory, Requests)
- **Detailed export**: Hourly cost breakdown with resource labels
- **Neither provides per-request granularity** — minimum granularity is hourly by service

### Setup Required

1. Create BigQuery dataset: `bq mk billing_export`
2. Enable in Cloud Billing → Billing Export → BigQuery Export
3. Wait 24-48 hours for data to flow
4. Query: `SELECT * FROM billing_export.gcp_billing_export_v1_* WHERE service.description = 'Cloud Run'`

### Verdict: Not Useful for Per-Request Cost

Billing export is useful for **monthly cost tracking and alerts**, not per-request pricing. Even detailed export only gives hourly aggregates by service.

## 4. Comparison of Approaches

| Approach | Per-Request? | Accuracy | Latency | Setup | Best For |
|----------|-------------|----------|---------|-------|----------|
| **Formula-based** (from request latency) | ✅ Yes | ⚠️ ~95% (excludes idle overhead) | Real-time | None | MVP pricing, client display |
| **Cloud Monitoring metrics** | ❌ Minute-level | ✅ High (actual billing data) | 1-3 min delay | API access | Dashboard, aggregate tracking |
| **Cloud Run logs** | ✅ Yes | ✅ High (actual latency) | ~seconds | Log sink | Per-request analytics |
| **Billing Export (BQ)** | ❌ Hourly | ✅ Exact | 24-48h delay | BQ + export | Monthly reporting, auditing |
| **Application-level tracking** | ✅ Yes | ⚠️ Processing only | Real-time | Code change | Granular timing breakdown |

## 5. Recommendation: Formula-Based + Log Validation

### Primary: Formula-Based Cost Calculation (Real-Time)

For the MVP, calculate cost per request in the application:

```python
# Constants for us-central1 Cloud Run pricing
VCPU_PER_SECOND = 0.000024      # $/vCPU-second
MEMORY_PER_GIB_SECOND = 0.0000025  # $/GiB-second
REQUEST_COST = 0.0000004        # $0.40/million
NUM_VCPU = 4
MEMORY_GIB = 8

def calculate_cost(processing_time_seconds: float) -> float:
    """Calculate per-request cost from processing time."""
    vcpu_cost = NUM_VCPU * processing_time_seconds * VCPU_PER_SECOND
    memory_cost = MEMORY_GIB * processing_time_seconds * MEMORY_PER_GIB_SECOND
    return vcpu_cost + memory_cost + REQUEST_COST

# Examples from real benchmarks:
# 480x320:   calculate_cost(4.3)  = $0.00050
# 1024x683:  calculate_cost(19.1) = $0.00222
# 1024x1536: calculate_cost(46.9) = $0.00545
```

The service already returns `X-Processing-Time-Ms` in response headers — the API gateway or pricing service can use this directly.

### Why This Works

With concurrency=1:
- **billable_instance_time ≈ sum of request latencies + idle warmup** (100ms minimum)
- For back-to-back requests, the formula matches actual billing within ~5%
- The main inaccuracy is idle time between requests (billed but not attributed to any request)
- For sparse traffic, add a flat overhead of ~$0.00012/request for 1s idle startup

### Secondary: Log-Based Validation (Weekly)

Set up a Cloud Run log sink to BigQuery for audit:

```bash
gcloud logging sinks create esrgan-request-logs \
  bigquery.googleapis.com/projects/photo-upscaler-24h/datasets/run_logs \
  --log-filter='resource.type="cloud_run_revision" AND resource.labels.service_name="esrgan-poc" AND httpRequest.requestMethod="POST"'
```

Then compare formula estimates against Cloud Monitoring `billable_instance_time` weekly:

```sql
-- Compare formula-estimated cost vs actual billed time
SELECT
  DATE(timestamp) as date,
  COUNT(*) as requests,
  SUM(CAST(REGEXP_EXTRACT(httpRequest.latency, r'([\d.]+)') AS FLOAT64)) as total_latency_s,
  -- Compare with Monitoring API billable_instance_time for same period
FROM `run_logs.stdout`
WHERE httpRequest.requestMethod = 'POST'
GROUP BY date
```

### Not Recommended for MVP

- **Billing Export**: Too slow (24-48h), too coarse (hourly), requires BQ setup
- **Monitoring metrics alone**: No per-request granularity, only useful for dashboards
- **GPU metrics**: Not applicable yet (CPU-only deployment)

## 6. Practical Implementation Plan

### MVP (Day 1)
1. Use `X-Processing-Time-Ms` header already returned by the service
2. Apply formula: `cost = processing_seconds × $0.000116`
3. Show estimated cost on receipt/invoice
4. Log to application database for analytics

### Week 1
1. Set up Cloud Run log sink → BigQuery
2. Create validation query comparing formula vs actual
3. Add Monitoring dashboard for `billable_instance_time` and `request_count`

### Month 1
1. Enable Billing Export to BigQuery
2. Build monthly reconciliation: formula estimates vs actual GCP bill
3. Tune formula if drift exceeds 10%
4. Consider adding idle-time overhead factor based on traffic patterns

### Key Insight: billable vCPU-seconds Per Request

**Can we get billable vCPU-seconds per request from GCP?** No — GCP only provides aggregate metrics. But with concurrency=1, we can derive it:

```
billable_vcpu_seconds_per_request = request_latency × num_vcpu
```

This is accurate because:
- Concurrency=1 means one request fully owns the instance
- Cloud Run bills from first request to last response + idle timeout
- `request_latency` from logs is the authoritative duration

For concurrency>1 in future, this breaks down — you'd need to divide aggregate `cpu/allocation_time` by `request_count` for the same period, accepting that it's an average.
