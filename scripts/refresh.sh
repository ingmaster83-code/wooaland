#!/bin/bash
# 월간 갱신: ① 최근 2개월 재수집(recent) → ② 확정 월 이력 보강(fill-hist) → ③ 법정동 단위 집계(process_land).
# 종류별 일일 호출 한도가 따로라 상업업무용·공장창고·단독다가구 3종을 병렬로 받는다. 하나라도 실패하면 비정상 종료해 빌드·배포를 막는다(기존 배포 유지).
# 토지 매매 API 는 일일 한도가 1,000회라 배포에서는 호출하지 않고, update-land-hist 워크플로가 커밋해 둔 스냅샷(_rawdata/land_recent)과 이력(_rawdata/land_hist)을 쓴다.
set -u
cd "$(dirname "$0")/.."
mkdir -p data
KINDS="nrg indu sh"
declare -A PID
for k in $KINDS; do
  (
    python scripts/fetch_land.py --kind "$k" --mode recent &&
    python scripts/fetch_land.py --kind "$k" --mode fill-hist
  ) > "data/fetch_$k.log" 2>&1 &
  PID[$k]=$!
done
FAIL=0
for k in $KINDS; do
  wait "${PID[$k]}" || { echo "[$k] 수집 실패"; FAIL=1; }
  echo "=== $k ==="
  tail -n 6 "data/fetch_$k.log"
done
echo "=== land: 스냅샷 $(ls _rawdata/land_recent/land_*.json.gz 2>/dev/null | wc -l)개 / 이력 $(ls _rawdata/land_hist/land_*.json.gz 2>/dev/null | wc -l)개 사용(API 호출 없음) ==="
[ "$FAIL" = "0" ] || exit 1
python scripts/process_land.py 3
