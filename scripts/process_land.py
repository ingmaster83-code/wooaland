#!/usr/bin/env python3
"""
process_land.py - data/cache/{land,nrg,indu,sh}/{ym}/{sgg}.json (+ _rawdata/land_hist/*.json.gz)을
법정동(읍면동·리) 단위로 집계해 _rawdata/land_{시도}.json 과 land_meta.json 을 만든다.

종류 → 사이트 구분: land=토지(땅값) / nrg=상업업무용(상가·사무실) / indu=공장·창고 / sh=단독·다가구
지번은 공공데이터에서 일부가 가려져 있어(예: '4*', '1**') 필지·건물 개별 페이지는 만들지 않는다.

레코드(동 1건 × 종류 1건) 필드
  k(종류) do sg dong sgg n(36개월 유효 거래) n12 last(최근 거래일)
  w: [[n, 중앙값 평당가(만원)] × 3]  = 최근 12개월 / 직전 12개월 / 그 전 12개월
  med(최근 12개월 평당가 중앙값, 부족하면 36개월) medAll avg mp(거래금액 중앙값, 만원) mx mn
  t: 유형별 [[유형, n, 평당가 중앙값, 면적 중앙값㎡, 금액 중앙값]] (토지=지목, 상가/공장=건물용도, 주택=유형)
  z: 용도지역별 [[이름, n]], b(법인 매수 %), c(집합건물 %), age(중앙 건물연식, 연)
  r: 최근 거래 최대 15건 [[ymd, 유형, 면적㎡, 대지면적㎡, 금액, 평당가, 지번, 용도지역, 거래유형]]
시군구 레코드는 dong=""(전 지역 통계) 이고, 시군구×지목 레코드는 jm=지목 을 가진다(토지 전용).
"""
import gzip, json, sys
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).parent.parent
CACHE = ROOT / "data" / "cache"
RAW = ROOT / "_rawdata"
HIST = RAW / "land_hist"
SNAP = RAW / "land_recent"
MIN_MONTHS = 12            # 이 개월 수 미만으로 모인 종류는 사이트에서 뺀다("최근 12개월" 통계가 틀려지므로)
SGG = json.loads((ROOT / "scripts" / "sgg_names.json").read_text(encoding="utf-8"))
TODAY = date.today()
PY = 3.3058                      # 1평 = 3.3058㎡
MIN_DONG = int(sys.argv[1]) if len(sys.argv) > 1 else 3        # 동 레코드를 만드는 최소 유효 거래(36개월)
MIN_JM = 5                                                       # 시군구×지목 레코드 최소 거래
MIN_TOTAL = 8000
KIND_SITE = {"land": "land", "nrg": "shop", "indu": "factory", "sh": "house"}
EXCL_JIMOK = {"도로", "하천", "구거", "제방", "묘지", "수도용지", "철도용지", "유지", "양어장", "공원", "체육용지", "종교용지", "사적지", "학교용지"}   # 시세 통계에서 제외(비시장·특수)
MAIN_JIMOK = ["대", "전", "답", "임야", "과수원", "잡종지", "공장용지", "목장용지"]


def ymd_of(d):
    return d.year * 10000 + d.month * 100 + d.day


Y12 = ymd_of(TODAY - timedelta(days=365))
Y24 = ymd_of(TODAY - timedelta(days=730))
Y36 = ymd_of(TODAY - timedelta(days=1095))


def med(a):
    if not a:
        return 0
    s = sorted(a)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def hist_months_of(base, kind):
    return {f.name[:-8].split("_")[-1] for f in base.glob(f"{kind}_*.json.gz")}


def kind_months(kind):
    """이 종류로 모인 개월 집합(이력 ∪ 스냅샷 ∪ 캐시)."""
    ms = hist_months_of(HIST, kind) | hist_months_of(SNAP, kind)
    base = CACHE / kind
    if base.exists():
        ms |= {m.name for m in base.iterdir() if len(list(m.glob("*.json"))) >= len(SGG)}
    return ms


def load(kind):
    """우선순위: 이력(_rawdata/land_hist) > 스냅샷(_rawdata/land_recent) > 최근 월 캐시(data/cache). 같은 달은 앞선 것만 쓴다. yield (sgg, row)"""
    seen = set()
    for base in (HIST, SNAP):
        for f in sorted(base.glob(f"{kind}_*.json.gz")):
            ym = f.name[:-8].split("_")[-1]
            if ym in seen:
                continue
            seen.add(ym)
            with gzip.open(f, "rt", encoding="utf-8") as fh:
                for sgg, rows in json.load(fh).items():
                    for r in rows:
                        yield sgg, r
    base = CACHE / kind
    if base.exists():
        for mdir in sorted(base.iterdir()):
            if mdir.name in seen:
                continue
            for f in mdir.glob("*.json"):
                for r in json.loads(f.read_text(encoding="utf-8")):
                    yield f.stem, r


def prep(kind, r):
    """원행 → 정규화 dict(통계 대상이면) 아니면 None."""
    if r[3] or r[2] < Y36:
        return None
    if kind == "land":
        area, amt, jm, zone, gbn, share = r[4], r[5], r[6], r[7], r[8], r[9]
        if share or amt <= 0 or area <= 0 or jm in EXCL_JIMOK:
            return None
        return {"ymd": r[2], "ty": jm, "a": area, "a2": 0, "amt": amt, "py": amt / (area / PY), "jb": r[1], "zone": zone, "gbn": gbn, "jm": jm, "dg": r[0]}
    if kind in ("nrg", "indu"):
        bar, lar, amt, by, bt, use, zone, floor, gbn, buyer, seller, share = r[4], r[5], r[6], r[7], r[8], r[9], r[10], r[11], r[12], r[13], r[14], r[15]
        if share or amt <= 0 or bar <= 0:
            return None
        return {"ymd": r[2], "ty": use or "기타", "a": bar, "a2": lar, "amt": amt, "py": amt / (bar / PY), "jb": r[1], "zone": zone, "gbn": gbn, "buyer": buyer, "bt": bt, "by": by, "dg": r[0]}
    far, lar, amt, by, ht, gbn = r[4], r[5], r[6], r[7], r[8], r[9]
    if amt <= 0 or (lar <= 0 and far <= 0):
        return None
    base_area = lar if lar > 0 else far
    ht = {"다가": "다가구"}.get(ht, ht)          # 수집 시 앞 2글자로 잘린 값 복원
    return {"ymd": r[2], "ty": ht or "단독", "a": far, "a2": lar, "amt": amt, "py": amt / (base_area / PY), "jb": r[1], "zone": "", "gbn": gbn, "by": by, "dg": r[0]}


def summarize(rows, kind, recent_n=15):
    """rows: prep 결과 리스트(36개월)."""
    n = len(rows)
    r12 = [x for x in rows if x["ymd"] >= Y12]
    p12 = [x for x in rows if Y24 <= x["ymd"] < Y12]
    p24 = [x for x in rows if x["ymd"] < Y24]
    pys = [x["py"] for x in rows]
    rec = {
        "n": n, "n12": len(r12), "last": max(x["ymd"] for x in rows),
        "w": [[len(w), round(med([x["py"] for x in w]))] for w in (r12, p12, p24)],
        "med": round(med([x["py"] for x in r12])) if len(r12) >= 3 else round(med(pys)), "medAll": round(med(pys)), "avg": round(sum(pys) / n),
        "mp": round(med([x["amt"] for x in rows])), "mx": max(x["amt"] for x in rows), "mn": min(x["amt"] for x in rows),
    }
    by_ty = defaultdict(list)
    for x in rows:
        by_ty[x["ty"]].append(x)
    tys = sorted(by_ty.items(), key=lambda kv: -len(kv[1]))[:8]
    rec["t"] = [[t, len(v), round(med([x["py"] for x in v])), round(med([x["a"] for x in v]), 1), round(med([x["amt"] for x in v]))] for t, v in tys]
    zc = Counter(x["zone"] for x in rows if x.get("zone"))
    rec["z"] = [[z, c] for z, c in zc.most_common(5)]
    if kind in ("nrg", "indu"):
        rec["b"] = round(100 * sum(1 for x in rows if x.get("buyer") == "법인") / n)
        rec["c"] = round(100 * sum(1 for x in rows if x.get("bt") == "집합") / n)
        ages = [TODAY.year - x["by"] for x in rows if x.get("by") and x["by"] > 1900]
        rec["age"] = round(med(ages)) if ages else 0
    elif kind == "sh":
        ages = [TODAY.year - x["by"] for x in rows if x.get("by") and x["by"] > 1900]
        rec["age"] = round(med(ages)) if ages else 0
    rows_sorted = sorted(rows, key=lambda x: -x["ymd"])[:recent_n]
    rec["r"] = [[x["ymd"], x["ty"], round(x["a"], 1), round(x["a2"], 1), x["amt"], round(x["py"]), x["jb"], x.get("zone", ""), x["gbn"], x["dg"]] for x in rows_sorted]
    top = sorted((x for x in rows if x["ymd"] >= Y12), key=lambda x: -x["amt"])[:5]
    rec["top"] = [[x["ymd"], x["ty"], round(x["a"], 1), x["amt"], round(x["py"]), x["dg"], x["jb"]] for x in top]
    return rec


def main():
    out_by_do = defaultdict(list)
    stat = Counter()
    for kind in ("land", "nrg", "indu", "sh"):
        months = kind_months(kind)
        if len(months) < MIN_MONTHS and "--partial" not in sys.argv:
            print(f"[{kind}] 수집된 개월 {len(months)} < {MIN_MONTHS} — 이 종류는 이번 빌드에서 제외", flush=True)
            stat[KIND_SITE[kind] + "_skipped"] += 1
            continue
        by_dong = defaultdict(list)
        by_sg = defaultdict(list)
        by_sgjm = defaultdict(list)
        raw_n = 0
        for sgg, r in load(kind):
            raw_n += 1
            if sgg not in SGG:
                stat["no_sgg"] += 1
                continue
            x = prep(kind, r)
            if x is None:
                continue
            by_dong[(sgg, r[0])].append(x)
            by_sg[sgg].append(x)
            if kind == "land" and x["jm"] in MAIN_JIMOK:
                by_sgjm[(sgg, x["jm"])].append(x)
        print(f"[{kind}] 원자료 {raw_n:,}행 → 유효 {sum(len(v) for v in by_sg.values()):,}건 / 동 {len(by_dong):,} / 시군구 {len(by_sg)}", flush=True)
        site = KIND_SITE[kind]
        for sgg, rows in by_sg.items():
            do, sg = SGG[sgg]
            rec = summarize(rows, kind, 20)
            rec.update({"k": site, "do": do, "sg": sg, "dong": "", "sgg": sgg})
            out_by_do[do].append(rec)
            stat[site + "_sg"] += 1
        for (sgg, umd), rows in by_dong.items():
            if len(rows) < MIN_DONG or not umd:
                stat[site + "_dong_skip"] += 1
                continue
            do, sg = SGG[sgg]
            rec = summarize(rows, kind)
            rec.update({"k": site, "do": do, "sg": sg, "dong": umd, "sgg": sgg})
            out_by_do[do].append(rec)
            stat[site + "_dong"] += 1
        for (sgg, jm), rows in by_sgjm.items():
            if len(rows) < MIN_JM:
                continue
            do, sg = SGG[sgg]
            rec = summarize(rows, kind, 20)
            dn = defaultdict(list)
            for x in rows:
                dn[x["dg"]].append(x["py"])
            rec["dl"] = [[d, len(v), round(med(v))] for d, v in sorted(dn.items(), key=lambda kv: -len(kv[1]))[:12] if len(v) >= 2]
            rec.update({"k": site, "do": do, "sg": sg, "dong": "", "sgg": sgg, "jm": jm})
            out_by_do[do].append(rec)
            stat["land_jm"] += 1

    for old in RAW.glob("land_[!h]*.json"):
        old.unlink()
    RAW.mkdir(exist_ok=True)
    total = 0
    latest = 0
    for do, lst in out_by_do.items():
        lst.sort(key=lambda r: (r["k"], r["sg"], r["dong"], r.get("jm", "")))
        (RAW / f"land_{do}.json").write_text(json.dumps(lst, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        total += len(lst)
        latest = max(latest, max(r["last"] for r in lst))
    (RAW / "land_meta.json").write_text(json.dumps({"latest": latest, "built": ymd_of(TODAY), "min_dong": MIN_DONG}), encoding="utf-8")
    sz = sum(f.stat().st_size for f in RAW.glob("land_*.json")) / 1e6
    print(f"레코드 {total:,} / {sz:.1f}MB / " + " ".join(f"{k}={v:,}" for k, v in sorted(stat.items())) + f" / 최근 거래일 {latest}")
    if "--partial" not in sys.argv:
        if total < MIN_TOTAL:
            raise SystemExit(f"레코드가 {total:,}건뿐입니다(최소 {MIN_TOTAL:,}). 수집 실패로 보여 중단합니다.")
        if latest < ymd_of(TODAY - timedelta(days=60)):
            raise SystemExit(f"최근 거래일이 {latest} 로 너무 오래됐습니다.")


if __name__ == "__main__":
    main()
