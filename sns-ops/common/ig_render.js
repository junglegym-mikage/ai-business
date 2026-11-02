// 数秘のとびら Instagram投稿ヘルパー（instagram.com のページ内で javascript_exec に貼って使う）
// 使い方: 1) このファイル全体を実行 → 2) await __igOpen() → 3) await __igAttach(spec)
//        → 4) await __igToCaption() → 5) 欄を left_click してキャプションを type
//        → 6) __igCaptionValue() === caption を確認 → 7) await __igShare(caption)
//        → 8) プロフィールで __igLatestId() / __igCaption(id) を使いキャプションが入ったか確認（RUNBOOK 参照）
// 投稿画面は2種類ある（2026-10-30確認）。どちらでも動くようにしてある:
//   A) ポップアップ（[role=dialog]、キャプション欄は contenteditable）
//   B) ページ遷移（/create/style/ → /create/details/、キャプション欄は textarea、「次へ」「シェア」は右上の button）
{
window.__sleep = ms => new Promise(r => setTimeout(r, ms));
window.__waitFor = async (fn, ms = 8000) => { const t = Date.now(); while (Date.now() - t < ms) { const v = fn(); if (v) return v; await __sleep(200); } return null; };
const F = { serif: '"Hiragino Mincho ProN","Yu Mincho","Noto Serif JP",serif', sans: '"Hiragino Sans","Hiragino Kaku Gothic ProN","Yu Gothic",sans-serif' };
const C = { paper: '#f3f0e8', ink: '#1d2433', soft: '#5a6276', gold: '#9a7428', seal: '#a83a2c', line: '#cfc8b6' };
function base() {
  const c = document.createElement('canvas'); c.width = 1080; c.height = 1080; const x = c.getContext('2d');
  x.fillStyle = C.paper; x.fillRect(0, 0, 1080, 1080); x.strokeStyle = C.line; x.lineWidth = 3; x.strokeRect(40, 40, 1000, 1000);
  x.lineWidth = 1; x.strokeRect(54, 54, 972, 972); x.textAlign = 'center'; x.textBaseline = 'top'; return [c, x];
}
function t(x, txt, y, size, font, color, weight = '', xpos = 540, align = 'center') { x.font = `${weight} ${size}px ${font}`; x.fillStyle = color; x.textAlign = align; x.fillText(txt, xpos, y); x.textAlign = 'center'; }
function footer(x) { t(x, '数秘のとびら', 940, 34, F.serif, C.ink, 'bold'); t(x, 'プロフのリンクから無料診断', 984, 26, F.sans, C.soft); }
window.__igDraw = (spec) => {
  const [c, x] = base();
  if (spec.type === 'card') {
    t(x, '運命数', 120, 46, F.serif, C.soft, 'bold');
    t(x, String(spec.n), spec.n < 10 ? 170 : 220, spec.n < 10 ? 420 : 330, F.serif, C.gold, 'bold');
    t(x, spec.name, 660, 72, F.serif, C.ink, 'bold'); t(x, spec.kw, 770, 36, F.sans, C.seal);
    x.strokeStyle = C.line; x.lineWidth = 2; x.beginPath(); x.moveTo(480, 840); x.lineTo(600, 840); x.stroke();
  } else if (spec.type === 'aisho') {
    t(x, '保存版', 110, 40, F.sans, C.soft); t(x, '運命数の相性早見表', 165, 76, F.serif, C.ink, 'bold');
    spec.rows.forEach(([n, s], i) => { const y = 300 + i * 66; t(x, String(n), y, 52, F.serif, C.gold, 'bold', 320); t(x, '×', y + 8, 40, F.sans, C.soft, '', 400); t(x, s, y + 2, 48, F.serif, C.ink, 'bold', 450, 'left'); });
  } else if (spec.type === 'year2026') {
    t(x, '誕生月＋誕生日＋2026 を一桁に', 110, 36, F.sans, C.soft); t(x, '2026年、あなたは何の年？', 165, 66, F.serif, C.ink, 'bold');
    ['始まりの年', '育てる年', '楽しむ年', '固める年', '動く年', 'つながる年', '深める年', '実る年', 'しめくくりの年'].forEach((s, i) => { const y = 300 + i * 66; t(x, String(i + 1), y, 52, F.serif, C.gold, 'bold', 350); t(x, s, y + 6, 46, F.serif, C.ink, 'bold', 420, 'left'); });
  } else if (spec.type === 'today') {
    x.fillStyle = C.ink; x.fillRect(0, 0, 1080, 1080); x.strokeStyle = '#3a4357'; x.lineWidth = 3; x.strokeRect(40, 40, 1000, 1000);
    t(x, spec.label, 110, 42, F.sans, '#a9adb8'); t(x, '今日の数字', 175, 56, F.serif, '#ece6d8', 'bold');
    t(x, String(spec.n), spec.n < 10 ? 250 : 290, spec.n < 10 ? 380 : 300, F.serif, '#d2ab5c', 'bold');
    t(x, spec.title, 690, 72, F.serif, '#ece6d8', 'bold');
    const m = spec.msg, cut = m.length > 22 ? m.indexOf('、') + 1 : m.length;
    t(x, m.slice(0, cut), 800, 38, F.sans, '#ece6d8'); if (cut < m.length) t(x, m.slice(cut), 852, 38, F.sans, '#ece6d8');
    t(x, '数秘のとびら', 950, 34, F.serif, '#d2ab5c', 'bold'); t(x, 'プロフのリンクから無料診断', 994, 26, F.sans, '#a9adb8');
    return c;
  } else if (spec.type === 'pair') {
    t(x, '運命数の相性', 120, 46, F.serif, C.soft, 'bold');
    const big = (spec.a >= 10 || spec.b >= 10) ? 230 : 300;
    t(x, String(spec.a), 230, big, F.serif, C.gold, 'bold', 330); t(x, '×', 330, 90, F.serif, C.soft, '', 540); t(x, String(spec.b), 230, big, F.serif, C.gold, 'bold', 750);
    t(x, `${spec.na} × ${spec.nb}`, 610, 50, F.serif, C.ink, 'bold');
    x.strokeStyle = C.gold; x.lineWidth = 2; x.strokeRect(390, 700, 300, 76); t(x, spec.level, 714, 46, F.serif, C.gold, 'bold');
    t(x, '全78通りの相性はプロフのリンクから', 830, 32, F.sans, C.seal);
  }
  footer(x); return c;
};
window.__igOpen = async () => {
  const s = document.querySelector('svg[aria-label="新しい投稿"]'); if (!s) return 'no create button';
  (s.closest('a,[role=button],button') || s).click(); await __sleep(1200);
  const sub = Array.from(document.querySelectorAll('span')).find(e => e.textContent.trim() === '投稿'); if (sub) (sub.closest('a,[role=button],button,[role=link]') || sub).click();
  return (await __waitFor(() => document.querySelector('input[type=file]'))) ? 'ok' : 'no file input';
};
// 「次へ」「シェア」などのボタンを探す（ポップアップがあればその中、無ければページ全体）
const findBtn = (txt) => { const root = document.querySelector('[role=dialog]') || document; return Array.from(root.querySelectorAll('div,span,button')).find(e => e.childElementCount === 0 && e.textContent.trim() === txt) || null; };
const clickText = async (txt, ms = 8000) => { const b = await __waitFor(() => findBtn(txt), ms); if (!b) return false; (b.closest('[role=button],button') || b).click(); await __sleep(1500); return true; };
// キャプション欄（A: contenteditable / B: textarea）
window.__igCaptionBox = () => document.querySelector('[role=dialog] div[contenteditable=true]') || document.querySelector('textarea[aria-label^="キャプション"]');
window.__igCaptionValue = () => { const el = __igCaptionBox(); if (!el) return null; return el.tagName === 'TEXTAREA' ? el.value : el.innerText.replace(/\n$/, ''); };
window.__igAttach = async (spec) => {
  const c = __igDraw(spec); const blob = await new Promise(r => c.toBlob(r, 'image/jpeg', 0.93));
  const inp = document.querySelector('input[type=file]'); if (!inp) return 'no file input';
  const dt = new DataTransfer(); dt.items.add(new File([blob], 'post.jpg', { type: 'image/jpeg' }));
  inp.files = dt.files; inp.dispatchEvent(new Event('change', { bubbles: true }));
  return (await __waitFor(() => findBtn('次へ'), 10000)) ? 'attached' : 'attach failed';
};
// 注意: JS の focus() だけでは Instagram の入力欄に文字が反映されず、キャプション空欄で投稿されることがある。
// __igToCaption の後は必ず computer の left_click でキャプション欄を実際にクリックしてから type すること。
// 欄の位置は screenshot で確認する（CSSピクセルとスクリーンショットの座標は一致しないことがある）。
window.__igToCaption = async () => {
  for (let i = 0; i < 3 && !__igCaptionBox(); i++) { if (!(await clickText('次へ'))) break; await __waitFor(() => __igCaptionBox(), 3000); }
  return __igCaptionBox() ? 'caption ready（欄をクリックしてから入力）' : 'no caption box';
};
// expected を渡すと、欄の中身が一致しないときはシェアしない（空欄投稿の防止）
window.__igShare = async (expected) => {
  if (expected != null) { const v = __igCaptionValue(); if (v !== expected) return 'caption mismatch（シェアしていません）: ' + (v == null ? 'no box' : v.length + '/' + expected.length + '文字'); }
  if (!(await clickText('シェア'))) return 'no share button';
  const ok = await __waitFor(() => /シェアされました|シェアしました|投稿されました/.test(document.body.innerText) || !/\/create\//.test(location.pathname) && !document.querySelector('[role=dialog]'), 30000);
  return ok ? 'shared' : 'not confirmed';
};
// 投稿後の確認: 公開ページのキャプションを読む（id は投稿の /p/<id>/）。空なら '(empty)'。
window.__igCaption = async (id) => { const h = await fetch('/p/' + id + '/', { cache: 'no-store' }).then(r => r.text()); const m = h.match(/<meta property="og:description" content="([^"]*)"/); const d = document.createElement('textarea'); d.innerHTML = m ? m[1] : ''; const v = d.value, i = v.indexOf(': "'); return i < 0 ? '(empty)' : v.slice(i + 3, v.lastIndexOf('"')); };
// プロフィールページで最新投稿の id を返す
window.__igLatestId = async () => { const a = await __waitFor(() => document.querySelector('a[href*="/p/"]')); return a ? a.getAttribute('href').split('/p/')[1].replace('/', '') : null; };
// 投稿ページ（/p/<id>/）でキャプション編集画面を開く。開いたら欄を left_click → type → 「完了」を left_click。
window.__igOpenEdit = async () => { const o = await __waitFor(() => document.querySelector('svg[aria-label="その他のオプション"]')); if (!o) return 'no options'; (o.closest('[role=button],button') || o).click(); await __sleep(1000); const e = Array.from(document.querySelectorAll('button,[role=button]')).find(b => b.textContent.trim() === '編集'); if (!e) return 'no edit'; e.click(); return (await __waitFor(() => document.querySelector('[role=dialog] div[contenteditable=true]'))) ? 'edit open' : 'no caption box'; };
window.__igAccount = () => Array.from(document.querySelectorAll('a[href^="/"]')).map(a => a.getAttribute('href')).filter(h => /^\/[a-z0-9._]+\/$/.test(h) && !/^\/(explore|reels|notifications|direct)\/$/.test(h))[0] || null;
}
'ig helpers loaded';
