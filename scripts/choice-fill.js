#!/usr/bin/env node
// 学习通线上作业作答 v2:选择题(单选/多选/判断)+ 连线题
// 用法: node choice-fill.js <课程关键字> <作业名> <答案JSON> [--click] [--submit --yes] [--tag=x]
// 默认只做「暂时保存」；--submit 还必须再加 --yes 才会真的提交(不可逆)
const { chromium } = require('../lib/playwright');
const path = require('path'); const fs = require('fs');
const { COOKIES: COOKIE_FILE, PROFILE, OUT: OUTDIR } = require('../lib/config');

const KEY = process.argv[2], WORK = process.argv[3], ANSFILE = process.argv[4];
const CLICK = process.argv.includes('--click');
const SUBMIT = process.argv.includes('--submit') && process.argv.includes('--yes');
const WANT_SUBMIT = process.argv.includes('--submit') && !process.argv.includes('--yes');
const TAGARG = process.argv.find(a => a.startsWith('--tag='));
const TAG = TAGARG ? TAGARG.split('=')[1] : WORK.replace(/[^\w.-]/g, '_');
const ANS = JSON.parse(fs.readFileSync(ANSFILE, 'utf8'));
const log = (...a) => console.log('[hwa2]', ...a);

const CHOICE = ANS.choice || {};
const LINES = ANS.lines || {};

async function snapshot(wp) {
  return wp.evaluate(({ CHOICE, LINES }) => {
    const qs = [...document.querySelectorAll('[id^="question"]')].filter(e => /^question\d+$/.test(e.id));
    return qs.map((q, qi) => {
      const n = qi + 1;
      const type = q.getAttribute('typename') || '';
      const qid = String(q.id).replace('question', '');
      const hid = document.getElementById('answer' + qid);
      const base = { n, qi, qid, type, hidden: hid ? String(hid.value || '') : null };
      if (/连线题/.test(type)) {
        const rows = [...q.querySelectorAll('.line_answer .line_answer_ct')].map(r => {
          const sp = r.querySelector('[id^="select"]');
          const lo = r.querySelector('.line_option');
          const opts = [...r.querySelectorAll('ul.options li')].map(li => ({ data: li.getAttribute('data'), show: (li.innerText || '').trim() }));
          return { index: r.getAttribute('index'), label: lo ? (lo.innerText || '').trim() : '', picked: sp ? (sp.innerText || '').trim() : '', opts };
        });
        return { ...base, rows, want: LINES[String(n)] || null };
      }
      const opts = [...q.querySelectorAll('[class*="answerBg"]')].map((o, i) => {
        const ds = o.querySelector('[data]');
        return { i, letter: ds ? ds.getAttribute('data') : null, txt: (o.innerText || '').replace(/\s+/g, ' ').trim(), sel: /check|cur|selected|active/i.test(String(o.className || '')) };
      });
      const want = CHOICE[String(n)] || null;
      const matches = [];
      if (want) for (const w of want) {
        const hit = opts.find(it => !matches.some(m => m.i === it.i) && (it.txt.replace(/^[A-Za-z]\s*/, '').trim() === w || it.txt.includes(w)));
        matches.push(hit ? { i: hit.i, txt: hit.txt, letter: hit.letter, sel: hit.sel } : { miss: w });
      }
      return { ...base, optCount: opts.length, matches, allOpts: opts.map(o => ({ i: o.i, txt: o.txt, letter: o.letter, sel: o.sel })) };
    });
  }, { CHOICE, LINES });
}

(async () => {
  if (!fs.existsSync(OUTDIR)) fs.mkdirSync(OUTDIR, { recursive: true });
  const cookies = JSON.parse(fs.readFileSync(COOKIE_FILE, 'utf8'));
  const ctx = await chromium.launchPersistentContext(PROFILE, { channel: 'msedge', headless: true, viewport: { width: 1360, height: 900 } });
  await ctx.addCookies(cookies);
  const page = ctx.pages()[0] || await ctx.newPage();
  await page.goto('https://mooc1.chaoxing.com/mycourse/studentcourse', { timeout: 45000, waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(4500);
  const s = (page.url().match(/[?&]s=([a-f0-9]+)/) || [])[1];
  if (!s) { log('NEED_RELOGIN', page.url().slice(0, 100)); await ctx.close(); process.exit(2); }
  await page.goto('http://mooc1-1.chaoxing.com/visit/interaction?s=' + s, { timeout: 45000, waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(4500);
  const norm = t => (t || '').replace(/[《》]/g, '');
  const target = await page.evaluate(({ k, k2 }) => {
    const list = [...document.querySelectorAll('a[href*="stucoursemiddle"]')].map(a => ({ name: (a.innerText || '').trim().replace(/\s+/g, ' '), href: a.href }));
    return list.find(x => x.name.includes(k)) || list.find(x => x.name.replace(/[《》]/g, '').includes(k2)) || null;
  }, { k: KEY, k2: norm(KEY) });
  if (!target) { log('NO_COURSE', KEY); await ctx.close(); process.exit(3); }
  log('课程:', target.name);
  await page.goto(target.href, { timeout: 45000, waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(5000);
  await page.evaluate(() => { for (const el of [...document.querySelectorAll('a, li, div, span, p')]) { if ((el.innerText || '').trim() === '作业' && el.offsetParent !== null) { el.click(); return; } } });
  let wf = null;
  for (let i = 0; i < 12; i++) { await page.waitForTimeout(1500); wf = page.frames().find(f => f.url().includes('/work/')); if (wf) break; }
  if (!wf) { log('NO_WORK_FRAME'); await ctx.close(); process.exit(4); }
  await wf.waitForTimeout(3000);
  const clicked = await wf.evaluate((workName) => {
    const nodes = [...document.querySelectorAll('div, li, a, span, p, td')];
    let el = nodes.find(e => (e.innerText || '').trim() === workName) || nodes.find(e => (e.innerText || '').trim().startsWith(workName) && (e.innerText || '').length < workName.length + 12);
    if (!el) return 'NOT_FOUND';
    let ct = el;
    for (let i = 0; i < 6 && ct; i++, ct = ct.parentElement) { if (ct.getAttribute('onclick') || ct.tagName === 'A' || String(ct.className || '').match(/task|work|item|list/i)) break; }
    try { ct.click(); return 'OK'; } catch (e) { return 'ERR:' + e.message; }
  }, WORK);
  log('点击作业:', clicked);
  await page.waitForTimeout(9000);
  const wp = ctx.pages().find(p => p.url().includes('dowork')) || (page.url().includes('dowork') ? page : null);
  if (!wp) { log('NO_DOWORK', page.url().slice(0, 120)); await ctx.close(); process.exit(5); }
  await wp.waitForTimeout(4000);
  await wp.evaluate(() => { [...document.querySelectorAll('button, a, div, span')].forEach(el => { if ((el.innerText || '').trim() === '知道了' && el.offsetParent !== null) { try { el.click(); } catch (e) {} } }); });
  await wp.waitForTimeout(1500);
  log('答题页:', wp.url().slice(0, 140));
  const taCount = await wp.evaluate(() => document.querySelectorAll('textarea').length);
  log('textarea:', taCount);

  const before = await snapshot(wp);
  before.forEach(q => {
    if (q.rows) log(`Q${q.n} ${q.type} hidden=${q.hidden} rows=${q.rows.map(r => r.label + '=' + r.picked).join(',')} want=${JSON.stringify(q.want)}`);
    else log(`Q${q.n} ${q.type} hidden=${q.hidden} opts=${q.optCount} => ${q.matches.map(m => m.miss ? '❌' + m.miss : `[${m.letter}]${m.txt.replace(/^[A-Za-z]\s*/, '')}${m.sel ? '*' : ''}`).join(' + ')}`);
  });

  if (CLICK) {
    // 1) 选择题
    const clicks = [];
    before.forEach(q => { if (!q.rows) (q.matches || []).forEach(m => { if (!m.miss && !m.sel) clicks.push({ qid: q.qid, i: m.i, txt: m.txt }); }); });
    const r1 = await wp.evaluate((clicks) => {
      let n = 0, skipped = 0, fail = [];
      clicks.forEach(c => {
        const q = document.getElementById('question' + c.qid);
        if (!q) { fail.push('noq:' + c.qid); return; }
        const o = [...q.querySelectorAll('[class*="answerBg"]')][c.i];
        if (!o) { fail.push('noopt:' + c.qid + '#' + c.i); return; }
        if (/check|cur|selected|active/i.test(String(o.className || ''))) { skipped++; return; }
        o.click(); n++;
      });
      return { clicked: n, skipped, fail };
    }, clicks);
    log('选择题点选:', JSON.stringify(r1));
    await wp.waitForTimeout(1000);

    // 2) 连线题
    const linePlan = [];
    before.forEach(q => { if (q.rows) q.rows.forEach(r => { const want = (q.want || {})[r.label]; if (want) linePlan.push({ qid: q.qid, index: r.index, label: r.label, show: want }); }); });
    const r2 = await wp.evaluate((plan) => {
      const res = [];
      plan.forEach(p => {
        const row = document.querySelector(`.line_answer[data="${p.qid}"] .line_answer_ct[index="${p.index}"]`);
        if (!row) { res.push({ ...p, ok: false, why: 'no-row' }); return; }
        const li = [...row.querySelectorAll('ul.options li')].find(x => (x.innerText || '').trim() === p.show);
        if (!li) { res.push({ ...p, ok: false, why: 'no-li' }); return; }
        // 展开下拉再点,兼容只在下拉可见时绑定事件的实现
        const trigger = row.querySelector('.selectBox p') || row.querySelector('span[id^="select"]');
        if (trigger) { try { trigger.click(); } catch (e) {} }
        const ul = row.querySelector('ul.options'); if (ul) ul.style.display = 'block';
        try { li.click(); } catch (e) {}
        if (ul) ul.style.display = '';
        const sp = row.querySelector('span[id^="select"]');
        res.push({ ...p, ok: true, picked: sp ? (sp.innerText || '').trim() : null, value: sp ? (sp.getAttribute('value') || '') : null });
      });
      return res;
    }, linePlan);
    log('连线题填写:', JSON.stringify(r2, null, 1));
    await wp.waitForTimeout(1200);
  }

  const after = await snapshot(wp);
  let bad = 0;
  after.forEach(q => {
    if (q.rows) {
      const want = q.want || {};
      let ok = true; const picked = {};
      q.rows.forEach(r => { picked[r.label] = r.picked; if (want[r.label] && r.picked !== want[r.label]) ok = false; if (want[r.label] && !r.picked) ok = false; });
      if (!ok) { bad++; log(`⚠️ Q${q.n} 连线未达成 picked=${JSON.stringify(picked)} want=${JSON.stringify(want)} hidden=${q.hidden}`); }
      else log(`✓ Q${q.n} 连线 picked=${JSON.stringify(picked)} hidden=${q.hidden}`);
      return;
    }
    const want = (q.matches || []).filter(m => !m.miss).map(m => m.letter);
    const hv = q.hidden || '';
    const multiChar = want.some(l => l && l.length > 1);
    let ok = (q.matches || []).length > 0 && (q.matches || []).every(m => !m.miss) && want.length > 0;
    if (ok) {
      if (multiChar) ok = want.every(l => hv === l || hv.includes(l));
      else {
        ok = want.every(l => l && hv.includes(l));
        if (ok) { const extra = [...hv].filter(c => !want.includes(c)); if (extra.length) ok = false; }
      }
    }
    if (!ok) { bad++; log(`⚠️ Q${q.n} 未达成 hidden=${JSON.stringify(hv)} want=${want.join(',')}`); }
    else log(`✓ Q${q.n} hidden=${JSON.stringify(hv)}`);
  });
  log('校验: 未达成题数 =', bad, '/', after.length);
  const shot = path.join(OUTDIR, 'hw2-ans-' + TAG + '.png');
  await wp.screenshot({ path: shot, fullPage: true });
  log('截图:', shot);
  fs.writeFileSync(path.join(OUTDIR, 'hw2-ans-' + TAG + '.json'), JSON.stringify({ url: wp.url().slice(0, 200), before, after }, null, 1));

  // 先「暂时保存」，把选择落服务端（提交与否都要保存）
  const saved = await wp.evaluate(() => {
    const t = [...document.querySelectorAll('a, button, div, span')].find(e =>
      (e.innerText || '').trim() === '暂时保存' && e.offsetParent !== null
      && !e.closest('[class*="dialog"], [class*="mask"], .pop'));
    if (t) { t.click(); return 'OK'; }
    return 'NO_BUTTON';
  });
  log('暂时保存:', saved);
  await wp.waitForTimeout(4000);

  if (WANT_SUBMIT) {
    log('⚠ 已指定 --submit 但缺少 --yes，跳过提交（只保存）');
  }
  if (SUBMIT && bad === 0) {
    log('=== 提交 ===');
    await wp.evaluate(() => { const t = [...document.querySelectorAll('a, button, div, span')].find(e => (e.innerText || '').trim() === '提交' && e.offsetParent !== null && !e.closest('[class*="dialog"], [class*="mask"], .pop')); if (t) t.click(); });
    await wp.waitForTimeout(3000);
    const dlg = await wp.evaluate(() => {
      const ds = [...document.querySelectorAll('[class*="dialog"], [class*="mask"], .pop, [class*="alert"]')];
      for (const d of ds) { const b = [...d.querySelectorAll('a, button, div, span')].filter(e => (e.innerText || '').trim() === '提交' && e.offsetParent !== null); if (b.length) { b[0].click(); return 'OK'; } }
      return 'NO_DIALOG';
    });
    log('确认弹窗:', dlg);
    await wp.waitForTimeout(6000);
    const body = await wp.evaluate(() => (document.body ? document.body.innerText : ''));
    log('提交后片段:', body.replace(/\n+/g, ' | ').slice(-500));
    await wp.screenshot({ path: path.join(OUTDIR, 'hw2-submitted-' + TAG + '.png'), fullPage: true });
  } else if (SUBMIT) log('存在未达成题,跳过提交');
  await ctx.close();
})().catch(e => { console.error('FATAL:', e.message); console.error(e.stack); process.exit(1); });
