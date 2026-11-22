/* 통합 스튜디오 허브 — 서버 상태 확인 + 바로가기
   GitHub Pages(https)에서도, 로컬 허브(127.0.0.1:8770)에서도 같은 파일을 씁니다. */
(() => {
  'use strict';

  const SERVERS = [
    { id: 'tts-studio',    port: 8765 },
    { id: 'shorts-maker',  port: 8766 },
    { id: 'coupas-hunter', port: 8767 },
    { id: 'video-cutter',  port: 8768 },
  ];
  const HUB_PORT = 8770;
  const HUB_BASE = location.port === String(HUB_PORT) ? '' : `http://127.0.0.1:${HUB_PORT}`;
  const IS_LOCAL_HUB = location.port === String(HUB_PORT);
  const APP_VERSION = (document.querySelector('meta[name="app-version"]') || {}).content || '';
  const RAW_VERSION_URL = 'https://raw.githubusercontent.com/anchirong9-arch/studio-launcher/main/version.json';

  const $  = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  const cards = {};
  SERVERS.forEach(s => { cards[s.id] = $(`[data-tool="${s.id}"]`); });

  let hub = null;              // 로컬 허브 /api/status 결과 (없으면 null)
  let busy = false;
  let lastCheck = 0;

  /* ───────── 유틸 ───────── */
  function withTimeout(promise, ms) {
    return new Promise((resolve, reject) => {
      const t = setTimeout(() => reject(new Error('timeout')), ms);
      promise.then(v => { clearTimeout(t); resolve(v); },
                   e => { clearTimeout(t); reject(e); });
    });
  }

  function toast(msg, ms = 2400) {
    const el = $('#toast');
    el.textContent = msg;
    el.hidden = false;
    clearTimeout(toast._t);
    toast._t = setTimeout(() => { el.hidden = true; }, ms);
  }

  async function getJSON(url, ms = 2500) {
    const res = await withTimeout(fetch(url, { cache: 'no-store' }), ms);
    if (!res.ok) throw new Error('HTTP ' + res.status);
    return res.json();
  }

  async function postJSON(url, ms = 6000, body = {}) {
    const res = await withTimeout(fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }), ms);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || ('HTTP ' + res.status));
    return data;
  }

  /* 서버 하나 상태 확인 — 세 서버 모두 /health 에 CORS·Private Network 헤더를 보냅니다.
     실제 응답을 읽지 못하면 '꺼짐'으로 봅니다. (프록시 환경에서 도달 여부만으로 판단하면
     꺼진 서버도 켜진 것처럼 보이기 때문) */
  async function ping(port) {
    const url = `http://127.0.0.1:${port}/health?t=${Date.now()}`;
    try {
      const data = await getJSON(url, 2600);
      return { online: true, data };
    } catch (err) {
      return { online: false };
    }
  }

  async function getHub() {
    try {
      const data = await getJSON(`${HUB_BASE}/api/status`, 2000);
      return data && data.app === 'studio-launcher' ? data : null;
    } catch (err) {
      return null;
    }
  }

  /* ───────── 카드 렌더 ───────── */
  function detailText(id, h) {
    if (!h) return '';
    if (id === 'tts-studio') {
      return h.edge_tts
        ? `edge-tts ${h.edge_tts} · 목소리 ${(h.voices || []).length}종` + (h.gtts ? ' · 번역기 포함' : '')
        : 'edge-tts 미설치 — 실행하기.bat 을 다시 실행해 주세요';
    }
    if (id === 'shorts-maker') {
      return h.ffmpeg ? `ffmpeg ${h.ffmpeg} · 1080×1920 · ${h.fps || 30}fps`
                      : 'ffmpeg 준비 안 됨 — 실행하기.bat 을 다시 실행해 주세요';
    }
    if (id === 'coupas-hunter') {
      return h.keySet ? `쿠팡 키 등록됨 · ${h.keyHint || ''}` : '쿠팡 파트너스 키 등록 필요';
    }
    if (id === 'video-cutter') {
      return h.ffmpegReady ? `ffmpeg ${h.ffmpeg} · 최대 ${h.maxClips || 5}개`
                           : 'ffmpeg 준비 안 됨 — 실행하기.bat 을 다시 실행해 주세요';
    }
    return '';
  }

  function setPill(card, state, label) {
    const pill = $('[data-pill]', card);
    pill.className = 'pill ' + state;
    $('span', pill).textContent = label;
  }

  function renderServer(server, result, hubTool) {
    const card = cards[server.id];
    if (!card) return;
    card.classList.toggle('on', !!result.online);

    const detail = $('[data-detail]', card);
    const openBtn = $('[data-open]', card);
    const startBtn = $('[data-start]', card);

    if (result.online) {
      setPill(card, 'on', '켜짐');
      detail.textContent = result.opaque
        ? `포트 ${server.port} 응답 있음 · 상태 정보는 못 읽었어요`
        : (detailText(server.id, result.data) || `포트 ${server.port} · 127.0.0.1`);
      openBtn.removeAttribute('aria-disabled');
    } else if (hubTool && hubTool.error) {
      setPill(card, 'off', '충돌');
      detail.textContent = hubTool.error;
      openBtn.setAttribute('aria-disabled', 'true');
    } else {
      setPill(card, 'off', '꺼짐');
      detail.textContent = `포트 ${server.port} · 실행하기.bat 을 켜면 자동으로 붙어요`;
      openBtn.setAttribute('aria-disabled', 'true');
    }

    // '다시 켜기' — 로컬 허브가 켜져 있을 때만 의미가 있음
    if (hub) {
      startBtn.hidden = !!result.online || !!(hubTool && hubTool.managed);
      startBtn.disabled = false;
    } else {
      startBtn.hidden = true;
    }
  }

  function renderSummary(results, hubTools) {
    const online = results.filter(r => r.online).length;
    const sum = $('#sum');
    sum.className = 'sum ' + (online === SERVERS.length ? 'on' : online > 0 ? 'wait' : 'off');
    $('#sum b').textContent = online === 0 ? '서버 꺼짐' : `${online}/${SERVERS.length} 온라인`;

    $('#offlineBanner').hidden = online > 0;
    const stopBtn = $('#stopAll');
    stopBtn.hidden = !hub || online === 0;

    return online;
  }

  function renderKeyPanel(results) {
    const coupas = results.find(r => r.id === 'coupas-hunter');
    const panel = $('#keyPanel');
    const data = coupas && coupas.online ? coupas.data : null;

    if (!data) { panel.hidden = true; return; }
    panel.hidden = false;

    const state = $('#keyState');
    const done = $('#keyDone');
    const formWrap = $('#keyFormWrap');

    if (data.keySet) {
      state.className = 'pill on';
      state.textContent = '등록됨';
      done.hidden = false;
      formWrap.hidden = true;
      $('[data-keyhint]').textContent = data.keyHint || '—';
    } else {
      state.className = 'pill warn';
      state.textContent = '키 필요';
      done.hidden = true;
      formWrap.hidden = false;
    }
  }

  /* ───────── 전체 갱신 ───────── */
  async function refresh(manual = false) {
    if (busy) return;
    busy = true;
    if (manual) $('#refresh').classList.add('spin');

    const hubData = await getHub();
    hub = hubData;
    const hubTools = {};
    if (hubData) (hubData.tools || []).forEach(t => { hubTools[t.id] = t; });

    const results = await Promise.all(
      SERVERS.map(async s => Object.assign({ id: s.id, port: s.port }, await ping(s.port)))
    );

    // 허브가 아는 정보(관리 중인 프로세스, 충돌 사유)를 덧붙임
    results.forEach(r => {
      const ht = hubTools[r.id];
      if (ht && !r.online && ht.online) {
        // 허브는 응답했는데 브라우저가 직접 못 읽은 경우 (CORS/혼합 콘텐츠)
        r.online = true;
        r.data = ht.health || null;
        r.opaque = true;
      }
    });

    SERVERS.forEach(s => renderServer(s, results.find(r => r.id === s.id), hubTools[s.id]));
    renderSummary(results, hubTools);
    renderKeyPanel(results);

    $('#hubLink').hidden = IS_LOCAL_HUB;
    lastCheck = Date.now();
    busy = false;
    if (manual) setTimeout(() => $('#refresh').classList.remove('spin'), 400);
  }

  /* ───────── 버전 · 업데이트 ───────── */
  function verTuple(v) {
    return String(v || '').replace(/^v/i, '').split('.').map(n => parseInt(n, 10) || 0)
      .concat([0, 0, 0]).slice(0, 3);
  }

  function isNewer(a, b) {
    const x = verTuple(a), y = verTuple(b);
    for (let i = 0; i < 3; i++) if (x[i] !== y[i]) return x[i] > y[i];
    return false;
  }

  function paintVersion(info) {
    const bar = $('#verbar');
    const localEl = $('#verLocal');
    const latestEl = $('#verLatest');
    const applyBtn = $('#applyBtn');
    const labelEl = $('#verLabel');
    bar.classList.remove('ok', 'new');

    if (info.installed) {          // 로컬 허브에 붙었음 = 설치된 버전을 아는 상태
      labelEl.textContent = '설치 버전';
      localEl.textContent = 'v' + info.installed;
      $('#footVer').textContent = 'v' + info.installed;
      applyBtn.hidden = !info.updateAvailable;
      if (info.updateAvailable) {
        bar.classList.add('new');
        latestEl.textContent = `새 버전 v${info.latest} 이 나왔어요 — 지금 업데이트할 수 있어요`;
      } else if (info.error) {
        latestEl.textContent = info.error;
      } else if (!info.checked) {
        latestEl.textContent = '업데이트 확인을 누르면 새 버전이 있는지 확인해요';
      } else {
        bar.classList.add('ok');
        latestEl.textContent = info.checkedAt ? `최신 버전이에요 · ${info.checkedAt} 확인` : '최신 버전이에요';
      }
      return;
    }

    // 로컬 허브가 없을 때: 이 페이지(GitHub)가 최신 상태
    labelEl.textContent = '이 페이지';
    localEl.textContent = APP_VERSION ? 'v' + APP_VERSION : '—';
    if (APP_VERSION) $('#footVer').textContent = 'v' + APP_VERSION;
    applyBtn.hidden = true;
    if (info.latest) {
      bar.classList.add(isNewer(info.latest, APP_VERSION) ? 'new' : 'ok');
      latestEl.textContent = `최신 v${info.latest} · PC에서 런처를 켜면 설치 버전과 업데이트를 확인해요`;
    } else {
      latestEl.textContent = '최신 버전을 확인하지 못했어요 (오프라인?)';
    }
  }

  async function refreshVersion(force) {
    let info = null;
    try {
      info = force ? await postJSON(`${HUB_BASE}/api/update/check`, 7000)
                   : await getJSON(`${HUB_BASE}/api/version`, 1600);
      if (!info || !info.version) info = null;
    } catch (err) { info = null; }

    if (info) {
      paintVersion({
        installed: info.version,
        latest: info.latest,
        updateAvailable: !!info.updateAvailable,
        checked: !!info.checked,
        checkedAt: info.checkedAt,
        error: info.error || '',
      });
      return info;
    }

    let remote = null;
    try { remote = await getJSON(`${RAW_VERSION_URL}?t=${Date.now()}`, 4000); } catch (err) { remote = null; }
    paintVersion({ latest: remote && remote.version ? remote.version : '' });
    return null;
  }

  async function applyUpdate() {
    const btn = $('#applyBtn');
    const label = btn.textContent;
    btn.disabled = true;
    btn.textContent = '받는 중…';
    try {
      const res = await postJSON(`${HUB_BASE}/api/update/apply`, 60000);
      if (res.ok && res.version) {
        toast(`v${res.version} 로 업데이트했어요. 종료하기.bat → 실행하기.bat 하면 새 버전으로 켜져요.`, 7000);
      } else if (res.uptodate) {
        toast('이미 최신 버전이에요.');
      } else {
        toast('업데이트하지 못했어요: ' + (res.error || '알 수 없는 오류'));
      }
    } catch (err) {
      toast('업데이트하지 못했어요: ' + err.message);
    } finally {
      btn.disabled = false;
      btn.textContent = label;
      refreshVersion(true);
    }
  }

  /* ───────── 이벤트 ───────── */
  $('#updateBtn').addEventListener('click', async () => {
    const btn = $('#updateBtn');
    btn.disabled = true;
    btn.textContent = '확인 중…';
    await refreshVersion(true);
    btn.disabled = false;
    btn.textContent = '업데이트 확인';
  });

  $('#applyBtn').addEventListener('click', applyUpdate);
  $('#refresh').addEventListener('click', () => refresh(true));

  $$('.card.srv').forEach(card => {
    $('[data-open]', card).addEventListener('click', ev => {
      if (ev.currentTarget.getAttribute('aria-disabled') === 'true') {
        ev.preventDefault();
        toast('서버가 꺼져 있어요. 실행하기.bat 을 먼저 켜 주세요.');
      }
    });

    $('[data-start]', card).addEventListener('click', async ev => {
      const btn = ev.currentTarget;
      const tool = card.dataset.tool;
      btn.disabled = true;
      btn.textContent = '켜는 중…';
      try {
        const res = await fetch(`${HUB_BASE}/api/start`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ tool }),
        });
        const data = await res.json();
        toast(data.ok ? '다시 켰어요. 잠시 뒤 새로고침될 거예요.' : (data.result && data.result.error) || data.error || '켜지 못했어요.');
      } catch (err) {
        toast('로컬 허브가 꺼져 있어요. 실행하기.bat 을 다시 실행해 주세요.');
      } finally {
        btn.textContent = '다시 켜기';
        setTimeout(() => refresh(true), 1400);
      }
    });
  });

  $('#stopAll').addEventListener('click', async () => {
    if (!confirm('이 런처가 켠 서버를 모두 끌까요?')) return;
    try {
      const res = await fetch(`${HUB_BASE}/api/shutdown`, { method: 'POST' });
      const data = await res.json();
      toast(data.remaining && data.remaining.length
        ? `${data.message} 이미 켜져 있던 ${data.remaining.join(', ')}는 그대로 둘게요.`
        : '서버를 모두 정리했어요.');
    } catch (err) {
      toast('로컬 허브가 꺼져 있어요.');
    }
    setTimeout(() => refresh(true), 1500);
  });

  $('#keyChange').addEventListener('click', () => {
    $('#keyDone').hidden = true;
    $('#keyFormWrap').hidden = false;
    $('#kAccess').focus();
  });

  $('#keyForm').addEventListener('submit', async ev => {
    ev.preventDefault();
    const msg = $('#keyMsg');
    const btn = $('#keySubmit');
    const access = $('#kAccess').value.trim();
    const secret = $('#kSecret').value.trim();
    if (!access || !secret) { msg.className = 'msg err'; msg.textContent = '두 칸을 모두 채워 주세요.'; return; }

    btn.disabled = true;
    msg.className = 'msg';
    msg.textContent = '쿠팡 API로 확인하는 중…';
    try {
      const res = await fetch('http://127.0.0.1:8767/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ access_key: access, secret_key: secret }),
      });
      const data = await res.json();
      if (data.ok) {
        msg.className = 'msg ok';
        msg.textContent = data.message || '저장했어요.';
        $('#kSecret').value = '';
        $('#kSecret').type = 'password';
        setTimeout(() => refresh(true), 700);
      } else {
        msg.className = 'msg err';
        msg.textContent = data.error || '저장하지 못했어요.';
      }
    } catch (err) {
      msg.className = 'msg err';
      msg.textContent = '쿠파스 헌터 서버가 응답하지 않아요. 서버를 먼저 켜 주세요.';
    } finally {
      btn.disabled = false;
    }
  });

  // 10초마다, 화면을 보고 있을 때만 자동 확인
  setInterval(() => {
    if (document.hidden) return;
    if (Date.now() - lastCheck < 9000) return;
    refresh(false);
  }, 3000);

  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) refresh(false);
  });

  refresh(false);
  refreshVersion(false);
})();
