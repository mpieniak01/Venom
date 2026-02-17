# Runbook: Authentication Failures

## Overview
This runbook addresses authentication and credential-related failures with AI providers.

## Symptoms
- Provider status shows `offline` with reason code `AUTH_ERROR`, `missing_api_key`, or `invalid_credentials`
- Authentication errors in logs
- 401/403 HTTP errors from cloud providers

## Common Causes
1. API key not configured
2. Invalid or expired API key
3. API key revoked or suspended
4. Incorrect environment variable name
5. API key not loaded after configuration change

## Diagnostic Steps

### 1. Check Provider Credential Status
```bash
# Via API
curl http://localhost:8000/api/v1/governance/status

# Check specific provider
curl http://localhost:8000/api/v1/providers/{provider_name}/status
```

### 2. Verify Environment Variables

**OpenAI:**
```bash
echo $OPENAI_API_KEY
# Should start with "sk-"
```

**Google:**
```bash
echo $GOOGLE_API_KEY
# Should start with "AI"
```

### 3. Check `.env` File
```bash
cat .env | grep -E "OPENAI_API_KEY|GOOGLE_API_KEY"
```

### 4. Test API Key Directly

**OpenAI:**
```bash
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer $OPENAI_API_KEY"
```

**Google:**
```bash
curl "https://generativelanguage.googleapis.com/v1beta/models?key=$GOOGLE_API_KEY"
```

### 5. Check Audit Log
```bash
# Check recent auth failures
curl "http://localhost:8000/api/v1/admin/audit?action=test_connection&limit=10"
```

## Resolution Steps

### For Missing API Key

**Option 1: Configure via Environment**
1. Edit `.env` file:
   ```bash
   # For OpenAI
   OPENAI_API_KEY=sk-your-key-here

   # For Google
   GOOGLE_API_KEY=AIza-your-key-here
   ```
2. Restart application:
   ```bash
   make restart
   ```

**Option 2: Configure via UI**
1. Navigate to `/config` in web UI
2. Find provider configuration section
3. Enter API key in secure input field
4. Click "Test Connection" to verify
5. Save configuration

### For Invalid/Expired API Key

**Option 1: Generate New Key**
1. **OpenAI**: Visit https://platform.openai.com/api-keys
   - Click "Create new secret key"
   - Copy the key immediately (shown only once)
   - Update `.env` or UI config

2. **Google**: Visit https://makersuite.google.com/app/apikey
   - Create new API key
   - Copy the key
   - Update `.env` or UI config

**Option 2: Verify Key Format**
- OpenAI keys must start with `sk-`
- Google keys must start with `AIza`
- No extra spaces or quotes in `.env` file
- Proper format: `OPENAI_API_KEY=sk-abc123` (no quotes)

### For Credential Not Loaded

**Option 1: Force Reload**
```bash
# Restart backend
make api-stop
make api-start

# Or restart everything
make restart
```

**Option 2: Clear Cache**
```bash
# Stop services
make stop

# Clear any cached credentials
rm -rf workspace/cache

# Start services
make start
```

## Prevention

### 1. Secure Key Storage
- Never commit API keys to git
- Use `.env` file (excluded in `.gitignore`)
- Consider using secrets manager in production

### 2. Key Rotation
- Rotate keys regularly (quarterly recommended)
- Document key rotation procedure
- Test new keys before revoking old ones

### 3. Monitoring
- Enable credential status checks
- Configure alerts for auth failures
- Review audit log regularly

### 4. Fallback Configuration
- Configure multiple providers
- Enable automatic fallback on auth errors:
  ```bash
  # In .env or UI
  ENABLE_AUTH_FALLBACK=true
  ```

## Troubleshooting Edge Cases

### API Key Works Manually But Fails in App
1. Check for trailing whitespace in `.env`
2. Verify environment variable is exported:
   ```bash
   env | grep -E "OPENAI|GOOGLE"
   ```
3. Check file encoding (should be UTF-8, no BOM)

### Different Behavior After Update
1. Check if API key format changed
2. Review provider API documentation for changes
3. Check application logs for deprecation warnings

### Intermittent Auth Failures
1. Check rate limiting (may appear as auth error)
2. Verify API key hasn't hit usage limits
3. Check provider status page for outages

## Escalation
If authentication continues to fail:
1. Verify API key status in provider dashboard
2. Check billing/payment status (may cause auth errors)
3. Review provider service status page
4. Contact provider support with:
   - API key ID (not the actual key)
   - Error messages from logs
   - Timestamp of failures
   - Request IDs if available

## Related Runbooks
- [Provider Offline](./provider-offline.md)
- [Budget Exhaustion](./budget-exhaustion.md)

## Verification
After resolution:
1. Test connection via UI or API:
   ```bash
   curl -X POST http://localhost:8000/api/v1/providers/{provider_name}/test-connection
   ```
2. Verify provider status shows `connected`
3. Test actual inference request
4. Check audit log shows successful test
