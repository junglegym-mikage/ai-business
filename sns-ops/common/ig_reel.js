// Instagramリール作成ヘルパー（全アカウント共通版。元は数秘のとびら ops/ig_reel.js。spec.brand でブランド名、spec.colors で配色を変えられる）（instagram.com のページ内で javascript_exec に貼って使う）
// 使い方: 1) このファイル全体を実行 → 2) __reelPreview(秒, spec) で描画を確認（任意）→ 3) __reelStart(spec) → __reelStatus().done まで待つ
//        → 4) await __reelCheck(秒) で動画のコマを確認（任意）→ 5) ig_render.js の __igOpen() → await __reelAttach() → 以降は RUNBOOK のリール手順
// （クラウドで見本を作るときは node ops/reel_render.js spec.json out.mp4 。同じ __reelDraw を使う）
// == reel_music：リール用の背景音楽をその場で作る（外部の曲・ダウンロードなし。自作の曲なので著作権・ミュートの心配なし） ==
// 同じ中身を次の場所に入れている。直すときはすべて同じに直すこと:
//   ai-business  sns/research          sns-ops/common/reel_music.js（正本）と sns-ops/common/ig_reel.js の中
//   ai-business  platform/issue-12-phase0  docs/platform/sns/tools/reel_music.js
//   suuhi-no-tobira  main              ops/reel_music.js と ops/ig_reel.js の中
// 雰囲気（mood）: bright＝明るい（ジム）／calm＝穏やか（御影ヘルスケア）／mystic＝神秘（数秘のとびら）／tech＝知的（PROCESS PERFORMANCE）
// 使い方（ブラウザ）: __reelMusicPCM({ mood, seed, dur }) → { sr, L, R, info }（ig_reel.js の __reelStart が自動で使う）
// 使い方（node）: node reel_music.js <mood> <seed> <秒> <out.wav>
(function (G) {
  const SR = 44100, TAU = Math.PI * 2;
  const SCALES = { major: [0, 2, 4, 5, 7, 9, 11], minor: [0, 2, 3, 5, 7, 8, 10] };
  const MOODS = {
    bright: { bpm: [108, 118], scale: 'major', progs: [[0, 4, 5, 3], [0, 5, 3, 4], [3, 4, 0, 0], [0, 3, 5, 4]], drums: 'pop', pad: 0.09, pluck: 0.15, bass: 0.17, bell: 0, arp: 8, decay: 5, seventh: false },
    calm: { bpm: [76, 86], scale: 'major', progs: [[0, 3, 0, 4], [0, 5, 3, 4], [3, 0, 4, 5], [0, 2, 3, 4]], drums: 'shaker', pad: 0.13, pluck: 0.12, bass: 0.10, bell: 0.05, arp: 4, decay: 2.2, seventh: true },
    mystic: { bpm: [64, 74], scale: 'minor', progs: [[0, 5, 2, 6], [0, 3, 4, 0], [0, 6, 5, 6], [0, 5, 3, 4]], drums: 'none', pad: 0.15, pluck: 0.07, bass: 0.09, bell: 0.10, arp: 4, decay: 1.6, seventh: true },
    tech: { bpm: [96, 106], scale: 'minor', progs: [[0, 5, 2, 6], [0, 6, 3, 4], [5, 6, 0, 0], [0, 3, 6, 5]], drums: 'four', pad: 0.08, pluck: 0.14, bass: 0.15, bell: 0, arp: 16, decay: 9, seventh: false },
  };
  function rng(seed) { let s = (seed >>> 0) || 1; return () => { s ^= s << 13; s >>>= 0; s ^= s >>> 17; s ^= s << 5; s >>>= 0; return s / 4294967296; }; }
  function hash(str) { let h = 2166136261; for (const ch of String(str)) { h ^= ch.codePointAt(0); h = Math.imul(h, 16777619); } return h >>> 0; }
  const mtof = (m) => 440 * Math.pow(2, (m - 69) / 12);

  // spec から雰囲気と種を決める。spec.music: false で無音、'bright' などの文字、または { mood, seed }
  function choose(spec) {
    spec = spec || {}; if (spec.music === false || spec.music === 'none') return null;
    const m = typeof spec.music === 'string' ? { mood: spec.music } : (spec.music || {});
    let mood = m.mood;
    if (!MOODS[mood]) {
      const b = String(spec.brand || '');
      mood = /JungleGym|ジム/i.test(b) ? 'bright' : /ヘルスケア|御影/.test(b) ? 'calm' : /PROCESS|AI/i.test(b) ? 'tech' : 'mystic';
    }
    const seed = m.seed != null ? (typeof m.seed === 'number' ? m.seed : hash(m.seed)) : hash(JSON.stringify(spec));
    return { mood, seed };
  }

  function render(opts) {
    const mood = MOODS[opts.mood] ? opts.mood : 'mystic', M = MOODS[mood], R = rng(opts.seed || 1);
    const dur = Math.max(3, Math.min(90, opts.dur || 8)), N = Math.ceil(dur * SR);
    const L = new Float32Array(N), Rt = new Float32Array(N), sendL = new Float32Array(N), sendR = new Float32Array(N);
    const bpm = M.bpm[0] + Math.floor(R() * (M.bpm[1] - M.bpm[0] + 1)), beat = 60 / bpm, bar = beat * 4;
    const key = 55 + Math.floor(R() * 8); // G3〜D4
    const prog = M.progs[Math.floor(R() * M.progs.length)], sc = SCALES[M.scale];
    const deg = (d) => Math.floor(d / 7) * 12 + sc[((d % 7) + 7) % 7];
    const chordAt = (i) => { const r = prog[i % prog.length]; const n = [deg(r), deg(r + 2), deg(r + 4)]; if (M.seventh) n.push(deg(r + 6)); return { root: r, notes: n }; };
    const bars = Math.ceil(dur / bar) + 1;
    // 1音を足す（gainL/gainR は左右の大きさ、send は残響へ送る量）
    function add(t0, len, fn, gL, gR, send) {
      const s0 = Math.max(0, Math.floor(t0 * SR)), s1 = Math.min(N, Math.floor((t0 + len) * SR));
      for (let s = s0; s < s1; s++) { const t = s / SR - t0, v = fn(t); L[s] += v * gL; Rt[s] += v * gR; if (send) { sendL[s] += v * gL * send; sendR[s] += v * gR * send; } }
    }
    const duck = M.drums === 'four' || M.drums === 'pop';
    const duckGain = (tAbs) => { if (!duck) return 1; const p = (tAbs % beat); return 1 - 0.38 * Math.exp(-p * 9); };
    for (let b = 0; b < bars; b++) {
      const T = b * bar, ch = chordAt(b);
      // パッド（和音の伸ばし）
      ch.notes.forEach((d, i) => {
        const f = mtof(key + d), len = bar + 0.6, det = 1.0018;
        add(T, len, (t) => { const env = Math.min(1, t / 0.45) * Math.min(1, Math.max(0, (len - t) / 0.6)); const g = env * duckGain(T + t);
          return g * (Math.sin(TAU * f * t) + 0.28 * Math.sin(TAU * 2 * f * t) + 0.1 * Math.sin(TAU * 3 * f * t)); }, M.pad * (i % 2 ? 0.8 : 1), M.pad * (i % 2 ? 1 : 0.8), 0.5);
        add(T, len, (t) => { const env = Math.min(1, t / 0.45) * Math.min(1, Math.max(0, (len - t) / 0.6)); return env * duckGain(T + t) * Math.sin(TAU * f * det * t); }, M.pad * 0.35, M.pad * 0.55, 0.5);
      });
      // ベース
      const bf = mtof(key - 12 + deg(ch.root)), hits = M.drums === 'four' ? [0, 1, 2, 3] : M.drums === 'pop' ? [0, 1.5, 2, 3.5] : [0, 2];
      hits.forEach((h) => { const len = beat * (M.drums === 'none' ? 2 : 0.9);
        add(T + h * beat, len, (t) => { const env = Math.min(1, t / 0.01) * Math.exp(-t * (M.drums === 'none' ? 1.2 : 3.5)) * Math.min(1, (len - t) / 0.05);
          return env * (Math.sin(TAU * bf * t) + 0.3 * Math.sin(TAU * 2 * bf * t)); }, M.bass, M.bass, 0); });
      // 分散和音（ポロンという音）
      const steps = M.arp, stepLen = bar / steps, pat = [0, 1, 2, 1, 0, 2, 1, 2, 0, 1, 2, 3, 2, 1, 0, 1];
      const offset = Math.floor(R() * 4);
      for (let k = 0; k < steps; k++) {
        if (M.arp >= 8 && R() < 0.12) continue; // ところどころ休む
        const idx = pat[(k + offset) % pat.length] % ch.notes.length, f = mtof(key + 12 + ch.notes[idx]);
        const len = Math.min(2.5, 6 / M.decay), pan = k % 2 ? 0.7 : 1, kd = M.decay;
        add(T + k * stepLen, len, (t) => { const env = Math.min(1, t / 0.004) * Math.exp(-t * kd);
          return env * (Math.sin(TAU * f * t) + 0.45 * Math.exp(-t * kd * 2) * Math.sin(TAU * 2 * f * t) + 0.18 * Math.exp(-t * kd * 3) * Math.sin(TAU * 3 * f * t)); }, M.pluck * pan, M.pluck * (1.7 - pan), 0.35);
      }
      // 鈴の音（神秘・穏やか）
      if (M.bell) for (let k = 0; k < 2; k++) {
        if (R() < 0.35) continue;
        const f = mtof(key + 24 + ch.notes[Math.floor(R() * ch.notes.length)]), len = 2.6, pan = R();
        add(T + k * 2 * beat + (R() < 0.5 ? beat : 0), len, (t) => { const env = Math.min(1, t / 0.003) * Math.exp(-t * 1.6);
          return env * Math.sin(TAU * f * t + 1.8 * Math.exp(-t * 3) * Math.sin(TAU * 3.5 * f * t)); }, M.bell * (0.5 + pan * 0.5), M.bell * (1 - pan * 0.5), 0.8);
      }
      // 打楽器
      for (let q = 0; q < 16; q++) {
        const tq = T + q * beat / 4;
        if ((M.drums === 'four' && q % 4 === 0) || (M.drums === 'pop' && (q === 0 || q === 6 || q === 8 || q === 11))) // バスドラム
          add(tq, 0.32, (t) => { const f = 45 + 80 * Math.exp(-t * 30); return Math.exp(-t * 12) * Math.sin(TAU * f * t + 2 * Math.sin(t * 6)); }, 0.42, 0.42, 0);
        if (M.drums === 'pop' && (q === 4 || q === 12)) { // 手拍子
          const nz = rng(hash('clap' + b + q)); add(tq, 0.2, (t) => Math.exp(-t * 22) * ((nz() * 2 - 1) * 0.8 + 0.3 * Math.sin(TAU * 190 * t)), 0.12, 0.14, 0.4);
        }
        const hat = M.drums === 'four' ? (q % 2 === 1 ? 1 : 0.45) : M.drums === 'pop' ? (q % 4 === 2 ? 1 : q % 2 ? 0.4 : 0) : M.drums === 'shaker' ? (q % 2 === 1 ? 0.7 : 0.3) : 0;
        if (hat) { const nz = rng(hash('hat' + b + q)); let prev = 0; const dk = M.drums === 'shaker' ? 28 : 55;
          add(tq, 0.12, (t) => { const n = nz() * 2 - 1, hp = n - prev; prev = n; return Math.exp(-t * dk) * hp; }, 0.035 * hat, 0.05 * hat, 0.1); }
      }
    }
    // 残響（簡単な部屋の響き）
    const verb = (inp, out, lens) => {
      const combs = lens.map(n => ({ b: new Float32Array(n), i: 0 })), ap = [new Float32Array(225), new Float32Array(556)], api = [0, 0];
      for (let s = 0; s < N; s++) { let y = 0; for (const c of combs) { const o = c.b[c.i]; y += o; c.b[c.i] = inp[s] + o * 0.8; c.i = (c.i + 1) % c.b.length; }
        y *= 0.25; for (let a = 0; a < 2; a++) { const bufA = ap[a], o = bufA[api[a]], v = y + o * 0.5; bufA[api[a]] = v; y = o - v * 0.5; api[a] = (api[a] + 1) % bufA.length; }
        out[s] += y * 0.32; }
    };
    verb(sendL, L, [1557, 1617, 1491, 1422]); verb(sendR, Rt, [1580, 1640, 1514, 1445]);
    // 仕上げ：はじめと終わりをなめらかに、音量をそろえる
    let peak = 1e-6; for (let s = 0; s < N; s++) peak = Math.max(peak, Math.abs(L[s]), Math.abs(Rt[s]));
    const g = 0.72 / peak, fi = 0.25 * SR, fo = 1.3 * SR;
    for (let s = 0; s < N; s++) { const e = Math.min(1, s / fi, (N - s) / fo); L[s] = Math.tanh(L[s] * g * 1.1) * e * 0.92; Rt[s] = Math.tanh(Rt[s] * g * 1.1) * e * 0.92; }
    return { sr: SR, L, R: Rt, info: { mood, bpm, key, seed: opts.seed } };
  }

  function wav(p) {
    const n = p.L.length, buf = new ArrayBuffer(44 + n * 4), dv = new DataView(buf), w = (o, s) => { for (let i = 0; i < s.length; i++) dv.setUint8(o + i, s.charCodeAt(i)); };
    w(0, 'RIFF'); dv.setUint32(4, 36 + n * 4, true); w(8, 'WAVE'); w(12, 'fmt '); dv.setUint32(16, 16, true); dv.setUint16(20, 1, true); dv.setUint16(22, 2, true);
    dv.setUint32(24, p.sr, true); dv.setUint32(28, p.sr * 4, true); dv.setUint16(32, 4, true); dv.setUint16(34, 16, true); w(36, 'data'); dv.setUint32(40, n * 4, true);
    for (let i = 0; i < n; i++) { dv.setInt16(44 + i * 4, Math.max(-1, Math.min(1, p.L[i])) * 32767, true); dv.setInt16(46 + i * 4, Math.max(-1, Math.min(1, p.R[i])) * 32767, true); }
    return new Uint8Array(buf);
  }

  G.__reelMusicChoose = choose;
  G.__reelMusicPCM = render;
  G.__reelMusicWav = wav;
  if (typeof module !== 'undefined' && module.exports) module.exports = { choose, render, wav, hash };
  if (typeof require !== 'undefined' && typeof module !== 'undefined' && require.main === module) {
    const [mood, seed, sec, out] = process.argv.slice(2);
    if (!out) { console.error('使い方: node reel_music.js <bright|calm|mystic|tech> <seed> <秒> <out.wav>'); process.exit(1); }
    const p = render({ mood, seed: /^\d+$/.test(seed) ? +seed : hash(seed), dur: +sec });
    require('fs').writeFileSync(out, wav(p)); console.log('ok', out, JSON.stringify(p.info));
  }
})(typeof window !== 'undefined' ? window : globalThis);
// == reel_music ここまで ==
{
const W = 1080, H = 1920, FPS = 30;
const F = { serif: '"Hiragino Mincho ProN","Yu Mincho","Noto Serif JP","Noto Serif CJK JP",serif', sans: '"Hiragino Sans","Hiragino Kaku Gothic ProN","Yu Gothic","Noto Sans CJK JP",sans-serif' };
const K = { bg: '#1d2433', bg2: '#262f43', ink: '#ece6d8', soft: '#a9adb8', gold: '#d2ab5c', seal: '#e07a62', line: '#3a4357' };
const clamp = (v) => Math.max(0, Math.min(1, v));
const ease = (v) => 1 - Math.pow(1 - clamp(v), 3);
const pop = (v) => { v = clamp(v); return v < 1 ? 1 + 2.2 * Math.pow(v - 1, 3) + 1.2 * Math.pow(v - 1, 2) : 1; };
function txt(x, s, px, py, size, font, color, weight = '', align = 'center', alpha = 1) {
  x.globalAlpha = alpha; x.font = `${weight} ${size}px ${font}`; x.fillStyle = color; x.textAlign = align; x.textBaseline = 'middle'; x.fillText(s, px, py); x.globalAlpha = 1;
}
function bg(x) {
  const g = x.createLinearGradient(0, 0, 0, H); g.addColorStop(0, K.bg2); g.addColorStop(1, K.bg); x.fillStyle = g; x.fillRect(0, 0, W, H);
  x.strokeStyle = K.line; x.lineWidth = 3; x.strokeRect(40, 40, W - 80, H - 80);
}
// type "chart": 運命数ごとの相性早見（rows: [[数字, 名前, [相性の数字...]], ...]）
function drawChart(x, spec, t) {
  bg(x);
  // 0〜2秒: 画面中央にフック → 2〜2.6秒で上へ移動
  const m = ease((t - 2.0) / 0.6), hy = 760 + (240 - 760) * m, hs = 1 - 0.42 * m, hin = 0.35 + 0.65 * ease(t / 0.3);
  x.save(); x.translate(W / 2, hy); x.scale(hs * (0.85 + 0.15 * hin), hs * (0.85 + 0.15 * hin));
  txt(x, spec.hook1, 0, -150, 64, F.sans, K.soft, 'bold', 'center', hin);
  txt(x, spec.hook2, 0, 0, 120, F.serif, K.ink, 'bold', 'center', hin);
  txt(x, spec.hook3, 0, 150, 120, F.serif, K.gold, 'bold', 'center', hin);
  x.restore();
  const subA = clamp((t - 0.5) / 0.3) * (1 - m);
  txt(x, spec.sub, W / 2, 1080, 46, F.sans, K.seal, 'bold', 'center', subA);
  txt(x, '↓ 自分の数字で止めてね', W / 2, 1180, 42, F.sans, K.soft, '', 'center', subA * (0.6 + 0.4 * Math.sin(t * 8)));
  // 2.4秒〜: 行が順番に出る
  const top = 480, step = 74;
  spec.rows.forEach(([n, name, comp], i) => {
    const t0 = 2.4 + i * 0.28, a = clamp((t - t0) / 0.25); if (a <= 0) return;
    const y = top + i * step, s = pop((t - t0) / 0.35);
    if (i % 2 === 0) { x.globalAlpha = 0.35 * a; x.fillStyle = K.line; x.fillRect(90, y - step / 2 + 4, W - 180, step - 8); x.globalAlpha = 1; }
    x.save(); x.translate(200, y); x.scale(s, s); txt(x, String(n), 0, 0, 60, F.serif, K.gold, 'bold', 'center', a); x.restore();
    txt(x, name, 270, y, 38, F.sans, K.ink, '', 'left', a);
    txt(x, comp.join('・'), 900, y, 54, F.serif, K.ink, 'bold', 'right', a);
  });
  const hdA = clamp((t - 2.4) / 0.3);
  txt(x, '運命数', 200, top - 62, 30, F.sans, K.soft, '', 'center', hdA);
  txt(x, '相性がいい数字', 900, top - 62, 30, F.sans, K.soft, '', 'right', hdA);
  // 終盤: 行動のお願い
  const ctaA = clamp((t - spec.ctaAt) / 0.4);
  if (ctaA > 0) {
    const y0 = top + spec.rows.length * step + 20;
    x.globalAlpha = ctaA; x.fillStyle = K.gold; x.fillRect(150, y0, W - 300, 3); x.globalAlpha = 1;
    txt(x, spec.cta1, W / 2, y0 + 62, 50, F.sans, K.ink, 'bold', 'center', ctaA);
    txt(x, spec.cta2, W / 2, y0 + 126, 40, F.sans, K.soft, '', 'center', ctaA);
  }
  txt(x, spec.brand || '数秘のとびら', W / 2, 1620, 40, F.serif, K.gold, 'bold', 'center', 0.9);
}
// type "pick": 運命数ひとつに絞って、相性がいい3つの数字を1つずつ見せる
// spec: { type:'pick', dur, n, name, picks:[[数字, 名前, くれるもの], ...], cta1, cta2 }
function drawPick(x, spec, t) {
  bg(x);
  const m = ease((t - 1.8) / 0.5), hin = 0.35 + 0.65 * ease(t / 0.3);
  // フック: 大きな数字 → 上へ
  const ny = 700 + (330 - 700) * m, ns = 1 - 0.45 * m;
  x.save(); x.translate(W / 2, ny); x.scale(ns, ns);
  txt(x, '運命数', 0, -300, 64, F.sans, K.soft, 'bold', 'center', hin);
  txt(x, String(spec.n), 0, -20, spec.n < 10 ? 400 : 320, F.serif, K.gold, 'bold', 'center', hin);
  txt(x, 'の人と', 0, 250, 72, F.serif, K.ink, 'bold', 'center', hin);
  x.restore();
  txt(x, '相性がいい数字は？', W / 2, 1150 + (560 - 1150) * m, 96 - 30 * m, F.serif, K.ink, 'bold', 'center', hin);
  txt(x, '↓ 自分の数字が出たら保存', W / 2, 1290, 42, F.sans, K.soft, '', 'center', clamp((t - 0.5) / 0.3) * (1 - m) * (0.6 + 0.4 * Math.sin(t * 8)));
  // 3つを順に
  spec.picks.forEach(([b, name, give], i) => {
    const t0 = 2.4 + i * 1.3, a = clamp((t - t0) / 0.3); if (a <= 0) return;
    const y = 760 + i * 230, s = pop((t - t0) / 0.4);
    x.globalAlpha = 0.45 * a; x.fillStyle = K.line; x.fillRect(110, y - 95, W - 220, 190); x.globalAlpha = 1;
    x.save(); x.translate(250, y); x.scale(s, s); txt(x, String(b), 0, 0, b < 10 ? 150 : 120, F.serif, K.gold, 'bold', 'center', a); x.restore();
    txt(x, name, 380, y - 34, 56, F.serif, K.ink, 'bold', 'left', a);
    txt(x, give, 380, y + 44, 36, F.sans, K.soft, '', 'left', a);
  });
  const ctaA = clamp((t - spec.ctaAt) / 0.4);
  if (ctaA > 0) {
    x.globalAlpha = ctaA; x.fillStyle = K.gold; x.fillRect(150, 1450, W - 300, 3); x.globalAlpha = 1;
    txt(x, spec.cta1, W / 2, 1515, 50, F.sans, K.ink, 'bold', 'center', ctaA);
    txt(x, spec.cta2, W / 2, 1580, 40, F.sans, K.soft, '', 'center', ctaA);
  }
  txt(x, spec.brand || '数秘のとびら', W / 2, 1680, 40, F.serif, K.gold, 'bold', 'center', 0.9);
}
// type "slides": 文字の場面を順に見せる（説明リール用）
// spec: { type:'slides', dur, top:'上に出し続ける見出し', topFrom:秒, scenes:[{at:秒, lines:[[文字, 大きさ, 色('ink'|'gold'|'soft'|'seal'), 'serif'|'sans'], ...]}, ...] }
function drawSlides(x, spec, t) {
  bg(x);
  const sc = spec.scenes; let i = 0; while (i + 1 < sc.length && t >= sc[i + 1].at) i++;
  const tin = t - sc[i].at, next = sc[i + 1], tout = next ? next.at - t : 99;
  const a = (i === 0 ? 0.35 + 0.65 * ease(tin / 0.3) : ease(tin / 0.3)) * clamp(tout / 0.2), dy = (1 - ease(tin / 0.35)) * 40;
  const L = sc[i].lines, gap = 34, hs = L.map(l => l[1] * 1.25), total = hs.reduce((p, h) => p + h, 0) + gap * (L.length - 1);
  let y = 900 - total / 2 + dy;
  L.forEach(([s, size, col, font], k) => { y += hs[k] / 2; txt(x, s, W / 2, y, size, font === 'sans' ? F.sans : F.serif, K[col] || K.ink, 'bold', 'center', a); y += hs[k] / 2 + gap; });
  if (spec.top && t >= spec.topFrom) txt(x, spec.top, W / 2, 230, 52, F.serif, K.gold, 'bold', 'center', ease((t - spec.topFrom) / 0.3));
  // 進み具合の点
  sc.forEach((_, k) => { x.globalAlpha = k === i ? 1 : 0.3; x.fillStyle = K.gold; x.beginPath(); x.arc(W / 2 + (k - (sc.length - 1) / 2) * 34, 1500, 8, 0, Math.PI * 2); x.fill(); x.globalAlpha = 1; });
  txt(x, spec.brand || '数秘のとびら', W / 2, 1620, 40, F.serif, K.gold, 'bold', 'center', 0.9);
}
// フィード用の spec（instagram_posts.json の today / pair / card / aisho / year2026）をそのまま縦動画にする（dur 省略時 8秒）
// 2026-10-31 から Instagram は全投稿リール。中身はフィード画像と同じで、順に出てくる動きを付けたもの。
function popNum(x, s, px, py, size, t0, t) { const a = clamp((t - t0) / 0.25); if (a <= 0) return; const k = pop((t - t0) / 0.4); x.save(); x.translate(px, py); x.scale(k, k); txt(x, s, 0, 0, size, F.serif, K.gold, 'bold', 'center', a); x.restore(); }
function fit(x, s, size, font, maxW = 940) { x.font = `bold ${size}px ${font}`; const w = x.measureText(s).width; return w > maxW ? Math.floor(size * maxW / w) : size; }
function fade(t, t0) { return ease((t - t0) / 0.35); }
function feedCta(x, t, t0, l1, l2) {
  const a = fade(t, t0); if (a <= 0) return;
  x.globalAlpha = a; x.fillStyle = K.gold; x.fillRect(150, 1380, W - 300, 3); x.globalAlpha = 1;
  txt(x, l1, W / 2, 1450, 46, F.sans, K.ink, 'bold', 'center', a); if (l2) txt(x, l2, W / 2, 1515, 38, F.sans, K.soft, '', 'center', a);
}
function drawFeed(x, spec, t) {
  bg(x); const hin = 0.35 + 0.65 * ease(t / 0.3);
  if (spec.type === 'today') {
    txt(x, spec.label, W / 2, 260, 52, F.sans, K.soft, 'bold', 'center', hin);
    txt(x, '今日の数字は…', W / 2, 360, 76, F.serif, K.ink, 'bold', 'center', hin);
    popNum(x, String(spec.n), W / 2, 680, spec.n < 10 ? 460 : 360, 1.0, t);
    txt(x, spec.title, W / 2, 1000, fit(x, spec.title, 92, F.serif), F.serif, K.ink, 'bold', 'center', fade(t, 2.0));
    const m = spec.msg, cut = m.length > 18 ? (m.indexOf('、') + 1 || Math.ceil(m.length / 2)) : m.length;
    txt(x, m.slice(0, cut), W / 2, 1140, 46, F.sans, K.ink, '', 'center', fade(t, 3.0)); if (cut < m.length) txt(x, m.slice(cut), W / 2, 1210, 46, F.sans, K.ink, '', 'center', fade(t, 3.0));
    feedCta(x, t, 4.6, 'あなたの運命数は？', 'プロフのリンクから無料診断');
  } else if (spec.type === 'pair') {
    txt(x, '運命数の相性', W / 2, 300, 64, F.serif, K.soft, 'bold', 'center', hin);
    const big = (spec.a >= 10 || spec.b >= 10) ? 260 : 340;
    popNum(x, String(spec.a), 300, 620, big, 0.4, t); txt(x, '×', W / 2, 620, 110, F.serif, K.soft, '', 'center', fade(t, 0.8)); popNum(x, String(spec.b), 780, 620, big, 1.1, t);
    txt(x, `${spec.na} × ${spec.nb}`, W / 2, 900, fit(x, `${spec.na} × ${spec.nb}`, 58, F.serif), F.serif, K.ink, 'bold', 'center', fade(t, 2.0));
    const la = clamp((t - 3.0) / 0.25); if (la > 0) { const k = pop((t - 3.0) / 0.4); x.save(); x.translate(W / 2, 1060); x.scale(k, k); x.globalAlpha = la; x.strokeStyle = K.gold; x.lineWidth = 3; x.strokeRect(-200, -60, 400, 120); x.globalAlpha = 1; txt(x, spec.level, 0, 0, 60, F.serif, K.gold, 'bold', 'center', la); x.restore(); }
    feedCta(x, t, 4.6, '全78通りの相性はプロフのリンクから', '気になる人の数字、コメントで教えてね');
  } else if (spec.type === 'card') {
    txt(x, '運命数', W / 2, 330, 80, F.serif, K.ink, 'bold', 'center', hin);
    popNum(x, String(spec.n), W / 2, 680, spec.n < 10 ? 460 : 360, 0.8, t);
    txt(x, `の人は「${spec.name}」`, W / 2, 1000, fit(x, `の人は「${spec.name}」`, 80, F.serif), F.serif, K.ink, 'bold', 'center', fade(t, 2.0));
    txt(x, spec.kw, W / 2, 1140, fit(x, spec.kw, 50, F.sans), F.sans, K.seal, 'bold', 'center', fade(t, 3.0));
    feedCta(x, t, 4.6, 'あなたの運命数は？', 'プロフのリンクから無料診断');
  } else {
    const rows = spec.type === 'aisho' ? spec.rows.map(([n, s]) => [n, s]) : ['始まりの年', '育てる年', '楽しむ年', '固める年', '動く年', 'つながる年', '深める年', '実る年', 'しめくくりの年'].map((s, i) => [i + 1, s]);
    const [h1, h2] = spec.type === 'aisho' ? ['保存版', '運命数の相性早見表'] : ['誕生月＋誕生日＋2026 を一桁に', '2026年、あなたは何の年？'];
    txt(x, h1, W / 2, 230, 44, F.sans, K.soft, 'bold', 'center', hin); txt(x, h2, W / 2, 320, 72, F.serif, K.ink, 'bold', 'center', hin);
    const step = Math.min(90, 900 / rows.length), top = 480;
    rows.forEach(([n, s], i) => { const t0 = 0.8 + i * 0.3, a = clamp((t - t0) / 0.25); if (a <= 0) return; const y = top + i * step;
      if (i % 2 === 0) { x.globalAlpha = 0.35 * a; x.fillStyle = K.line; x.fillRect(110, y - step / 2 + 4, W - 220, step - 8); x.globalAlpha = 1; }
      txt(x, String(n), 260, y, 60, F.serif, K.gold, 'bold', 'center', a); txt(x, s, 360, y, 50, F.serif, K.ink, 'bold', 'left', a); });
    feedCta(x, t, 0.8 + rows.length * 0.3 + 0.6, '自分の数字のところで保存してね', 'プロフのリンクから無料診断');
  }
  txt(x, spec.brand || '数秘のとびら', W / 2, 1640, 40, F.serif, K.gold, 'bold', 'center', 0.9);
}
const FEED = ['today', 'pair', 'card', 'aisho', 'year2026'];
const K0 = Object.assign({}, K);
window.__reelDraw = (x, spec, t) => { Object.assign(K, K0, spec.colors || {}); if (spec.type === 'chart') drawChart(x, spec, t); else if (spec.type === 'pick') drawPick(x, spec, t); else if (spec.type === 'slides') drawSlides(x, spec, t); else if (FEED.includes(spec.type)) drawFeed(x, spec, t); };
window.__reelCanvas = () => { let c = window.__rc; if (!c) { c = window.__rc = document.createElement('canvas'); c.width = W; c.height = H; } return c; };
// 指定秒のコマを画面右上に小さく表示（確認用）。もう一度呼ぶと差し替え、null で消す。
window.__reelPreview = (sec, spec = window.__reelSpec) => {
  let img = document.getElementById('__reelprev'); if (sec == null) { if (img) img.remove(); return 'removed'; }
  const c = document.createElement('canvas'); c.width = W; c.height = H; __reelDraw(c.getContext('2d'), spec, sec);
  if (!img) { img = document.createElement('img'); img.id = '__reelprev'; img.style.cssText = 'position:fixed;top:0;right:0;height:100vh;z-index:999999;border:2px solid red'; document.body.appendChild(img); }
  img.src = c.toDataURL('image/jpeg', 0.9); return 'shown ' + sec + 's';
};
// 動画（mp4）はページ内で WebCodecs（VideoEncoder・H.264）で1コマずつ符号化し、下の小さな mp4 組み立てで1ファイルにする。
// （MediaRecorder は内蔵ブラウザだと数フレームしか録れず、外部URLからの取得も Instagram の CSP で止められるため、この方式）
function box(type, ...parts) {
  const body = parts.map(p => p instanceof Uint8Array ? p : new Uint8Array(p)); const len = 8 + body.reduce((s, p) => s + p.length, 0);
  const out = new Uint8Array(len), dv = new DataView(out.buffer); dv.setUint32(0, len); for (let i = 0; i < 4; i++) out[4 + i] = type.charCodeAt(i);
  let o = 8; for (const p of body) { out.set(p, o); o += p.length; } return out;
}
const u32 = (...v) => { const a = new Uint8Array(v.length * 4), d = new DataView(a.buffer); v.forEach((x, i) => d.setUint32(i * 4, x)); return a; };
const u16 = (...v) => { const a = new Uint8Array(v.length * 2), d = new DataView(a.buffer); v.forEach((x, i) => d.setUint16(i * 2, x)); return a; };
const bytes = (...v) => new Uint8Array(v);
const full = (type, ver, flags, ...parts) => box(type, u32((ver << 24) | flags), ...parts);
const MATRIX = u32(0x10000, 0, 0, 0, 0x10000, 0, 0, 0, 0x40000000);
function mp4(samples, avcC, w, h, fps, audio) {
  // audio（任意）: { samples: [AACの1フレームずつ], asc: AudioSpecificConfig, sr }。あれば音声トラックを2本目として入れる（2026-11-07〜）
  const n = samples.length, dur = n; // media timescale = fps, 1 tick per frame
  const te = (s) => new TextEncoder().encode(s);
  const ftyp = box('ftyp', te('isom'), u32(512), te('isomiso2avc1mp41'));
  const vBytes = samples.reduce((s, x) => s + x.data.length, 0), aBytes = audio ? audio.samples.reduce((s, x) => s + x.length, 0) : 0;
  const mdatLen = 8 + vBytes + aBytes;
  const keys = samples.map((s, i) => s.key ? i + 1 : 0).filter(Boolean);
  const avc1 = box('avc1', new Uint8Array(6), u16(1), new Uint8Array(16), u16(w, h), u32(0x480000, 0x480000, 0), u16(1), new Uint8Array(32), u16(0x18, 0xffff), box('avcC', avcC));
  const dinf = () => box('dinf', full('dref', 0, 0, u32(1), full('url ', 0, 1)));
  const mvdur = Math.round(dur * 1000 / fps);
  const an = audio ? audio.samples.length : 0, adur = an * 1024, amv = audio ? Math.min(mvdur, Math.round(adur * 1000 / audio.sr)) : 0;
  const esds = () => {
    const asc = audio.asc, dsi = bytes(0x05, asc.length, ...asc), sl = bytes(0x06, 1, 0x02);
    const dcd = bytes(0x04, 13 + dsi.length, 0x40, 0x15, 0, 0, 0, ...u32(128000, 128000), ...dsi);
    return full('esds', 0, 0, bytes(0x03, 3 + dcd.length + sl.length, 0, 2, 0, ...dcd, ...sl));
  };
  const moovOf = (vOff, aOff) => box('moov',
    full('mvhd', 0, 0, u32(0, 0, 1000, mvdur, 0x10000), u16(0x100, 0), u32(0, 0), MATRIX, new Uint8Array(24), u32(audio ? 3 : 2)),
    box('trak',
      full('tkhd', 0, 3, u32(0, 0, 1, 0, mvdur, 0, 0), u16(0, 0, 0, 0), MATRIX, u32(w << 16, h << 16)),
      box('mdia',
        full('mdhd', 0, 0, u32(0, 0, fps, dur), u16(0x55c4, 0)),
        full('hdlr', 0, 0, u32(0), te('vide'), new Uint8Array(12), te('VideoHandler\0')),
        box('minf', full('vmhd', 0, 1, new Uint8Array(8)), dinf(), box('stbl',
          full('stsd', 0, 0, u32(1), avc1),
          full('stts', 0, 0, u32(1, n, 1)),
          full('stss', 0, 0, u32(keys.length, ...keys)),
          full('stsc', 0, 0, u32(1, 1, n, 1)),
          full('stsz', 0, 0, u32(0, n, ...samples.map(s => s.data.length))),
          full('stco', 0, 0, u32(1, vOff)))))),
    ...(audio ? [box('trak',
      full('tkhd', 0, 3, u32(0, 0, 2, 0, amv, 0, 0), u16(0, 0, 0x100, 0), MATRIX, u32(0, 0)),
      box('mdia',
        full('mdhd', 0, 0, u32(0, 0, audio.sr, adur), u16(0x55c4, 0)),
        full('hdlr', 0, 0, u32(0), te('soun'), new Uint8Array(12), te('SoundHandler\0')),
        box('minf', full('smhd', 0, 0, u16(0, 0)), dinf(), box('stbl',
          full('stsd', 0, 0, u32(1), box('mp4a', new Uint8Array(6), u16(1), new Uint8Array(8), u16(2, 16, 0, 0), u32(audio.sr * 65536), esds())),
          full('stts', 0, 0, u32(1, an, 1024)),
          full('stsc', 0, 0, u32(1, 1, an, 1)),
          full('stsz', 0, 0, u32(0, an, ...audio.samples.map(s => s.length))),
          full('stco', 0, 0, u32(1, aOff))))))] : []));
  const moovLen = moovOf(0, 0).length, vOff = ftyp.length + moovLen + 8; // faststart: ftyp → moov → mdat（映像のあとに音声）
  const mdatHead = new Uint8Array(8); new DataView(mdatHead.buffer).setUint32(0, mdatLen); mdatHead.set([109, 100, 97, 116], 4);
  return new Blob([ftyp, moovOf(vOff, vOff + vBytes), mdatHead, ...samples.map(s => s.data), ...(audio ? audio.samples : [])], { type: 'video/mp4' });
}
// 背景音楽を AAC に符号化する（WebCodecs の AudioEncoder）。使えない環境では例外を投げる（そのときは無音の動画になり、__reelStatus().audio に理由が入る）
async function reelAAC(p) {
  if (typeof AudioEncoder === 'undefined') throw new Error('AudioEncoder なし');
  const cfg = { codec: 'mp4a.40.2', sampleRate: p.sr, numberOfChannels: 2, bitrate: 128000, aac: { format: 'aac' } };
  if (!(await AudioEncoder.isConfigSupported(cfg).catch(() => ({}))).supported) throw new Error('AAC の符号化に未対応');
  const out = []; let asc = null, err = null;
  const enc = new AudioEncoder({ output: (c, meta) => { if (meta && meta.decoderConfig && meta.decoderConfig.description) asc = new Uint8Array(meta.decoderConfig.description); const d = new Uint8Array(c.byteLength); c.copyTo(d); out.push(d); }, error: e => err = String(e) });
  enc.configure(cfg);
  const CH = 4410;
  for (let i = 0; i < p.L.length && !err; i += CH) {
    const k = Math.min(CH, p.L.length - i), data = new Float32Array(k * 2); data.set(p.L.subarray(i, i + k), 0); data.set(p.R.subarray(i, i + k), k);
    const ad = new AudioData({ format: 'f32-planar', sampleRate: p.sr, numberOfFrames: k, numberOfChannels: 2, timestamp: Math.round(i * 1e6 / p.sr), data }); enc.encode(ad); ad.close();
  }
  await enc.flush(); enc.close(); if (err) throw new Error(err); if (!out.length) throw new Error('AAC の出力なし');
  const frames = out.map(d => (d[0] === 0xff && (d[1] & 0xf0) === 0xf0) ? d.subarray((d[1] & 1) ? 7 : 9) : d); // ADTS の見出しが付いていたら外す
  return { samples: frames, asc: asc && asc.length ? asc : bytes(0x12, 0x10), sr: p.sr }; // 0x12 0x10 = AAC-LC 44.1kHz ステレオ
}
// 動画に入れる音を用意する（spec.music: false で無音。'bright' などで雰囲気を指定。省略時は spec.brand から自動）
async function reelAudio(spec, st) {
  const mc = __reelMusicChoose(spec); if (!mc) { st.audio = 'なし（spec.music:false）'; return null; }
  try {
    const a = window.__reelAudioTest || await reelAAC(__reelMusicPCM({ mood: mc.mood, seed: mc.seed, dur: spec.dur }));
    st.audio = 'あり（' + mc.mood + '）'; return a;
  } catch (e) { st.audio = 'なし（' + (e && e.message || e) + '）'; return null; }
}
window.__reelMux = mp4; // 確認用
// spec から mp4 を作る。内蔵ブラウザの符号化は遅い（1080x1920 で数fps）ので裏で動かし、__reelStatus() で進み具合を見る。
// 終わると window.__reelBlob に入り、__reelStatus().done が true になる（目安 1〜2分。ソフトウェア符号化）。途中で止まったらページを再読み込みしてやり直す。
window.__reelStart = (spec) => {
  if (!spec.dur) spec = Object.assign({}, spec, { dur: 8 }); window.__reelSpec = spec; const st = window.__reelState = { frame: 0, total: Math.round(spec.dur * FPS), out: 0, done: false, err: null, t0: Date.now() };
  (async () => {
    const c = __reelCanvas(), x = c.getContext('2d'), samples = []; let avcC = null;
    const enc = new VideoEncoder({ output: (chunk, meta) => { if (meta && meta.decoderConfig && meta.decoderConfig.description) avcC = new Uint8Array(meta.decoderConfig.description); const d = new Uint8Array(chunk.byteLength); chunk.copyTo(d); samples.push({ data: d, key: chunk.type === 'key' }); st.out = samples.length; }, error: e => st.err = String(e) });
    // 2026-11-03: 内蔵ブラウザが画面に出ていない（隠れている）と、ハードウェア符号化が数コマで止まる。ソフトウェア符号化なら隠れていても約1分半で終わるので、使えるときはそれを使う。
    const cfg = { codec: 'avc1.640028', width: W, height: H, bitrate: 6000000, framerate: FPS, avc: { format: 'avc' } };
    const sw = Object.assign({}, cfg, { hardwareAcceleration: 'prefer-software' });
    st.hw = (await VideoEncoder.isConfigSupported(sw).catch(() => ({}))).supported ? 'software' : 'default';
    enc.configure(st.hw === 'software' ? sw : cfg);
    // 15秒進まなければ止まったとみなす（err に stalled。ページを再読み込みしてやり直す）
    let last = -1, lastT = Date.now(); const dog = setInterval(() => { if (st.done || st.err) return clearInterval(dog); if (st.out !== last) { last = st.out; lastT = Date.now(); } else if (Date.now() - lastT > 15000) { st.err = 'stalled at frame ' + st.frame + ' (' + st.hw + ')'; clearInterval(dog); } }, 1000);
    for (let f = 0; f < st.total && !st.err; f++) {
      __reelDraw(x, spec, f / FPS);
      const vf = new VideoFrame(c, { timestamp: Math.round(f * 1e6 / FPS), duration: Math.round(1e6 / FPS) });
      enc.encode(vf, { keyFrame: f % 60 === 0 }); vf.close(); st.frame = f + 1;
      while (enc.encodeQueueSize > 4 && !st.err) await new Promise(r => setTimeout(r, 20));
    }
    await enc.flush(); enc.close();
    if (st.err) return; if (!avcC) { st.err = 'no avcC'; return; }
    const audio = await reelAudio(spec, st); // 背景音楽（2026-11-07〜）
    window.__reelBlob = mp4(samples, avcC, W, H, FPS, audio);
    const v = document.createElement('video'); v.muted = true; v.src = URL.createObjectURL(__reelBlob);
    await new Promise(r => { v.onloadedmetadata = r; v.onerror = r; setTimeout(r, 5000); });
    Object.assign(st, { bytes: __reelBlob.size, duration: v.duration, w: v.videoWidth, h: v.videoHeight, verr: v.error && v.error.message, done: true });
  })().catch(e => st.err = String(e));
  return 'started ' + st.total + ' frames';
};
window.__reelStatus = () => { const s = window.__reelState; return s ? Object.assign({}, s, { sec: Math.round((Date.now() - s.t0) / 1000) }) : null; };
// 作った mp4 の指定秒のコマを画面右に表示（確認用。__reelPreview(null) で消す）
window.__reelCheck = async (sec) => {
  const v = document.createElement('video'); v.muted = true; v.src = URL.createObjectURL(__reelBlob);
  await new Promise(r => { v.onloadeddata = r; setTimeout(r, 5000); }); v.currentTime = sec; await new Promise(r => { v.onseeked = r; setTimeout(r, 5000); });
  const c = document.createElement('canvas'); c.width = W; c.height = H; c.getContext('2d').drawImage(v, 0, 0);
  let img = document.getElementById('__reelprev'); if (!img) { img = document.createElement('img'); img.id = '__reelprev'; img.style.cssText = 'position:fixed;top:0;right:0;height:100vh;z-index:999999;border:2px solid red'; document.body.appendChild(img); }
  img.src = c.toDataURL('image/jpeg', 0.9); return 'video frame ' + sec + 's';
};
// 投稿画面のファイル欄に動画を入れる（先に ig_render.js の __igOpen() を実行しておく）。
// 注意: 先頭の input[type=file] はプロフィール写真用なので使わない（video/mp4 を受け付ける欄を選ぶ）
window.__reelAttach = async () => {
  const inp = Array.from(document.querySelectorAll('input[type=file]')).find(i => /video\/mp4/.test(i.accept)); if (!inp) return 'no video file input'; if (!window.__reelBlob) return 'no video';
  const dt = new DataTransfer(); dt.items.add(new File([__reelBlob], 'reel.mp4', { type: 'video/mp4' }));
  inp.files = dt.files; inp.dispatchEvent(new Event('change', { bubbles: true })); return 'attached';
};
}
'reel helpers loaded';
