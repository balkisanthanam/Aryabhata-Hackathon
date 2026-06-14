#!/bin/bash
# Test Azure Function with curl
# Works on Linux, Mac, Windows (Git Bash/WSL)

FUNCTION_URL="${AZURE_FUNCTION_URL:-<FUNCTION_URL>}"
FUNCTION_KEY="${AZURE_FUNCTION_KEY:-<FUNCTION_KEY>}"
PAYLOAD_FILE="payload.json"

echo "Testing Azure Function with curl"
echo "================================="
echo "URL: $FUNCTION_URL"
echo "Payload: $PAYLOAD_FILE"
echo ""

if [ ! -f "$PAYLOAD_FILE" ]; then
    echo "Error: $PAYLOAD_FILE not found!"
    echo "Create it first with: python create_curl_payload.py <image_path>"
    exit 1
fi

if [ "$FUNCTION_URL" = "<FUNCTION_URL>" ] || [ "$FUNCTION_KEY" = "<FUNCTION_KEY>" ]; then
    echo "Set AZURE_FUNCTION_URL and AZURE_FUNCTION_KEY before running this script."
    exit 1
fi

echo "Sending request..."
echo ""

curl -X POST "${FUNCTION_URL}?code=${FUNCTION_KEY}" \
     -H "Content-Type: application/json" \
     -d @"${PAYLOAD_FILE}" \
     -w "\n\nHTTP Status: %{http_code}\n" \
     -o response.json \
     --max-time 300

echo ""
echo "Response saved to: response.json"
echo ""
echo "Response preview:"
cat response.json | head -50
