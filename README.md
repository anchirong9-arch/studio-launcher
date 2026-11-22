# 🚀 통합 스튜디오 런처 (studio-launcher)

로컬 서버가 필요한 도구 3종을 **`실행하기.bat` 한 번**으로 같이 켜고, 웹 도구 5종은 바로 열 수 있는 통합 허브입니다.

- 🌐 허브 (웹): https://anchirong9-arch.github.io/studio-launcher/
- 💻 허브 (내 PC): `실행하기.bat` 실행 후 http://127.0.0.1:8770/
- ⬇ 실행용 ZIP: https://github.com/anchirong9-arch/studio-launcher/releases/latest/download/studio-launcher.zip

## 한 번에 켜지는 서버 3종

| # | 도구 | 포트 | 주소 | 하는 일 |
| - | --- | --- | --- | --- |
| 1 | TTS 스튜디오 | 8765 | http://127.0.0.1:8765/ | 대본 → AI 음성 `.mp3` + 단어 타이밍 `.srt` |
| 2 | 쇼츠 메이커 | 8766 | http://127.0.0.1:8766/ | 짤 + 음성 + 자막 → 1080×1920 `.mp4` |
| 3 | 쿠파스 헌터 | 8767 | http://127.0.0.1:8767/ | 쿠팡 가성비 상품 + 4채널 단축 링크 |
| – | 통합 허브 | 8770 | http://127.0.0.1:8770/ | 세 서버 상태 확인 · 바로가기 · 키 등록 |

## 바로 쓰는 웹 도구 5종

| # | 도구 | 주소 |
| - | --- | --- |
| 4 | 짤 썸네일 스튜디오 | https://anchirong9-arch.github.io/meme-thumb-studio/ |
| 5 | 후킹 제목 생성기 | https://anchirong9-arch.github.io/hook-title-gen/ |
| 6 | 백수톡 게임즈 | https://anchirong9-arch.github.io/baeksutalk-games/ |
| 7 | 칼바람 추첨기 | https://anchirong9-arch.github.io/lol-aram-picker/ |
| 8 | shop-links | https://anchirong9-arch.github.io/shop-links/ |

## 처음 한 번

1. [ZIP](https://github.com/anchirong9-arch/studio-launcher/releases/latest/download/studio-launcher.zip)을 받아 `C:\studio-launcher` 처럼 **짧은 영문 경로**에 풉니다.
2. `실행하기.bat` 을 더블클릭합니다. (파일명이 깨져 보이면 `run.bat`)
   - 처음 한 번만 `.venv` 를 만들고 `edge-tts · imageio-ffmpeg · Pillow` 를 설치합니다. 1~3분.
   - 끝나면 브라우저가 http://127.0.0.1:8770/ 을 열고, 세 서버가 같이 켜져 있습니다.
3. 허브의 **🔑 쿠팡 파트너스 키** 칸에 Access/Secret Key를 넣습니다. 처음 한 번만.
   - 키는 `tools\coupas-hunter\coupas-api-key.env` 에만 저장되고 저장소에는 올라가지 않습니다.

Python 3.9 이상이 필요합니다. 없으면 안내 창이 뜨고 python.org 주소를 알려 줍니다.

## 끄기 / 다시 켜기

- `종료하기.bat` (또는 `stop.bat`): 이 런처가 켠 서버 3개와 허브를 정리합니다.
- `실행하기.bat` 창을 닫거나 `Ctrl+C` 를 눌러도 같이 정리됩니다.
- 이미 켜져 있는 서버는 런처가 **그대로 다시 씁니다**. 중복으로 켜지 않습니다.
- 포트가 다른 프로그램에 잡혀 있으면 허브 카드에 `충돌` 로 표시되고 사유가 나옵니다.

## 폴더 구조

```
studio-launcher/
├─ index.html · style.css · app.js   # 통합 허브 (GitHub Pages 와 로컬 8770 에서 같은 파일)
├─ launcher.py                       # 서버 3개 관리 + 허브 서버 (표준 라이브러리만)
├─ 실행하기.bat / run.bat            # 1클릭 실행
├─ 종료하기.bat / stop.bat           # 정리
├─ requirements.txt                  # edge-tts · imageio-ffmpeg · Pillow
└─ tools/
   ├─ tts-studio/                    # 8765
   ├─ shorts-maker/                  # 8766
   └─ coupas-hunter/                 # 8767
```

`logs/` 에 각 도구의 실행 로그가 쌓입니다 (`tts-studio.log` 등). 문제가 생기면 이 파일을 보면 됩니다.

## 허브가 상태를 아는 방법

- 브라우저가 각 서버의 `GET /health` 를 직접 호출합니다. 세 서버 모두 CORS 와 `Access-Control-Allow-Private-Network` 를 허용합니다.
- 로컬 허브(8770)가 켜져 있으면 `GET /api/status` 로 프로세스 상태·충돌 사유까지 함께 읽습니다.
- 브라우저가 CORS 응답을 못 읽는 경우 `no-cors` 로 도달 여부만 확인해 `켜짐` 으로 표시합니다.
- 서버는 `127.0.0.1` 에만 열립니다. 같은 와이파이의 다른 기기에서는 접속되지 않습니다.

## 개발 메모

```bash
python launcher.py            # 서버 3개 + 허브
python launcher.py --no-open  # 브라우저 없이
python launcher.py --stop     # 이 런처가 켠 것 정리
```

- `.bat` 은 `goto` 방식으로만 작성했습니다. `if (...)` 블록 안의 괄호는 cmd 문법 오류를 내므로 쓰지 않습니다.
- `.bat` 은 UTF-8 + CRLF 로 저장합니다. 한글 파일명이 깨지는 환경을 위해 `run.bat` / `stop.bat` 을 함께 둡니다.
- 도구 본체는 각자의 저장소(`tts-studio`, `shorts-maker`, `coupas-hunter`)가 원본이고, 여기 `tools/` 는 실행용 사본입니다. 원본을 고치면 이 폴더에도 복사해 주세요.
