# 🚀 백수톡 스튜디오 (studio-launcher)

로컬 서버가 필요한 도구 4종을 **한 번에 켜고**, 웹 도구 8종과 크리에이터 툴킷 7종을 바로 여는 통합 런처입니다.
이제 **까만 콘솔 창 없이** 앱 창으로 열리고, 실행할 때마다 **GitHub에서 새 버전을 자동으로 받아** 갱신합니다.
**사진 편집기에서 인스타그램·쓰레드 게시물 링크의 원본 사진을 바로 불러옵니다** (`/api/extract-media`).

- 🌐 허브 (웹): https://anchirong9-arch.github.io/studio-launcher/
- 💻 허브 (내 PC): 앱 창 또는 http://127.0.0.1:8770/
- ⬇ 실행용 ZIP: https://github.com/anchirong9-arch/studio-launcher/releases/latest/download/studio-launcher.zip
- 📦 현재 버전: `version.json` (허브 ③ 위쪽 버전 줄에서도 확인)

## 한 번에 켜지는 서버 4종

| # | 도구 | 포트 | 주소 | 하는 일 |
| - | --- | --- | --- | --- |
| 1 | TTS 스튜디오 | 8765 | http://127.0.0.1:8765/ | 대본 → AI 음성 `.mp3` + 단어 타이밍 `.srt` · 목소리 6종 · 쇼츠 메타 프리셋 12종 |
| 2 | 쇼츠 메이커 | 8766 | http://127.0.0.1:8766/ | 짤 + 음성 + 자막 → 1080×1920 `.mp4` |
| 3 | 쿠파스 헌터 | 8767 | http://127.0.0.1:8767/ | 쿠팡 가성비 상품 + 4채널 단축 링크 |
| 4 | 영상 컷 편집기 | 8768 | http://127.0.0.1:8768/ | 영상 최대 5개 구간 자르기 · 순서대로 1개 MP4 합치기 |
| – | 허브(백수톡 스튜디오) | 8770 | http://127.0.0.1:8770/ | 네 서버 상태 확인 · 바로가기 · 키 등록 · 버전/업데이트 · 링크 사진 불러오기 |

## 바로 쓰는 웹 도구 8종

| # | 도구 | 주소 |
| - | --- | --- |
| 5 | 사진 편집기 | https://anchirong9-arch.github.io/photo-editor/ |
| 6 | 후킹 제목 생성기 | https://anchirong9-arch.github.io/hook-title-gen/ |
| 7 | 백수톡 게임즈 | https://anchirong9-arch.github.io/baeksutalk-games/ |
| 8 | 칼바람 추첨기 | https://anchirong9-arch.github.io/lol-aram-picker/ |
| 9 | 다중 영상 컷 편집기 | https://anchirong9-arch.github.io/video-cutter/ |
| 10 | shop-links | https://anchirong9-arch.github.io/shop-links/ |
| 11 | 1:1 블러 카드 | https://anchirong9-arch.github.io/card-maker/ |
| 12 | 무료 브금 박스 | https://anchirong9-arch.github.io/shorts-bgm-box/ |

## 크리에이터 툴킷 7종 (허브 ③ 미니 앱 아이콘)

허브 가운데의 **미니 런처 아이콘 줄**에서 바로 열립니다. 모두 브라우저 안에서만 처리하고 서버로 아무것도 보내지 않습니다.

| 아이콘 | 도구 | 주소 |
| --- | --- | --- |
| EXIF | EXIF 제거 · 모자이크 | https://anchirong9-arch.github.io/creator-toolkit/#/exif |
| URL | URL 추적 제거 | https://anchirong9-arch.github.io/creator-toolkit/#/url |
| PDF | PDF ↔ 이미지 | https://anchirong9-arch.github.io/creator-toolkit/#/pdf |
| 압축 | 이미지 압축 · 포맷 변환 | https://anchirong9-arch.github.io/creator-toolkit/#/compress |
| QR | QR 생성기 | https://anchirong9-arch.github.io/creator-toolkit/#/qr |
| 비율 | 비율 리사이즈 | https://anchirong9-arch.github.io/creator-toolkit/#/resize |
| 워터마크 | 일괄 워터마크 | https://anchirong9-arch.github.io/creator-toolkit/#/mark |

아이콘 이름·색·경로는 `creator-toolkit` 의 `CT.register({ id, short })` 를 그대로 따릅니다. (워터마크의 실제 라우트는 `#/watermark` 가 아니라 **`#/mark`** 입니다.)

## 실행하기 — 앱처럼

1. ZIP을 받아 `C:\studio-launcher` 처럼 **짧은 영문 경로**에 풉니다.
2. **`실행하기.bat`** 더블클릭 (파일명이 깨져 보이면 `run.bat`)
   - 처음 한 번만 `.venv` 를 만들고 `edge-tts · gTTS · imageio-ffmpeg · Pillow` 설치 (1~3분).
   - 준비가 끝나면 **`pythonw.exe` 로 백그라운드 실행** → 까만 cmd 창은 2초 뒤 사라집니다.
   - 브라우저는 **Edge/Chrome `--app` 모드**로 열려 주소창·북마크바가 없는 독립 앱 창이 됩니다. (둘 다 없으면 기본 브라우저로 폴백)
3. **`바탕화면 바로가기 만들기.bat`** 을 한 번 실행하면 바탕화면에 **`백수톡 스튜디오`** 아이콘(`assets/app.ico`)이 생깁니다. 다음부터는 그 아이콘만 누르면 됩니다.
4. 쿠팡 키는 허브의 **🔑 쿠팡 파트너스 키** 칸에 처음 한 번만 넣습니다.
   `tools\coupas-hunter\coupas-api-key.env` 에만 저장되고 저장소에는 올라가지 않습니다.

> 바로가기는 `.venv\Scripts\pythonw.exe "<폴더>\launcher.py"` 를 실행합니다. 콘솔이 뜨지 않습니다.
> 중간에 문제가 생기면 **`logs\launcher.log`** 에 이유가 남습니다.

## 자동 업데이트

- 실행할 때마다(`launcher.py` 시작) GitHub의 `version.json` 을 **3초 타임아웃**으로 확인합니다. 느리거나 오프라인이면 그냥 현재 버전으로 켜집니다.
- 새 버전이 있으면 릴리스 ZIP을 받아 **현재 폴더에 안전하게 덮어쓰고**, 새 코드로 다시 시작(`execv`)합니다.
- **보존되는 것**: `.venv/`(설치된 패키지) · `logs/` · `*.env`(쿠팡 키) · `tools/video-cutter/jobs/` · `tools/shorts-maker/output/`
- 덮어쓰기 전에 최상위 파일은 `logs/backup/` 에 백업되고, 적용 결과는 `logs/update.json` 에 기록됩니다.
- 압축 안의 `../` 같은 경로 탈출, 버전이 더 낮은 ZIP, 런처가 아닌 ZIP은 **거부**합니다.
- 허브 화면 상단에 **설치 버전 · 최신 버전 · `업데이트 확인` 버튼**이 있고, 새 버전이 있으면 **`지금 업데이트`** 버튼이 나타납니다. (적용 뒤에는 `종료하기.bat → 실행하기.bat` 한 번)
- CLI: `launcher.py --update` (지금 확인·적용) / `--no-update` (이번엔 확인 안 함) / `--version`

## 끄기 / 다시 켜기

- `종료하기.bat` (또는 `stop.bat`): 이 런처가 켠 서버 4개와 허브를 정리합니다.
- 이미 켜져 있는 서버는 런처가 **그대로 다시 씁니다**. 중복으로 켜지 않습니다.
- 포트가 다른 프로그램에 잡혀 있으면 허브 카드에 `충돌` 로 표시되고 사유가 나옵니다.

## 폴더 구조

```
studio-launcher/
├─ index.html · style.css · app.js   # 통합 허브 (GitHub Pages 와 로컬 8770 에서 같은 파일)
├─ version.json                      # 현재 버전 · 업데이트 주소 · 변경 요약
├─ launcher.py                       # 서버 4개 관리 + 허브 서버 + 자동 업데이트 (표준 라이브러리만)
├─ 실행하기.bat / run.bat            # 1클릭 실행 (준비 후 pythonw 로 백그라운드 실행)
├─ 종료하기.bat / stop.bat           # 정리
├─ 바탕화면 바로가기 만들기.bat / make-shortcut.bat + create-shortcut.ps1
├─ assets/app.ico · app-icon-256.png · make_app_icon.py   # 앱 아이콘(Pillow 로 생성)
├─ requirements.txt                  # edge-tts · gTTS · imageio-ffmpeg · Pillow
└─ tools/
   ├─ tts-studio/                    # 8765
   ├─ shorts-maker/                  # 8766
   ├─ coupas-hunter/                 # 8767
   └─ video-cutter/                  # 8768 (server.py + 같은 웹 화면)
```

`logs/` 에 실행 로그가 쌓입니다 (`launcher.log`, `tts-studio.log` 등).

## 허브가 상태를 아는 방법

- 브라우저가 각 서버의 `GET /health` 를 직접 호출합니다. 세 서버 모두 CORS 와 `Access-Control-Allow-Private-Network` 를 허용합니다.
- 로컬 허브(8770)가 켜져 있으면 `GET /api/status` 로 프로세스 상태·충돌 사유까지, `GET /api/version` 으로 버전까지 함께 읽습니다.
- 업데이트 API: `POST /api/update/check` (확인만) · `POST /api/update/apply` (지금 적용)
- 서버는 `127.0.0.1` 에만 열립니다. 같은 와이파이의 다른 기기에서는 접속되지 않습니다.

## 사진 편집기(photo-editor) 연동 — 링크에서 원본 사진 불러오기

웹(HTTPS)에 있는 사진 편집기는 인스타그램·쓰레드 페이지를 직접 열 수 없습니다(CORS·로그인).
그래서 **집 PC의 런처가 대신 링크를 열어** 원본 사진을 받아 넘겨 줍니다. 사진 편집기의 **🔗 링크** 버튼이 이 API 를 부릅니다.

| 요청 | 하는 일 |
| --- | --- |
| `GET http://localhost:8770/api/health` | 살아 있으면 `200 {"ok": true}` |
| `POST http://localhost:8770/api/extract-media` | 본문 `{"url": "<인스타·쓰레드 게시물 링크>"}` → `{"images": [{"dataUrl": "data:image/jpeg;base64,…", "name": "인스타 1"}]}` |

- 캐러셀(여러 장)이면 **원본 크기 그대로 전체 장수**를 옮깁니다. (한 번에 최대 30장)
- 모든 응답(OPTIONS 프리플라이트 `204` 포함)에 CORS 헤더가 붙습니다:
  `Access-Control-Allow-Origin: *` · `Access-Control-Allow-Methods: GET, POST, OPTIONS` · `Access-Control-Allow-Headers: Content-Type` · `Access-Control-Allow-Private-Network: true`
- 사진 주소의 `stp=` 잘린 미리보기 값을 원본 크기(`dst-jpg_e35`)로 바꿔 받습니다.
- 글만 있는 게시물·비공개 게시물은 사진이 없다고 알려 줍니다(프로필 사진은 사진으로 치지 않습니다).
- 휴대폰에서 열어도 사진 편집기는 `localhost:8770` 을 찾지 못합니다. 집 PC에서 런처를 켜고 그 PC의 브라우저에서 쓰는 방식입니다.

## 최근 변경

- **2026-11-25 · v1.1.0 — 사진 편집기 추가 + 인스타·쓰레드 링크 사진 불러오기**
  - ② 웹 도구에서 `짤 썸네일 스튜디오`(meme-thumb-studio)를 빼고 `사진 편집기`(5)를 넣었습니다. (`1:1 블러 카드`와 기능이 겹쳐서) 웹 도구는 그대로 8종입니다.
  - `사진 편집기` — https://anchirong9-arch.github.io/photo-editor/ · 보정·자르기·문구·모자이크·내보내기. PC 런처가 켜져 있으면 인스타·쓰레드 링크에서 원본 사진을 바로 불러옵니다.
  - 허브에 `GET /api/health` 와 `POST /api/extract-media` 를 추가했습니다. 캐러셀은 원본 크기로 전체 장수, CORS·프라이빗 네트워크 프리플라이트까지 허용.
  - ② 섹션 `NEW` 표시는 새로 넣은 사진 편집기 카드로 옮겼습니다.
- **2026-11-24 · v1.0.2 — ② 웹 도구에 '1:1 블러 카드' · '무료 브금 박스' 추가 (총 8종)**
  - `1:1 블러 카드`(11): 사진 → 1080×1080 블러 배경 + 썸네일 2줄 문구 · 1줄 코멘트 · 다크 아웃트로 카드, PNG/ZIP 저장. (https://anchirong9-arch.github.io/card-maker/)
  - `무료 브금 박스`(12): CC0 브금 20곡 + 자체 합성 효과음 89종, 검색·미리듣기·MP3/WAV/ZIP · 영상에서 소리만 뽑아 구간 자르기. (https://anchirong9-arch.github.io/shorts-bgm-box/)
  - 두 도구 모두 설치·로그인 없이 브라우저에서만 처리하고, 사진·음원을 서버로 보내지 않습니다.
  - ② 섹션 `NEW` 표시는 이번에 추가한 두 카드로 옮겼습니다.
- **2026-11-23 · v1.0.1 — 크리에이터 툴킷 아이콘 + 자동 업데이트 + 앱처럼 실행**
  - 허브 ③번 자리에 크리에이터 툴킷 7종을 둥근 사각형 앱 아이콘으로 가로 나열(모바일은 옆으로 밀기, PC는 가운데 정렬).
  - 실행할 때 GitHub `version.json` 을 확인해 새 버전 ZIP을 자동 적용, 허브에 버전 표시·`업데이트 확인`·`지금 업데이트` 버튼 추가.
  - `pythonw.exe` 백그라운드 실행 + Edge/Chrome `--app` 앱 창으로 열기(콘솔 창 없음).
  - `바탕화면 바로가기 만들기.bat` + `assets/app.ico`, 바탕화면에 **백수톡 스튜디오** 아이콘 생성.
- **2026-11-22 · 쿠파스 헌터 사진 수정** — 상품 카드 사진이 빈 채로 나오던 문제를 고쳤습니다.

## 개발 메모

```bash
python launcher.py            # 서버 4개 + 허브 (콘솔에서 로그 보기)
python launcher.py --no-open  # 창 없이
python launcher.py --stop     # 이 런처가 켠 것 정리
python launcher.py --update   # 새 버전 확인·적용만 하고 종료
python assets/make_app_icon.py  # 앱 아이콘 다시 만들기 (Pillow)
python ../build-studio-launcher-zip.py  # 배포용 ZIP
```

- `.bat` 은 `goto` 방식으로만 작성했습니다. `if (...)` 블록 안의 괄호는 cmd 문법 오류를 냅니다.
- `.bat` 은 UTF-8 + CRLF, `create-shortcut.ps1` 은 **UTF-8 BOM** 으로 저장합니다. (Windows PowerShell 5.1 이 BOM 없는 UTF-8 의 한글을 깨뜨립니다)
- `version.json` 의 `version` 을 올린 커밋을 푸시하고 릴리스 ZIP을 교체하면, 다음 실행부터 자동 업데이트가 동작합니다.
- 도구 본체는 각자의 저장소(`tts-studio`, `shorts-maker`, `coupas-hunter`)가 원본이고, 여기 `tools/` 는 실행용 사본입니다.
