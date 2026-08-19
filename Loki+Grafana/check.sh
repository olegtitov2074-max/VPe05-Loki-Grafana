#!/bin/bash
NOW=$(date +%s)
START=$((NOW - 300))
echo "=== Логи crypto-backend за последние 5 минут ==="
curl -s -G "http://localhost:3100/loki/api/v1/query_range" \
  --data-urlencode 'query={container="crypto-backend"}' \
  --data-urlencode 'limit=3' \
  --data-urlencode "start=$START" \
  --data-urlencode "end=$NOW" | python3 -c "
import json,sys
d=json.load(sys.stdin)
print('status:', d.get('status'))
results = d.get('data',{}).get('result',[])
print('streams found:', len(results))
for r in results:
    for v in r.get('values',[]):
        print(v[1][:200])
"