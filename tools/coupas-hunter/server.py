#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""쿠파스 가성비 상품 헌터 — 로컬 프록시 서버

Python 표준 라이브러리만 사용합니다. (추가 pip 설치 없음)

보안 원칙
  * 쿠팡 파트너스 Access/Secret Key 는 이 서버가 도는 PC 안에서만 읽습니다.
  * 키 값은 어떤 응답에도 담기지 않습니다. (/health 는 앞 4자리만 마스킹해 반환)
  * 서버는 127.0.0.1 에만 바인딩되어 같은 PC 밖에서는 접근할 수 없습니다.
  * 키 저장 위치: 이 파일 옆 coupas-api-key.env (권한 600)

주소 (기본 포트 8767)
  GET  /health                      서버·키 상태 (키 값은 절대 반환하지 않음)
  POST /config                      {"access_key":"...","secret_key":"..."} → 로컬 env 파일 저장
  POST /config/clear                로컬 키 삭제
  GET  /api/search?q=..&max_price=..&rocket=1&sort=value|price|discount
                                    쿠팡 상품 검색 (가성비 점수·가격·할인율 정렬)
  POST /api/links                   {"product_id":".."} → 4채널(쓰레드·유튜브·틱톡·shop-links) 단축 링크
  GET  /download/zip                이 폴더의 실행용 ZIP (키 파일 제외)
  GET  /                            웹 UI

실행: python server.py [--port 8767] [--no-browser]
"""

from __future__ import annotations

import hashlib
import hmac
import io
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
import zipfile
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

APP_NAME = "쿠파스 가성비 상품 헌터"
APP_ID = "coupas-hunter"
VERSION = "1.0.0"
DEFAULT_PORT = 8767
HOST = "127.0.0.1"

BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / "coupas-api-key.env"
HOME_ENV_FILE = Path.home() / ".coupas-api-key.env"

API_HOST = "https://api-gateway.coupang.com"
SEARCH_PATH = "/v2/providers/affiliate_open_api/apis/openapi/v1/products/search"
DEEPLINK_PATH = "/v2/providers/affiliate_open_api/apis/openapi/v1/deeplink"
PRODUCT_URL = "https://www.coupang.com/vp/products/{pid}"

# 채널 순서: 쓰레드 · 유튜브 · 틱톡 · shop-links
CHANNELS = (
    ("anchithreads", "쓰레드"),
    ("anchiyoutube", "유튜브"),
    ("anchitiktok", "틱톡"),
    ("anchishoplinks", "shop-links"),
)
SUB_ID_MIN, SUB_ID_MAX = 8, 20

STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "application/javascript; charset=utf-8"),
    "/favicon.svg": ("favicon.svg", "image/svg+xml"),
    "/README.md": ("README.md", "text/markdown; charset=utf-8"),
}

CACHE_TTL = 600  # 검색 결과 메모리 캐시(초) — 프리셋을 눌러도 API 호출을 아낍니다
_cache: dict[str, tuple[float, list[dict]]] = {}
_cache_lock = threading.Lock()


class ApiError(RuntimeError):
    pass


# --------------------------------------------------------------------- 키 파일
def _parse_env(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        values[key.strip()] = val.strip().strip('"').strip("'")
    return values


def current_keys() -> tuple[str, str]:
    """키를 읽습니다. 우선순위: 환경변수 → 이 폴더 env → 홈 폴더 env."""
    access = os.environ.get("COUPANG_ACCESS_KEY", "").strip()
    secret = os.environ.get("COUPANG_SECRET_KEY", "").strip()
    if access and secret:
        return access, secret
    for path in (ENV_FILE, HOME_ENV_FILE):
        values: dict[str, str] = {}
        try:
            if path.is_file():
                values = _parse_env(path.read_text(encoding="utf-8"))
        except OSError:
            continue
        access = values.get("COUPANG_ACCESS_KEY", "").strip()
        secret = values.get("COUPANG_SECRET_KEY", "").strip()
        if access and secret:
            return access, secret
    raise ApiError(
        "쿠팡 파트너스 키가 설정되지 않았습니다. 화면 오른쪽 위 [키 설정]에서 "
        "Access Key / Secret Key를 입력해 주세요."
    )


def has_keys() -> bool:
    try:
        current_keys()
        return True
    except ApiError:
        return False


def key_hint() -> str:
    """키 값 자체는 절대 밖으로 내보내지 않고 앞 4자리만 보여 줍니다."""
    try:
        access, _ = current_keys()
    except ApiError:
        return ""
    return access[:4] + "*" * 6


def save_keys(access: str, secret: str) -> Path:
    text = (
        "# 쿠파스 가성비 상품 헌터 — 이 PC 전용 키 파일\n"
        "# 절대 GitHub 저장소나 웹 코드에 올리지 마세요.\n"
        f"COUPANG_ACCESS_KEY={access}\n"
        f"COUPANG_SECRET_KEY={secret}\n"
    )
    fd = os.open(str(ENV_FILE), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fp:
        fp.write(text)
    try:
        os.chmod(str(ENV_FILE), 0o600)
    except OSError:
        pass
    return ENV_FILE


def clear_keys() -> None:
    for path in (ENV_FILE, HOME_ENV_FILE):
        try:
            if path.is_file():
                path.unlink()
        except OSError:
            pass


# ------------------------------------------------------------------- 쿠팡 API
def signed_date_now() -> str:
    return datetime.now(timezone.utc).strftime("%y%m%dT%H%M%SZ")


def build_authorization(access: str, secret: str, method: str, path: str, query: str) -> str:
    """쿠팡 파트너스 규격: message = signed-date + method + path + query"""
    when = signed_date_now()
    message = when + method.upper() + path + query
    signature = hmac.new(
        secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return (
        f"CEA algorithm=HmacSHA256, access-key={access}, "
        f"signed-date={when}, signature={signature}"
    )


def coupang_request(
    method: str,
    path: str,
    query: str = "",
    payload: dict | None = None,
    access: str | None = None,
    secret: str | None = None,
    timeout: int = 20,
) -> dict:
    if access is None or secret is None:
        access, secret = current_keys()

    query = query.lstrip("?")
    url = API_HOST + path + (f"?{query}" if query else "")
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    headers = {
        "Authorization": build_authorization(access, secret, method, path, query),
        "Content-Type": "application/json;charset=UTF-8",
        "Accept": "application/json",
    }
    req = urllib.request.Request(url, data=body, headers=headers, method=method.upper())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            status = resp.status
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        if exc.code in (401, 403):
            raise ApiError(
                "쿠팡 파트너스 키가 거부되었습니다. Access/Secret Key를 다시 확인해 주세요. "
                f"(HTTP {exc.code})"
            ) from exc
        raise ApiError(f"쿠팡 API 오류 HTTP {exc.code}: {detail[:200]}") from exc
    except urllib.error.URLError as exc:
        raise ApiError(f"쿠팡 API에 연결하지 못했습니다: {exc.reason}") from exc
    except TimeoutError as exc:
        raise ApiError("쿠팡 API 응답이 너무 늦습니다. 잠시 뒤 다시 시도해 주세요.") from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise ApiError(f"쿠팡 API 응답을 해석할 수 없습니다 (HTTP {status}): {raw[:200]}")

    if str(data.get("rCode", "0")) not in ("0", "None"):
        raise ApiError(f"쿠팡 API 오류 rCode={data.get('rCode')} {data.get('rMessage') or ''}".strip())
    return data


def raw_search(keyword: str, limit: int = 10) -> list[dict]:
    keyword = keyword.strip()
    if not keyword:
        raise ApiError("검색어를 입력해 주세요.")
    limit = max(1, min(int(limit), 10))  # API 상한 10
    cache_key = f"{keyword.lower()}::{limit}"
    now = time.time()
    with _cache_lock:
        hit = _cache.get(cache_key)
        if hit and now - hit[0] < CACHE_TTL:
            return hit[1]

    query = urllib.parse.urlencode({"keyword": keyword, "limit": limit})
    data = coupang_request("GET", SEARCH_PATH, query)
    payload = data.get("data") or {}
    items = payload.get("productData") if isinstance(payload, dict) else payload
    items = items or []
    with _cache_lock:
        _cache[cache_key] = (now, items)
    return items


def deeplink(urls: list[str], sub_id: str, access: str, secret: str) -> list[dict]:
    payload: dict = {"coupangUrls": urls}
    if sub_id:
        payload["subId"] = sub_id
    data = coupang_request("POST", DEEPLINK_PATH, "", payload, access, secret)
    return data.get("data") or []


# ---------------------------------------------------------------- 검색 결과 정리
def _int(value) -> int | None:
    try:
        return int(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def normalize_items(items: list[dict]) -> list[dict]:
    """가성비 점수 = (최저가 ÷ 이 상품 가격) 70점 + 인기순위 보정 30점"""
    prices = [p for p in (_int(item.get("productPrice")) for item in items) if p]
    min_price = min(prices) if prices else 0
    out: list[dict] = []
    for idx, item in enumerate(items):
        pid = str(item.get("productId") or "").strip()
        price = _int(item.get("productPrice"))
        rank = _int(item.get("rank")) or (idx + 1)
        price_score = (min_price / price) if (price and min_price) else 0.0
        pop_score = max(0.0, 1.0 - (rank - 1) / 10.0)
        value_score = int(round(100 * (0.7 * min(price_score, 1.0) + 0.3 * pop_score)))

        list_price = (
            _int(item.get("listPrice"))
            or _int(item.get("originalPrice"))
            or _int(item.get("basePrice"))
        )
        discount_rate = None
        if list_price and price and list_price > price:
            discount_rate = int(round((1 - price / list_price) * 100))

        out.append(
            {
                "id": pid,
                "name": item.get("productName") or "(상품명 없음)",
                "price": price,
                "listPrice": list_price,
                "discountRate": discount_rate,
                "valueScore": value_score,
                "image": item.get("productImage") or "",
                "url": PRODUCT_URL.format(pid=pid) if pid else (item.get("productUrl") or ""),
                "affiliateUrl": item.get("productUrl") or "",
                "rocket": bool(item.get("isRocket")),
                "freeShipping": bool(item.get("isFreeShipping")),
                "category": item.get("categoryName") or "",
                "rank": rank,
                "under10k": bool(price and price <= 10000),
            }
        )
    return out


def filter_and_sort(
    items: list[dict],
    max_price: int | None = None,
    min_price: int | None = None,
    rocket: bool = False,
    free_shipping: bool = False,
    sort: str = "value",
) -> tuple[list[dict], str]:
    note = ""
    result = list(items)
    if min_price is not None:
        result = [p for p in result if p["price"] and p["price"] >= min_price]
    if max_price is not None:
        result = [p for p in result if p["price"] and p["price"] <= max_price]
    if rocket:
        result = [p for p in result if p["rocket"]]
    if free_shipping:
        filtered = [p for p in result if p["freeShipping"] or p["rocket"]]
        if filtered:
            result = filtered
        elif result:
            note = (
                "쿠팡 검색 API가 로켓배송 상품도 무료배송 값을 false로 주는 경우가 많아 "
                "무료배송 필터는 로켓배송까지 함께 봅니다."
            )

    if sort == "price":
        result.sort(key=lambda p: (p["price"] is None, p["price"] or 0))
    elif sort == "discount":
        if any(p["discountRate"] is not None for p in result):
            result.sort(key=lambda p: (p["discountRate"] is None, -(p["discountRate"] or 0)))
        else:
            result.sort(key=lambda p: -p["valueScore"])
            note = (
                "쿠팡 검색 API가 정가(할인 전 가격)를 주지 않아 "
                "할인율 대신 가성비 점수 높은 순으로 정렬했습니다."
            )
    elif sort == "rank":
        result.sort(key=lambda p: p["rank"])
    else:  # value
        result.sort(key=lambda p: -p["valueScore"])
    return result, note


def search_products(
    keyword: str,
    limit: int = 10,
    max_price: int | None = None,
    min_price: int | None = None,
    rocket: bool = False,
    free_shipping: bool = False,
    sort: str = "value",
) -> dict:
    items = normalize_items(raw_search(keyword, limit))
    filtered, note = filter_and_sort(items, max_price, min_price, rocket, free_shipping, sort)
    if not filtered and items:
        note = "조건에 맞는 상품이 없습니다. 가격·로켓 조건을 풀어 보세요."
    return {
        "ok": True,
        "keyword": keyword,
        "fetchedCount": len(items),
        "count": len(filtered),
        "items": filtered,
        "note": note,
        "fetchedAt": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
    }


def build_channel_links(product_id: str, name: str, price, image: str, category: str) -> dict:
    access, secret = current_keys()
    pid = str(product_id or "").strip()
    if not (pid.isdigit() and 4 <= len(pid) <= 20):
        raise ApiError("상품 ID가 올바르지 않습니다.")
    canonical = PRODUCT_URL.format(pid=pid)

    links = []
    for sub_id, label in CHANNELS:
        entry = {
            "subId": sub_id,
            "channel": label,
            "shortenUrl": "",
            "landingUrl": "",
            "error": None,
        }
        try:
            data = deeplink([canonical], sub_id, access, secret)
            found = data[0] if data else {}
            entry["shortenUrl"] = found.get("shortenUrl") or ""
            entry["landingUrl"] = found.get("landingUrl") or ""
            if not entry["shortenUrl"]:
                entry["error"] = "단축 링크를 받지 못했습니다."
        except ApiError as exc:
            entry["error"] = str(exc)
        links.append(entry)

    ok_count = sum(1 for l in links if l["shortenUrl"])
    return {
        "ok": ok_count > 0,
        "partial": 0 < ok_count < len(links),
        "product": {
            "id": pid,
            "name": name or "",
            "price": _int(price),
            "image": image or "",
            "category": category or "",
            "url": canonical,
        },
        "links": links,
        "generatedAt": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
    }


# ------------------------------------------------------------------ HTTP 서버
class Handler(BaseHTTPRequestHandler):
    server_version = f"CoupasHunter/{VERSION}"
    protocol_version = "HTTP/1.1"

    # ---- 공통 ----
    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.send_header("Access-Control-Max-Age", "86400")

    def _send(self, status: int, body: bytes, content_type: str, extra: dict | None = None) -> None:
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8")

    def _error(self, status: int, message: str) -> None:
        self._json(status, {"ok": False, "error": message})

    def _read_json(self) -> dict:
        if getattr(self, "_body_read", False):
            raw = self._raw_body
        else:
            self._raw_body = self._drain_body()
            self._body_read = True
            raw = self._raw_body
        if not raw:
            return {}
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ApiError("요청 본문이 올바른 JSON이 아닙니다.")
        return data if isinstance(data, dict) else {}

    def _drain_body(self) -> bytes:
        """본문을 끝까지 읽어 둡니다. 안 읽으면 keep-alive 연결에서 다음 요청으로 오해됩니다."""
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length <= 0:
            return b""
        return self.rfile.read(min(length, 64 * 1024))

    def log_message(self, fmt: str, *args) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        sys.stdout.write(f"[{stamp}] {fmt % args}\n")
        sys.stdout.flush()

    # ---- 라우팅 ----
    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_HEAD(self) -> None:  # noqa: N802
        self.do_GET()

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        params = urllib.parse.parse_qs(parsed.query)

        try:
            if path == "/health":
                return self._json(
                    200,
                    {
                        "ok": True,
                        "app": APP_ID,
                        "name": APP_NAME,
                        "version": VERSION,
                        "port": self.server.server_address[1],
                        "keySet": has_keys(),
                        "keyHint": key_hint(),
                        "channels": [{"subId": s, "label": l} for s, l in CHANNELS],
                        "localOnly": True,
                    },
                )

            if path == "/api/search":
                keyword = (params.get("q") or params.get("keyword") or [""])[0]
                max_price = _int((params.get("max_price") or [""])[0])
                min_price = _int((params.get("min_price") or [""])[0])
                rocket = (params.get("rocket") or ["0"])[0] in ("1", "true", "on", "yes")
                free_shipping = (params.get("free_shipping") or ["0"])[0] in ("1", "true", "on", "yes")
                sort = (params.get("sort") or ["value"])[0]
                limit = _int((params.get("limit") or ["10"])[0]) or 10
                if sort not in ("value", "price", "discount", "rank"):
                    sort = "value"
                result = search_products(
                    keyword, limit, max_price, min_price, rocket, free_shipping, sort
                )
                return self._json(200, result)

            if path == "/download/zip":
                return self._send_zip()

            if path in STATIC_FILES:
                return self._send_static(*STATIC_FILES[path])

            if path == "/favicon.ico":
                self.send_response(204)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return

            return self._error(404, "없는 주소입니다.")
        except ApiError as exc:
            return self._error(400, str(exc))
        except Exception as exc:  # noqa: BLE001
            self.log_message("처리 중 오류: %s", exc)
            return self._error(500, f"서버 처리 중 오류: {exc}")

    def do_POST(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        # 어떤 경로든 본문은 먼저 비워 둡니다 (HTTP/1.1 keep-alive 오해 방지)
        self._raw_body = self._drain_body()
        self._body_read = True
        try:
            if path == "/config":
                body = self._read_json()
                access = (body.get("access_key") or body.get("accessKey") or "").strip()
                secret = (body.get("secret_key") or body.get("secretKey") or "").strip()
                if not access or not secret:
                    raise ApiError("Access Key 와 Secret Key 를 모두 입력해 주세요.")
                if len(access) < 8 or len(secret) < 8:
                    raise ApiError("키 길이가 너무 짧습니다. 쿠팡 파트너스에서 발급받은 값을 그대로 넣어 주세요.")
                # 저장 전에 실제 호출로 검증 (잘못된 키를 저장하지 않음)
                try:
                    query = urllib.parse.urlencode({"keyword": "텀블러", "limit": 1})
                    coupang_request("GET", SEARCH_PATH, query, access=access, secret=secret)
                except ApiError as exc:
                    raise ApiError(f"키 확인에 실패했습니다: {exc}") from exc
                saved = save_keys(access, secret)
                with _cache_lock:
                    _cache.clear()
                return self._json(
                    200,
                    {
                        "ok": True,
                        "keySet": True,
                        "keyHint": access[:4] + "*" * 6,
                        "savedTo": saved.name,
                        "message": "키를 이 PC에 저장했습니다. 이제 검색할 수 있습니다.",
                    },
                )

            if path == "/config/clear":
                clear_keys()
                with _cache_lock:
                    _cache.clear()
                return self._json(200, {"ok": True, "keySet": False, "message": "이 PC의 키를 삭제했습니다."})

            if path == "/api/links":
                body = self._read_json()
                product_id = body.get("product_id") or body.get("productId") or ""
                if not product_id and body.get("url"):
                    product_id = _product_id_from_url(str(body["url"]))
                result = build_channel_links(
                    product_id,
                    body.get("name") or "",
                    body.get("price"),
                    body.get("image") or "",
                    body.get("category") or "",
                )
                return self._json(200, result)

            return self._error(404, "없는 주소입니다.")
        except ApiError as exc:
            return self._error(400, str(exc))
        except Exception as exc:  # noqa: BLE001
            self.log_message("처리 중 오류: %s", exc)
            return self._error(500, f"서버 처리 중 오류: {exc}")

    # ---- 파일 ----
    def _send_static(self, name: str, content_type: str) -> None:
        target = (BASE_DIR / name).resolve()
        if not str(target).startswith(str(BASE_DIR)) or not target.is_file():
            return self._error(404, "파일을 찾을 수 없습니다.")
        body = target.read_bytes()
        self._send(200, body, content_type)

    def _send_zip(self) -> None:
        buffer = io.BytesIO()
        skip_suffix = {".env", ".pyc", ".zip"}
        skip_dirs = {".git", "__pycache__", ".github"}
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for path in sorted(BASE_DIR.rglob("*")):
                rel = path.relative_to(BASE_DIR)
                if any(part in skip_dirs for part in rel.parts):
                    continue
                if path.is_dir() or path.suffix.lower() in skip_suffix:
                    continue
                if ".env" in path.name.lower() or "key" in path.name.lower():
                    continue
                zf.write(path, Path(APP_ID) / rel)
        body = buffer.getvalue()
        self._send(
            200,
            body,
            "application/zip",
            {"Content-Disposition": f'attachment; filename="{APP_ID}-{VERSION}.zip"'},
        )


def _product_id_from_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    params = urllib.parse.parse_qs(parsed.query)
    for key in ("pageKey", "productId", "itemId"):
        if params.get(key):
            candidate = params[key][0]
            if candidate.isdigit():
                return candidate
    parts = [p for p in parsed.path.split("/") if p]
    for part in reversed(parts):
        if part.isdigit():
            return part
    return ""


# --------------------------------------------------------------------- 실행부
def parse_args(argv: list[str]) -> tuple[int, bool]:
    port = DEFAULT_PORT
    open_browser = True
    args = argv[1:]
    i = 0
    while i < len(args):
        arg = args[i]
        if arg in ("--port", "-p") and i + 1 < len(args):
            try:
                port = int(args[i + 1])
            except ValueError:
                print(f"[경고] 포트 번호를 읽지 못했습니다: {args[i + 1]}")
            i += 2
            continue
        if arg.startswith("--port="):
            try:
                port = int(arg.split("=", 1)[1])
            except ValueError:
                pass
            i += 1
            continue
        if arg in ("--no-browser",):
            open_browser = False
        if arg in ("-h", "--help"):
            print(__doc__)
            raise SystemExit(0)
        i += 1
    return port, open_browser


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
    port, open_browser = parse_args(argv)
    url = f"http://{HOST}:{port}/"

    print("=" * 62)
    print(f"  {APP_NAME} v{VERSION}")
    print("=" * 62)
    print(f"  주소      : {url}   (이 PC에서만 접근 가능)")
    print(f"  키 파일   : {ENV_FILE}")
    print(f"  키 상태   : {'설정됨 (' + key_hint() + ')' if has_keys() else '아직 없음 — 화면에서 입력'}")
    print("=" * 62)
    print("  종료하려면 이 창에서 Ctrl+C 를 누르세요.")
    print()

    try:
        server = ThreadingHTTPServer((HOST, port), Handler)
    except OSError as exc:
        print(f"[알림] {port} 포트를 열지 못했습니다: {exc}")
        print("       이미 서버가 실행 중이면 아래 주소를 브라우저에서 열면 됩니다.")
        print(f"       {url}")
        if open_browser:
            webbrowser.open(url)
        try:
            input("       Enter 키를 누르면 창이 닫힙니다...")
        except EOFError:
            pass
        return 0

    server.daemon_threads = True
    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n서버를 종료합니다.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
