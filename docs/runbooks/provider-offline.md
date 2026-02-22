# Runbook: Provider Offline

## Overview
This runbook guides you through diagnosing and resolving provider offline issues.

## Symptoms
- Provider status shows `offline` or `connection_failed`
- Reason codes: `PROVIDER_OFFLINE`, `connection_failed`, `no_endpoint`, `http_error`
- API requests to provider fail with connection errors

## Common Causes
1. Provider service not running (Ollama, vLLM) or ONNX runtime not ready
2. Incorrect endpoint configuration
3. Network connectivity issues
4. Provider service crashed or hung

## Diagnostic Steps

### 1. Check Provider Status
```bash
curl http://localhost:8000/api/v1/providers/{provider_name}/status
```

### 2. Verify Service is Running

**For Ollama:**
```bash
# Check if Ollama is running
curl http://localhost:11434/api/tags

# Check process
ps aux | grep ollama

# Check logs
journalctl -u ollama -n 50
```

**For vLLM:**
```bash
# Check if vLLM is running
curl http://localhost:8001/health

# Check process
ps aux | grep vllm

# Check logs
tail -f logs/vllm.log
```

**For Cloud Providers (OpenAI, Google):**
```bash
# Verify API key is set
echo $OPENAI_API_KEY
echo $GOOGLE_API_KEY

# Test API directly
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer $OPENAI_API_KEY"
```

### 3. Check Network Connectivity
```bash
# Test localhost connectivity (for local providers)
ping localhost
nc -zv localhost 11434  # Ollama
nc -zv localhost 8001   # vLLM

# Test cloud API connectivity
curl -I https://api.openai.com
curl -I https://generativelanguage.googleapis.com
```

### 4. Review Configuration
```bash
# Check environment variables
cat .env | grep -E "VLLM_ENDPOINT|OLLAMA|OPENAI|GOOGLE"

# Check config from API
curl http://localhost:8000/api/v1/config/runtime
```

## Resolution Steps

### For Local Providers (Ollama, vLLM, ONNX)

**Option 1: Restart Service**
```bash
# Ollama
make ollama-restart

# vLLM
make vllm-restart
```

**ONNX note (in-process):**
- ONNX does not expose a standalone daemon to restart.
- Verify ONNX readiness instead:
```bash
curl http://localhost:8000/api/v1/system/llm-servers | jq '.servers[] | select(.name=="onnx")'
```
- If `status` is not `online`, validate ONNX LLM profile install and model path configuration.

**Option 2: Check Configuration**
1. Verify endpoint in `.env`:
   - `VLLM_ENDPOINT=http://127.0.0.1:8001`
2. Restart application:
   ```bash
   make restart
   ```

**Option 3: Start Service if Not Running**
```bash
# Ollama
make ollama-start

# vLLM
make vllm-start
```

### For Cloud Providers (OpenAI, Google)

**Option 1: Configure API Key**
1. Edit `.env` file:
   ```bash
   OPENAI_API_KEY=sk-...
   GOOGLE_API_KEY=AI...
   ```
2. Restart application:
   ```bash
   make restart
   ```

**Option 2: Verify API Key via UI**
1. Navigate to `/config` in web UI
2. Check provider configuration panel
3. Click "Test Connection"
4. Follow recovery hints if validation fails

### For Endpoint Configuration Issues

**Option 1: Update Endpoint**
1. Edit `.env`:
   ```bash
   VLLM_ENDPOINT=http://correct-host:port
   ```
2. Restart:
   ```bash
   make restart
   ```

**Option 2: Use UI**
1. Navigate to `/config`
2. Update provider endpoint
3. Click "Test Connection"
4. Save if successful

## Prevention
1. **Health Monitoring**: Enable provider health checks (already active)
2. **Auto-restart**: Configure systemd or docker restart policies
3. **Fallback**: Enable automatic fallback to alternative providers
4. **Alerts**: Configure alert notifications for provider offline events

## Escalation
If provider remains offline after these steps:
1. Check system resources (disk, memory, CPU)
2. Review application logs: `logs/backend.log`
3. Check for known issues in provider documentation
4. Contact support with:
   - Provider name
   - Error messages from logs
   - Steps already attempted
   - System environment details

## Related Runbooks
- [Auth Failures](./auth-failures.md)
- [Latency Spike](./latency-spike.md)
- [Budget Exhaustion](./budget-exhaustion.md)

## Verification
After resolution, verify:
1. Provider status shows `connected`:
   ```bash
   curl http://localhost:8000/api/v1/providers/{provider_name}/status
   ```
2. Test inference request succeeds
3. No alerts for this provider
