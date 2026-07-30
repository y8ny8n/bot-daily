# bot-daily

토스 트레이딩 봇의 **일일 요약 공개 파일**만 담는 저장소.
봇 코드·비밀은 여기 없다(별도 비공개 저장소). 여기엔 요약(json/md)만 공개된다.

## 왜 있나
Cowork 예약 브리핑(아침 7시)이 도는 환경은 `db.hap-py.us` 를 못 뚫는다. 그래서
GitHub Actions(러너는 db 를 잘 뚫음)가 매일 요약을 만들어 여기 커밋하고, 예약 브리핑은
아래 raw 주소를 읽는다.

- `bot_summary.md` — 사람이 읽는 요약
- `bot_summary.json` — 브리핑이 파싱하는 값

raw 주소(예약 브리핑이 읽는 곳):
```
https://raw.githubusercontent.com/<OWNER>/bot-daily/main/bot_summary.md
https://raw.githubusercontent.com/<OWNER>/bot-daily/main/bot_summary.json
```

## 내용
- 봇 상태(모드·보유·킬스위치), 누적/당일 손익, 승률
- **슬롯 만석이라 못 산 애들 실적** — 직전 거래일 매수 신호는 났지만 보유에 없는(=진입 못 한)
  종목의 신호가 대비 현재가 등락률. 평균이 마이너스면 "캡이 손실 막음", 플러스면 "기회 놓침".

## 실행
- 자동: 매일 06:00 KST (`.github/workflows/daily.yml`)
- 수동: Actions 탭 → bot-daily-summary → Run workflow
- 로컬 테스트: `python make_bot_summary.py`
