import collections, glob, json, sys

sys.stdout.reconfigure(encoding="utf-8")
base = "C:/개인/wooahouse/wooaland/data/cache"
for kind in ("land", "nrg", "indu", "sh"):
    files = glob.glob(f"{base}/{kind}/*/*.json")
    rows = []
    for f in files:
        rows += json.load(open(f, encoding="utf-8"))
    dongs = {(f.split("/")[-1].split("\\")[-1], r[0]) for f in files for r in json.load(open(f, encoding="utf-8"))}
    canc = sum(1 for r in rows if r[3])
    print(f"== {kind}: files {len(files)}, rows {len(rows)}, 취소 {canc}, 고유 시군구-동 {len(dongs)}")
    print("  sample:", rows[0] if rows else None)
    if kind == "land":
        print("  지목:", collections.Counter(r[6] for r in rows).most_common(10))
        print("  용도지역:", collections.Counter(r[7] for r in rows).most_common(8))
        print("  지분:", collections.Counter(r[9] for r in rows).most_common(3), "거래유형:", collections.Counter(r[8] for r in rows).most_common(3))
        print("  면적 중앙:", sorted(r[4] for r in rows)[len(rows) // 2], "금액 중앙(만원):", sorted(r[5] for r in rows)[len(rows) // 2])
    elif kind in ("nrg", "indu"):
        print("  건물용도:", collections.Counter(r[9] for r in rows).most_common(10))
        print("  건물유형:", collections.Counter(r[8] for r in rows).most_common(3), "지분:", collections.Counter(r[15] for r in rows).most_common(3))
        print("  매수자:", collections.Counter(r[13] for r in rows).most_common(3))
    else:
        print("  주택유형:", collections.Counter(r[8] for r in rows).most_common(4))
