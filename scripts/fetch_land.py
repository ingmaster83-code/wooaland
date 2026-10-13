#!/usr/bin/env python3
"""
fetch_land.py - 국토교통부 토지·상업업무용·공장창고·단독다가구 매매 실거래 API를 시군구×월 단위로 수집한다.

종류(kind): land(토지 매매) nrg(상업업무용 매매) indu(공장·창고 등 매매) sh(단독/다가구 매매)
저장소: data/cache/{kind}/{ym}/{sgg}.json  (최근 월·로컬 캐시, gitignore)
        _rawdata/land_hist/{kind}_{ym}.json.gz  (확정된 달 — 최근 RECENT_N개월보다 오래된 달, git 에 보관: {sgg: rows})
모드(--mode)
  full       : 창(매매 36·전월세 24개월) 전체를 캐시로 받는다(로컬 부트스트랩). 받은 (월, 시군구)는 건너뛴다.
  recent     : 최근 RECENT_N개월만 캐시로 다시 받는다(신고 지연·해제 반영). 하나라도 실패하면 비정상 종료(빌드·배포 차단).
  fill-hist  : 확정된 달 중 이력(gz)이 없는 달만 받아 이력으로 저장하고, 창을 벗어난 오래된 이력은 지운다(월 1회 사실상 1개월분).
  pack-cache : 로컬 캐시의 확정된 달을 이력(gz)으로 묶는다(부트스트랩 1회).
- 일일 호출 한도(API별)에 걸리면(초당 제한과 다름) 정상 종료한다. 종류별로 따로 프로세스를 띄우면 한도가 따로 적용된다.
사용: python scripts/fetch_land.py --kind land --mode recent [--workers 2] [--max-calls 9500]
키: 환경변수 DATA_GO_KR_API_KEY (없으면 ../hosppass/.env 의 API_KEY — 로컬 전용)
"""
import argparse, gzip, json, os, sys, threading, time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

import requests

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).parent.parent
CACHE = ROOT / "data" / "cache"
HIST = ROOT / "_rawdata" / "land_hist"
SNAP = ROOT / "_rawdata" / "land_recent"   # 최근 RECENT_N개월 스냅샷(토지처럼 일일 한도가 작은 API 용: 별도 워크플로가 주기적으로 갱신해 커밋)
SGG = json.loads((ROOT / "scripts" / "sgg_codes.json").read_text(encoding="utf-8"))
RECENT_N = 2           # 빌드마다 다시 받는 최근 개월 수(신고 지연 30일 → 2개월이면 충분)
ROWS = 1000

BASE = "https://apis.data.go.kr/1613000/"
URLS = {
    "land": BASE + "RTMSDataSvcLandTrade/getRTMSDataSvcLandTrade",
    "nrg": BASE + "RTMSDataSvcNrgTrade/getRTMSDataSvcNrgTrade",
    "indu": BASE + "RTMSDataSvcInduTrade/getRTMSDataSvcInduTrade",
    "sh": BASE + "RTMSDataSvcSHTrade/getRTMSDataSvcSHTrade",
}
DEFAULT_MONTHS = {"land": 36, "nrg": 36, "indu": 36, "sh": 36}


def get_key():
    k = os.environ.get("DATA_GO_KR_API_KEY")
    if k:
        return k
    env = ROOT.parent / "hosppass" / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("API_KEY="):
                return line.split("=", 1)[1].strip()
    raise SystemExit("DATA_GO_KR_API_KEY 가 없습니다.")


KEY = get_key()
sess = requests.Session()
HTTP = [0]


class QuotaExceeded(Exception):
    pass


MIN_GAP = 0.6                 # 프로세스 전체 호출 간격(초) — 초당 요청 제한(코드 23) 회피
_gate = threading.Lock()
_next_at = [0.0]


def throttle(extra=0.0):
    """모든 스레드가 공유하는 호출 간격 제어. extra>0 이면 그만큼 전체를 멈춘다(초당 제한에 걸린 뒤 냉각)."""
    with _gate:
        now = time.time()
        if extra:
            _next_at[0] = max(_next_at[0], now + extra)
        wait = _next_at[0] - now
        _next_at[0] = max(_next_at[0], now) + MIN_GAP
    if wait > 0:
        time.sleep(wait)


def txt(it, tag):
    e = it.find(tag)
    return (e.text or "").strip() if e is not None and e.text else ""


def num(s, f=float):
    try:
        return f(str(s).replace(",", "").strip())
    except ValueError:
        return 0


def parse_items(root, kind):
    """행 형식 (모두 앞 4칸 공통: 법정동, 지번(가려짐), ymd, 해제여부)
    land : [umd, jibun, ymd, cancel, 거래면적㎡, 금액(만원), 지목, 용도지역, 거래유형, 지분거래]
    nrg/indu : [umd, jibun, ymd, cancel, 건물면적㎡, 대지면적㎡, 금액, 준공연도, 건물유형(일반/집합), 건물용도, 용도지역, 층, 거래유형, 매수자구분, 매도자구분, 지분거래]
    sh   : [umd, jibun, ymd, cancel, 연면적㎡, 대지면적㎡, 금액, 준공연도, 주택유형(단독/다가구), 거래유형, 매수자구분, 매도자구분]"""
    rows = []
    for it in root.iter("item"):
        ymd = num(txt(it, "dealYear"), int) * 10000 + num(txt(it, "dealMonth"), int) * 100 + num(txt(it, "dealDay"), int)
        cancelled = 1 if txt(it, "cdealType") == "O" or txt(it, "cdealDay") else 0
        base = [txt(it, "umdNm"), txt(it, "jibun"), ymd, cancelled]
        amt = num(txt(it, "dealAmount"), int)
        if kind == "land":
            base += [num(txt(it, "dealArea")), amt, txt(it, "jimok"), txt(it, "landUse"), txt(it, "dealingGbn")[:2], txt(it, "shareDealingType")[:2]]
        elif kind in ("nrg", "indu"):
            base += [num(txt(it, "buildingAr")), num(txt(it, "plottageAr")), amt, num(txt(it, "buildYear"), int), txt(it, "buildingType")[:2], txt(it, "buildingUse"), txt(it, "landUse"),
                     num(txt(it, "floor"), int), txt(it, "dealingGbn")[:2], txt(it, "buyerGbn")[:2], txt(it, "slerGbn")[:2], txt(it, "shareDealingType")[:2]]
        else:
            base += [num(txt(it, "totalFloorAr")), num(txt(it, "plottageAr")), amt, num(txt(it, "buildYear"), int), txt(it, "houseType")[:2], txt(it, "dealingGbn")[:2], txt(it, "buyerGbn")[:2], txt(it, "slerGbn")[:2]]
        rows.append(base)
    return rows


def fetch_one(kind, sgg, ym):
    rows, page = [], 1
    while True:
        for attempt in range(8):
            try:
                throttle()
                HTTP[0] += 1
                r = sess.get(URLS[kind], params={"serviceKey": KEY, "LAWD_CD": sgg, "DEAL_YMD": ym, "numOfRows": ROWS, "pageNo": page}, timeout=(15, 45))
                if "PER_SECOND" in r.text:
                    throttle(extra=15)          # 초당 제한: 일일 한도가 아니므로 쉬었다가 다시 시도
                    raise RuntimeError("per-second limit")
                if "LIMITED_NUMBER_OF_SERVICE_REQUESTS" in r.text:
                    raise QuotaExceeded()       # 일일 한도
                if r.status_code == 429:
                    throttle(extra=15)
                    raise RuntimeError("HTTP 429")
                if r.status_code != 200:
                    raise RuntimeError(f"HTTP {r.status_code}")
                root = ET.fromstring(r.text)
                code = (root.findtext(".//resultCode") or "").strip()
                if code not in ("000", "00"):
                    msg = root.findtext(".//resultMsg") or r.text[:100]
                    if "LIMIT" in msg.upper():
                        raise QuotaExceeded()
                    raise RuntimeError(f"resultCode {code}: {msg}")
                break
            except QuotaExceeded:
                raise
            except Exception:
                if attempt == 7:
                    raise
                time.sleep(3 * (attempt + 1))
        batch = parse_items(root, kind)
        rows.extend(batch)
        total = num(root.findtext(".//totalCount") or "0", int)
        if len(rows) >= total or not batch:
            return rows
        page += 1
        time.sleep(0.05)


def months_back(n):
    t = date.today()
    y, m = t.year, t.month
    out = []
    for _ in range(n):
        out.append(f"{y}{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return out


def hist_path(kind, ym):
    return HIST / f"{kind}_{ym}.json.gz"


def write_hist(kind, ym, by_sgg, base=None):
    base = base or HIST
    base.mkdir(parents=True, exist_ok=True)
    with gzip.open(base / f"{kind}_{ym}.json.gz", "wt", encoding="utf-8") as f:
        json.dump(by_sgg, f, ensure_ascii=False, separators=(",", ":"))


def prune_hist(kind, months):
    keep = set(months)
    for f in HIST.glob(f"{kind}_*.json.gz"):
        ym = f.name[:-8].split("_")[-1]
        if ym not in keep:
            f.unlink()
            print("오래된 이력 삭제:", f.name, flush=True)


def fetch_months(kind, months, workers, dest, max_calls, force):
    """months 를 순서대로 받는다. to_hist 면 gz 이력으로, 아니면 캐시 파일로 저장. 일일 한도 도달 시 (False, 받은 수)."""
    done = 0
    for ym in months:
        d = CACHE / kind / ym
        if dest == "cache":
            d.mkdir(parents=True, exist_ok=True)
            todo = [g for g in SGG if force or not (d / f"{g}.json").exists()]
        else:
            todo = list(SGG)
        if not todo:
            continue
        if HTTP[0] >= max_calls:
            print(f"호출 {HTTP[0]}회 도달 — 중단(다음 실행에서 이어서). 받음 {done}", flush=True)
            return False, done
        try:
            with ThreadPoolExecutor(max_workers=workers) as ex:
                results = list(ex.map(lambda g: (g, fetch_one(kind, g, ym)), todo))
        except QuotaExceeded:
            print(f"일일 호출 한도 도달(HTTP {HTTP[0]}회) — 중단(다음 실행에서 이어서). 받음 {done}", flush=True)
            return False, done
        done += len(results)
        if dest in ("hist", "snap"):
            write_hist(kind, ym, {g: rows for g, rows in results}, SNAP if dest == "snap" else HIST)
            print(f"{'스냅샷' if dest == 'snap' else '이력'} 저장: {kind} {ym} (HTTP {HTTP[0]})", flush=True)
        else:
            for g, rows in results:
                (d / f"{g}.json").write_text(json.dumps(rows, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            print(f"[{kind}] {ym} {len(results)}개 시군구 (HTTP {HTTP[0]})", flush=True)
    return True, done


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", required=True, choices=list(URLS))
    ap.add_argument("--mode", default="full", choices=["full", "recent", "fill-hist", "pack-cache", "snapshot-recent", "pack-recent"])
    ap.add_argument("--months", type=int, default=0)
    ap.add_argument("--max-calls", type=int, default=9500)
    ap.add_argument("--workers", type=int, default=2)
    args = ap.parse_args()
    kind = args.kind
    window = months_back(args.months or DEFAULT_MONTHS[kind])
    recent, confirmed = window[:RECENT_N], window[RECENT_N:]

    if args.mode == "pack-cache":      # 로컬 부트스트랩: 캐시의 확정 월을 이력 파일로 묶는다
        n = 0
        for ym in confirmed:
            d = CACHE / kind / ym
            files = list(d.glob("*.json")) if d.exists() else []
            if hist_path(kind, ym).exists() or len(files) < len(SGG):
                continue
            write_hist(kind, ym, {f.stem: json.loads(f.read_text(encoding="utf-8")) for f in files})
            n += 1
        prune_hist(kind, confirmed)
        print(f"[{kind}] 이력 파일 {n}개 생성", flush=True)
        return

    if args.mode == "fill-hist":
        missing = [ym for ym in confirmed if not hist_path(kind, ym).exists()]
        print(f"[{kind}] 이력 보강 대상 {len(missing)}개월 {missing}", flush=True)
        ok, done = fetch_months(kind, missing, args.workers, "hist", args.max_calls, False)
        prune_hist(kind, confirmed)
        print(f"완료: 이력 {done}개 시군구-월 {'(한도로 일부만)' if not ok else ''}", flush=True)
        return      # 이력 보강이 덜 되어도 빌드는 가능하다(다음 실행에서 이어서)

    if args.mode == "snapshot-recent":      # 최근 월을 받아 _rawdata/land_recent 에 스냅샷으로 저장(전체가 받아져야 저장; 한도에 걸리면 비정상 종료)
        ok, done = fetch_months(kind, recent, args.workers, "snap", args.max_calls, True)
        if not ok:
            sys.exit(2)
        for f in SNAP.glob(f"{kind}_*.json.gz"):
            if f.name[:-8].split("_")[-1] not in set(recent):
                f.unlink()
        print(f"완료: 스냅샷 {len(recent)}개월 {done}개 시군구-월", flush=True)
        return

    if args.mode == "pack-recent":          # 로컬 부트스트랩: 캐시의 최근 월을 스냅샷으로 묶는다
        n = 0
        for ym in recent:
            d = CACHE / kind / ym
            files = list(d.glob("*.json")) if d.exists() else []
            if len(files) < len(SGG):
                continue
            write_hist(kind, ym, {f.stem: json.loads(f.read_text(encoding="utf-8")) for f in files}, SNAP)
            n += 1
        print(f"[{kind}] 스냅샷 {n}개 생성", flush=True)
        return

    if args.mode == "recent":
        ok, done = fetch_months(kind, recent, args.workers, "cache", args.max_calls, True)
        if not ok:
            sys.exit(2)       # 최근 월은 일부만 받으면 안 된다(빌드·배포 차단, 기존 배포 유지)
        print(f"완료: 최근 {len(recent)}개월 {done}개 시군구-월", flush=True)
        return

    ok, done = fetch_months(kind, window, args.workers, "cache", args.max_calls, False)   # full
    print(f"완료: 받음 {done}", flush=True)


if __name__ == "__main__":
    main()
