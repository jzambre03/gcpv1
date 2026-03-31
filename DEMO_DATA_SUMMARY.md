# Demo Data Summary

## Overview
Mock data has been populated for 5 services with realistic drift scenarios for your demo.

## Service Status Distribution

### 🔴 CRITICAL (2 services)
1. **payments-api** - 4 issues (2 HIGH, 1 MEDIUM, 1 LOW)
2. **analytics-pipeline** - 3 issues (1 HIGH, 1 MEDIUM, 1 LOW)

### 🟡 WARNING (1 service)
3. **user-service** - 3 issues (0 HIGH, 2 MEDIUM, 1 LOW)

### 🟢 HEALTHY (2 services)
4. **inventory-service** - 0 issues
5. **notification-engine** - 0 issues

---

## Detailed Drift Scenarios

### 1. payments-api (CRITICAL - 4 issues)

#### HIGH Risk Issues (2)

**Issue 1: Payment Transaction Timeout Reduction**
- **File**: `config/payment-gateway.yaml`
- **Setting**: `payment.transaction.timeout_ms`
- **Change**: 30000 → 5000 (30s → 5s)
- **Risk**: CRITICAL BUSINESS IMPACT - Payment failures, revenue loss, customer experience degradation
- **Impact**: 3DS authentication flows typically take 10-20 seconds, 5s timeout will cause massive payment failures
- **Action**: IMMEDIATE ROLLBACK - P0 incident

**Issue 2: Fraud Detection Disabled**
- **File**: `config/security.yaml`
- **Setting**: `security.fraud_detection.enabled`
- **Change**: true → false
- **Risk**: CRITICAL SECURITY AND FINANCIAL RISK - Fraud exposure, chargebacks, PCI-DSS violation
- **Impact**: Fraud rate increases from 0.1-0.3% to 2-5%, chargebacks increase 300-500%
- **Action**: DO NOT DEPLOY - Security incident

#### MEDIUM Risk Issues (1)

**Issue 3: Database Connection Pool Increase**
- **File**: `config/database.yaml`
- **Setting**: `database.connection_pool.max_connections`
- **Change**: 100 → 250
- **Risk**: Resource exhaustion, database overload, memory pressure (7.5GB just for connections)
- **Impact**: May exceed database server capacity, performance degradation
- **Action**: Conditional approval with load testing and gradual rollout

#### LOW Risk Issues (1)

**Issue 4: Card Last 4 Digits Logging**
- **File**: `config/application.yaml`
- **Setting**: `logging.payment_details.include_card_last4`
- **Change**: false → true
- **Risk**: PCI-DSS compliance consideration, log security requirements
- **Impact**: Allowed by PCI-DSS but requires proper log security controls
- **Action**: Approve with safeguards (encrypted logs, access controls, retention policy)

---

### 2. analytics-pipeline (CRITICAL - 3 issues)

#### HIGH Risk Issues (1)

**Issue 1: Encryption Algorithm Downgrade**
- **File**: `config/application.yaml`
- **Setting**: `security.encryption.algorithm`
- **Change**: AES-256-GCM → AES-128-CBC
- **Risk**: CRITICAL SECURITY RISK - Data breach exposure, compliance violations (GDPR, PCI-DSS, HIPAA)
- **Impact**: Weaker encryption for PII/financial data, vulnerable to padding oracle attacks, no authentication
- **Action**: IMMEDIATE ROLLBACK - Security incident, data re-encryption required

#### MEDIUM Risk Issues (1)

**Issue 2: Data Retention Reduction**
- **File**: `config/application.yaml`
- **Setting**: `pipeline.data_retention.days`
- **Change**: 90 → 30
- **Risk**: Compliance violation (SOX, PCI-DSS, GDPR), audit trail loss, business analytics impact
- **Impact**: Insufficient for quarterly audits, security investigations, trend analysis
- **Action**: Review with compliance team, likely revert, consider tiered storage instead

#### LOW Risk Issues (1)

**Issue 3: Logging Level Change**
- **File**: `config/logging.yaml`
- **Setting**: `logging.level.root`
- **Change**: INFO → ERROR
- **Risk**: Observability reduction, troubleshooting difficulty
- **Impact**: 60-80% log volume reduction but loses operational visibility
- **Action**: Conditional approval with metrics/tracing infrastructure and selective logging

---

### 3. user-service (WARNING - 3 issues)

#### MEDIUM Risk Issues (2)

**Issue 1: Session Timeout Extension**
- **File**: `config/auth.yaml`
- **Setting**: `auth.session.max_age_hours`
- **Change**: 24 → 168 (1 day → 7 days)
- **Risk**: Security risk - extended attack window, session hijacking, compliance issues
- **Impact**: Compromised sessions valid for 7 days, violates OWASP/NIST recommendations
- **Action**: Review and likely revert, consider sliding sessions or idle timeout

**Issue 2: Rate Limit Increase**
- **File**: `config/rate-limiting.yaml`
- **Setting**: `rate_limiting.api.requests_per_minute`
- **Change**: 100 → 500
- **Risk**: DDoS vulnerability, brute force attacks, resource exhaustion
- **Impact**: Single user can generate 8.3 req/sec, enables password guessing and data scraping
- **Action**: Conditional approval with tiered limits, burst limiting, and monitoring

#### LOW Risk Issues (1)

**Issue 3: Cache TTL Increase**
- **File**: `config/cache.yaml`
- **Setting**: `cache.user_profile.ttl_seconds`
- **Change**: 300 → 3600 (5min → 1hr)
- **Risk**: Data staleness, delayed permission updates
- **Impact**: Profile changes take up to 1 hour to propagate
- **Action**: Approve if permissions not cached and cache invalidation implemented

---

### 4. inventory-service (HEALTHY - 0 issues)
✅ No configuration drifts detected
✅ All configurations match golden branch
✅ Service is compliant and ready for production

---

### 5. notification-engine (HEALTHY - 0 issues)
✅ No configuration drifts detected
✅ All configurations match golden branch
✅ Service is compliant and ready for production

---

## Demo Flow Recommendations

### Main Dashboard
- Shows 5 services with status badges
- 2 Critical (red), 1 Warning (yellow), 2 Healthy (green)
- Issue counts visible for services with drifts

### Service Detail Pages

**For Critical Services (payments-api, analytics-pipeline):**
1. **Overview Tab**: Shows environments with issue count badges
2. **Certifications Tab**: Shows certification status with drift counts
3. **Drift Analysis Tab**: Shows detailed drift analysis with:
   - Nested YAML structure showing old → new values
   - Comprehensive risk assessments (multiple paragraphs)
   - Detailed suggested actions (step-by-step remediation)
   - Risk level badges (HIGH/MEDIUM/LOW)

**For Warning Service (user-service):**
- Similar structure but with MEDIUM/LOW risks only

**For Healthy Services (inventory-service, notification-engine):**
- Drift Analysis tab shows "No drifts detected" or empty state

---

## Key Talking Points for Demo

1. **Realistic Scenarios**: All drifts are based on real-world configuration issues
2. **Comprehensive Analysis**: AI provides detailed risk assessments and remediation steps
3. **Compliance Focus**: Highlights regulatory implications (GDPR, PCI-DSS, SOX, HIPAA)
4. **Business Impact**: Quantifies financial and operational risks
5. **Actionable Guidance**: Step-by-step remediation with code examples
6. **Risk Categorization**: Clear HIGH/MEDIUM/LOW classification
7. **Nested YAML Display**: Shows configuration context with proper structure

---

## Technical Details

- All data stored in SQLite database (`config_data/golden_config.db`)
- Drift details in `llm_outputs.llm_data.drifts` array
- Each drift has: file, locator, old/new values, risk level, AI analysis, remediation snippet
- UI automatically loads latest run data from database
- Locator format: `{"value": "key1.key2.key3", "type": "yaml_path"}`

---

## Refresh Instructions

If UI shows cached data:

```javascript
// In browser console (F12):
sessionStorage.clear()
location.reload(true)
```

Then navigate to any service → Drift Analysis tab to see the detailed scenarios.
