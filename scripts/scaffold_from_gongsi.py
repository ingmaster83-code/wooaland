#!/usr/bin/env python3
"""scaffold_from_gongsi.py - 우아공시가 사이트의 공용 뼈대(CSS·JS·include·개인정보·robots·deploy·기본 레이아웃)를 복사해 우아땅값용으로 치환한다(1회성)."""
import re, shutil, sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
SRC = Path(r"C:\개인\wooahouse\wooagongsi")
DST = Path(r"C:\개인\wooahouse\wooaland")

COLORS = {            # 스카이블루 → 그린
    "#0369A1": "#15803D", "#0369a1": "#15803D",
    "#0EA5E9": "#22C55E", "#0ea5e9": "#22C55E",
    "#075985": "#166534",
    "#0C4A6E": "#14532D", "#0c4a6e": "#14532D",
    "#F0F9FF": "#F0FDF4", "#f0f9ff": "#F0FDF4",
    "#E0F2FE": "#DCFCE7", "#e0f2fe": "#DCFCE7",
    "#BAE6FD": "#BBF7D0", "#bae6fd": "#BBF7D0",
    "#7DD3FC": "#86EFAC", "#7dd3fc": "#86EFAC",
}
TEXT = [("wooagongsi", "wooaland"), ("우아공시가", "우아땅값")]


def conv(text):
    for a, b in COLORS.items():
        text = text.replace(a, b)
    for a, b in TEXT:
        text = text.replace(a, b)
    return text


def copy(rel, convert=True):
    s, d = SRC / rel, DST / rel
    d.parent.mkdir(parents=True, exist_ok=True)
    if convert:
        d.write_text(conv(s.read_text(encoding="utf-8")), encoding="utf-8")
    else:
        shutil.copyfile(s, d)
    print("복사:", rel)


for rel in ["assets/css/main.css", "assets/js/ad-dev-placeholder.js", "assets/js/wooa-sidebar.js", "assets/js/wooa-sites-bar.js",
            "_includes/ad.html", "_includes/faq.html", "privacy/index.html", "robots.txt", "CNAME", "Gemfile", "_layouts/default.html", ".github/workflows/deploy.yml"]:
    copy(rel, convert=not rel.startswith("assets/js"))

p = DST / "_layouts" / "default.html"
s = p.read_text(encoding="utf-8")
s = re.sub(r'\s*<meta name="naver-site-verification"[^>]*/>\n', "\n", s)
s = s.replace("우아땅값 - 아파트·빌라 공시가격 조회와 추이", "우아땅값 - 토지·상가 실거래가와 땅값 시세")
s = s.replace('<span class="logo-icon">🏷️</span>', '<span class="logo-icon">🌱</span>')
s = re.sub(r"<nav class=\"header-nav\">.*?</nav>", '''<nav class="header-nav">
      <a href="{{ '/land/' | relative_url }}">땅값</a>
      <a href="{{ '/shop/' | relative_url }}">상가</a>
      <a href="{{ '/rank/' | relative_url }}">랭킹</a>
      <a href="{{ '/search/' | relative_url }}">검색</a>
      <a href="https://wooahouse.com">WooaHouse →</a>
    </nav>''', s, count=1, flags=re.S)
s = s.replace("page.layout == 'complex' or page.layout == 'dong' or page.layout == 'sigungu' or page.layout == 'do' or page.layout == 'rank'",
              "page.layout == 'hub' or page.layout == 'jimok' or page.layout == 'rank' or page.layout == 'kindindex'")
i = s.find('<p class="footer-disclaimer">')
j = s.find("</p>", i) + 4
disc = '''<p class="footer-disclaimer">
      거래 금액·면적은 국토교통부 실거래가 신고 자료(공공데이터포털: 토지·상업업무용·공장창고·단독다가구 매매)를 법정동(읍면동·리) 단위로 집계한 것입니다. 지번은 공개 자료에서 일부가 가려져 있어 개별 필지·건물은 특정하지 않습니다.<br>
      평당가는 지분 거래·해제 거래·도로 등 비시장 지목을 제외한 거래금액 ÷ 면적(평)의 중앙값이며, 거래가 적은 지역은 실제와 차이가 큽니다. 투자·거래 판단의 근거가 아니며 매매 전 등기부등본과 감정평가 등으로 확인하세요.
    </p>'''
s = s[:i] + disc + s[j:]
s = s.replace('<a href="https://wooavilla.wooahouse.com">우아빌라</a> ·', '<a href="https://wooavilla.wooahouse.com">우아빌라</a> ·\n      <a href="https://wooagongsi.wooahouse.com">우아공시가</a> ·')
p.write_text(s, encoding="utf-8")
print("기본 레이아웃 정리 완료")
