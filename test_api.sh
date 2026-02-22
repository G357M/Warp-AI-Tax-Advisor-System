#!/bin/bash
echo "Testing API endpoint..."
echo ""

# Test 1: Simple query
echo "Test 1: Simple query 'test'"
curl -s -X POST https://tax-advisor.ge/api/v1/public/query \
  -H "Content-Type: application/json" \
  -d '{"query":"test","language":"ka"}' | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(f'Retrieved count: {data.get(\"retrieved_count\", 0)}')
print(f'Sources count: {len(data.get(\"sources\", []))}')
if data.get('sources'):
    print(f'First source title: {data[\"sources\"][0].get(\"text\", \"N/A\")}')
"

echo ""
echo "Test 2: Georgian query 'რა არის დღგ?'"
curl -s -X POST https://tax-advisor.ge/api/v1/public/query \
  -H "Content-Type: application/json" \
  -d '{"query":"რა არის დღგ?","language":"ka"}' | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(f'Retrieved count: {data.get(\"retrieved_count\", 0)}')
print(f'Sources count: {len(data.get(\"sources\", []))}')
if data.get('sources'):
    print(f'First source title: {data[\"sources\"][0].get(\"text\", \"N/A\")}')
    print(f'First source URL: {data[\"sources\"][0].get(\"metadata\", {}).get(\"source_url\", \"N/A\")}')
"
