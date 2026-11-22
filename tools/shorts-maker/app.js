/* 쇼츠 메이커 — 웹 UI
   이미지 여러 장 + 음성 + 자막 + BGM 을 로컬 서버(/render)로 보내 MP4 를 받는다. */
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const DEFAULT_PORTS = [8766];

  const state = {
    serverUrl: null,
    images: [],            // {file, url, w, h}
    audio: null,           // {file, url, duration}
    srt: null,             // {file, name, text, cues, duration}
    bgm: null,             // {file, url, duration}
    opts: { zoom: true, bg_style: "black", subtitle_size: 58, bgm_vol: 12 },
    result: null,          // {url, sizeBlob, meta}
    busy: false,
    playingScene: -1,
    previewTimer: null,
  };

  const previewAudio = new Audio();
  previewAudio.preload = "metadata";

  /* ───────────── 유틸 ───────────── */
  const fmtSec = (s) => {
    s = Math.max(0, Number(s) || 0);
    const m = Math.floor(s / 60);
    const r = s - m * 60;
    return m > 0 ? `${m}분 ${r.toFixed(1)}초` : `${r.toFixed(1)}초`;
  };
  const fmtSize = (b) => {
    b = Number(b) || 0;
    if (b < 1024) return b + "B";
    if (b < 1024 * 1024) return (b / 1024).toFixed(0) + "KB";
    return (b / (1024 * 1024)).toFixed(1) + "MB";
  };
  const stamp = () => {
    const d = new Date();
    const p = (n) => String(n).padStart(2, "0");
    return `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}_${p(d.getHours())}${p(d.getMinutes())}`;
  };
  const isImage = (f) => (f.type || "").startsWith("image/") || /\.(jpe?g|png|webp|bmp|gif|heic|heif|tiff?)$/i.test(f.name || "");
  const isAudio = (f) => (f.type || "").startsWith("audio/") || /\.(mp3|m4a|wav|ogg|opus|aac|flac)$/i.test(f.name || "");
  const isSrt = (f) => /\.(srt|vtt)$/i.test(f.name || "") || (f.type || "").includes("text");

  /* ───────────── 서버 연결 확인 ───────────── */
  function serverCandidates() {
    const list = [];
    if (location.protocol === "http:" || location.protocol === "https:") {
      const h = location.hostname;
      if (h === "127.0.0.1" || h === "localhost" || h === "::1") list.push(location.origin);
    }
    DEFAULT_PORTS.forEach((p) => {
      list.push(`http://127.0.0.1:${p}`);
      list.push(`http://localhost:${p}`);
    });
    return [...new Set(list)];
  }

  async function ping(base, timeout = 1500) {
    // 브라우저가 요청을 붙잡고 있어도 우리 타이머가 먼저 끝나도록 race 로 감싼다
    return new Promise((resolve) => {
      let settled = false;
      const finish = (value) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        try { ctrl.abort(); } catch (e) { /* 무시 */ }
        resolve(value);
      };
      const ctrl = new AbortController();
      const timer = setTimeout(() => finish(null), timeout);
      try {
        fetch(base + "/health", { cache: "no-store", signal: ctrl.signal })
          .then(async (res) => {
            if (!res.ok) return finish(null);
            let data = null;
            try { data = await res.json(); } catch (e) { data = null; }
            finish(data && data.ok ? { base, data } : null);
          })
          .catch(() => finish(null));
      } catch (e) {
        finish(null);
      }
    });
  }

  async function checkServer(opts = {}) {
    const { quiet } = opts;
    if (!quiet) setStatus("checking", "서버 확인 중…");
    const list = serverCandidates();
    const hits = await Promise.all(list.map((base) => ping(base)));
    const hit = hits.find(Boolean) || null;
    if (hit) {
      state.serverUrl = hit.base;
      const port = hit.data.port || "";
      setStatus("ok", `서버 연결됨${port ? " · " + port : ""}`);
      $("notice").hidden = true;
      return true;
    }
    state.serverUrl = null;
    setStatus("off", "서버 꺼짐 · 아래 3단계");
    $("notice").hidden = false;
    return false;
  }

  function setStatus(kind, text) {
    const el = $("status");
    el.dataset.state = kind;
    $("statusText").textContent = text;
  }

  /* ───────────── 옵션 ───────────── */
  const OPT_KEY = "shorts-maker-opts-v1";

  function loadOpts() {
    try {
      const raw = localStorage.getItem(OPT_KEY);
      if (raw) Object.assign(state.opts, JSON.parse(raw) || {});
    } catch (e) { /* 무시 */ }
    $("optZoom").checked = !!state.opts.zoom;
    $("optSubSize").value = state.opts.subtitle_size;
    $("optBgmVol").value = state.opts.bgm_vol;
    syncOptLabels();
    document.querySelectorAll("#optBg button").forEach((b) => {
      b.classList.toggle("on", b.dataset.bg === state.opts.bg_style);
    });
    document.querySelectorAll(".phone-screen").forEach((s) => (s.dataset.bg = state.opts.bg_style));
  }

  function saveOpts() {
    try { localStorage.setItem(OPT_KEY, JSON.stringify(state.opts)); } catch (e) { /* 무시 */ }
  }

  function syncOptLabels() {
    $("subSizeValue").textContent = state.opts.subtitle_size;
    $("bgmVolValue").textContent = state.opts.bgm_vol + "%";
  }

  /* ───────────── 이미지 목록 ───────────── */
  function addImages(files) {
    const list = [...files].filter(isImage);
    if (!list.length) return;
    const room = 40 - state.images.length;
    const use = list.slice(0, Math.max(0, room));
    use.forEach((file) => {
      const url = URL.createObjectURL(file);
      state.images.push({ file, url, name: file.name || "image" });
    });
    renderScenes();
    if (list.length > use.length) toast(`이미지는 최대 40장까지예요. ${list.length - use.length}장은 넣지 못했습니다.`);
  }

  function renderScenes() {
    const ol = $("sceneList");
    ol.innerHTML = "";
    const n = state.images.length;
    $("imgCount").textContent = n + "장";
    $("btnClearImages").hidden = n === 0;
    $("pgEmpty").hidden = n > 0 || !!state.result;
    $("pgPlay").hidden = n < 1;
    $("resultBadge").hidden = !state.result;

    state.images.forEach((img, i) => {
      const li = document.createElement("li");
      li.className = "scene-item";
      li.draggable = true;
      li.dataset.index = i;
      li.innerHTML = `
        <span class="scene-num">${i + 1}</span>
        <span class="scene-thumb"><img src="${img.url}" alt=""></span>
        <span class="scene-info">
          <b>${escapeHtml(img.name)}</b>
          <small>${fmtSize(img.file.size)}</small>
        </span>
        <span class="scene-tools">
          <button type="button" class="icon-btn" data-act="up" title="위로" ${i === 0 ? "disabled" : ""}>↑</button>
          <button type="button" class="icon-btn" data-act="down" title="아래로" ${i === n - 1 ? "disabled" : ""}>↓</button>
          <button type="button" class="icon-btn danger" data-act="del" title="빼기">✕</button>
        </span>`;
      ol.appendChild(li);
    });

    ol.querySelectorAll(".scene-item").forEach((li) => {
      const i = Number(li.dataset.index);
      li.querySelector('[data-act="up"]').addEventListener("click", () => move(i, -1));
      li.querySelector('[data-act="down"]').addEventListener("click", () => move(i, 1));
      li.querySelector('[data-act="del"]').addEventListener("click", () => remove(i));
      li.addEventListener("dragstart", (e) => {
        li.classList.add("dragging");
        e.dataTransfer.effectAllowed = "move";
        e.dataTransfer.setData("text/plain", String(i));
      });
      li.addEventListener("dragend", () => {
        li.classList.remove("dragging");
        ol.querySelectorAll(".drop-target").forEach((x) => x.classList.remove("drop-target"));
      });
      li.addEventListener("dragover", (e) => {
        e.preventDefault();
        li.classList.add("drop-target");
      });
      li.addEventListener("dragleave", () => li.classList.remove("drop-target"));
      li.addEventListener("drop", (e) => {
        e.preventDefault();
        li.classList.remove("drop-target");
        const from = Number(e.dataTransfer.getData("text/plain"));
        if (Number.isInteger(from) && from !== i) reorder(from, i);
      });
    });

    updateTimeline();
    updatePreviewScene(0);
    updatePhoneMeta();
  }

  function move(i, dir) {
    const j = i + dir;
    if (j < 0 || j >= state.images.length) return;
    reorder(i, j);
  }

  function reorder(from, to) {
    const [item] = state.images.splice(from, 1);
    state.images.splice(to, 0, item);
    renderScenes();
  }

  function remove(i) {
    const [item] = state.images.splice(i, 1);
    if (item) URL.revokeObjectURL(item.url);
    renderScenes();
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  /* ───────────── 길이 계산 ───────────── */
  function totalDuration() {
    if (state.audio && state.audio.duration > 0) return state.audio.duration;
    return Math.max(0, state.images.length) * 2.5;
  }

  function updateTimeline() {
    const n = state.images.length;
    const wrap = $("timelineWrap");
    if (!n) {
      wrap.hidden = true;
      return;
    }
    wrap.hidden = false;
    const total = totalDuration();
    const seg = total / n;
    const bars = $("timelineBars");
    bars.innerHTML = "";
    state.images.forEach((_, i) => {
      const d = document.createElement("div");
      d.className = "timeline-bar";
      d.style.flex = String(seg);
      if (seg >= 0.85) d.innerHTML = `<span>${i + 1}</span>`;
      d.title = `${i + 1}번 장면 · ${seg.toFixed(1)}초`;
      bars.appendChild(d);
    });
    $("timelineTotal").textContent = fmtSec(total);
    $("timelineHint").textContent = state.audio
      ? `음성 ${fmtSec(total)}을 ${n}장에 똑같이 나눕니다 (장면당 ${seg.toFixed(1)}초).`
      : "음성을 넣으면 그 길이에 맞춰 나눕니다. 지금은 임시로 장면당 2.5초입니다.";
  }

  function updatePhoneMeta() {
    const n = state.images.length;
    const total = totalDuration();
    $("phoneMeta").textContent = n
      ? `1080 × 1920 · ${fmtSec(total)} · ${n}장`
      : "1080 × 1920 · 30fps";
  }

  /* ───────────── 폰 미리보기 ───────────── */
  function updatePreviewScene(index) {
    const n = state.images.length;
    if (!n) {
      $("pgImg").hidden = true;
      $("pgSub").hidden = true;
      $("pgBg").style.backgroundImage = "";
      $("pgEmpty").hidden = false;
      return;
    }
    const i = Math.max(0, Math.min(n - 1, index || 0));
    const img = state.images[i];
    const el = $("pgImg");
    el.src = img.url;
    el.hidden = false;
    $("pgEmpty").hidden = true;
    $("pgBg").style.backgroundImage = `url("${img.url}")`;
    state.playingScene = i;
    updatePreviewSub(previewAudio.currentTime || 0);
  }

  function updatePreviewSub(t) {
    const box = $("pgSub");
    if (!state.srt || !state.srt.cues.length) {
      box.hidden = true;
      return;
    }
    const cue = state.srt.cues.find((c) => t >= c.start && t < c.end);
    if (!cue) {
      box.hidden = true;
      return;
    }
    box.hidden = false;
    box.textContent = cue.text;
    box.style.fontSize = Math.max(11, Math.round(state.opts.subtitle_size * 0.30)) + "px";
  }

  function stopPreview() {
    previewAudio.pause();
    if (state.previewTimer) {
      clearInterval(state.previewTimer);
      state.previewTimer = null;
    }
    $("pgPlay").classList.remove("hide");
    $("pgSub").hidden = true;
  }

  function isPreviewPlaying() {
    return !previewAudio.paused || state.previewTimer !== null;
  }

  function playPreview() {
    if (!state.images.length) return;
    const total = totalDuration();
    const n = state.images.length;
    const seg = total / n || 2.5;
    $("pgPlay").classList.add("hide");
    updatePreviewSub(0);

    if (state.audio && state.audio.duration > 0) {
      previewAudio.currentTime = 0;
      previewAudio.play().catch(() => { /* 자동재생 차단 무시 */ });
    } else {
      updatePreviewScene(0);
      state.previewTimer = setInterval(() => {
        const next = state.playingScene + 1;
        if (next >= n) {
          stopPreview();
          return;
        }
        updatePreviewScene(next);
      }, seg * 1000);
    }
  }

  previewAudio.addEventListener("timeupdate", () => {
    const t = previewAudio.currentTime;
    const n = state.images.length;
    if (!n) return;
    const seg = totalDuration() / n || 2.5;
    const idx = Math.min(n - 1, Math.floor(t / seg));
    if (idx !== state.playingScene) updatePreviewScene(idx);
    updatePreviewSub(t);
  });

  previewAudio.addEventListener("ended", () => {
    $("pgPlay").classList.remove("hide");
    $("pgSub").hidden = true;
  });

  /* ───────────── 파일 슬롯 ───────────── */
  function setAudio(file) {
    if (!file) return;
    if (!isAudio(file)) return toast("음성은 mp3 파일을 넣어 주세요.");
    if (state.audio) URL.revokeObjectURL(state.audio.url);
    const url = URL.createObjectURL(file);
    state.audio = { file, url, duration: 0 };
    previewAudio.src = url;
    $("audioName").textContent = `${file.name} · 읽는 중…`;
    $("slotAudio").classList.add("loaded");
    updateSlotButtons();
    updateTimeline();
    updatePhoneMeta();
  }

  function setSrt(file) {
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      const text = String(reader.result || "");
      const cues = parseSrt(text);
      if (!cues.length) {
        toast("자막 파일에서 시간 정보를 찾지 못했습니다. .srt 형식인지 확인해 주세요.");
        return;
      }
      state.srt = { file, name: file.name, text, cues };
      $("srtName").textContent = `${file.name} · 자막 ${cues.length}개`;
      $("slotSrt").classList.add("loaded");
      updateSlotButtons();
    };
    reader.onerror = () => toast("자막 파일을 읽지 못했습니다.");
    reader.readAsText(file, "utf-8");
  }

  function setBgm(file) {
    if (!file) return;
    if (!isAudio(file)) return toast("BGM은 mp3 파일을 넣어 주세요.");
    if (state.bgm) URL.revokeObjectURL(state.bgm.url);
    const url = URL.createObjectURL(file);
    state.bgm = { file, url, duration: 0 };
    const probe = new Audio();
    probe.preload = "metadata";
    probe.onloadedmetadata = () => {
      state.bgm.duration = probe.duration || 0;
      $("bgmName").textContent = `${file.name} · ${fmtSec(state.bgm.duration)}`;
    };
    probe.src = url;
    $("bgmName").textContent = `${file.name} · 읽는 중…`;
    $("slotBgm").classList.add("loaded");
    updateSlotButtons();
  }

  function clearSlot(kind) {
    if (kind === "audio") {
      if (state.audio) URL.revokeObjectURL(state.audio.url);
      state.audio = null;
      previewAudio.removeAttribute("src");
      $("audioName").textContent = ".mp3 · TTS 스튜디오에서 만든 파일";
    } else if (kind === "bgm") {
      if (state.bgm) URL.revokeObjectURL(state.bgm.url);
      state.bgm = null;
      $("bgmName").textContent = "음성 아래 깔리는 배경음악";
    } else if (kind === "srt") {
      state.srt = null;
      $("srtName").textContent = "없으면 자막 없이 만듭니다";
    }
    $("slot" + kind[0].toUpperCase() + kind.slice(1)).classList.remove("loaded");
    updateSlotButtons();
    updateTimeline();
    updatePhoneMeta();
  }

  function updateSlotButtons() {
    ["audio", "srt", "bgm"].forEach((kind) => {
      const slot = $("slot" + kind[0].toUpperCase() + kind.slice(1));
      const btn = slot.querySelector("[data-pick]");
      const loaded = !!(kind === "audio" ? state.audio : kind === "srt" ? state.srt : state.bgm);
      btn.textContent = loaded ? "교체" : "선택";
      let del = slot.querySelector(".slot-del");
      if (loaded && !del) {
        del = document.createElement("button");
        del.type = "button";
        del.className = "icon-btn danger slot-del";
        del.title = "빼기";
        del.textContent = "✕";
        del.addEventListener("click", (e) => {
          e.stopPropagation();
          clearSlot(kind);
        });
        slot.appendChild(del);
      } else if (!loaded && del) {
        del.remove();
      }
    });
  }

  previewAudio.addEventListener("loadedmetadata", () => {
    if (!state.audio) return;
    state.audio.duration = previewAudio.duration || 0;
    $("audioName").textContent = `${state.audio.file.name} · ${fmtSec(state.audio.duration)}`;
    updateTimeline();
    updatePhoneMeta();
  });
  previewAudio.addEventListener("error", () => {
    if (state.audio) $("audioName").textContent = `${state.audio.file.name} · (길이 확인 실패)`;
  });

  /* ───────────── SRT 파싱 (미리보기용) ───────────── */
  function srtTime(v) {
    const m = /(\d+):(\d{1,2}):(\d{1,2})[,.](\d{1,3})/.exec(v || "");
    if (!m) return null;
    return Number(m[1]) * 3600 + Number(m[2]) * 60 + Number(m[3]) + Number(m[4].padEnd(3, "0")) / 1000;
  }

  function parseSrt(text) {
    const clean = text.replace(/\r\n?/g, "\n");
    const cues = [];
    clean.split(/\n\s*\n/).forEach((block) => {
      const lines = block.split("\n").map((l) => l.trim()).filter(Boolean);
      if (!lines.length) return;
      let i = 0;
      if (/^\d+$/.test(lines[0])) i = 1;
      if (!lines[i] || lines[i].indexOf("-->") < 0) return;
      const [left, right] = lines[i].split("-->");
      const start = srtTime(left);
      const end = srtTime((right || "").trim().split(" ")[0]);
      if (start === null || end === null) return;
      const body = lines.slice(i + 1).join(" ").replace(/<[^>]+>/g, "").replace(/\{[^}]*\}/g, "").trim();
      if (!body) return;
      cues.push({ start, end: end > start ? end : start + 1, text: body });
    });
    return cues.sort((a, b) => a.start - b.start);
  }

  /* ───────────── 렌더 ───────────── */
  let abortCtl = null;
  let progressTimer = null;

  function setBusy(on) {
    state.busy = on;
    $("btnRender").disabled = on;
    $("btnRender").querySelector(".spin").hidden = !on;
    $("btnRenderText").textContent = on ? "만드는 중…" : "🎬 쇼츠 영상 만들기";
    $("btnCancel").hidden = !on;
    $("progress").hidden = !on;
    if (!on) {
      clearInterval(progressTimer);
      progressTimer = null;
    }
  }

  function showError(msg) {
    const box = $("error");
    box.innerHTML = "<b>영상 만들기 실패</b>\n" + escapeHtml(msg);
    box.hidden = false;
  }

  function clearError() {
    $("error").hidden = true;
    $("error").textContent = "";
  }

  function toast(msg) {
    const box = $("error");
    box.innerHTML = escapeHtml(msg);
    box.hidden = false;
    clearTimeout(toast._t);
    toast._t = setTimeout(() => { box.hidden = true; }, 5000);
  }

  function startProgress(estimateSec) {
    const started = performance.now();
    const stages = [
      [0, "업로드 중…"],
      [1.2, "이미지 준비 중…"],
      [3.5, "장면 합성 중…"],
      [7, "영상 인코딩 중… (10~40초)"],
    ];
    const fill = $("progressFill");
    const wrap = $("progress");
    wrap.classList.add("indeterminate");
    progressTimer = setInterval(() => {
      const el = (performance.now() - started) / 1000;
      $("progressTime").textContent = el.toFixed(1) + "초";
      let label = stages[0][1];
      stages.forEach(([at, txt]) => { if (el >= at) label = txt; });
      if (el > estimateSec * 1.6) label = "거의 다 됐어요…";
      $("progressText").textContent = label;
      // 대략적인 진행률 (끝은 응답이 오면 100%)
      const pct = Math.min(94, (el / Math.max(6, estimateSec)) * 100);
      if (el > 1.5) {
        wrap.classList.remove("indeterminate");
        fill.style.width = pct.toFixed(1) + "%";
      }
    }, 250);
  }

  async function render() {
    if (state.busy) return;
    clearError();
    if (!state.images.length) return toast("이미지를 1장 이상 넣어 주세요.");
    if (!state.audio) return toast("음성 파일(.mp3)을 넣어 주세요. TTS 스튜디오에서 만든 파일을 쓰면 됩니다.");
    if (!state.serverUrl) {
      const ok = await checkServer({ quiet: true });
      if (!ok) {
        $("notice").hidden = false;
        $("notice").scrollIntoView({ behavior: "smooth", block: "center" });
        return toast("로컬 서버가 꺼져 있어요. 실행하기.bat 을 켠 뒤 다시 눌러 주세요.");
      }
    }

    const fd = new FormData();
    state.images.forEach((it) => fd.append("images", it.file, it.file.name));
    fd.append("audio", state.audio.file, state.audio.file.name);
    if (state.srt) fd.append("srt", new Blob([state.srt.text], { type: "text/plain" }), "subtitle.srt");
    if (state.bgm) fd.append("bgm", state.bgm.file, state.bgm.file.name);
    fd.append("zoom", state.opts.zoom ? "1" : "0");
    fd.append("bg_style", state.opts.bg_style);
    fd.append("bgm_vol", String(state.opts.bgm_vol / 100));
    fd.append("subtitle_size", String(state.opts.subtitle_size));

    abortCtl = new AbortController();
    setBusy(true);
    $("resultEmpty").hidden = true;
    const estimate = 3 + totalDuration() * 1.1;
    startProgress(estimate);

    try {
      const res = await fetch(state.serverUrl + "/render", {
        method: "POST",
        body: fd,
        signal: abortCtl.signal,
      });
      const ctype = res.headers.get("Content-Type") || "";
      if (!res.ok || ctype.indexOf("json") >= 0) {
        let msg = `서버가 ${res.status} 로 응답했습니다.`;
        try {
          const data = await res.json();
          if (data && data.error) msg = data.error;
        } catch (e) { /* 무시 */ }
        throw new Error(msg);
      }
      const blob = await res.blob();
      if (!blob.size) throw new Error("빈 영상이 돌아왔습니다. 다시 시도해 주세요.");
      showResult(blob, {
        duration: Number(res.headers.get("X-Video-Duration") || 0),
        frames: Number(res.headers.get("X-Video-Frames") || 0),
        subtitles: Number(res.headers.get("X-Video-Subtitles") || 0),
        renderSec: Number(res.headers.get("X-Render-Sec") || 0),
        saved: res.headers.get("X-Saved-Path") || "",
      });
    } catch (err) {
      const msg = err && err.name === "AbortError" ? "취소했습니다." : (err && err.message) || String(err);
      if (err && err.name === "TypeError") {
        showError("서버에 연결하지 못했습니다. 로컬 서버(실행하기.bat)가 켜져 있는지 확인해 주세요.");
        $("notice").hidden = false;
      } else {
        showError(msg);
      }
      $("resultEmpty").hidden = !!state.result;
    } finally {
      abortCtl = null;
      setBusy(false);
      $("progressFill").style.width = "";
      $("progress").classList.remove("indeterminate");
    }
  }

  function showResult(blob, meta) {
    if (state.result) URL.revokeObjectURL(state.result.url);
    const url = URL.createObjectURL(blob);
    state.result = { url, meta, blob };
    const video = $("video");
    video.src = url;
    video.hidden = false;
    video.load();

    const name = `shorts_${stamp()}.mp4`;
    const a = $("btnDownload");
    a.href = url;
    a.download = name;
    $("resultActions").hidden = false;
    $("resultBadge").hidden = false;
    $("resultEmpty").hidden = true;
    $("pgEmpty").hidden = true;

    const rows = [
      ["길이", meta.duration ? fmtSec(meta.duration) : "—"],
      ["용량", fmtSize(blob.size)],
      ["자막", meta.subtitles ? meta.subtitles + "개 번인" : "없음"],
      ["만드는 데", meta.renderSec ? meta.renderSec.toFixed(1) + "초" : "—"],
    ];
    $("resultMeta").innerHTML = rows.map(([k, v]) => `<span>${k}</span><b>${escapeHtml(v)}</b>`).join("");
    $("resultMeta").hidden = false;

    const hint = $("resultHint");
    hint.textContent = meta.saved
      ? `내 PC의 output 폴더에도 저장됐습니다 (${meta.saved}). 저장 버튼으로 원하는 곳에 내려받으세요.`
      : "저장 버튼으로 내려받으세요.";
    hint.hidden = false;

    if (window.matchMedia("(max-width:1180px)").matches) {
      setTimeout(() => video.scrollIntoView({ behavior: "smooth", block: "center" }), 150);
    }
  }

  /* ───────────── 이벤트 연결 ───────────── */
  function bind() {
    $("btnRetry").addEventListener("click", () => checkServer());
    $("btnNoticeRetry").addEventListener("click", () => checkServer());

    // 이미지 선택 / 드롭
    $("fileImages").addEventListener("change", (e) => {
      addImages(e.target.files);
      e.target.value = "";
    });
    const dz = $("dropImages");
    ["dragenter", "dragover"].forEach((ev) =>
      dz.addEventListener(ev, (e) => {
        e.preventDefault();
        dz.classList.add("over");
      })
    );
    ["dragleave", "dragend"].forEach((ev) => dz.addEventListener(ev, () => dz.classList.remove("over")));
    dz.addEventListener("drop", (e) => {
      e.preventDefault();
      dz.classList.remove("over");
      if (e.dataTransfer.files) addImages(e.dataTransfer.files);
    });

    $("btnClearImages").addEventListener("click", () => {
      state.images.forEach((it) => URL.revokeObjectURL(it.url));
      state.images = [];
      renderScenes();
    });

    // 파일 슬롯
    const pickers = {
      audio: { input: $("fileAudio"), set: setAudio },
      srt: { input: $("fileSrt"), set: setSrt },
      bgm: { input: $("fileBgm"), set: setBgm },
    };
    ["audio", "srt", "bgm"].forEach((kind) => {
      const slot = $("slot" + kind[0].toUpperCase() + kind.slice(1));
      const conf = pickers[kind];
      slot.addEventListener("click", (e) => {
        if (e.target.closest(".slot-del")) return;
        conf.input.click();
      });
      conf.input.addEventListener("change", (e) => {
        const f = e.target.files && e.target.files[0];
        if (f) conf.set(f);
        e.target.value = "";
      });
      ["dragenter", "dragover"].forEach((ev) =>
        slot.addEventListener(ev, (e) => {
          e.preventDefault();
          slot.classList.add("over");
        })
      );
      ["dragleave", "dragend"].forEach((ev) => slot.addEventListener(ev, () => slot.classList.remove("over")));
      slot.addEventListener("drop", (e) => {
        e.preventDefault();
        slot.classList.remove("over");
        const f = e.dataTransfer.files && e.dataTransfer.files[0];
        if (f) conf.set(f);
      });
    });

    // 옵션
    $("optZoom").addEventListener("change", (e) => {
      state.opts.zoom = e.target.checked;
      saveOpts();
    });
    document.querySelectorAll("#optBg button").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.opts.bg_style = btn.dataset.bg;
        document.querySelectorAll("#optBg button").forEach((b) => b.classList.toggle("on", b === btn));
        document.querySelectorAll(".phone-screen").forEach((s) => (s.dataset.bg = btn.dataset.bg));
        saveOpts();
      });
    });
    $("optSubSize").addEventListener("input", (e) => {
      state.opts.subtitle_size = Number(e.target.value);
      syncOptLabels();
      saveOpts();
    });
    $("optBgmVol").addEventListener("input", (e) => {
      state.opts.bgm_vol = Number(e.target.value);
      syncOptLabels();
      saveOpts();
    });

    // 만들기 / 취소
    $("btnRender").addEventListener("click", render);
    $("btnCancel").addEventListener("click", () => {
      if (abortCtl) abortCtl.abort();
    });
    document.addEventListener("keydown", (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
        e.preventDefault();
        if (!state.busy) render();
      }
    });

    // 미리보기 재생
    $("pgPlay").addEventListener("click", (e) => {
      e.stopPropagation();
      playPreview();
    });
    $("phoneScreen").addEventListener("click", () => {
      if (isPreviewPlaying()) stopPreview();
    });

    $("btnSaveAgain").addEventListener("click", () => {
      if (state.result) window.open(state.result.url, "_blank");
    });
  }

  /* ───────────── 시작 ───────────── */
  function init() {
    loadOpts();
    bind();
    renderScenes();
    checkServer();
    setInterval(() => {
      if (!state.busy) checkServer({ quiet: true });
    }, 20000);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
