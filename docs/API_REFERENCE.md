# 🌐 API Reference - Golden Config AI System

**Version**: 1.0  
**Base URL**: `http://localhost:3000` (configurable via PORT env var)  
**Date**: October 7, 2025

---

## 📋 Table of Contents

1. [Overview](#overview)
2. [Authentication](#authentication)
3. [Endpoints](#endpoints)
4. [Data Models](#data-models)
5. [Error Handling](#error-handling)
6. [Examples](#examples)

---

## 🔍 Overview

The Golden Config AI System provides RESTful API endpoints for configuration drift analysis using AI-powered multi-agent orchestration.

### **Key Features**
- Configuration drift detection
- AI-powered risk analysis
- Policy-based validation
- Real-time status updates
- LLM output in adjudicator format

---

## 🔐 Authentication

Currently, the API does not require authentication. **For production deployment, implement authentication middleware.**

### **Recommended**:
- API Keys
- OAuth 2.0
- JWT tokens

---

## 🛣️ Endpoints

### **1. System Information**

#### **GET /**
Main UI dashboard

**Response**: HTML page

---

#### **GET /health**
Health check endpoint

**Response**:
```json
{
  "status": "healthy",
  "timestamp": "2025-10-07T12:34:56.789Z",
  "service": "golden-config-validation",
  "version": "1.0.0"
}
```

---

#### **GET /api/info**
API information and available endpoints

**Response**:
```json
{
  "service": "Golden Config Validation Service",
  "version": "1.0.0",
  "timestamp": "2025-10-07T12:34:56.789Z",
  "default_repo": "https://gitlab.verizon.com/saja9l7/golden_config.git",
  "default_branches": {
    "golden": "gold",
    "drift": "drift"
  },
  "endpoints": {
    "ui": "GET /",
    "validate": "POST /api/validate",
    "quick_analyze": "POST /api/analyze/quick",
    "latest_results": "GET /api/latest-results",
    "validation_status": "GET /api/validation-status",
    "config": "GET /api/config",
    "llm_output": "GET /api/llm-output",
    "health": "GET /health"
  }
}
```

---

### **2. Configuration**

#### **GET /api/config**
Get environment configuration

**Response**:
```json
{
  "repo_url": "https://gitlab.verizon.com/saja9l7/golden_config.git",
  "golden_branch": "gold",
  "drift_branch": "drift",
  "timestamp": "2025-10-07T12:34:56.789Z"
}
```

**Use Case**: UI loads this to populate forms with defaults

---

### **3. Validation**

#### **POST /api/validate**
Trigger full configuration validation

**Request Body**:
```json
{
  "repo_url": "https://gitlab.verizon.com/saja9l7/golden_config.git",
  "golden_branch": "gold",
  "drift_branch": "drift",
  "target_folder": "",
  "project_id": "config-validation",
  "mr_iid": "auto"
}
```

**Parameters**:
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `repo_url` | string | Yes | Git repository URL |
| `golden_branch` | string | Yes | Golden config branch |
| `drift_branch` | string | Yes | Drift config branch |
| `target_folder` | string | No | Specific folder to analyze (empty = all) |
| `project_id` | string | No | Project identifier |
| `mr_iid` | string | No | Merge request ID |

**Response**:
```json
{
  "status": "success",
  "validation_result": {
    "run_id": "run_20251007_123456_auto",
    "verdict": "COMPLETED",
    "summary": "Validation completed successfully",
    "execution_time_ms": 12345,
    "timestamp": "2025-10-07T12:34:56.789Z",
    
    "files_analyzed": 5,
    "files_compared": 5,
    "files_with_drift": 2,
    "total_deltas": 37,
    "deltas_analyzed": 30,
    "total_clusters": 8,
    
    "policy_violations_count": 15,
    "policy_violations": [...],
    "critical_violations": 2,
    "high_violations": 6,
    
    "overall_risk_level": "medium",
    "risk_assessment": {...},
    "recommendations": [...],
    
    "llm_output": {
      "meta": {...},
      "overview": {...},
      "high": [...],
      "medium": [...],
      "low": [...],
      "allowed_variance": [...]
    },
    "llm_output_path": "config_data/llm_output/llm_output_20251007_123456.json"
  }
}
```

**Status Codes**:
- `200 OK` - Validation completed successfully
- `400 Bad Request` - Invalid request parameters
- `500 Internal Server Error` - Validation failed

---

#### **POST /api/analyze/quick**
Quick analysis (Config Collector only)

**Request Body**:
```json
{
  "repo_url": "https://gitlab.verizon.com/saja9l7/golden_config.git",
  "golden_ref": "gold",
  "drift_ref": "drift"
}
```

**Response**:
```json
{
  "status": "success",
  "analysis": {
    "files_compared": 5,
    "files_with_drift": 2,
    "total_deltas": 37,
    "context_bundle_file": "config_data/context_bundle/context_bundle_20251007_123456.json"
  }
}
```

---

### **4. Results**

#### **GET /api/latest-results**
Get the latest validation results

**Response**:
```json
{
  "status": "success",
  "validation_result": {
    ...same as /api/validate response...
  }
}
```

**Status Codes**:
- `200 OK` - Results found
- `404 Not Found` - No results available yet

---

#### **GET /api/llm-output** ⭐ **NEW**
Get the latest LLM output in adjudicator format

**Response**:
```json
{
  "status": "success",
  "file_path": "config_data/llm_output/llm_output_20251007_123456.json",
  "data": {
    "meta": {
      "golden": "abc123def456",
      "candidate": "xyz789abc012",
      "golden_name": "gold",
      "candidate_name": "drift",
      "generated_at": "2025-10-07T12:34:56.789Z"
    },
    "overview": {
      "total_files": 5,
      "drifted_files": 2,
      "added_files": 0,
      "removed_files": 0,
      "modified_files": 2,
      "total_deltas": 37
    },
    "high": [
      {
        "id": "cfg~config/app.yml~spring.datasource.url",
        "file": "config/application.yml",
        "locator": {
          "type": "yamlpath",
          "value": "spring.datasource.url"
        },
        "old": "jdbc:mysql://old-host:3306/db",
        "new": "jdbc:mysql://new-host:3306/db",
        "drift_category": "Database",
        "risk_level": "high",
        "risk_reason": "Database endpoint changed",
        "why": "Database connection string modified",
        "remediation": {
          "snippet": "spring:\n  datasource:\n    url: jdbc:mysql://old-host:3306/db"
        },
        "ai_review_assistant": {
          "potential_risk": "Service outage if database unreachable",
          "suggested_action": "Validate database endpoint"
        }
      }
    ],
    "medium": [...],
    "low": [...],
    "allowed_variance": [...]
  }
}
```

**Status Codes**:
- `200 OK` - LLM output found
- `404 Not Found` - No LLM output available yet
- `500 Internal Server Error` - Failed to load LLM output

**Use Case**: UI/adjudicator fetches this to display categorized drifts

---

#### **GET /api/validation-status**
Get validation status summary

**Response**:
```json
{
  "status": "healthy",
  "last_validation": "2025-10-07T12:34:56.789Z",
  "supervisor_status": "ready",
  "config_collector_status": "ready",
  "diff_engine_status": "ready"
}
```

---

## 📦 Data Models

### **LLM Output Structure**

```typescript
interface LLMOutput {
  meta: {
    golden: string;           // Golden commit SHA or branch
    candidate: string;        // Drift commit SHA or branch
    golden_name: string;      // Golden branch name
    candidate_name: string;   // Drift branch name
    generated_at: string;     // ISO 8601 timestamp
  };
  overview: {
    total_files: number;
    drifted_files: number;
    added_files: number;
    removed_files: number;
    modified_files: number;
    total_deltas: number;
  };
  high: DriftItem[];          // Critical drifts
  medium: DriftItem[];        // Moderate drifts
  low: DriftItem[];           // Minor drifts
  allowed_variance: AllowedItem[];  // Policy-approved
}

interface DriftItem {
  id: string;
  file: string;
  locator: {
    type: string;             // "yamlpath", "jsonpath", "properties"
    value: string;            // Key path
  };
  old: any;
  new: any;
  drift_category: string;     // "Database", "Network", etc.
  risk_level: string;         // "high", "medium", "low"
  risk_reason: string;
  why: string;
  remediation: {
    snippet: string;
    steps?: string[];
  };
  ai_review_assistant: {
    potential_risk: string;
    suggested_action: string;
  };
}

interface AllowedItem {
  id: string;
  file: string;
  locator: object;
  old: any;
  new: any;
  drift_category: string;
  why_allowed: string;
  risk_level: string;
  risk_reason: string;
  ai_review_assistant: object;
}
```

### **Validation Request**

```typescript
interface ValidationRequest {
  repo_url: string;
  golden_branch: string;
  drift_branch: string;
  target_folder?: string;
  project_id?: string;
  mr_iid?: string;
}
```

### **Validation Response**

```typescript
interface ValidationResponse {
  status: "success" | "error";
  validation_result?: {
    run_id: string;
    verdict: string;
    summary: string;
    execution_time_ms: number;
    timestamp: string;
    
    // File metrics
    files_analyzed: number;
    files_compared: number;
    files_with_drift: number;
    
    // Delta metrics
    total_deltas: number;
    deltas_analyzed: number;
    total_clusters: number;
    
    // Policy metrics
    policy_violations_count: number;
    policy_violations: PolicyViolation[];
    critical_violations: number;
    high_violations: number;
    
    // Risk metrics
    overall_risk_level: string;
    risk_assessment: RiskAssessment;
    recommendations: string[];
    
    // LLM output (NEW)
    llm_output: LLMOutput;
    llm_output_path: string;
  };
  error?: string;
}
```

---

## ❌ Error Handling

### **Error Response Format**

```json
{
  "status": "error",
  "error": "Error message",
  "detail": "Detailed error description",
  "timestamp": "2025-10-07T12:34:56.789Z"
}
```

### **Common HTTP Status Codes**

| Code | Meaning | Description |
|------|---------|-------------|
| 200 | OK | Request successful |
| 400 | Bad Request | Invalid request parameters |
| 404 | Not Found | Resource not found |
| 500 | Internal Server Error | Server-side error |
| 503 | Service Unavailable | Service temporarily unavailable |

### **Error Scenarios**

#### **Invalid Repository URL**
```json
{
  "status": "error",
  "error": "Repository not accessible",
  "detail": "Failed to clone: https://invalid-url.git"
}
```

#### **Branch Not Found**
```json
{
  "status": "error",
  "error": "Branch not found",
  "detail": "Branch 'invalid-branch' does not exist"
}
```

#### **No Results Available**
```json
{
  "status": "error",
  "error": "No validation results available",
  "detail": "Run validation first using POST /api/validate"
}
```

---

## 💡 Examples

### **Example 1: Full Validation Flow**

```bash
# 1. Check service health
curl http://localhost:3000/health

# 2. Get configuration
curl http://localhost:3000/api/config

# 3. Trigger validation
curl -X POST http://localhost:3000/api/validate \
  -H "Content-Type: application/json" \
  -d '{
    "repo_url": "https://gitlab.verizon.com/saja9l7/golden_config.git",
    "golden_branch": "gold",
    "drift_branch": "drift"
  }'

# 4. Get LLM output
curl http://localhost:3000/api/llm-output

# 5. Get full results
curl http://localhost:3000/api/latest-results
```

### **Example 2: Quick Analysis**

```bash
curl -X POST http://localhost:3000/api/analyze/quick \
  -H "Content-Type: application/json" \
  -d '{
    "repo_url": "https://gitlab.verizon.com/saja9l7/golden_config.git",
    "golden_ref": "gold",
    "drift_ref": "drift"
  }'
```

### **Example 3: JavaScript/Fetch**

```javascript
// Trigger validation
const response = await fetch('http://localhost:3000/api/validate', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    repo_url: 'https://gitlab.verizon.com/saja9l7/golden_config.git',
    golden_branch: 'gold',
    drift_branch: 'drift'
  })
});

const result = await response.json();
console.log('Validation result:', result);

// Fetch LLM output
const llmResponse = await fetch('http://localhost:3000/api/llm-output');
const llmData = await llmResponse.json();
console.log('LLM output:', llmData.data);
```

### **Example 4: Python/Requests**

```python
import requests

# Trigger validation
response = requests.post('http://localhost:3000/api/validate', json={
    'repo_url': 'https://gitlab.verizon.com/saja9l7/golden_config.git',
    'golden_branch': 'gold',
    'drift_branch': 'drift'
})

result = response.json()
print(f"Validation result: {result}")

# Fetch LLM output
llm_response = requests.get('http://localhost:3000/api/llm-output')
llm_data = llm_response.json()
print(f"High risk items: {len(llm_data['data']['high'])}")
```

---

## 🔧 Rate Limiting

**Current**: No rate limiting implemented

**Recommended for Production**:
- 100 requests/minute per IP
- 10 concurrent validations per IP
- Implement with middleware (e.g., `slowapi`)

---

## 📊 Monitoring

### **Health Check**
```bash
# Monitor service health
watch -n 5 'curl -s http://localhost:3000/health | jq .'
```

### **Metrics to Track**
- Request count
- Response times
- Error rates
- Validation duration
- LLM API calls
- Token usage

---

## 🚀 Deployment

### **Production Considerations**

1. **Security**:
   - Enable authentication
   - Use HTTPS
   - Implement rate limiting
   - Sanitize inputs

2. **Performance**:
   - Use async workers (e.g., Gunicorn with uvicorn workers)
   - Enable caching
   - Optimize AI calls

3. **Monitoring**:
   - Add logging middleware
   - Track metrics (Prometheus/Grafana)
   - Set up alerts

4. **Scaling**:
   - Horizontal scaling (multiple instances)
   - Load balancing
   - Queue-based validation (Celery/RabbitMQ)

---

## 📞 Support

For API issues or questions:
1. Check service health: `GET /health`
2. Review API logs
3. Verify request format
4. Contact development team

---

**Document Status**: ✅ Complete  
**Last Updated**: October 7, 2025  
**API Version**: 1.0  
**Maintained By**: Golden Config AI Team

