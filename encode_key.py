import base64
import json

# Read the actual credentials from your JSON file
with open('<your-gcp-json-key.json>', 'r') as f:
    creds = json.load(f)

# Encode to base64
encoded = base64.b64encode(json.dumps(creds).encode()).decode()
print("Add this to your secrets.toml:")
print(f'ENCODED_CREDS = "{encoded}"') 