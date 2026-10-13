#!/bin/bash
# 4종 API를 병렬로(종류별 일일 한도가 따로) 받고, 실패 시 재시도한다.
cd "$(dirname "$0")/.."
mkdir -p data
for k in land nrg indu sh; do
  (
    for i in 1 2 3 4 5 6; do
      python -I scripts/fetch_land.py --kind "$k" --workers 2 && break
      echo "[$k] 재시도 $i" >&2
      sleep 30
    done
  ) > "data/fetch_$k.log" 2>&1 &
done
wait
echo "ALL DONE"
