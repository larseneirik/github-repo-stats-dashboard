import base64
import json

# Read the credentials file
with open('.streamlit/secrets.toml', 'r') as f:
    creds_text = f.read()

# Extract the JSON part
start = creds_text.find('{')
end = creds_text.rfind('}') + 1
creds_json = creds_text[start:end]

# Encode the JSON
encoded = base64.b64encode(creds_json.encode()).decode()
print("Add this to your secrets.toml or Streamlit Cloud secrets:")
print(f'ENCODED_CREDS = "{encoded}"') 