# 🚀 Deployment & Testing Guide

**Version**: 1.0  
**Date**: October 7, 2025  
**Target**: Production Deployment

---

## 📋 Overview

This guide covers deploying the Golden Config AI Multi-Agent System with LLM output format to production environments.

---

## 🎯 Pre-Deployment Checklist

### **1. System Requirements**

- [ ] Python 3.9+ installed
- [ ] AWS credentials configured
- [ ] AWS Bedrock model access granted
- [ ] GitLab access token configured
- [ ] Network access to GitLab repositories
- [ ] Sufficient disk space (5GB+ recommended)

### **2. Dependencies**

```bash
# Check Python version
python --version  # Should be 3.9+

# Check AWS CLI
aws --version

# Verify AWS credentials
aws sts get-caller-identity

# Check Bedrock access
aws bedrock list-foundation-models --region us-west-2
```

### **3. Configuration Files**

- [ ] `.env` file configured
- [ ] `shared/policies.yaml` customized
- [ ] AWS region set correctly
- [ ] GitLab token valid

---

## 📦 Installation Steps

### **Step 1: Clone Repository**

```bash
# Clone the repository
cd /path/to/installation
git clone <repository-url>
cd strands-multi-agent-system
```

### **Step 2: Create Virtual Environment**

```bash
# Create venv
python3 -m venv venv

# Activate venv
source venv/bin/activate  # Linux/Mac
# OR
venv\Scripts\activate  # Windows
```

### **Step 3: Install Dependencies**

```bash
# Install Strands SDK
cd ../Strands-agent/sdk-python-main
pip install -e .
cd ../../strands-multi-agent-system

# Install project dependencies
pip install fastapi uvicorn python-dotenv pyyaml gitpython boto3
```

### **Step 4: Configure Environment**

```bash
# Copy example .env
cp .env.example .env

# Edit .env with your settings
nano .env
```

**Required Variables**:
```bash
# AWS Configuration
AWS_REGION=us-west-2
BEDROCK_MODEL_ID=anthropic.claude-3-5-sonnet-20241022-v2:0

# GitLab Configuration (if using GitLab integration)
GITLAB_TOKEN=your-token-here
DEFAULT_REPO_URL=https://gitlab.verizon.com/org/repo.git
DEFAULT_GOLDEN_BRANCH=gold
DEFAULT_DRIFT_BRANCH=drift

# Logging
LOG_LEVEL=INFO
```

### **Step 5: Create Required Directories**

```bash
# Create output directories
mkdir -p config_data/context_bundles
mkdir -p config_data/enhanced_analysis
mkdir -p config_data/llm_output
mkdir -p config_data/aggregated_results
mkdir -p config_data/reports
```

---

## 🧪 Pre-Deployment Testing

### **Test 1: Unit Tests**

```bash
# Run LLM format unit tests
python tests/test_llm_format.py
```

**Expected Output**:
```
======================================================================
🧪 UNIT TESTS - LLM Format Output
======================================================================
✅ Passed: 5
❌ Failed: 0
📊 Total: 5

🎉 All tests passed!
```

### **Test 2: Integration Tests**

```bash
# Run integration tests
python tests/test_integration_llm.py
```

**Expected Output**:
```
======================================================================
🧪 INTEGRATION TEST - LLM Output Format
======================================================================
✅ Prompt generation works
✅ Output structure validation works
✅ Expected format matches schema
✅ All required fields present

🎉 System is ready to generate LLM output format!
```

### **Test 3: Health Check**

```bash
# Start server in test mode
python main.py &
sleep 5

# Test health endpoint
curl http://localhost:3000/health

# Expected response:
# {"status":"healthy","timestamp":"...","service":"golden-config-validation"}

# Stop server
pkill -f "python main.py"
```

### **Test 4: End-to-End Validation**

```bash
# Start server
python main.py &

# Wait for server to start
sleep 5

# Trigger validation
curl -X POST http://localhost:3000/api/validate \
  -H "Content-Type: application/json" \
  -d '{
    "repo_url": "https://gitlab.verizon.com/saja9l7/golden_config.git",
    "golden_branch": "gold",
    "drift_branch": "drift"
  }'

# Check LLM output was generated
ls -lh config_data/llm_output/

# Fetch LLM output via API
curl http://localhost:3000/api/llm-output | jq '.'

# Stop server
pkill -f "python main.py"
```

**Expected Files**:
```
config_data/
├── context_bundles/context_bundle_TIMESTAMP.json
├── enhanced_analysis/enhanced_analysis_TIMESTAMP.json
├── llm_output/llm_output_TIMESTAMP.json  ← NEW!
├── aggregated_results/aggregated_TIMESTAMP.json
└── reports/validation_report_TIMESTAMP.md
```

---

## 🚀 Deployment Options

### **Option 1: Standalone Service (Development)**

```bash
# Start server manually
python main.py

# Server runs on http://localhost:3000
# Access UI at http://localhost:3000
```

### **Option 2: Systemd Service (Production)**

Create systemd service file:

```bash
sudo nano /etc/systemd/system/golden-config-ai.service
```

**Service Configuration**:
```ini
[Unit]
Description=Golden Config AI Multi-Agent System
After=network.target

[Service]
Type=simple
User=your-user
WorkingDirectory=/path/to/strands-multi-agent-system
Environment="PATH=/path/to/strands-multi-agent-system/venv/bin"
ExecStart=/path/to/strands-multi-agent-system/venv/bin/python main.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**Enable and Start Service**:
```bash
# Reload systemd
sudo systemctl daemon-reload

# Enable service (auto-start on boot)
sudo systemctl enable golden-config-ai

# Start service
sudo systemctl start golden-config-ai

# Check status
sudo systemctl status golden-config-ai

# View logs
sudo journalctl -u golden-config-ai -f
```

### **Option 3: Docker Container**

**Dockerfile**:
```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Create output directories
RUN mkdir -p config_data/context_bundles \
    config_data/enhanced_analysis \
    config_data/llm_output \
    config_data/aggregated_results \
    config_data/reports

# Expose port
EXPOSE 8000

# Run application
CMD ["python", "main.py"]
```

**Build and Run**:
```bash
# Build image
docker build -t golden-config-ai:latest .

# Run container (change host port as needed, container port should match PORT env var)
docker run -d \
  --name golden-config-ai \
  -p 3000:3000 \
  -v $(pwd)/config_data:/app/config_data \
  -e AWS_REGION=us-west-2 \
  -e GITLAB_TOKEN=your-token \
  -e PORT=3000 \
  golden-config-ai:latest

# Check logs
docker logs -f golden-config-ai

# Stop container
docker stop golden-config-ai
```

### **Option 4: Gunicorn + Nginx (Production)**

**Install Gunicorn**:
```bash
pip install gunicorn
```

**Start with Gunicorn**:
```bash
# Note: Set PORT env var to change the port (defaults to 3000)
gunicorn main:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:3000 \
  --timeout 300 \
  --access-logfile logs/access.log \
  --error-logfile logs/error.log
```

**Nginx Configuration**:
```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 300;
    }

    # Serve static files
    location /static/ {
        alias /path/to/strands-multi-agent-system/api/templates/;
    }
}
```

---

## 📊 Monitoring & Logging

### **Log Files**

```bash
# Application logs (console output)
tail -f logs/app.log

# Agent-specific logs
tail -f logs/supervisor.log
tail -f logs/config_collector.log
tail -f logs/diff_engine.log
```

### **Health Monitoring**

```bash
# Continuous health check
watch -n 5 'curl -s http://localhost:3000/health | jq .'

# Monitor validation status
watch -n 10 'curl -s http://localhost:3000/api/validation-status | jq .'
```

### **Metrics to Track**

1. **System Metrics**:
   - CPU usage
   - Memory usage
   - Disk usage (config_data/ directory)

2. **Application Metrics**:
   - Request count
   - Response times
   - Error rates
   - Validation duration

3. **Business Metrics**:
   - Total validations
   - High-risk drifts detected
   - Policy violations
   - LLM API calls
   - Token usage

### **Prometheus Integration** (Optional)

```python
# Add to main.py
from prometheus_client import Counter, Histogram, generate_latest

# Metrics
validation_counter = Counter('validations_total', 'Total validations')
validation_duration = Histogram('validation_duration_seconds', 'Validation duration')

# Endpoint
@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type="text/plain")
```

---

## 🔐 Security Considerations

### **1. API Security**

```python
# Add authentication middleware
from fastapi import Security, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer()

@app.post("/api/validate")
async def validate(
    request: ValidationRequest,
    credentials: HTTPAuthorizationCredentials = Security(security)
):
    # Verify token
    if credentials.credentials != os.getenv("API_KEY"):
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    # ... validation logic ...
```

### **2. File Permissions**

```bash
# Restrict access to config_data/
chmod 750 config_data/
chmod 640 config_data/*/*.json

# Restrict .env file
chmod 600 .env
```

### **3. Network Security**

- Use HTTPS in production (Let's Encrypt + Nginx)
- Implement rate limiting
- Restrict API access to internal network
- Use VPN for remote access

### **4. Secrets Management**

```bash
# Use AWS Secrets Manager for sensitive data
aws secretsmanager create-secret \
  --name golden-config/gitlab-token \
  --secret-string "your-token-here"

# Retrieve in code
import boto3
secret = boto3.client('secretsmanager').get_secret_value(SecretId='golden-config/gitlab-token')
```

---

## 🔄 Backup & Recovery

### **Backup Strategy**

```bash
# Daily backup script
#!/bin/bash
BACKUP_DIR="/backup/golden-config"
DATE=$(date +%Y%m%d)

# Backup output files
tar -czf "$BACKUP_DIR/config_data_$DATE.tar.gz" config_data/

# Backup configuration
cp .env "$BACKUP_DIR/.env_$DATE"
cp shared/policies.yaml "$BACKUP_DIR/policies_$DATE.yaml"

# Cleanup old backups (keep 30 days)
find "$BACKUP_DIR" -name "*.tar.gz" -mtime +30 -delete
```

### **Recovery**

```bash
# Restore from backup
tar -xzf /backup/golden-config/config_data_20251007.tar.gz -C ./

# Restore configuration
cp /backup/golden-config/.env_20251007 .env
cp /backup/golden-config/policies_20251007.yaml shared/policies.yaml
```

---

## 🧪 Post-Deployment Verification

### **Verification Checklist**

- [ ] Service is running
- [ ] Health endpoint responds
- [ ] UI loads successfully
- [ ] Validation completes successfully
- [ ] LLM output file generated
- [ ] API endpoints accessible
- [ ] Logs are being written
- [ ] No errors in logs

### **Verification Commands**

```bash
# 1. Check service status
systemctl status golden-config-ai

# 2. Test health endpoint
curl http://localhost:3000/health

# 3. Test UI
curl http://localhost:3000 | grep "Golden Config"

# 4. Run validation
curl -X POST http://localhost:3000/api/validate \
  -H "Content-Type: application/json" \
  -d '{"repo_url":"...","golden_branch":"gold","drift_branch":"drift"}'

# 5. Verify LLM output
curl http://localhost:3000/api/llm-output | jq '.data.high | length'

# 6. Check logs
journalctl -u golden-config-ai --since "5 minutes ago"
```

---

## 📈 Performance Tuning

### **1. Increase Worker Count**

```bash
# For Gunicorn
gunicorn main:app \
  --workers 8 \  # Increase workers (2-4 * CPU cores)
  --worker-class uvicorn.workers.UvicornWorker
```

### **2. Enable Caching**

```python
# Add caching for LLM output
from functools import lru_cache

@lru_cache(maxsize=100)
def get_llm_output(file_hash):
    # ... load from file ...
    pass
```

### **3. Optimize AI Calls**

- Batch size: Keep at 10 deltas per batch
- Max tokens: 8000 (increased for larger outputs)
- Model selection: Use Haiku for faster analysis

### **4. Database for Results** (Future Enhancement)

Consider moving from file-based to database storage:
- PostgreSQL for results
- Redis for caching
- S3 for archival

---

## 🐛 Troubleshooting

### **Common Issues**

#### **1. Service Won't Start**

```bash
# Check logs
journalctl -u golden-config-ai -n 50

# Common causes:
# - Port 8000 already in use
# - Missing dependencies
# - Invalid .env configuration
```

#### **2. LLM Output Not Generated**

```bash
# Check Diff Engine logs
grep "LLM output saved" logs/diff_engine.log

# Verify AI is being called
grep "Calling AI for LLM format analysis" logs/diff_engine.log

# Check for errors
grep "ERROR" logs/diff_engine.log
```

#### **3. API Returns 404 for /api/llm-output**

```bash
# Verify output files exist
ls -l config_data/llm_output/

# If empty, run validation first
curl -X POST http://localhost:3000/api/validate -H "Content-Type: application/json" -d '{...}'
```

#### **4. High Memory Usage**

```bash
# Monitor memory
watch -n 1 'ps aux | grep python | grep main.py'

# Reduce workers
# Implement result cleanup (delete old files)
find config_data/ -name "*.json" -mtime +7 -delete
```

---

## 📞 Support & Maintenance

### **Regular Maintenance Tasks**

1. **Daily**:
   - Check service health
   - Monitor logs for errors
   - Review validation results

2. **Weekly**:
   - Backup config_data/
   - Clean old output files
   - Update policies if needed

3. **Monthly**:
   - Review performance metrics
   - Update dependencies
   - Test disaster recovery

### **Getting Help**

1. Check logs first
2. Review documentation
3. Run tests to isolate issue
4. Contact development team

---

## 🎓 Training & Documentation

### **For System Administrators**

- Review this guide thoroughly
- Understand backup/recovery procedures
- Know how to restart service
- Monitor system health

### **For Developers**

- Read `docs/LLM_OUTPUT_FORMAT.md`
- Review `docs/API_REFERENCE.md`
- Run unit and integration tests
- Understand agent architecture

### **For End Users**

- Access UI documentation
- Learn API endpoints
- Understand drift categories
- Review policy rules

---

## 📋 Deployment Checklist Summary

```
Pre-Deployment:
☐ System requirements met
☐ Dependencies installed
☐ Configuration files ready
☐ Unit tests pass
☐ Integration tests pass
☐ End-to-end test successful

Deployment:
☐ Service installed
☐ Service started
☐ Health check passes
☐ UI accessible
☐ API endpoints working

Post-Deployment:
☐ Monitoring configured
☐ Logs being captured
☐ Backup strategy implemented
☐ Security measures applied
☐ Team trained
☐ Documentation reviewed
```

---

**Document Status**: ✅ Complete  
**Last Updated**: October 7, 2025  
**Next Review**: October 7, 2026  
**Maintained By**: Golden Config AI Team

