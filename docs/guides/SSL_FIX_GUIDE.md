# SSL Certificate Error Fix Guide

## Problem
SSL certificate verification errors when submitting to Kaggle API:
```
SSLError(SSLCertVerificationError(1, '[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: self-signed certificate in certificate chain
```

## Solutions

### Solution 1: Disable SSL Verification (Quick Fix - NOT for Production)
Add this to your environment before running:
```bash
export CURL_CA_BUNDLE=""
export REQUESTS_CA_BUNDLE=""
export PYTHONWARNINGS="ignore:Unverified HTTPS request"
```

Or in Python code (add to kim.py):
```python
import ssl
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# In the submit_predictions method
import requests
requests.packages.urllib3.disable_warnings()
```

### Solution 2: Use System Certificates (Recommended)
```bash
# On macOS, update certificates
brew install ca-certificates
export REQUESTS_CA_BUNDLE=$(brew --prefix)/etc/ca-certificates/cert.pem
```

### Solution 3: Configure Kaggle API with Proxy
If behind a corporate proxy, create/update `~/.kaggle/kaggle.json`:
```json
{
    "username": "your_username",
    "key": "your_api_key",
    "proxy": "http://your_proxy:port",
    "ssl_ca_cert": "/path/to/your/certificate.pem"
}
```

### Solution 4: Set Environment Variable for Python
```bash
# Find Python's certificate bundle
python -m certifi

# Export it
export SSL_CERT_FILE=$(python -m certifi)
export REQUESTS_CA_BUNDLE=$(python -m certifi)
```

### Solution 5: Update pip/requests certificates
```bash
# Update pip certificates
pip install --upgrade certifi

# Or with uv
uv add --upgrade certifi
```

## Testing the Fix

After applying a solution, test with:
```bash
# Test Kaggle API directly
uv run python -c "from kaggle.api.kaggle_api_extended import KaggleApi; api = KaggleApi(); api.authenticate(); print('Success!')"

# Or test full system
uv run python main.py
```

## Note for auto_kaggler

Since the crawler successfully downloads data, the SSL issue only affects the submission step. You can:
1. Run experiments without submissions (data analysis only)
2. Set `simulation_mode: true` in config.json to skip real submissions
3. Apply one of the fixes above for full functionality

The SSL error doesn't affect the crawler integration - only the final submission to Kaggle.