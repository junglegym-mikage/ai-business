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
