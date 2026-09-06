# BEST-11 Clan Bot

BEST 클랜용 Discord 봇입니다. 기존 `app.py` 기능을 유지하면서 `best_bot.py`가 추가 기능을 함께 로드합니다.

## 실행

```bash
python -m pip install -r requirements.txt
python best_bot.py
```

환경변수:

```env
DISCORD_TOKEN=디스코드_봇_토큰
ADMIN_ROLE_NAME=관리자역할명
VERIFY_ROLE_NAME=인증유저
DB_PATH=team.db
YOUTUBE_POLL_SECONDS=120
```

## BEST 기능

- `/스크림등록` 기존 스크림 일정 등록
- `/내전패널` 기존 스크림을 버튼형 참여 신청 임베드로 표시
- `/정기내전등록` 매주 지정 요일/시간에 내전 패널 자동 게시
- `/이벤트생성` 이벤트 참여 임베드 생성
- `/추첨역할설정 @역할 1.5` 해당 역할의 추첨 가중치를 1.5배로 설정
- `/이벤트추첨 이벤트ID` 가중치 기반 추첨
- `/유튜브알림설정 #채널` 새 영상 알림 채널 설정
- `/유튜브구독 채널URL` 개인 구독 등록
- `/유튜브구독취소 채널URL` 개인 구독 취소

YouTube 알림은 공개 YouTube 채널 피드(RSS/Atom)를 주기적으로 확인합니다. 같은 서버에서 특정 채널을 구독한 사람만 새 영상 알림 멘션 대상이 됩니다. 최초 등록 시에는 현재 최신 영상을 기준점으로 저장하여 과거 영상이 새 영상으로 잘못 알림되지 않도록 합니다.

사진 자동지급 기능은 다음 단계에서 별도 구현 예정입니다.
