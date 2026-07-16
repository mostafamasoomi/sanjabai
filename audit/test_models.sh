#!/bin/bash
# Model audit test script
TOKEN="Z-4O4bPgHz0CEkaLqfaSyDf3E0PptLJ2wqi2vL363Io"
BASE="http://127.0.0.1:8081"
OUTDIR="/root/multiai/audit"
mkdir -p "$OUTDIR"

# All bynara models (12)
BYNARA_MODELS=(
  "agnes-2.0-flash"
  "agnes-2.5-flash"
  "gemini-3.5-flash"
  "mimo-v2.5"
  "mimo-v2.5-pro"
  "mimo-v2.5-pro-ultraspeed"
  "mistral-large"
  "mistral-medium-3-5"
  "tencent-hy3"
  "grok-4.5"
  "glm-5.2-free"
  "kimi-k2.7-code-free"
)

# Representative openrouter models (30+)
OPENROUTER_MODELS=(
  "openai/gpt-5.6-luna"
  "openai/gpt-5.5"
  "openai/gpt-5"
  "openai/gpt-4o"
  "openai/gpt-4o-mini"
  "openai/gpt-3.5-turbo"
  "openai/o3-mini"
  "openai/o4-mini"
  "anthropic/claude-sonnet-5"
  "anthropic/claude-opus-4.8"
  "anthropic/claude-haiku-4.5"
  "anthropic/claude-sonnet-4"
  "google/gemini-3.5-flash"
  "google/gemini-2.5-flash"
  "google/gemini-2.5-pro"
  "deepseek/deepseek-v4-pro"
  "deepseek/deepseek-chat"
  "deepseek/deepseek-r1"
  "x-ai/grok-4.5"
  "qwen/qwen3.7-max"
  "qwen/qwen3.6-plus"
  "qwen/qwen3-coder"
  "mistralai/mistral-large-2512"
  "mistralai/mistral-medium-3-5"
  "mistralai/mistral-small-3.2-24b-instruct"
  "meta-llama/llama-4-maverick"
  "meta-llama/llama-3.3-70b-instruct"
  "nousresearch/hermes-4-405b"
  "nousresearch/hermes-3-llama-3.1-70b"
  "perplexity/sonar-pro"
  "cohere/command-a"
  "openrouter/auto"
)

echo "===== BYNARA MODELS ====="
for model in "${BYNARA_MODELS[@]}"; do
  result=$(curl -s -w "\n%{http_code}" -X POST "$BASE/v1/chat/completions" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"model\":\"$model\",\"messages\":[{\"role\":\"user\",\"content\":\"say hi\"}],\"max_tokens\":10}" 2>&1)
  http_code=$(echo "$result" | tail -1)
  body=$(echo "$result" | head -n -1)
  
  if [ "$http_code" = "200" ]; then
    echo "WORKING: $model (200)"
  elif [ "$http_code" = "429" ]; then
    echo "QUOTA_EXCEEDED: $model (429)"
  else
    # Check for specific error in body
    err_type=$(echo "$body" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('error',{}).get('code','unknown'))" 2>/dev/null || echo "parse_error")
    echo "BROKEN_${http_code}: $model (code=$err_type)"
  fi
done

echo ""
echo "===== OPENROUTER MODELS ====="
for model in "${OPENROUTER_MODELS[@]}"; do
  result=$(curl -s -w "\n%{http_code}" -X POST "$BASE/v1/chat/completions" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"model\":\"$model\",\"messages\":[{\"role\":\"user\",\"content\":\"say hi\"}],\"max_tokens\":10}" 2>&1)
  http_code=$(echo "$result" | tail -1)
  body=$(echo "$result" | head -n -1)
  
  if [ "$http_code" = "200" ]; then
    echo "WORKING: $model (200)"
  elif [ "$http_code" = "429" ]; then
    echo "QUOTA_EXCEEDED: $model (429)"
  else
    err_type=$(echo "$body" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('error',{}).get('code','unknown'))" 2>/dev/null || echo "parse_error")
    echo "BROKEN_${http_code}: $model (code=$err_type)"
  fi
done

echo ""
echo "===== DONE ====="