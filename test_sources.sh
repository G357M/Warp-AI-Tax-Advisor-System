#!/bin/bash
echo "Testing API sources..."
curl -s -X POST https://tax-advisor.ge/api/v1/public/query \
  -H "Content-Type: application/json" \
  -d '{"query":"რა არის დღგ?","language":"ka"}' | python3 -c "
import sys, json

data = json.load(sys.stdin)
print(f'Retrieved count: {data.get(\"retrieved_count\", 0)}')
print(f'Sources count: {len(data.get(\"sources\", []))}')
print()

sources = data.get('sources', [])
for i, source in enumerate(sources[:3], 1):
    print(f'Source {i}:')
    print(f'  text: {source.get(\"text\", \"N/A\")[:80]}...')
    print(f'  relevance: {source.get(\"relevance\", 0)}')
    metadata = source.get('metadata', {})
    print(f'  metadata.source_url: {metadata.get(\"source_url\", \"NOT FOUND\")}')
    print(f'  metadata.document_type: {metadata.get(\"document_type\", \"NOT FOUND\")}')
    print(f'  metadata.title: {metadata.get(\"title\", \"NOT FOUND\")}')
    print()
"
