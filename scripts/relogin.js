// 重新登录:勾选"下次自动登录",登录成功后把 cookie 导出到 cookies.json
const { chromium } = require('../lib/playwright');
const path = require('path');
const fs = require('fs');

const { PROFILE } = require('../lib/config');
const { COOKIES: COOKIE_FILE } = require('../lib/config');

(async () => {
  const ctx = await chromium.launchPersistentContext(PROFILE, {
    channel: 'msedge',
    headless: false,  // 扫码登录必须有头
    viewport: { width: 1280, height: 900 },
  });
  const page = ctx.pages()[0] || await ctx.newPage();

  await page.goto('https://i.chaoxing.com', { timeout: 45000, waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(2500);
  console.log('URL_NOW:', page.url());

  // 勾选"下次自动登录"(若有)
  try {
    const cb = await page.$('input[type="checkbox"]');
    if (cb) {
      await cb.check({ timeout: 3000 }).catch(() => console.log('checkbox check failed, skip'));
      console.log('AUTOLOGIN_CHECKED');
    }
  } catch (e) { console.log('no checkbox'); }

  // 截图二维码
  await page.screenshot({ path: path.join(require('../lib/config').HOME, 'qr.png') });
  console.log('READY_FOR_SCAN');

  // 等待登录完成
  let ok = false;
  for (let i = 0; i < 48; i++) {
    await page.waitForTimeout(5000);
    const u = page.url();
    if (!u.includes('passport2.chaoxing.com') && !u.includes('/login')) { ok = true; break; }
    const bodyTxt = await page.evaluate(() => document.body ? document.body.innerText.slice(0, 150) : '').catch(() => '');
    if (bodyTxt.includes('退出') || bodyTxt.includes('我的课程') || bodyTxt.includes('学习空间')) { ok = true; break; }
  }
  if (!ok) { console.log('SCAN_TIMEOUT'); await ctx.close(); process.exit(2); }

  await page.waitForTimeout(2000);
  const cookies = await ctx.cookies();
  fs.writeFileSync(COOKIE_FILE, JSON.stringify(cookies, null, 2));
  console.log('COOKIES_SAVED:', cookies.length);
  console.log('LOGIN_OK URL:', page.url());

  // 验证:带 cookie 重新开一个 context 访问
  const ctx2 = await chromium.launchPersistentContext(require('../lib/config').PROFILE, {
    channel: 'msedge',
    headless: true,
  });
  await ctx2.addCookies(cookies);
  const p2 = await ctx2.newPage();
  await p2.goto('https://i.chaoxing.com/base', { timeout: 45000, waitUntil: 'domcontentloaded' });
  await p2.waitForTimeout(3000);
  console.log('VERIFY_URL:', p2.url());
  await ctx2.close();

  await ctx.close();
  console.log('DONE');
})().catch(e => { console.error('ERROR:', e.message); process.exit(1); });