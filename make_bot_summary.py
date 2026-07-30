#!/usr/bin/env python3
"""봇 일일 요약 생성기 — GitHub Actions 러너에서 실행.

db.hap-py.us(Datasette)는 GitHub 러너에선 잘 뚫린다(막히는 건 Cowork 예약 환경뿐).
여기서 봇 상태 + "슬롯 만석이라 못 산 애들 실적"을 계산해 bot_summary.json / .md 로 쓴다.
Cowork 예약 브리핑은 이 파일을 raw.githubusercontent 로 읽는다.

의존성 없음(표준 라이브러리만). 러너: `python make_bot_summary.py`.
"""
import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta

BASE = "https://db.hap-py.us/bot.json"
KST = timezone(timedelta(hours=9))


def q(sql):
    """Datasette 에 SQL 을 던져 rows 를 dict 리스트로 반환."""
    url = BASE + "?" + urllib.parse.urlencode({"sql": sql})
    with urllib.request.urlopen(url, timeout=20) as r:
        body = json.loads(r.read().decode("utf-8"))
    cols = body.get("columns", [])
    return [dict(zip(cols, row)) for row in body.get("rows", [])]


def is_kr(symbol):
    """한국 종목코드는 전부 숫자(6자리). 미국 티커는 알파벳."""
    return symbol is not None and symbol.isdigit()


def build():
    now = datetime.now(KST)

    # 1) 봇 상태
    status = q("select mode, regime, held, kill_switch, updated_at from bot_status")
    st = status[0] if status else {}

    # 2) 누적/당일 손익 (daily_stats 최근 2행)
    ds = q("select date, total_pnl, unrealized_pnl, realized_pnl, win_rate, open_positions "
           "from daily_stats order by date desc limit 2")
    today = ds[0] if ds else {}
    prev = ds[1] if len(ds) > 1 else {}
    total_pnl = today.get("total_pnl")
    day_change = None
    if total_pnl is not None and prev.get("total_pnl") is not None:
        day_change = round(total_pnl - prev["total_pnl"])

    # 3) 최근 30시간 매수 신호 (직전 거래일)
    since = (now - timedelta(hours=30)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    signals = q("select tag, symbol, price, created_at from candle_scalp_log "
                f"where action='BUY' and created_at >= '{since}' order by created_at")

    # 4) 보유(진입) 종목 — candle_peak 에 있으면 '들어간' 것
    held_rows = q("select distinct symbol from candle_peak")
    held = {r["symbol"] for r in held_rows}

    # 5) 못 산 애들 = 신호 났지만 보유에 없음(=진입 못 함). 종목당 1건(첫 신호가).
    skipped = {}
    for s in signals:
        sym = s["symbol"]
        if sym in held or sym in skipped:
            continue
        skipped[sym] = {"tag": s["tag"], "signal_price": s["price"]}

    # 6) 각 못 산 종목의 현재가 → 등락률
    rows = []
    for sym, info in skipped.items():
        px = q(f"select price from price_log where symbol='{sym}' order by id desc limit 1")
        if not px:
            continue
        try:
            last = float(px[0]["price"])
            sig = float(info["signal_price"])
        except (TypeError, ValueError):
            continue
        if sig == 0:
            continue
        chg = round((last - sig) / sig * 100, 2)
        rows.append({"symbol": sym, "market": "KR" if is_kr(sym) else "US",
                     "signal_price": sig, "last_price": last, "change_pct": chg})

    rows.sort(key=lambda x: x["change_pct"])  # 최악 → 최고
    kr = [r for r in rows if r["market"] == "KR"]

    def agg(lst):
        if not lst:
            return None
        chgs = [r["change_pct"] for r in lst]
        up = sum(1 for c in chgs if c > 0)
        return {
            "count": len(lst),
            "up": up, "down": len(lst) - up,
            "avg_pct": round(sum(chgs) / len(chgs), 2),
            "worst": lst[0], "best": lst[-1],
        }

    kr_agg = agg(kr)
    # 해석: 못 산 종목 평균이 마이너스면 캡이 손실을 막아준 것
    verdict = None
    if kr_agg:
        verdict = ("캡이 손실을 막아줌 (못 산 종목 평균 하락)"
                   if kr_agg["avg_pct"] < 0 else
                   "캡 때문에 기회 놓침 (못 산 종목 평균 상승)")

    summary = {
        "generated_at": now.strftime("%Y-%m-%d %H:%M KST"),
        "as_of_trading_day": today.get("date"),
        "mode": st.get("mode"),
        "regime": st.get("regime"),
        "held": st.get("held"),
        "kill_switch": st.get("kill_switch"),
        "total_pnl": total_pnl,
        "day_change": day_change,
        "win_rate": today.get("win_rate"),
        "open_positions": today.get("open_positions"),
        "skipped_kr": {"verdict": verdict, "agg": kr_agg, "rows": kr},
        "skipped_all_count": len(rows),
    }

    with open("bot_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    with open("bot_summary.md", "w", encoding="utf-8") as f:
        f.write(render_md(summary))
    print("wrote bot_summary.json / bot_summary.md")
    return summary


def render_md(s):
    lines = []
    lines.append(f"# 봇 요약 · {s['as_of_trading_day']} (생성 {s['generated_at']})")
    lines.append("")
    lines.append(f"- 상태: {s['mode']}·{s['regime']} · 보유 {s['held']}종목 · "
                 f"킬스위치 {'ON' if s['kill_switch'] else 'off'}")
    tp = s["total_pnl"]
    dc = s["day_change"]
    dc_txt = "" if dc is None else f" (당일 {'+' if dc >= 0 else ''}{dc:,})"
    if tp is not None:
        lines.append(f"- 누적 손익: {tp:,}원{dc_txt} · 승률 {s['win_rate']}%")
    lines.append("")
    ska = s["skipped_kr"]
    lines.append("## 슬롯 만석이라 못 산 애들 (국내)")
    if not ska["agg"]:
        lines.append("- 직전 거래일 못 산 국내 종목 없음")
    else:
        a = ska["agg"]
        lines.append(f"- {a['count']}종목 · 오른 것 {a['up']} / 내린 것 {a['down']} · "
                     f"평균 {'+' if a['avg_pct'] >= 0 else ''}{a['avg_pct']}%")
        lines.append(f"- **{ska['verdict']}**")
        w, b = a["worst"], a["best"]
        best_txt = f"+{b['change_pct']}" if b["change_pct"] >= 0 else f"{b['change_pct']}"
        lines.append(f"- 최악 {w['symbol']} {w['change_pct']}% · 최고 {b['symbol']} {best_txt}%")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    build()
