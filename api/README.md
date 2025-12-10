# API & Web UI

This directory contains the web interface and server endpoints for the Golden Config AI multi-agent system.

---

## 📁 Contents

```
api/
├── templates/
│   ├── overview.html       # Enterprise services overview dashboard
│   ├── service-detail.html # Service-specific analysis dashboard
│   └── [legacy templates]  # Archived for reference
└── README.md               # This file
```

---

## 🌐 Web UI

### Enterprise Multi-Service Dashboard

A modern, enterprise-level web interface for managing multiple services with configuration drift analysis.

**Architecture:**
- **Overview Dashboard** (`/`) - View all configured services at a glance
- **Service Detail Pages** (`/service/{service_id}`) - Detailed analysis for each service

**Features:**
- ✅ **Multi-service management** - Monitor multiple services from one dashboard
- ✅ **Service-specific analysis** - Each service has its own detailed view
- ✅ **Real-time status** - See current health and issues for all services
- ✅ **On-demand analysis** - Trigger analysis for any service with one click
- ✅ **Persistent results** - Results stored and retrieved across sessions
- ✅ **Risk assessment** - Visual indicators for policy violations and risk levels
- ✅ **Professional design** - Clean, enterprise-grade interface

**Access:**
- **Production Server:** http://localhost:3000 (configurable via PORT env var)

**Current Services:**
- **CXP Ordering Services** - `/service/cxp_ordering_services`
- **CXP Credit Services** - `/service/cxp_credit_services`

---

## 🚀 Running the Servers

### Production Server (`main.py`)

**Complete multi-agent orchestration:**
```bash
cd strands-multi-agent-system
python main.py
```

**Features:**
- Full Supervisor orchestration
- Config Collector + Diff Engine
- Real GitLab repository analysis
- File-based communication
- Port: 3000

### Test Server (`agent_analysis_server.py`)

**Single-agent testing:**
```bash
cd strands-multi-agent-system
python agent_analysis_server.py
```

**Features:**
- Direct Diff Engine testing
- Local test data analysis
- Quick iteration
- Port: 8002

**Both servers use the same UI!**

---

## 📡 API Endpoints

### Production Server (localhost:3000)

#### UI Routes
- `GET /` - Services overview dashboard
- `GET /service/{service_id}` - Service-specific detail dashboard
  - Example: `/service/cxp_ordering_services`
  - Example: `/service/cxp_credit_services`

#### Services API
- `GET /api/services` - Get all configured services with status
  ```json
  {
    "services": [
      {
        "id": "cxp_ordering_services",
        "name": "CXP Ordering Services",
        "status": "healthy",
        "last_check": "2025-10-12T10:30:00Z",
        "issues": 0,
        "repo_url": "https://gitlab.verizon.com/...",
        "golden_branch": "main",
        "drift_branch": "feature/config-update"
      }
    ],
    "total_services": 2,
    "active_issues": 0,
    "timestamp": "2025-10-12T10:30:00Z"
  }
  ```

- `POST /api/services/{service_id}/analyze` - Trigger analysis for specific service
  - Uses service's configured repository URLs and branches
  - Stores results persistently to `config_data/service_results/{service_id}/`

- `GET /api/services/{service_id}/results` - Get all stored results for a service
  - Returns list of historical analysis results

- `POST /api/services/{service_id}/import-result` - Import external analysis result
  - Useful for transferring results from other machines

#### Legacy Validation Endpoints (backward compatibility)
- `POST /api/validate` - Full validation with custom parameters
- `POST /api/analyze/quick` - Quick analysis with defaults
- `POST /api/analyze/agent` - Legacy compatibility endpoint
- `GET /api/latest-results` - Get most recent validation results
- `GET /api/validation-status` - Check if validation is running

#### System
- `GET /api/info` - Server information
- `GET /api/agent-status` - Agent system status
- `GET /health` - Health check

---

### Test Server (localhost:8002)

#### UI
- `GET /` - Main dashboard (same as production)

#### Analysis
- `POST /api/analyze/agent` - Analyze test data
  ```json
  {
    "file_types": "all"  // or "yml", "json", "properties", "xml"
  }
  ```

- `GET /api/sample-data` - Load sample analysis (uses test data)

- `GET /api/latest-results` - Get latest analysis results

#### System
- `GET /api/info` - Server information

- `GET /api/agent-status` - Agent status

- `GET /health` - Health check

---

## 🎮 Using the Web UI

### Step-by-Step Guide:

1. **Start Server**
   ```bash
   python main.py  # Production
   # OR
   python agent_analysis_server.py  # Testing
   ```

2. **Open Browser**
   - Production: http://localhost:3000
   - Testing: http://localhost:8002

3. **Run Analysis**
   - Click **"Analyze"** for default repository
   - Or click **"Load Sample Data"** for test data

4. **Wait for Results**
   - Validation takes ~1-2 minutes (production)
   - Analysis takes ~10-30 seconds (testing)

5. **Review Results**
   - View drift analysis
   - Check policy violations
   - Read recommendations
   - See risk assessment

---

## 🔧 Customizing the UI

### Modify Templates

Edit `templates/index.html` to customize:
- Branding and colors
- Layout and styling
- Feature additions
- Custom visualizations

### Add New Endpoints

Add endpoints in `main.py` or `agent_analysis_server.py`:

```python
@app.get("/api/my-custom-endpoint")
async def my_custom_endpoint():
    return {"custom": "data"}
```

---

## 🎨 UI Features

### Current Features:
- ✅ Configuration drift visualization
- ✅ Policy violation display
- ✅ Risk level indicators
- ✅ Recommendation lists
- ✅ File-by-file analysis
- ✅ Loading states
- ✅ Error handling

### Potential Enhancements:
- [ ] Chart visualizations (risk distribution, trends)
- [ ] Diff syntax highlighting
- [ ] Export to PDF/Excel
- [ ] Historical analysis comparison
- [ ] Real-time updates via WebSocket
- [ ] Multi-repository dashboard

---

## 📊 API Response Format

### Validation Response (Production):

```json
{
  "status": "success",
  "architecture": "multi_agent_supervisor",
  "agents_used": [
    "supervisor",
    "config_collector",
    "diff_policy_engine"
  ],
  "communication_method": "file_based",
  "validation_result": {
    "run_id": "run_20251004_165130_123",
    "verdict": "FAIL",
    "summary": "...",
    "execution_time_ms": 125000
  },
  "execution_time_seconds": 125.5,
  "timestamp": "2025-10-04T16:51:33.123456",
  "request_params": {
    "repo_url": "https://gitlab.verizon.com/saja9l7/golden_config.git",
    "golden_branch": "gold",
    "drift_branch": "drift",
    "target_folder": "/"
  }
}
```

### Analysis Response (Testing):

```json
{
  "status": "success",
  "analysis_type": "strands_agent_system",
  "agent_used": "DiffPolicyEngineAgent",
  "agent_status": "success",
  "processing_time_seconds": 8.5,
  "data_source": {
    "golden_path": "tests/data/golden",
    "drifted_path": "tests/data/drifted",
    "file_types_analyzed": "all"
  },
  "agent_response": {
    "task_id": "agent_analysis_1728065493",
    "status": "success",
    "result": {
      "drift_analysis": {...},
      "ai_policy_analysis": {...}
    }
  }
}
```

---

## 🔒 CORS Configuration

Both servers enable CORS for development:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Change for production!
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
```

**Production:** Restrict `allow_origins` to specific domains.

---

## 🐛 Troubleshooting

### "Template not found"
**Check:**
1. `templates/index.html` exists
2. Path in server code is correct
3. Working directory is project root

### "CORS error in browser"
**Fix:**
1. Check CORS middleware is enabled
2. Verify `allow_origins` includes your domain
3. Clear browser cache

### "API endpoint not found"
**Check:**
1. URL path is correct
2. HTTP method matches (GET vs POST)
3. Server is running
4. Port is correct (3000 vs 8002)

### "Connection refused"
**Check:**
1. Server is running
2. Correct port (3000 for main.py, 8002 for test)
3. Firewall not blocking
4. Using correct host (localhost vs 127.0.0.1)

---

## 📚 Related

- **Main Server:** `../main.py`
- **Test Server:** `../agent_analysis_server.py`
- **Main README:** `../README.md`

---

## 🔗 Technologies Used

- **FastAPI** - Modern Python web framework
- **Uvicorn** - ASGI server
- **Jinja2** - Template engine
- **HTML/CSS/JavaScript** - Frontend
- **CORS Middleware** - Cross-origin support

---

**Your gateway to the multi-agent system!** 🌐

