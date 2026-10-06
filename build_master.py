"""한국(KRX KOSPI/KOSDAQ) + 미국(NASDAQ/NYSE/AMEX) 전 종목 마스터 생성.

공식 상장목록을 받아 tossbot/stock_master.json 으로 저장한다(검색용). 인터넷 필요.
사용: python build_master.py
"""
import json
import os
import re
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "tossbot", "stock_master.json")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"


def _fetch(url, headers=None):
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=45) as r:
        return r.read()


def krx(market_param, label):
    url = "https://kind.krx.co.kr/corpgeneral/corpList.do?method=download&marketType=" + market_param
    html = _fetch(url).decode("cp949", "replace")
    out = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
        if len(cells) >= 3:
            name = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", cells[0])).strip()
            code = re.sub(r"\D", "", cells[2])
            if re.fullmatch(r"\d{6}", code) and name:
                out.append([code, name, label])
    return out


def us():
    url = "https://api.nasdaq.com/api/screener/stocks?tableonly=true&limit=25000&download=true"
    data = json.loads(_fetch(url, {"Accept": "application/json"}))
    d = data.get("data") or {}
    rows = d.get("rows") or (d.get("table") or {}).get("rows") or []
    out = []
    for row in rows:
        sym = (row.get("symbol") or "").strip().upper()
        name = (row.get("name") or "").strip()
        if sym and name and re.fullmatch(r"[A-Z]{1,5}(\.[A-Z])?", sym):
            out.append([sym, name, "US"])
    return out


def main():
    master = []
    for param, label in (("stockMkt", "KOSPI"), ("kosdaqMkt", "KOSDAQ")):
        try:
            r = krx(param, label)
            print(f"  {label}: {len(r)}")
            master += r
        except Exception as e:
            print(f"  {label} 실패: {e}")
    try:
        r = us()
        print(f"  US: {len(r)}")
        master += r
    except Exception as e:
        print(f"  US 실패: {e}")

    seen, uniq = set(), []
    for s, n, m in master:
        if s in seen:
            continue
        seen.add(s)
        uniq.append([s, n, m])

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(uniq, f, ensure_ascii=False, separators=(",", ":"))
    from collections import Counter
    print("저장:", OUT)
    print("  총", len(uniq), "종목", dict(Counter(m for _, _, m in uniq)), f"({os.path.getsize(OUT)/1024:.0f}KB)")


if __name__ == "__main__":
    main()
