/* 쿠파스 가성비 상품 헌터 — 프론트엔드
 * 키는 브라우저에 저장하지 않습니다. 모든 쿠팡 호출은 로컬 서버(127.0.0.1:8767)가 대신 합니다.
 */
(() => {
  "use strict";

  const SERVER_PORT = 8767;
  const SHOP_LINKS_PRODUCTS = "https://anchirong9-arch.github.io/shop-links/products.json";

  const $ = (id) => document.getElementById(id);
  const isLocal = ["127.0.0.1", "localhost", "[::1]"].includes(location.hostname);
  const API_BASE = isLocal ? location.origin : `http://127.0.0.1:${SERVER_PORT}`;

  const state = {
    online: false,
    keySet: false,
    keyHint: "",
    maxPrice: null,
    rocket: false,
    sort: "value",
    items: [],
    keyword: "",
    lastQuery: "",
    shopLinksNextNo: null,
    currentProduct: null,
    currentLinks: null,
  };

  /* ------------------------------------------------------------- 유틸 */
  const won = (n) => (n == null ? "-" : `${Number(n).toLocaleString("ko-KR")}원`);
  const esc = (s) => String(s == null ? "" : s);

  function toast(msg) {
    const el = $("toast");
    el.textContent = msg;
    el.classList.remove("hidden");
    requestAnimationFrame(() => el.classList.add("show"));
    clearTimeout(toast._t);
    toast._t = setTimeout(() => {
      el.classList.remove("show");
      setTimeout(() => el.classList.add("hidden"), 180);
    }, 1900);
  }

  async function copyText(text, okMsg = "복사했습니다") {
    if (!text) {
      toast("복사할 값이 없습니다");
      return false;
    }
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(text);
      } else {
        const ta = document.createElement("textarea");
        ta.value = text;
        ta.setAttribute("readonly", "");
        ta.style.position = "fixed";
        ta.style.opacity = "0";
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        document.body.removeChild(ta);
      }
      toast(okMsg);
      return true;
    } catch (err) {
      toast("복사 실패 — 길게 눌러 직접 복사해 주세요");
      return false;
    }
  }

  async function api(path, options = {}) {
    const res = await fetch(`${API_BASE}${path}`, {
      method: options.method || "GET",
      headers: options.body ? { "Content-Type": "application/json" } : undefined,
      body: options.body ? JSON.stringify(options.body) : undefined,
      cache: "no-store",
    });
    let data = null;
    try {
      data = await res.json();
    } catch (err) {
      data = null;
    }
    if (!res.ok || !data || data.ok === false) {
      throw new Error((data && data.error) || `서버 응답 오류 (HTTP ${res.status})`);
    }
    return data;
  }

  /* ------------------------------------------------------- 서버 상태 */
  function setStatus(mode, text) {
    const pill = $("statusPill");
    pill.classList.remove("on", "warn");
    if (mode === "on") pill.classList.add("on");
    if (mode === "warn") pill.classList.add("warn");
    pill.querySelector(".status-text").textContent = text;
  }

  function updateBanner() {
    const banner = $("connBanner");
    const zip = $("zipBtn");
    if (!state.online) {
      banner.classList.remove("hidden");
      $("connTitle").textContent = "로컬 서버에 연결되지 않았습니다";
      $("connDesc").innerHTML =
        "이 PC에서 <code>실행하기.bat</code>을 더블클릭해 서버를 켜면 검색과 링크 뽑기가 열립니다. " +
        "처음이면 ZIP을 받아 압축을 풀고 실행하세요 (키는 이 PC에만 저장됩니다).";
      zip.textContent = "⬇ ZIP 다운로드";
      zip.href = "https://github.com/anchirong9-arch/coupas-hunter/archive/refs/heads/main.zip";
      setStatus("off", "서버 꺼짐");
      $("searchBtn").disabled = false;
      return;
    }
    if (!state.keySet) {
      banner.classList.remove("hidden");
      $("connTitle").textContent = "키만 넣으면 바로 시작됩니다";
      $("connDesc").innerHTML =
        "쿠팡 파트너스 <b>Open API</b>의 Access Key / Secret Key를 넣으면 이 PC의 " +
        "<code>coupas-api-key.env</code>에만 저장합니다.";
      zip.textContent = "⬇ 서버 프로그램 ZIP";
      zip.href = `${API_BASE}/download/zip`;
      setStatus("warn", "키 필요");
      return;
    }
    banner.classList.add("hidden");
    setStatus("on", `연결됨 · ${state.keyHint || "키 설정됨"}`);
  }

  async function checkHealth(showError = false) {
    try {
      const h = await api("/health");
      state.online = true;
      state.keySet = !!h.keySet;
      state.keyHint = h.keyHint || "";
    } catch (err) {
      state.online = false;
      state.keySet = false;
      if (showError) toast("서버에 연결하지 못했습니다");
    }
    updateBanner();
    return state.online;
  }

  /* ------------------------------------------------------------ 검색 */
  function currentQueryParams() {
    const params = new URLSearchParams();
    params.set("q", state.keyword);
    params.set("sort", state.sort);
    params.set("limit", "10");
    if (state.maxPrice) params.set("max_price", String(state.maxPrice));
    if (state.rocket) params.set("rocket", "1");
    return params;
  }

  function renderSkeletons() {
    const grid = $("results");
    grid.innerHTML = "";
    for (let i = 0; i < 6; i += 1) {
      const sk = document.createElement("div");
      sk.className = "skeleton";
      grid.appendChild(sk);
    }
  }

  async function search() {
    const q = $("q").value.trim();
    if (!q) {
      $("q").focus();
      toast("검색어를 입력해 주세요");
      return;
    }
    state.keyword = q;
    $("empty").classList.add("hidden");

    if (!(await checkHealth())) {
      $("results").innerHTML = "";
      $("empty").classList.remove("hidden");
      toast("로컬 서버가 꺼져 있습니다 — 실행하기.bat 을 실행해 주세요");
      return;
    }
    if (!state.keySet) {
      openKeySheet();
      return;
    }

    $("searchBtn").disabled = true;
    $("searchBtn").textContent = "검색 중";
    renderSkeletons();
    $("resultMeta").classList.add("hidden");
    $("note").classList.add("hidden");

    try {
      const data = await api(`/api/search?${currentQueryParams().toString()}`);
      state.items = data.items || [];
      state.lastQuery = data.keyword || q;
      renderResults(data);
    } catch (err) {
      $("results").innerHTML = "";
      $("empty").classList.remove("hidden");
      $("note").classList.remove("hidden");
      $("note").textContent = err.message;
      if (/키/.test(err.message)) openKeySheet();
    } finally {
      $("searchBtn").disabled = false;
      $("searchBtn").textContent = "검색";
    }
  }

  function renderResults(data) {
    const grid = $("results");
    grid.innerHTML = "";
    const items = data.items || [];

    const meta = $("resultMeta");
    meta.classList.remove("hidden");
    meta.innerHTML = `<b>${esc(data.keyword)}</b> · ${items.length}개 표시 (API 응답 ${data.fetchedCount || 0}개)`;

    const note = $("note");
    if (data.note) {
      note.classList.remove("hidden");
      note.textContent = data.note;
    } else {
      note.classList.add("hidden");
    }

    if (!items.length) {
      $("empty").classList.remove("hidden");
      return;
    }
    $("empty").classList.add("hidden");

    items.forEach((item) => grid.appendChild(buildCard(item)));
  }

  function buildCard(item) {
    const card = document.createElement("article");
    card.className = "card";

    const thumb = document.createElement("a");
    thumb.className = "thumb";
    thumb.href = item.url || "#";
    thumb.target = "_blank";
    thumb.rel = "noopener noreferrer";

    if (item.image) {
      const img = document.createElement("img");
      img.src = item.image;
      img.alt = item.name;
      img.loading = "lazy";
      img.referrerPolicy = "no-referrer";
      thumb.appendChild(img);
    }

    const badges = document.createElement("div");
    badges.className = "badges";
    if (item.under10k) badges.appendChild(badge("1만원 이내", "under"));
    if (item.rocket) badges.appendChild(badge("로켓", "rocket"));
    if (item.valueScore >= 80) badges.appendChild(badge(`가성비 ${item.valueScore}`, "value"));
    thumb.appendChild(badges);
    card.appendChild(thumb);

    const body = document.createElement("div");
    body.className = "card-body";

    const name = document.createElement("h3");
    name.className = "card-name";
    name.textContent = item.name;
    name.title = item.name;
    body.appendChild(name);

    const priceRow = document.createElement("div");
    priceRow.className = "price-row";
    const price = document.createElement("span");
    price.className = "price";
    price.textContent = won(item.price);
    priceRow.appendChild(price);
    if (item.discountRate) {
      const d = document.createElement("span");
      d.className = "discount";
      d.textContent = `${item.discountRate}%↓`;
      priceRow.appendChild(d);
    }
    if (item.listPrice && item.listPrice > (item.price || 0)) {
      const o = document.createElement("span");
      o.className = "price-origin";
      o.textContent = won(item.listPrice);
      priceRow.appendChild(o);
    }
    body.appendChild(priceRow);

    if (item.category) {
      const cat = document.createElement("p");
      cat.className = "cat";
      cat.textContent = `${item.category} · 인기 ${item.rank}위 · 가성비 ${item.valueScore}점`;
      body.appendChild(cat);
    }

    const actions = document.createElement("div");
    actions.className = "card-actions";

    const linkBtn = document.createElement("button");
    linkBtn.type = "button";
    linkBtn.className = "btn-link";
    linkBtn.textContent = "🔗 4채널 링크";
    linkBtn.addEventListener("click", () => openLinkSheet(item));
    actions.appendChild(linkBtn);

    const imgBtn = document.createElement("button");
    imgBtn.type = "button";
    imgBtn.className = "btn-copy-img";
    imgBtn.textContent = "🖼";
    imgBtn.title = "이미지 URL 복사";
    imgBtn.addEventListener("click", () => copyText(item.image, "이미지 URL을 복사했습니다"));
    actions.appendChild(imgBtn);

    body.appendChild(actions);
    card.appendChild(body);
    return card;
  }

  function badge(text, cls) {
    const b = document.createElement("span");
    b.className = `badge ${cls || ""}`.trim();
    b.textContent = text;
    return b;
  }

  /* ------------------------------------------------------- 링크 시트 */
  function openSheet(id) {
    $(id).classList.remove("hidden");
    document.body.style.overflow = "hidden";
  }

  function closeSheet(id) {
    $(id).classList.add("hidden");
    document.body.style.overflow = "";
  }

  async function openLinkSheet(item) {
    state.currentProduct = item;
    state.currentLinks = null;

    const box = $("sheetProduct");
    box.innerHTML = "";
    if (item.image) {
      const img = document.createElement("img");
      img.src = item.image;
      img.alt = "";
      box.appendChild(img);
    }
    const meta = document.createElement("div");
    meta.className = "meta";
    const nm = document.createElement("p");
    nm.className = "nm";
    nm.textContent = item.name;
    const pr = document.createElement("p");
    pr.className = "pr";
    pr.textContent = `${won(item.price)}${item.rocket ? " · 로켓배송" : ""}`;
    meta.appendChild(nm);
    meta.appendChild(pr);
    box.appendChild(meta);

    const linksBox = $("sheetLinks");
    linksBox.innerHTML = "";
    linksBox.classList.add("hidden");
    $("sheetProgress").classList.remove("hidden");
    $("copyAllLinks").disabled = true;
    $("copySnippet").disabled = true;
    $("snippetHint").textContent = "";
    openSheet("linkSheet");

    try {
      const data = await api("/api/links", {
        method: "POST",
        body: {
          product_id: item.id,
          name: item.name,
          price: item.price,
          image: item.image,
          category: item.category,
        },
      });
      state.currentLinks = data;
      renderLinks(data);
    } catch (err) {
      linksBox.classList.remove("hidden");
      const row = document.createElement("div");
      row.className = "link-row err";
      row.innerHTML = `<span class="ch">오류</span><span class="url"></span>`;
      row.querySelector(".url").textContent = err.message;
      linksBox.appendChild(row);
      if (/키/.test(err.message)) openKeySheet();
    } finally {
      $("sheetProgress").classList.add("hidden");
    }
  }

  function renderLinks(data) {
    const box = $("sheetLinks");
    box.innerHTML = "";
    box.classList.remove("hidden");

    const lines = [];
    (data.links || []).forEach((link) => {
      const row = document.createElement("div");
      row.className = `link-row ${link.error ? "err" : ""}`.trim();

      const ch = document.createElement("span");
      ch.className = "ch";
      ch.textContent = link.channel;
      row.appendChild(ch);

      const url = document.createElement("span");
      url.className = "url";
      url.textContent = link.error || link.shortenUrl;
      url.title = link.error || link.shortenUrl;
      row.appendChild(url);

      if (!link.error) {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "copy";
        btn.textContent = "복사";
        btn.addEventListener("click", () =>
          copyText(link.shortenUrl, `${link.channel} 링크를 복사했습니다`)
        );
        row.appendChild(btn);
        lines.push(`[${link.channel}] ${link.shortenUrl}`);
      }
      box.appendChild(row);
    });

    state.copyAllText = lines.join("\n");
    $("copyAllLinks").disabled = lines.length === 0;
    $("copySnippet").disabled = !data.links || !data.links.some((l) => l.subId === "anchishoplinks" && l.shortenUrl);
    $("snippetHint").textContent = data.partial
      ? "일부 채널 링크를 만들지 못했습니다. 다시 눌러 시도해 보세요."
      : "";
  }

  /* ------------------------------------------- shop-links JSON 스니펫 */
  function slugFor(item) {
    return `product-${item.id || Date.now()}`;
  }

  function snippetTag(item) {
    const bits = [];
    if (item.listPrice && item.price && item.listPrice > item.price) {
      bits.push(`${won(item.listPrice).replace("원", "")}원 → ${won(item.price)}`);
    } else {
      bits.push(won(item.price));
    }
    if (item.rocket) bits.push("로켓배송");
    bits.push(`가성비 ${item.valueScore}점`);
    return bits.join(" · ");
  }

  async function nextShopLinksNo() {
    if (state.shopLinksNextNo != null) return state.shopLinksNextNo;
    try {
      const res = await fetch(SHOP_LINKS_PRODUCTS, { cache: "no-store" });
      if (!res.ok) throw new Error("fetch failed");
      const list = await res.json();
      const maxNo = Math.max(0, ...list.map((p) => Number(p.no) || 0));
      state.shopLinksNextNo = maxNo + 1;
    } catch (err) {
      state.shopLinksNextNo = null;
    }
    return state.shopLinksNextNo;
  }

  async function buildSnippet() {
    const item = state.currentProduct;
    const data = state.currentLinks;
    if (!item || !data) return null;
    const shop = (data.links || []).find((l) => l.subId === "anchishoplinks");
    const url = shop && shop.shortenUrl ? shop.shortenUrl : item.url;
    const slug = slugFor(item);
    const no = await nextShopLinksNo();
    const today = new Date().toISOString().slice(0, 10);
    const entry = {};
    if (no != null) entry.no = no;
    entry.id = slug;
    entry.name = item.name;
    entry.tag = snippetTag(item);
    entry.category = item.category || "기타";
    entry.price = item.price;
    entry.listPrice = item.listPrice || item.price;
    entry.image = `images/${slug}.jpg`;
    entry.url = url;
    entry.posted = today;
    return entry;
  }

  async function copySnippet() {
    const entry = await buildSnippet();
    if (!entry) {
      toast("먼저 링크를 뽑아 주세요");
      return;
    }
    const ok = await copyText(JSON.stringify(entry, null, 2), "shop-links JSON을 복사했습니다");
    if (ok) {
      $("snippetHint").textContent = entry.no
        ? `${entry.no}번 항목으로 복사했습니다. 상품 사진은 shop-links 저장소 images/${entry.id}.jpg 로 저장하세요.`
        : `shop-links 다음 번호를 못 읽었습니다. products.json의 no를 확인해 넣고, 사진은 images/${entry.id}.jpg 로 저장하세요.`;
    }
  }

  /* --------------------------------------------------------- 키 설정 */
  function openKeySheet() {
    $("keyMsg").classList.add("hidden");
    $("keyMsg").textContent = "";
    $("accessKey").value = "";
    $("secretKey").value = "";
    openSheet("keySheet");
    setTimeout(() => $("accessKey").focus(), 120);
  }

  function keyMsg(text, kind) {
    const el = $("keyMsg");
    el.textContent = text;
    el.className = `key-msg ${kind}`;
  }

  async function saveKey() {
    const access = $("accessKey").value.trim();
    const secret = $("secretKey").value.trim();
    if (!access || !secret) {
      keyMsg("Access Key 와 Secret Key 를 모두 넣어 주세요.", "bad");
      return;
    }
    if (!(await checkHealth())) {
      keyMsg("로컬 서버가 꺼져 있습니다. 실행하기.bat 을 먼저 실행해 주세요.", "bad");
      return;
    }
    $("saveKey").disabled = true;
    $("saveKey").textContent = "확인 중…";
    try {
      const res = await api("/config", { method: "POST", body: { access_key: access, secret_key: secret } });
      keyMsg(res.message || "저장했습니다.", "ok");
      state.keySet = true;
      state.keyHint = res.keyHint || "";
      updateBanner();
      setTimeout(() => closeSheet("keySheet"), 900);
    } catch (err) {
      keyMsg(err.message, "bad");
    } finally {
      $("saveKey").disabled = false;
      $("saveKey").textContent = "저장하고 확인";
    }
  }

  async function removeKey() {
    if (!confirm("이 PC에 저장된 쿠팡 파트너스 키를 삭제할까요?")) return;
    try {
      await api("/config/clear", { method: "POST", body: {} });
      state.keySet = false;
      state.keyHint = "";
      updateBanner();
      keyMsg("이 PC의 키를 삭제했습니다.", "ok");
    } catch (err) {
      keyMsg(err.message, "bad");
    }
  }

  /* ------------------------------------------------------------ 프리셋 */
  function applyPreset(name) {
    if (name === "under10k") {
      state.maxPrice = state.maxPrice === 10000 ? null : 10000;
    } else if (name === "rocket") {
      state.rocket = !state.rocket;
    } else if (name === "cheap") {
      state.sort = "price";
    } else if (name === "discount") {
      state.sort = "discount";
    } else if (name === "reset") {
      state.maxPrice = null;
      state.rocket = false;
      state.sort = "value";
    }
    syncControls();
    if (state.keyword) search();
  }

  function syncControls() {
    $("under10k").checked = state.maxPrice === 10000;
    $("rocketOnly").checked = state.rocket;
    $("sort").value = state.sort;
    document.querySelectorAll(".chip").forEach((chip) => {
      const p = chip.dataset.preset;
      const active =
        (p === "under10k" && state.maxPrice === 10000) ||
        (p === "rocket" && state.rocket) ||
        (p === "cheap" && state.sort === "price") ||
        (p === "discount" && state.sort === "discount");
      chip.classList.toggle("active", active);
    });
  }

  /* ------------------------------------------------------------- 이벤트 */
  function bindEvents() {
    $("searchForm").addEventListener("submit", (e) => {
      e.preventDefault();
      search();
    });

    document.querySelectorAll(".chip").forEach((chip) => {
      chip.addEventListener("click", () => applyPreset(chip.dataset.preset));
    });

    document.querySelectorAll(".kw").forEach((btn) => {
      btn.addEventListener("click", () => {
        $("q").value = btn.textContent.trim();
        search();
      });
    });

    $("rocketOnly").addEventListener("change", (e) => {
      state.rocket = e.target.checked;
      syncControls();
      if (state.keyword) search();
    });
    $("under10k").addEventListener("change", (e) => {
      state.maxPrice = e.target.checked ? 10000 : null;
      syncControls();
      if (state.keyword) search();
    });
    $("sort").addEventListener("change", (e) => {
      state.sort = e.target.value;
      syncControls();
      if (state.keyword) search();
    });

    $("statusPill").addEventListener("click", async () => {
      const ok = await checkHealth(true);
      if (ok) toast(state.keySet ? "서버 연결됨" : "서버 연결됨 · 키를 넣어 주세요");
    });
    $("retryBtn").addEventListener("click", () => checkHealth(true));
    $("keyBtn").addEventListener("click", openKeySheet);

    $("sheetClose").addEventListener("click", () => closeSheet("linkSheet"));
    $("keyClose").addEventListener("click", () => closeSheet("keySheet"));
    document.querySelectorAll("[data-close]").forEach((el) =>
      el.addEventListener("click", () => {
        el.closest(".sheet").classList.add("hidden");
        document.body.style.overflow = "";
      })
    );
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        document.querySelectorAll(".sheet:not(.hidden)").forEach((s) => s.classList.add("hidden"));
        document.body.style.overflow = "";
      }
    });

    $("copyAllLinks").addEventListener("click", () =>
      copyText(state.copyAllText || "", "4채널 링크를 한 번에 복사했습니다")
    );
    $("copySnippet").addEventListener("click", copySnippet);
    $("copyImage").addEventListener("click", () =>
      copyText(state.currentProduct ? state.currentProduct.image : "", "이미지 URL을 복사했습니다")
    );

    $("saveKey").addEventListener("click", saveKey);
    $("removeKey").addEventListener("click", removeKey);
    $("secretKey").addEventListener("keydown", (e) => {
      if (e.key === "Enter") saveKey();
    });
  }

  /* -------------------------------------------------------------- 시작 */
  async function init() {
    bindEvents();
    syncControls();
    await checkHealth();
    setInterval(() => {
      if (!state.online) checkHealth();
    }, 8000);
  }

  document.addEventListener("DOMContentLoaded", init);
})();
