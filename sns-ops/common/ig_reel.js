// Instagramリール作成ヘルパー（全アカウント共通版。元は数秘のとびら ops/ig_reel.js。spec.brand でブランド名、spec.colors で配色を変えられる）（instagram.com のページ内で javascript_exec に貼って使う）
// 使い方: 1) このファイル全体を実行 → 2) __reelPreview(秒, spec) で描画を確認（任意）→ 3) __reelStart(spec) → __reelStatus().done まで待つ
//        → 4) await __reelCheck(秒) で動画のコマを確認（任意）→ 5) ig_render.js の __igOpen() → await __reelAttach() → 以降は RUNBOOK のリール手順
// （クラウドで見本を作るときは node ops/reel_render.js spec.json out.mp4 。同じ __reelDraw を使う）
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
function mp4(samples, avcC, w, h, fps) {
  const n = samples.length, dur = n; // media timescale = fps, 1 tick per frame
  const ftyp = box('ftyp', new TextEncoder().encode('isom'), u32(512), new TextEncoder().encode('isomiso2avc1mp41'));
  const mdatLen = 8 + samples.reduce((s, x) => s + x.data.length, 0);
  const keys = samples.map((s, i) => s.key ? i + 1 : 0).filter(Boolean);
  const avc1 = box('avc1', new Uint8Array(6), u16(1), new Uint8Array(16), u16(w, h), u32(0x480000, 0x480000, 0), u16(1), new Uint8Array(32), u16(0x18, 0xffff), box('avcC', avcC));
  const stbl = box('stbl',
    full('stsd', 0, 0, u32(1), avc1),
    full('stts', 0, 0, u32(1, n, 1)),
    full('stss', 0, 0, u32(keys.length, ...keys)),
    full('stsc', 0, 0, u32(1, 1, n, 1)),
    full('stsz', 0, 0, u32(0, n, ...samples.map(s => s.data.length))),
    full('stco', 0, 0, u32(1, 0)));
  const mvdur = Math.round(dur * 1000 / fps);
  const moovOf = (off) => {
    const st = stbl.slice(); const dv = new DataView(st.buffer); dv.setUint32(st.length - 4, off); // stco の唯一のオフセット
    return box('moov',
      full('mvhd', 0, 0, u32(0, 0, 1000, mvdur, 0x10000), u16(0x100, 0), u32(0, 0), MATRIX, new Uint8Array(24), u32(2)),
      box('trak',
        full('tkhd', 0, 3, u32(0, 0, 1, 0, mvdur, 0, 0), u16(0, 0, 0, 0), MATRIX, u32(w << 16, h << 16)),
        box('mdia',
          full('mdhd', 0, 0, u32(0, 0, fps, dur), u16(0x55c4, 0)),
          full('hdlr', 0, 0, u32(0), new TextEncoder().encode('vide'), new Uint8Array(12), new TextEncoder().encode('VideoHandler\0')),
          box('minf', full('vmhd', 0, 1, new Uint8Array(8)), box('dinf', full('dref', 0, 0, u32(1), full('url ', 0, 1))), st))));
  };
  const moovLen = moovOf(0).length, off = ftyp.length + moovLen + 8; // faststart: ftyp → moov → mdat
  const mdatHead = new Uint8Array(8); new DataView(mdatHead.buffer).setUint32(0, mdatLen); mdatHead.set([109, 100, 97, 116], 4);
  return new Blob([ftyp, moovOf(off), mdatHead, ...samples.map(s => s.data)], { type: 'video/mp4' });
}
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
    window.__reelBlob = mp4(samples, avcC, W, H, FPS);
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
