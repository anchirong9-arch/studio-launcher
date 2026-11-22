#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
쇼츠 메이커 로컬 서버
--------------------
짤 이미지 여러 장 + 음성(.mp3) + 자막(.srt, 선택) + BGM(.mp3, 선택)
  -> 1080x1920 세로 쇼츠 영상(.mp4) 을 내 PC에서 만들어 줍니다.

- 정적 파일 서빙 : http://127.0.0.1:8766/
- GET  /health   : 연결 확인 (웹페이지가 서버 켜짐 여부를 판단)
- POST /render   : multipart/form-data 또는 JSON(base64) -> video/mp4
                   이미지 여러 장(images), audio(.mp3), srt(.srt), bgm(.mp3),
                   옵션 zoom, bgm_vol, subtitle_size, bg_style

실행:  python server.py            (브라우저 자동 열림)
       python server.py --no-open  (브라우저 안 열림)
       python server.py --port 9000
"""

import argparse
import base64
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SERVER_VERSION = "1.0.0"
DEFAULT_PORT = 8766

OUT_W, OUT_H = 1080, 1920
BASE_SCALE = 4.0 / 3.0          # 합성 원본 해상도 배율 (1080x1920 -> 1440x2560)
FPS = 30
MAX_IMAGES = 40
MAX_IMAGE_BYTES = 30 * 1024 * 1024
MAX_AUDIO_BYTES = 60 * 1024 * 1024
MAX_SRT_BYTES = 2 * 1024 * 1024
MAX_TOTAL_BYTES = 260 * 1024 * 1024
MAX_DURATION = 600.0            # 10분
MIN_SEGMENT = 0.35              # 이미지 한 장 최소 노출(초)
SUB_BOTTOM = 400                # 자막 하단 여백(px)
SUB_MAX_WIDTH = 940             # 자막 최대 폭(px)
MAX_SUBTITLES = 300             # 한 영상에 넣을 자막 토막 최대 수

OUTPUT_DIR = os.path.join(BASE_DIR, "output")

IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".heic", ".heif", ".tif", ".tiff")


def log(msg):
    print("[shorts-maker] " + str(msg), flush=True)


# ───────────────────────────── ffmpeg / Pillow ─────────────────────────────

def ffmpeg_exe():
    """imageio-ffmpeg 가 내려받은 ffmpeg 바이너리 경로 (없으면 시스템 ffmpeg)."""
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:  # noqa: BLE001
        found = shutil.which("ffmpeg")
        if found:
            return found
        raise RuntimeError(
            "ffmpeg 를 찾을 수 없습니다. 실행하기.bat 을 다시 실행하면 자동으로 설치됩니다."
        )


FONT_CANDIDATES = [
    # Windows (맑은 고딕 굵게 -> 일반)
    r"C:\Windows\Fonts\malgunbd.ttf",
    r"C:\Windows\Fonts\malgun.ttf",
    r"C:\Windows\Fonts\NanumGothicBold.ttf",
    r"C:\Windows\Fonts\NanumGothic.ttf",
    # macOS
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",
    "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
    # Linux
    "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/pickle-hwp/NotoSansCJKkr-Regular.otf",
]

_FONT_CACHE = {}


def resolve_font():
    """자막용 한글 폰트 경로를 찾는다 (한 번 찾으면 캐시)."""
    if "path" in _FONT_CACHE:
        return _FONT_CACHE["path"]
    env = os.environ.get("SHORTS_FONT")
    cands = ([env] if env else []) + [
        os.path.join(BASE_DIR, "fonts", "NotoSansKR-Regular.ttf"),
        os.path.join(BASE_DIR, "fonts", "NanumGothicBold.ttf"),
        os.path.join(BASE_DIR, "fonts", "malgunbd.ttf"),
    ] + FONT_CANDIDATES
    for c in cands:
        if c and os.path.isfile(c):
            _FONT_CACHE["path"] = c
            log("자막 폰트: %s" % c)
            return c
    _FONT_CACHE["path"] = None
    log("경고: 한글 폰트를 찾지 못했습니다. 자막이 네모로 보일 수 있습니다.")
    return None


def run(cmd, cwd=None, timeout=900):
    proc = subprocess.run(
        cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout
    )
    return proc.returncode, proc.stdout.decode("utf-8", "replace"), proc.stderr.decode(
        "utf-8", "replace"
    )


_FILTER_OPT = {}


def filter_file_option(work):
    """filter_complex 를 파일로 넘기는 옵션명을 찾는다.
    ffmpeg 7.1+ 는 -/filter_complex, 그 전 버전은 -filter_complex_script.
    (Windows 명령줄 8191자 제한을 피하려고 항상 파일로 넘긴다)"""
    if "opt" in _FILTER_OPT:
        return _FILTER_OPT["opt"]
    exe = ffmpeg_exe()
    probe = os.path.join(work, "_probe.txt")
    with open(probe, "w", encoding="utf-8") as fh:
        fh.write("[0:v]null[vout]")
    for opt in ("-/filter_complex", "-filter_complex_script"):
        code, _, _ = run(
            [exe, "-hide_banner", "-y", "-f", "lavfi", "-i", "color=c=black:s=16x16:d=0.1",
             opt, "_probe.txt", "-map", "[vout]", "-f", "null", "-"],
            cwd=work,
        )
        if code == 0:
            _FILTER_OPT["opt"] = opt
            log("filter 파일 옵션: %s" % opt)
            return opt
    _FILTER_OPT["opt"] = "-filter_complex_script"
    return _FILTER_OPT["opt"]


DUR_RE = re.compile(r"Duration:\s*(\d+):(\d+):(\d+)(?:[.,](\d+))?")


def probe_duration(path):
    """ffmpeg -i 출력에서 길이(초)를 읽는다. (ffprobe 없이)"""
    exe = ffmpeg_exe()
    cwd = os.path.dirname(os.path.abspath(path))
    _, _, err = run([exe, "-hide_banner", "-i", os.path.basename(path)], cwd=cwd)
    m = DUR_RE.search(err)
    if not m:
        return 0.0
    h, mi, s, frac = m.group(1), m.group(2), m.group(3), m.group(4) or "0"
    return int(h) * 3600 + int(mi) * 60 + int(s) + float("0." + frac)


# ───────────────────────────── 자막(.srt) ─────────────────────────────

def decode_text(raw):
    for enc in ("utf-8-sig", "utf-8", "cp949", "euc-kr"):
        try:
            return raw.decode(enc)
        except Exception:  # noqa: BLE001
            continue
    return raw.decode("utf-8", "replace")


def srt_time(value):
    m = re.match(
        r"\s*(\d+):(\d{1,2}):(\d{1,2})[,.](\d{1,3})\s*$", value.replace(",", ".")
    )
    if not m:
        return None
    h, mi, s, ms = (int(g) for g in m.groups())
    return h * 3600 + mi * 60 + s + ms / 1000.0


def parse_srt(text):
    """자막 파일에서 [{start, end, lines[]}] 를 뽑는다. WEBVTT 도 관대하게 처리."""
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    cues = []
    blocks = re.split(r"\n\s*\n", text)
    for block in blocks:
        lines = [ln.strip() for ln in block.split("\n") if ln.strip()]
        if not lines:
            continue
        if lines[0].isdigit() and len(lines) > 1:
            lines = lines[1:]
        if not lines:
            continue
        if "-->" not in lines[0]:
            continue
        left, _, right = lines[0].partition("-->")
        start = srt_time(left)
        end = srt_time(right.strip().split(" ")[0])
        if start is None or end is None:
            continue
        body = " ".join(lines[1:])
        body = re.sub(r"<[^>]+>", "", body)            # <i> 등 태그 제거
        body = re.sub(r"\{\\[^}]*\}", "", body)        # {\an8} 등 제거
        body = body.replace("&nbsp;", " ").replace("&amp;", "&")
        body = re.sub(r"\s+", " ", body).strip()
        if not body:
            continue
        if end <= start:
            end = start + 1.0
        cues.append({"start": start, "end": end, "text": body})
    cues.sort(key=lambda c: c["start"])
    # 겹치는 자막은 앞 자막 끝을 당겨서 한 번에 두 줄이 뜨지 않게 정리
    for i in range(len(cues) - 1):
        if cues[i]["end"] > cues[i + 1]["start"]:
            cues[i]["end"] = max(cues[i]["start"] + 0.2, cues[i + 1]["start"] - 0.04)
    return cues


# ───────────────────────────── 이미지 합성(Pillow) ─────────────────────────────

def load_font(size):
    from PIL import ImageFont
    path = resolve_font()
    if not path:
        return None
    try:
        return ImageFont.truetype(path, size)
    except Exception:  # noqa: BLE001
        return None


def _wrap_once(text, font, size, max_width):
    out, cur = [], ""
    for ch in text:
        trial = cur + ch
        try:
            width = font.getlength(trial)
        except Exception:  # noqa: BLE001
            width = len(trial) * size
        if width > max_width and cur:
            # 공백이 있으면 공백에서 끊는다 (영어 단어가 쪼개지지 않게)
            if " " in cur:
                head, _, tail = cur.rpartition(" ")
                if tail:
                    out.append(head)
                    cur = tail + ch
                    continue
            out.append(cur)
            cur = ch
        else:
            cur = trial
    if cur:
        out.append(cur)
    return out


def wrap_subtitle(text, size, max_width=SUB_MAX_WIDTH):
    """실제 폰트로 폭을 재서 자막을 여러 줄로 나눈다. 마지막 줄이 외톨이가 되지 않게 균형도 맞춘다."""
    font = load_font(size)
    if font is None:
        per_line = max(6, int(max_width / (size * 0.98)))
        out, cur = [], ""
        for w in text.split(" "):
            trial = (cur + " " + w).strip()
            if len(trial) > per_line and cur:
                out.append(cur)
                cur = w
            else:
                cur = trial
        if cur:
            out.append(cur)
        return [l.strip() for l in out if l.strip()]

    lines = _wrap_once(text, font, size, max_width)
    if len(lines) > 1:
        try:
            total = font.getlength(text)
        except Exception:  # noqa: BLE001
            total = len(text) * size
        # 줄 수는 그대로 두고 폭만 줄여 가며 고르게 나누기
        for factor in (1.08, 1.0, 0.92, 0.84, 0.76):
            target = min(max_width, total / len(lines) * factor)
            if target < size * 3:
                break
            if target >= max_width:
                continue
            alt = _wrap_once(text, font, size, target)
            if len(alt) == len(lines):
                def weakness(ls):
                    try:
                        return min(font.getlength(x) for x in ls) / max(1.0, max(font.getlength(x) for x in ls))
                    except Exception:  # noqa: BLE001
                        return 1.0
                if weakness(alt) > weakness(lines):
                    lines = alt
    return [l.strip() for l in lines if l.strip()]


def compose_base(src, dst, style, w, h):
    """이미지를 9:16 캔버스(배경 + 가운데 이미지)로 합성해 PNG 로 저장."""
    from PIL import Image, ImageFilter, ImageOps

    with Image.open(src) as im0:
        try:
            im0 = ImageOps.exif_transpose(im0)
        except Exception:  # noqa: BLE001
            pass
        im = im0.convert("RGBA")

    iw, ih = im.size
    if iw <= 0 or ih <= 0:
        raise ValueError("이미지를 읽을 수 없습니다: %s" % os.path.basename(src))

    # 배경
    if style == "white":
        canvas = Image.new("RGB", (w, h), (255, 255, 255))
    else:
        canvas = Image.new("RGB", (w, h), (8, 8, 10))

    if style == "fill":
        scale = max(w / iw, h / ih)
        nw, nh = max(1, int(round(iw * scale))), max(1, int(round(ih * scale)))
        big = im.resize((nw, nh), Image.LANCZOS)
        left = (nw - w) // 2
        top = (nh - h) // 2
        flat = big.convert("RGB").crop((left, top, left + w, top + h))
        flat.save(dst, "PNG")
        return

    if style == "blur":
        scale = max(w / iw, h / ih)
        nw, nh = max(1, int(round(iw * scale))), max(1, int(round(ih * scale)))
        cover = im.convert("RGB").resize((nw, nh), Image.LANCZOS)
        left = (nw - w) // 2
        top = (nh - h) // 2
        cover = cover.crop((left, top, left + w, top + h))
        # 빠른 블러: 작게 줄였다가 되돌린다
        small_w, small_h = max(8, w // 14), max(8, h // 14)
        small = cover.resize((small_w, small_h), Image.BILINEAR)
        small = small.filter(ImageFilter.GaussianBlur(radius=6))
        bg = small.resize((w, h), Image.BICUBIC)
        # 살짝 어둡게 해서 가운데 이미지가 뜨게
        bg = bg.point(lambda v: int(v * 0.72))
        canvas = bg

    # 가운데 맞춤(contain)
    scale = min(w / iw, h / ih)
    tw, th = max(1, int(round(iw * scale))), max(1, int(round(ih * scale)))
    fitted = im.resize((tw, th), Image.LANCZOS)
    canvas.paste(fitted, ((w - tw) // 2, (h - th) // 2), fitted)
    canvas.save(dst, "PNG")


def render_subtitle_png(lines, size, font_path, dst, w):
    """자막 한 토막을 글자 띠만큼만 투명 PNG 로 그린다 (굵은 흰 글씨 + 검은 테두리).
    ffmpeg 의 drawtext/폰트 설정에 기대지 않고, 메모리도 아끼려고 띠 모양으로 그린다.
    돌려주는 값은 이 PNG 를 붙일 y 위치."""
    from PIL import Image, ImageDraw, ImageFont

    font = ImageFont.truetype(font_path, size)
    line_h = int(round(size * 1.30))
    stroke = max(3, int(round(size * 0.12)))
    pad = 4
    total_h = line_h * len(lines)
    band_h = total_h + 2 * (stroke + pad)
    img = Image.new("RGBA", (w, band_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    for i, line in enumerate(lines):
        cy = stroke + pad + i * line_h + line_h // 2
        draw.text(
            (w // 2, cy), line, font=font, fill=(255, 255, 255, 255),
            stroke_width=stroke, stroke_fill=(0, 0, 0, 238), anchor="mm",
        )
    img.save(dst, "PNG")
    return max(0, OUT_H - SUB_BOTTOM - total_h - stroke - pad)


# ───────────────────────────── 렌더링 ─────────────────────────────

def build_filter(cues, seg_frames, zoom, sub_input_base):
    """filter_complex 문자열. 이미지별 줌 -> 이어붙이기 -> 자막 PNG 오버레이."""
    parts = []
    for i, frames in enumerate(seg_frames):
        f = max(2, int(frames))
        zoom_in = (i % 2 == 0)
        if zoom:
            z = "min(1+0.11*on/%d,1.11)" % f if zoom_in else "max(1.11-0.11*on/%d,1.0)" % f
        else:
            z = "1"
        # zoompan 은 정지 이미지 1장을 d 프레임으로 늘려 준다 (줌 없을 때도 z=1 로 같은 경로)
        zp = "zoompan=z='%s':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=%d:s=%dx%d:fps=%d" % (
            z, f, OUT_W, OUT_H, FPS,
        )
        parts.append("[%d:v]%s,setsar=1[v%d]" % (i, zp, i))

    n = len(seg_frames)
    if n == 1:
        last = "v0"
    else:
        inputs = "".join("[v%d]" % i for i in range(n))
        parts.append("%sconcat=n=%d:v=1:a=0[vcat]" % (inputs, n))
        last = "vcat"

    for k, cue in enumerate(cues):
        src = "[%s]" % last
        out = "vs%d" % k
        parts.append(
            "%s[%d:v]overlay=0:%d:enable='between(t,%.3f,%.3f)'[%s]"
            % (src, sub_input_base + k, cue.get("y", OUT_H - SUB_BOTTOM), cue["start"], cue["end"], out)
        )
        last = out
    parts.append("[%s]format=yuv420p[vout]" % last)
    return ";".join(parts)


def render_job(images, audio, srt_cues, bgm, opts, work):
    """이미지/음성/자막/BGM 으로 mp4 를 만든다. 결과 파일 경로와 정보를 돌려준다."""
    started = time.time()
    style = str(opts.get("bg_style") or "black").lower()
    if style not in ("black", "white", "blur", "fill"):
        style = "black"
    zoom = bool(opts.get("zoom", True))
    sub_size = int(opts.get("subtitle_size") or 58)
    sub_size = max(28, min(110, sub_size))
    bgm_vol = float(opts.get("bgm_vol") or 0.0)
    bgm_vol = max(0.0, min(1.0, bgm_vol))

    # 1) 음성 길이
    duration = 0.0
    if audio:
        duration = probe_duration(audio)
    if duration <= 0:
        duration = max(3.0, 3.0 * len(images))
    duration = min(duration, MAX_DURATION + 0.01)
    total_frames = max(len(images), int(round(duration * FPS)))

    # 2) 장면 길이 균등 배분 (마지막 장이 남는 프레임을 흡수)
    n = len(images)
    base = total_frames // n
    seg = [base] * n
    for i in range(total_frames - base * n):
        seg[i] += 1
    min_frames = max(2, int(round(MIN_SEGMENT * FPS)))
    for i in range(n):
        if seg[i] < min_frames:
            seg[i] = min_frames
    if sum(seg) != total_frames:
        # 최소 길이 보정으로 늘어난 프레임은 가장 긴 장면에서 덜어낸다
        diff = sum(seg) - total_frames
        while diff > 0:
            j = seg.index(max(seg))
            take = min(diff, seg[j] - min_frames)
            if take <= 0:
                break
            seg[j] -= take
            diff -= take
        total_frames = sum(seg)
    duration = total_frames / float(FPS)

    # 3) 배경 합성
    base_w, base_h = int(OUT_W * BASE_SCALE), int(OUT_H * BASE_SCALE)
    for i, src in enumerate(images):
        compose_base(src, os.path.join(work, "base_%03d.png" % i), style, base_w, base_h)

    # 4) 자막 준비 — Pillow 로 투명 PNG 를 그려 둔다
    use_bgm = bool(audio and bgm and bgm_vol > 0)
    sub_base = n + (1 if audio else 0) + (1 if use_bgm else 0)
    font_path = resolve_font()
    cues = []
    if srt_cues and font_path:
        for cue in srt_cues:
            if cue["start"] >= duration:
                continue
            lines = wrap_subtitle(cue["text"], sub_size)
            if not lines:
                continue
            item = dict(cue)
            item["end"] = min(item["end"], duration)
            item["lines"] = lines
            if item["end"] - item["start"] < 0.15:
                continue
            cues.append(item)
        if len(cues) > MAX_SUBTITLES:
            cues = cues[:MAX_SUBTITLES]
        try:
            for idx, cue in enumerate(cues):
                cue["y"] = render_subtitle_png(
                    cue["lines"], sub_size, font_path,
                    os.path.join(work, "sub_%03d.png" % idx), OUT_W,
                )
        except Exception as exc:  # noqa: BLE001
            log("자막 그림을 만들지 못했습니다 (%s) — 자막 없이 진행합니다." % exc)
            cues = []

    # 5) ffmpeg 실행
    filter_str = build_filter(cues, seg, zoom, sub_base)

    if use_bgm:
        # 영상 필터와 오디오 믹싱 필터를 하나의 filter_complex 로 합친다
        afilter = (
            "[%d:a]volume=1.0,aresample=44100[voice];"
            "[%d:a]volume=%.3f,atrim=0:%.3f,asetpts=N/SR/TB,aresample=44100[music];"
            "[voice][music]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.97[aout]"
            % (n, n + 1, bgm_vol, duration)
        )
        filter_str = filter_str + ";" + afilter
    with open(os.path.join(work, "filter.txt"), "w", encoding="utf-8") as fh:
        fh.write(filter_str)

    cmd = [ffmpeg_exe(), "-hide_banner", "-y", "-loglevel", "error"]
    for i in range(n):
        cmd += ["-i", "base_%03d.png" % i]
    if audio:
        cmd += ["-i", os.path.abspath(audio)]
    if use_bgm:
        cmd += ["-stream_loop", "-1", "-i", os.path.abspath(bgm)]
    for idx in range(len(cues)):
        cmd += ["-i", "sub_%03d.png" % idx]
    cmd += [filter_file_option(work), "filter.txt", "-map", "[vout]"]
    if use_bgm:
        cmd += ["-map", "[aout]"]
    elif audio:
        cmd += ["-map", "%d:a" % n]

    out_name = "short_%s.mp4" % time.strftime("%Y%m%d_%H%M%S")
    cmd += [
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-pix_fmt", "yuv420p", "-profile:v", "high", "-level", "4.1",
        "-r", str(FPS), "-g", str(FPS * 2),
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
        "-movflags", "+faststart",
        "-t", "%.3f" % duration,
        out_name,
    ]

    log("렌더 시작: 이미지 %d장 / %.1f초 / %d프레임 / 스타일=%s / 줌=%s" % (n, duration, total_frames, style, zoom))
    code, out, err = run(cmd, cwd=work)
    if code != 0:
        tail = "\n".join(err.strip().splitlines()[-12:])
        raise RuntimeError("영상 인코딩에 실패했습니다.\n%s" % (tail or "알 수 없는 오류"))
    out_path = os.path.join(work, out_name)
    if not os.path.isfile(out_path) or os.path.getsize(out_path) < 1024:
        raise RuntimeError("영상 파일이 만들어지지 않았습니다.")

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    saved = os.path.join(OUTPUT_DIR, out_name)
    try:
        shutil.copyfile(out_path, saved)
    except Exception:  # noqa: BLE001
        saved = out_path
    return {
        "path": out_path,
        "saved": saved if os.path.isfile(saved) else None,
        "duration": round(duration, 2),
        "frames": total_frames,
        "images": n,
        "segments": [round(s / float(FPS), 2) for s in seg],
        "subtitles": len(cues),
        "bgm": bool(audio and bgm and bgm_vol > 0),
        "elapsed": round(time.time() - started, 1),
        "size": os.path.getsize(out_path),
    }


# ───────────────────────────── 요청 파싱 ─────────────────────────────

class RequestError(Exception):
    pass


def parse_multipart(body, boundary):
    """{name: [(filename, ctype, data), ...]} 로 나눈다."""
    out = {}
    delim = b"--" + boundary
    for chunk in body.split(delim):
        if not chunk or chunk.startswith(b"--"):
            continue
        if chunk.startswith(b"\r\n"):
            chunk = chunk[2:]
        elif chunk.startswith(b"\n"):
            chunk = chunk[1:]
        head, sep, data = chunk.partition(b"\r\n\r\n")
        if not sep:
            head, sep, data = chunk.partition(b"\n\n")
            if not sep:
                continue
        if data.endswith(b"\r\n"):
            data = data[:-2]
        elif data.endswith(b"\n"):
            data = data[:-1]
        head_txt = head.decode("utf-8", "replace")
        name_m = re.search(r'name="([^"]*)"', head_txt)
        if not name_m:
            continue
        file_m = re.search(r'filename="([^"]*)"', head_txt)
        ctype_m = re.search(r"Content-Type:\s*([^\r\n;]+)", head_txt, re.I)
        content_type = ctype_m.group(1).strip() if ctype_m else ""
        out.setdefault(name_m.group(1), []).append(
            (file_m.group(1) if file_m else None, content_type, data)
        )
    return out


def parse_base64(value):
    if not value:
        return b""
    if isinstance(value, dict):
        value = value.get("base64") or value.get("data") or ""
    if not isinstance(value, str):
        return b""
    if "," in value and value.strip().lower().startswith("data:"):
        value = value.split(",", 1)[1]
    try:
        return base64.b64decode(value, validate=False)
    except Exception as exc:  # noqa: BLE001
        raise RequestError("이미지/음성 데이터(base64)를 읽지 못했습니다: %s" % exc)


def clamp_float(value, default, low, high):
    try:
        num = float(str(value).strip())
    except Exception:  # noqa: BLE001
        return default
    if num != num:  # NaN
        return default
    return max(low, min(high, num))


def clamp_int(value, default, low, high):
    try:
        num = int(round(float(str(value).strip())))
    except Exception:  # noqa: BLE001
        return default
    return max(low, min(high, num))


def truthy(value, default=True):
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "on", "y", "t")


class Handler(SimpleHTTPRequestHandler):
    server_version = "ShortsMaker/" + SERVER_VERSION
    protocol_version = "HTTP/1.1"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=BASE_DIR, **kwargs)

    def log_message(self, fmt, *args):
        log("%s - %s" % (self.address_string(), fmt % args))

    # ---------- 공통 ----------
    def cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header(
            "Access-Control-Allow-Headers",
            "Content-Type, Accept, X-Requested-With, Range",
        )
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.send_header("Access-Control-Max-Age", "86400")

    def json_response(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.cors()
        self.end_headers()
        self.wfile.write(body)

    def read_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return b""
        if length > MAX_TOTAL_BYTES:
            raise RequestError(
                "업로드 용량이 너무 큽니다. (최대 %dMB) 이미지 수나 크기를 줄여 주세요."
                % (MAX_TOTAL_BYTES // (1024 * 1024))
            )
        return self.rfile.read(length)

    # ---------- 라우팅 ----------
    def do_OPTIONS(self):
        self.send_response(204)
        self.cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/health", "/healthz", "/api/health"):
            return self.json_response(self.health_payload())
        return super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path in ("/render", "/api/render"):
            return self.handle_render()
        try:
            self.read_body()
        except Exception:  # noqa: BLE001
            pass
        self.json_response({"ok": False, "error": "알 수 없는 경로입니다: %s" % parsed.path}, 404)

    # ---------- 상태 ----------
    def health_payload(self):
        try:
            exe = ffmpeg_exe()
            ff = os.path.basename(exe)
        except Exception:  # noqa: BLE001
            ff = None
        return {
            "ok": True,
            "service": "shorts-maker",
            "version": SERVER_VERSION,
            "ffmpeg": ff,
            "font": os.path.basename(resolve_font() or "") or None,
            "python": sys.version.split()[0],
            "port": self.server.server_address[1],
            "output": "1080x1920",
            "fps": FPS,
            "max_images": MAX_IMAGES,
        }

    # ---------- 렌더 ----------
    def handle_render(self):
        work = tempfile.mkdtemp(prefix="shorts-maker-")
        try:
            images, audio, srt_text, bgm, opts = self.collect(work)
        except RequestError as exc:
            shutil.rmtree(work, ignore_errors=True)
            return self.json_response({"ok": False, "error": str(exc)}, 400)
        except Exception as exc:  # noqa: BLE001
            shutil.rmtree(work, ignore_errors=True)
            traceback.print_exc()
            return self.json_response({"ok": False, "error": "요청을 읽지 못했습니다: %s" % exc}, 400)

        if not images:
            shutil.rmtree(work, ignore_errors=True)
            return self.json_response({"ok": False, "error": "이미지를 1장 이상 넣어 주세요."}, 400)

        cues = parse_srt(srt_text) if srt_text else []
        try:
            info = render_job(images, audio, cues, bgm, opts, work)
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            shutil.rmtree(work, ignore_errors=True)
            return self.json_response(
                {"ok": False, "error": str(exc) or "영상 생성에 실패했습니다."}, 500
            )

        size = info["size"]
        try:
            with open(info["path"], "rb") as fh:
                payload = fh.read()
        except Exception as exc:  # noqa: BLE001
            shutil.rmtree(work, ignore_errors=True)
            return self.json_response({"ok": False, "error": "영상 파일을 읽지 못했습니다: %s" % exc}, 500)

        log(
            "렌더 완료: %.1fs / %.1fMB / %.1f초 / 자막 %d개 / %s"
            % (info["elapsed"], size / 1048576.0, info["duration"], info["subtitles"], info["saved"] or "-")
        )

        self.send_response(200)
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Disposition", 'inline; filename="shorts.mp4"')
        self.send_header("X-Video-Duration", "%.2f" % info["duration"])
        self.send_header("X-Video-Frames", str(info["frames"]))
        self.send_header("X-Video-Segments", ",".join("%.2f" % s for s in info["segments"]))
        self.send_header("X-Video-Subtitles", str(info["subtitles"]))
        self.send_header("X-Render-Sec", "%.1f" % info["elapsed"])
        self.send_header("X-Saved-Path", os.path.basename(info["saved"] or ""))
        self.send_header(
            "Access-Control-Expose-Headers",
            "X-Video-Duration, X-Video-Frames, X-Video-Segments, X-Video-Subtitles, "
            "X-Render-Sec, X-Saved-Path",
        )
        self.cors()
        self.end_headers()
        try:
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def collect(self, work):
        """요청(multipart 또는 JSON base64)을 파일로 풀어 놓는다."""
        raw = self.read_body()
        ctype = (self.headers.get("Content-Type") or "").lower()
        images, audio, bgm, srt_text = [], None, None, ""
        opts = {}

        if "multipart/form-data" in ctype:
            m = re.search(r"boundary=([^;]+)", self.headers.get("Content-Type") or "", re.I)
            if not m:
                raise RequestError("multipart 경계값이 없습니다.")
            boundary = m.group(1).strip().strip('"').encode("utf-8")
            fields = parse_multipart(raw, boundary)

            def files(name):
                return [f for f in fields.get(name, []) if f[0] is not None and len(f[2]) > 0]

            for i, (fname, fctype, data) in enumerate(files("images")):
                ext = pick_ext(fname, fctype, IMAGE_EXTS, ".jpg")
                if len(data) > MAX_IMAGE_BYTES:
                    raise RequestError("이미지 한 장은 %dMB 까지 가능합니다." % (MAX_IMAGE_BYTES // 1048576))
                dst = os.path.join(work, "src_%03d%s" % (i, ext))
                with open(dst, "wb") as fh:
                    fh.write(data)
                images.append(dst)

            audio_files = files("audio") or files("voice") or files("mp3")
            if audio_files:
                fname, fctype, data = audio_files[0]
                if len(data) > MAX_AUDIO_BYTES:
                    raise RequestError("음성 파일은 %dMB 까지 가능합니다." % (MAX_AUDIO_BYTES // 1048576))
                audio = os.path.join(work, "voice" + pick_ext(fname, fctype, (".mp3", ".wav", ".m4a", ".aac", ".ogg", ".opus"), ".mp3"))
                with open(audio, "wb") as fh:
                    fh.write(data)

            bgm_files = files("bgm")
            if bgm_files:
                fname, fctype, data = bgm_files[0]
                if len(data) > MAX_AUDIO_BYTES:
                    raise RequestError("BGM 파일은 %dMB 까지 가능합니다." % (MAX_AUDIO_BYTES // 1048576))
                bgm = os.path.join(work, "bgm" + pick_ext(fname, fctype, (".mp3", ".wav", ".m4a", ".aac", ".ogg", ".opus"), ".mp3"))
                with open(bgm, "wb") as fh:
                    fh.write(data)

            srt_files = files("srt") or files("subtitle")
            if srt_files:
                data = srt_files[0][2][:MAX_SRT_BYTES]
                srt_text = decode_text(data)
            elif fields.get("srt_text"):
                srt_text = decode_text(fields["srt_text"][0][2])

            for key, name in (("zoom", "zoom"), ("bg_style", "bg_style"), ("bgm_vol", "bgm_vol"),
                              ("subtitle_size", "subtitle_size")):
                if fields.get(key):
                    opts[key] = decode_text(fields[key][0][2]).strip()
        else:
            try:
                payload = json.loads(raw.decode("utf-8", "replace") or "{}")
            except json.JSONDecodeError as exc:
                raise RequestError("JSON 형식이 올바르지 않습니다: %s" % exc)
            if not isinstance(payload, dict):
                raise RequestError("JSON 본문이 올바르지 않습니다.")

            raw_images = payload.get("images") or payload.get("images_base64") or []
            if isinstance(raw_images, str):
                raw_images = [raw_images]
            for i, item in enumerate(raw_images):
                data = parse_base64(item)
                if not data:
                    continue
                ext = pick_ext(
                    (item or {}).get("name") if isinstance(item, dict) else "",
                    "",
                    IMAGE_EXTS,
                    ".jpg",
                )
                dst = os.path.join(work, "src_%03d%s" % (i, ext))
                with open(dst, "wb") as fh:
                    fh.write(data)
                images.append(dst)

            audio = write_b64(work, "voice", payload.get("audio") or payload.get("audio_base64"), ".mp3", MAX_AUDIO_BYTES)
            bgm = write_b64(work, "bgm", payload.get("bgm") or payload.get("bgm_base64"), ".mp3", MAX_AUDIO_BYTES)
            srt_raw = payload.get("srt_text") or payload.get("srt")
            if isinstance(srt_raw, str) and srt_raw.strip() and "-->" in srt_raw:
                srt_text = srt_raw
            else:
                srt_data = parse_base64(srt_raw) if srt_raw else parse_base64(payload.get("srt_base64"))
                if srt_data:
                    srt_text = decode_text(srt_data[:MAX_SRT_BYTES])
            opts = payload.get("options") if isinstance(payload.get("options"), dict) else payload

        if len(images) > MAX_IMAGES:
            raise RequestError("이미지는 최대 %d장까지 넣을 수 있습니다." % MAX_IMAGES)

        return (
            images,
            audio,
            srt_text,
            bgm,
            {
                "zoom": truthy(opts.get("zoom"), True),
                "bg_style": str(opts.get("bg_style") or "black"),
                "bgm_vol": clamp_float(opts.get("bgm_vol"), 0.12, 0.0, 1.0),
                "subtitle_size": clamp_int(opts.get("subtitle_size"), 58, 28, 110),
            },
        )


def pick_ext(filename, content_type, allowed, default):
    name = (filename or "").lower()
    ext = os.path.splitext(name)[1]
    if ext in allowed:
        return ext
    if ext in (".jpeg",) and ".jpg" in allowed:
        return ".jpg"
    ct = (content_type or "").lower()
    if "png" in ct:
        return ".png"
    if "webp" in ct:
        return ".webp"
    if "mpeg" in ct or "mp3" in ct:
        return ".mp3"
    if "wav" in ct:
        return ".wav"
    if "mp4" in ct or "m4a" in ct:
        return ".m4a"
    return default


def write_b64(work, stem, value, ext, limit):
    if not value:
        return None
    data = parse_base64(value)
    if not data:
        return None
    if len(data) > limit:
        raise RequestError("파일 용량이 너무 큽니다. (%dMB 초과)" % (limit // 1048576))
    dst = os.path.join(work, stem + ext)
    with open(dst, "wb") as fh:
        fh.write(data)
    return dst


# ───────────────────────────── 실행 ─────────────────────────────

def find_free_port(host, port, tries=30):
    for offset in range(tries):
        candidate = port + offset
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind((host, candidate))
                return candidate
            except OSError:
                continue
    return port


def open_browser_later(url, delay=1.0):
    def runner():
        time.sleep(delay)
        try:
            webbrowser.open(url)
        except Exception:  # noqa: BLE001
            log("브라우저 자동 열기에 실패했습니다. 직접 %s 를 열어 주세요." % url)

    threading.Thread(target=runner, daemon=True).start()


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

    parser = argparse.ArgumentParser(description="쇼츠 메이커 로컬 서버")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--open", dest="open_browser", action="store_true", help="브라우저 자동 열기")
    parser.add_argument("--no-open", dest="open_browser", action="store_false", help="브라우저 열지 않기")
    parser.set_defaults(open_browser=True)
    args = parser.parse_args()

    port = find_free_port(args.host, args.port)
    if port != args.port:
        log("포트 %d 가 사용 중이라 %d 로 시작합니다." % (args.port, port))

    try:
        exe = ffmpeg_exe()
        log("ffmpeg: %s" % os.path.basename(exe))
    except Exception as exc:  # noqa: BLE001
        log("경고: %s" % exc)
    resolve_font()
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    url = "http://%s:%d/" % (args.host, port)
    try:
        httpd = ThreadingHTTPServer((args.host, port), Handler)
    except OSError as exc:
        log("서버를 시작할 수 없습니다: %s" % exc)
        input("엔터를 누르면 종료합니다...")
        return 1

    httpd.daemon_threads = True
    log("쇼츠 메이커 서버 시작 → %s" % url)
    log("이 창을 닫으면 서버가 꺼집니다. (Ctrl+C 로도 종료)")
    if args.open_browser:
        open_browser_later(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        log("서버를 종료합니다.")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
