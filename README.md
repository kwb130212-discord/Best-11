# BEST-11 Clan Bot

BEST 클랜용 Discord 봇입니다. 기존 `app.py` 기능을 유지하면서 `best_bot.py`가 BEST 전용 기능을 함께 로드합니다.

## DisHost 배포

### 1. 시작 명령

```bash
python best_bot.py
```

저장소에는 `Procfile`도 포함되어 있으며 worker 시작 명령은 `python best_bot.py`입니다.

### 2. 환경변수

DisHost의 Environment Variables에 아래 값을 등록하세요. **실제 디스코드 봇 토큰은 GitHub에 올리지 않습니다.**

```env
DISCORD_TOKEN=디스코드_봇_토큰
ADMIN_ROLE_NAME=관리자
VERIFY_ROLE_NAME=인증유저
DB_PATH=team.db
YOUTUBE_POLL_SECONDS=120
ROUED_YOUTUBE_CHANNEL=https://www.youtube.com/@루에드
BOT_NAME=루에드 유튜브
```

로컬에서 사용할 경우 `.env.example`을 복사해 `.env`로 만들 수 있습니다. `.env`는 `.gitignore`에 등록되어 있습니다.

## BEST 기능

- `/스크림등록` 기존 스크림 일정 등록
- `/내전패널` 기존 스크림을 버튼형 참여 신청 임베드로 표시
- `/정기내전등록` 매주 지정 요일/시간에 내전 패널 자동 게시
- `/이벤트 물품 주최자` 무료 이벤트 생성
- `/확률업 역할 배율` 역할별 무료 이벤트 당첨 가중치 설정 (예: 1.5배)
- `/이벤트추첨 이벤트ID` 가중치 기반 무료 이벤트 추첨
- `/루에드알림 켜기:true/false` 개인별 루에드 유튜브 알림 구독
- `/루에드채널설정 채널` 루에드 유튜브 채널 및 알림 채널 설정

`관리자`라는 **정확한 역할 이름**을 가진 사용자는 관리자 전용 스크림/이벤트 관리 명령을 사용할 수 있습니다.

YouTube 알림은 공개 YouTube 채널 피드를 주기적으로 확인하며, 같은 서버에서 해당 채널 알림을 켠 사용자만 멘션 대상으로 처리합니다.

사진 기반 자동 지급 기능은 다음 단계에서 별도 구현합니다.
