# 🎬 쇼츠 메이커 (shorts-maker)

짤 이미지 여러 장 + 음성(.mp3) + 자막(.srt) + BGM(.mp3) → **1080×1920 세로 쇼츠 영상(.mp4)** 을
내 PC에서 한 번에 만들어 주는 도구입니다. [TTS 스튜디오](https://github.com/anchirong9-arch/tts-studio)에서
뽑은 음성·자막 파일을 그대로 넣으면 됩니다.

- 웹 UI: **https://anchirong9-arch.github.io/shorts-maker/**
- 영상 합성은 내 PC에서 (서버·계정·업로드 없음, 인터넷도 필요 없음)

## 빠른 시작 (처음 한 번, 3분)

1. **[ZIP 내려받기](https://github.com/anchirong9-arch/shorts-maker/archive/refs/heads/main.zip)** → 압축 풀기
2. 폴더 안의 **`실행하기.bat`** 더블클릭
   - 처음 한 번: `.venv` 생성 → `Pillow`, `FFmpeg` 자동 설치 (2~4분)
   - **FFmpeg를 따로 설치할 필요 없습니다** (`imageio-ffmpeg`가 바이너리를 자동으로 받아 옵니다)
3. 자동으로 열리는 **http://127.0.0.1:8766** 에서 사용

`실행하기.bat`이 안 되면 `run.bat`(영문 이름, 같은 동작)을 눌러 보세요.
검은 창은 **켜 둔 채로** 쓰고, 다 쓰면 닫으면 됩니다.

## 쓰는 법

| 순서 | 할 일 |
|---|---|
| 1 | **장면**에 짤 이미지를 여러 장 끌어다 놓기 (순서대로 영상에 나옴, ↑↓·드래그로 순서 변경) |
| 2 | **음성 파일**(.mp3) 넣기 — TTS 스튜디오에서 받은 파일 |
| 3 | (선택) **자막 .srt**, **BGM .mp3** 넣기 |
| 4 | 옵션 고르기 → **[🎬 쇼츠 영상 만들기]** |
| 5 | 완성된 영상을 미리 보고 **⬇ MP4 저장** |

- **[Ctrl] + [Enter]** 로 바로 만들 수 있습니다.
- 완성 영상은 `output` 폴더에도 같이 저장됩니다.
- 오른쪽 미리보기(▶)로 만들기 전에 장면·자막 위치를 미리 확인할 수 있습니다.

## 옵션

| 옵션 | 설명 |
|---|---|
| **줌 효과** | 장면마다 천천히 확대/축소 (홀수·짝수 장면이 번갈아 움직임) |
| **배경** | 이미지 비율이 9:16이 아닐 때 채우는 방식 — 블랙 / 화이트 / 블러(원본을 흐리게) / 꽉 채우기(가운데 크롭) |
| **자막 크기** | 36~90 (기본 58). 자막은 하단 UI를 피해 **아래에서 400px 위**에 번인 |
| **BGM 볼륨** | 0~60% (기본 12%). 음성은 그대로, BGM만 낮춰 믹싱 |
| 장면 길이 | 음성 길이를 이미지 수만큼 **똑같이** 나눔 (마지막 장면이 남는 시간을 흡수) |

## 동작 방식

```
이미지 N장 ──▶ Pillow 로 9:16 캔버스 합성(배경 + 가운데 맞춤)
              ──▶ ffmpeg zoompan 으로 장면별 줌
              ──▶ concat 으로 이어붙이기
              ──▶ 자막을 Pillow 로 그린 PNG 로 얹기(흰 글씨 + 검은 테두리)
음성 + BGM  ──▶ amix 로 볼륨 낮춰 믹싱 ──▶ AAC 192k
                        결과: H.264 / 1080×1920 / 30fps / CRF 20 / faststart
```

## 파일 구성

| 파일 | 역할 |
|---|---|
| `index.html` · `style.css` · `app.js` | 웹 UI (GitHub Pages에서도 열림) |
| `server.py` | 로컬 서버 — 정적 파일 + `/health` + `/render` |
| `requirements.txt` | `imageio-ffmpeg`, `Pillow` |
| `실행하기.bat` · `run.bat` | 1클릭 실행 (venv + 패키지 + FFmpeg 자동 설치) |
| `output/` | 완성된 mp4 저장 폴더 |

## 서버 API (다른 데서도 씀)

```bash
# 상태
curl http://127.0.0.1:8766/health

# 렌더 (multipart)
curl -X POST http://127.0.0.1:8766/render \
  -F "images=@1.jpg" -F "images=@2.jpg" \
  -F "audio=@voice.mp3" -F "srt=@sub.srt" -F "bgm=@bgm.mp3" \
  -F "zoom=1" -F "bg_style=blur" -F "bgm_vol=0.12" -F "subtitle_size=58" \
  -o shorts.mp4
```

JSON(base64)도 됩니다: `{"images":[{"name":"a.jpg","base64":"..."}], "audio_base64":"...",
"srt_text":"1\n00:00:00,000 --> ...", "options":{"zoom":true,"bg_style":"black","bgm_vol":0.12,"subtitle_size":58}}`

응답 헤더로 결과 정보를 돌려줍니다: `X-Video-Duration`, `X-Video-Frames`, `X-Video-Segments`,
`X-Video-Subtitles`, `X-Render-Sec`, `X-Saved-Path`

포트가 사용 중이면 서버가 8767, 8768…로 자동 이동하고 시작 로그에 주소를 찍습니다.
(웹페이지는 8766·8767을 자동으로 찾아봅니다.)

## 문제 해결

| 증상 | 해결 |
|---|---|
| `Python 이 설치되어 있지 않습니다` | [python.org](https://www.python.org/downloads/windows/) 설치, 첫 화면에서 **Add python.exe to PATH** 체크 |
| `패키지 설치에 실패했습니다` | 인터넷 확인 후 `실행하기.bat` 다시 실행 (이어서 설치됨) |
| `가상환경을 만들지 못했습니다` | `C:\shorts-maker` 처럼 단순한 경로에 압축 풀기 |
| 페이지에 `서버 꺼짐` | `실행하기.bat` 창이 켜져 있는지 확인 → [연결 확인] 버튼 |
| 자막이 네모로 보임 | Windows 기본 폰트(맑은 고딕)를 못 찾은 경우 — `fonts` 폴더에 `NotoSansKR-Regular.ttf`를 넣으면 됩니다 |
| 영상이 느리게 만들어짐 | 길이가 길수록 오래 걸립니다 (60초 영상 ≈ 20~40초). 창을 닫지 마세요 |

## 참고

- 영상은 가로·세로 어느 쪽이든 넣을 수 있고, 9:16 프레임에 맞춰집니다.
- 지원 이미지: jpg, png, webp, bmp, gif, heic(변환 필요할 수 있음), tiff
- 지원 음성: mp3(권장), wav, m4a, aac, ogg
- 한 번에 이미지 최대 40장, 영상 최대 10분, 업로드 합계 260MB
