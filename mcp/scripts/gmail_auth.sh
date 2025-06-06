#!/bin/bash

DESTINATION_PATH="/root/.gmail-mcp"
PYTHON_SCRIPT_NAME="gmail_auth.py"
AUTH_PATH= "${DESTINATION_PATH}/gcp-oauth.keys.json"
cat "${AUTH_PATH}"
cd "/root/.gmail-mcp/"


      
pip install --upgrade google-api-python-client google-auth-oauthlib google-auth-httplib2

python "${PYTHON_SCRIPT_NAME}"

