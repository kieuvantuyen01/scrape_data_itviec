import { chromium } from 'playwright-extra';
import stealth from 'puppeteer-extra-plugin-stealth';
import * as cheerio from 'cheerio';
import fs from 'fs';
import pLimit from 'p-limit';

chromium.use(stealth());

const CONFIG = {
  baseUrl: 'https://itviec.com/it-jobs',
  maxPages: null,        // null = scrape tất cả
  outputFile: '../public/itviec-jobs.json',
  cookiesFile: 'itviec-cookies.json',
  stateFile: 'itviec-state.json',  // resume checkpoint; xóa file này để scrape lại từ đầu
  headless: true,       // false khi dev, true khi stable
  detailConcurrency: 3,  // số detail page parse song song
  saveEvery: 5,          // save state sau mỗi N detail jobs
};

const STATE_VERSION = 1;

const sleep = (min, max = min) => new Promise(r => 
  setTimeout(r, min + Math.random() * (max - min))
);

// ============ PARSE HTML FUNCTIONS ============

/**
 * Parse list page → array of job summary
 * Selector có thể đổi theo thời gian, cần update khi cần
 */
function parseJobList(html) {
  const $ = cheerio.load(html);
  const jobs = [];

  $('.job-card').each((_, el) => {
    const $el = $(el);

    const slug = $el.attr('data-search--job-selection-job-slug-value');
    const jobKey = $el.attr('data-job-key');
    if (!slug) return;

    // Title nằm ở <h3>, không phải <a> bên trong
    const $h3 = $el.find('h3[data-search--job-selection-target="jobTitle"]').first();
    const title = $h3.text().trim();
    const url = `https://itviec.com/it-jobs/${slug}`;

    // Company: anchor đến /companies/<slug>
    const $companyA = $el.find('a[href*="/companies/"]').last();
    const company = $companyA.text().trim();
    const companySlug = ($companyA.attr('href') || '').match(/\/companies\/([^?]+)/)?.[1] || '';

    // Salary: .salary div; nếu chưa sign-in hiện "Sign in to view salary"
    let salary = $el.find('.salary').first().text().replace(/\s+/g, ' ').trim();
    if (!salary) {
      const signInText = $el.find('.sign-in-view-salary').first().text().trim();
      salary = signInText || '';
    }

    // Working mode ("At office" / "Hybrid" / "Remote") + location
    // Cả 2 nằm trong block text-rich-grey sau salary
    const infoTexts = $el.find('.text-rich-grey').map((_, n) => $(n).text().trim()).get()
      .filter(t => t && t.length < 80);
    // Bỏ tên company ra khỏi list
    const infoFiltered = infoTexts.filter(t => t !== company);
    const workingMode = infoFiltered.find(t => /office|remote|hybrid/i.test(t)) || '';
    const location = infoFiltered.find(t =>
      /Ho Chi Minh|Ha Noi|Hanoi|Da Nang|Can Tho|Hai Phong|Others/i.test(t)
    ) || '';

    // Tags/skills: .itag - bỏ tag "+N" overflow
    const tags = $el.find('a.itag').map((_, t) => $(t).text().trim()).get()
      .filter(t => t && !/^\+\d+$/.test(t));

    // Posted time: span.small-text.text-dark-grey (ở đầu card)
    const postedTime = $el.find('.small-text.text-dark-grey').first().text()
      .replace(/\s+/g, ' ').trim();

    // Label (HOT / NEW) nếu có
    const label = $el.find('.ilabel').first().text().trim();

    jobs.push({
      jobKey,
      slug,
      title,
      url,
      company,
      companySlug,
      salary: salary || 'Sign in to view salary',
      workingMode,
      location,
      tags,
      postedTime,
      label,
    });
  });

  return jobs;
}

/**
 * Parse detail page → job info đầy đủ
 */
function parseJobDetail(html, baseData) {
  const $ = cheerio.load(html);

  // Scope: main column (excludes "More jobs for you" sidebar)
  const $mainCol = $('.col-xl-8.im-0').first();
  const $scope = $mainCol.length ? $mainCol : $.root();

  const title = $('h1').first().text().trim() || baseData.title;

  // Salary block nằm trong .job-header-info (khi chưa login sẽ là "Sign in to view salary")
  const salary = $('.job-header-info .salary').first().text().replace(/\s+/g, ' ').trim()
    || baseData.salary || '';

  // Extract sections từ h2 → nội dung tới h2 kế tiếp
  const sectionMap = {};
  $scope.find('h2').each((_, h) => {
    const heading = $(h).text().trim();
    if (!heading) return;
    if (/^(More jobs|Make Your|Feedback)/i.test(heading)) return;

    let sib = $(h).next();
    const chunks = [];
    while (sib.length && sib[0].tagName !== 'h2') {
      const lis = sib.find('li');
      if (lis.length) {
        chunks.push(lis.map((_, li) => '- ' + $(li).text().trim().replace(/\s+/g, ' ')).get().join('\n'));
      } else {
        const t = sib.text().trim().replace(/\s+\n/g, '\n').replace(/\n{3,}/g, '\n\n');
        if (t) chunks.push(t);
      }
      sib = sib.next();
    }
    sectionMap[heading] = chunks.join('\n\n').trim();
  });

  // Company info: label/value đều là <div class="col"> cạnh nhau
  const companyInfo = { name: baseData.company };
  const labels = ['Company type', 'Company industry', 'Company size', 'Country', 'Working days', 'Overtime policy'];
  $('div.col').each((_, col) => {
    const text = $(col).text().trim().replace(/\s+/g, ' ');
    if (labels.includes(text)) {
      const val = $(col).next('.col').text().trim().replace(/\s+/g, ' ');
      if (val) companyInfo[text] = val;
    }
  });

  // Skills chỉ lấy trong main column (tránh pollute từ "More jobs for you")
  const mainSkills = $scope.find('a.itag').map((_, t) => $(t).text().trim()).get();
  const skills = [...new Set([...(baseData.tags || []), ...mainSkills])]
    .filter(s => s && !/^\+\d+$/.test(s));

  return {
    ...baseData,
    title,
    salary,
    skills,
    reasons: sectionMap['Top 3 reasons to join us'] || '',
    jobDescription: sectionMap['Job description'] || '',
    requirements: sectionMap['Your skills and experience'] || '',
    benefits: sectionMap["Why you'll love working here"] || '',
    companyInfo,
    scrapedAt: new Date().toISOString(),
  };
}

// ============ SCRAPE FLOW ============

async function setupBrowser() {
  const browser = await chromium.launch({
    headless: CONFIG.headless,
    args: ['--disable-blink-features=AutomationControlled', '--no-sandbox'],
  });

  const contextOptions = {
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    viewport: { width: 1920, height: 1080 },
    locale: 'vi-VN',
    timezoneId: 'Asia/Ho_Chi_Minh',
    extraHTTPHeaders: {
      'Accept-Language': 'vi-VN,vi;q=0.9,en;q=0.8',
    },
  };

  // Reuse cookies nếu có
  if (fs.existsSync(CONFIG.cookiesFile)) {
    contextOptions.storageState = CONFIG.cookiesFile;
    console.log('📂 Loaded cookies từ file');
  }

  const context = await browser.newContext(contextOptions);
  return { browser, context };
}

async function bypassCloudflare(page) {
  const title = await page.title();
  if (title.includes('Just a moment') || title.includes('Cloudflare')) {
    console.log('🛑 Cloudflare challenge, đợi 15s...');
    await sleep(15000);
    // Đợi thêm cho tới khi title đổi
    try {
      await page.waitForFunction(
        () => !document.title.includes('Just a moment'),
        { timeout: 30000 }
      );
    } catch {
      console.log('⚠️ Cloudflare challenge chưa qua, nhưng tiếp tục...');
    }
  }
}

async function detectTotalPages(page) {
  // ITviec thường có pagination ở cuối trang với link đến page cuối
  const total = await page.evaluate(() => {
    const links = document.querySelectorAll('a[href*="page="]');
    let max = 1;
    for (const link of links) {
      const match = link.href.match(/page=(\d+)/);
      if (match) max = Math.max(max, parseInt(match[1]));
    }
    return max;
  });
  return total;
}

async function scrapeListPage(page, pageNum) {
  const url = `${CONFIG.baseUrl}?page=${pageNum}`;
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await bypassCloudflare(page);
  
  try {
    await page.waitForSelector('h3, [class*="job"]', { timeout: 10000 });
  } catch {}

  const html = await page.content();
  
  // DEBUG: lưu page 1 ra file để inspect
//   if (pageNum === 1) {
//     fs.writeFileSync('debug-page1.html', html);
//     console.log('  💾 Saved debug-page1.html');
//   }
  
  return parseJobList(html);
}

async function scrapeJobDetail(context, job) {
  const page = await context.newPage();
  try {
    await page.goto(job.url, { waitUntil: 'domcontentloaded', timeout: 60000 });
    await bypassCloudflare(page);
    const html = await page.content();
    return parseJobDetail(html, job);
  } finally {
    await page.close();
  }
}

// ============ STATE / RESUME ============

function createInitialState() {
  return {
    version: STATE_VERSION,
    phase: 'list',       // 'list' → 'detail' → 'done'
    totalPages: 0,
    allJobs: [],         // list-page summaries (deduped by URL)
    completedPages: [],  // page numbers đã scrape list xong
    detailed: {},        // url → full job detail
    startedAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
  };
}

function loadState() {
  if (!fs.existsSync(CONFIG.stateFile)) return null;
  try {
    const s = JSON.parse(fs.readFileSync(CONFIG.stateFile, 'utf8'));
    if (s.version !== STATE_VERSION) {
      console.log(`⚠️ State file version mismatch (${s.version} ≠ ${STATE_VERSION}), bắt đầu lại`);
      return null;
    }
    return s;
  } catch (err) {
    console.log(`⚠️ State file corrupt (${err.message}), bắt đầu lại`);
    return null;
  }
}

// Atomic write: tmp → rename để tránh corrupt nếu crash giữa chừng
function saveState(state) {
  state.updatedAt = new Date().toISOString();
  const tmp = CONFIG.stateFile + '.tmp';
  fs.writeFileSync(tmp, JSON.stringify(state, null, 2));
  fs.renameSync(tmp, CONFIG.stateFile);
}

// ============ MAIN ============

async function main() {
  console.time('⏱️ Total time');

  // ============ Load or init state ============
  let state = loadState();
  const resuming = !!state;
  if (resuming) {
    const detailDone = Object.keys(state.detailed).length;
    console.log(
      `📂 Resuming: phase=${state.phase}, ` +
      `list ${state.completedPages.length}/${state.totalPages || '?'}, ` +
      `detail ${detailDone}/${state.allJobs.length}`
    );
  } else {
    state = createInitialState();
    console.log('🆕 Bắt đầu scrape mới (không có state file)');
  }

  // Nếu lần trước đã xong → chỉ cần re-materialize output
  if (state.phase === 'done') {
    const finalJobs = Object.values(state.detailed);
    fs.writeFileSync(CONFIG.outputFile, JSON.stringify(finalJobs, null, 2));
    console.log(`✅ State đã done. Re-saved ${finalJobs.length} jobs → ${CONFIG.outputFile}`);
    console.log(`ℹ️ Xóa ${CONFIG.stateFile} để scrape lại từ đầu.`);
    console.timeEnd('⏱️ Total time');
    return;
  }

  const { browser, context } = await setupBrowser();

  // ============ SIGINT: save state trước khi exit ============
  let shuttingDown = false;
  const gracefulExit = async (signal) => {
    if (shuttingDown) return;
    shuttingDown = true;
    console.log(`\n⚠️ Nhận ${signal}, saving state...`);
    try { saveState(state); } catch (err) { console.error('State save fail:', err.message); }
    try { await context.storageState({ path: CONFIG.cookiesFile }); } catch {}
    try { await browser.close(); } catch {}
    console.log('💾 State saved. Chạy lại scraper để resume.');
    process.exit(130);
  };
  process.on('SIGINT', () => gracefulExit('SIGINT'));
  process.on('SIGTERM', () => gracefulExit('SIGTERM'));

  const page = await context.newPage();

  // ============ STEP 1: Warmup (chỉ lần đầu) ============
  if (!resuming) {
    console.log('🏠 Visiting homepage...');
    await page.goto('https://itviec.com/', { waitUntil: 'domcontentloaded', timeout: 60000 });
    await bypassCloudflare(page);
    await sleep(2000, 4000);
  }

  // ============ STEP 2: Detect total pages (nếu chưa có) ============
  if (!state.totalPages) {
    console.log('📊 Detecting total pages...');
    await page.goto(`${CONFIG.baseUrl}?page=1`, { waitUntil: 'domcontentloaded', timeout: 60000 });
    await bypassCloudflare(page);

    let totalPages = await detectTotalPages(page);
    if (CONFIG.maxPages) totalPages = Math.min(totalPages, CONFIG.maxPages);
    state.totalPages = totalPages;
    saveState(state);
  }
  console.log(`📊 Total pages: ${state.totalPages}`);

  // ============ STEP 3: List phase (skip pages đã xong) ============
  if (state.phase === 'list') {
    const completedSet = new Set(state.completedPages);
    const seenUrls = new Set(state.allJobs.map(j => j.url));

    for (let p = 1; p <= state.totalPages; p++) {
      if (completedSet.has(p)) continue;

      console.log(`\n📄 Page ${p}/${state.totalPages}`);
      try {
        const jobs = await scrapeListPage(page, p);
        const newJobs = jobs.filter(j => !seenUrls.has(j.url));
        newJobs.forEach(j => seenUrls.add(j.url));
        state.allJobs.push(...newJobs);
        state.completedPages.push(p);
        saveState(state);
        console.log(`  ✓ Got ${jobs.length} jobs (${newJobs.length} new, total: ${state.allJobs.length})`);
      } catch (err) {
        console.error(`  ❌ Page ${p} failed: ${err.message} (sẽ retry lần resume sau)`);
      }

      if (p % 5 === 0) {
        await context.storageState({ path: CONFIG.cookiesFile });
      }
      await sleep(1500, 3500);
    }

    // Nếu còn page fail → giữ phase='list' để lần resume sau retry.
    // Nếu user muốn bỏ qua page fail và force sang detail: edit state.phase = 'detail' trong file.
    const doneSet = new Set(state.completedPages);
    const failed = [];
    for (let p = 1; p <= state.totalPages; p++) {
      if (!doneSet.has(p)) failed.push(p);
    }
    if (failed.length) {
      console.log(`\n⚠️ ${failed.length} page(s) fail: [${failed.join(',')}]. Chạy lại scraper để retry, hoặc edit ${CONFIG.stateFile} → phase="detail" để bỏ qua.`);
      await page.close();
      await context.storageState({ path: CONFIG.cookiesFile });
      await browser.close();
      console.timeEnd('⏱️ Total time');
      return;
    }

    state.phase = 'detail';
    saveState(state);
  }

  await page.close();
  console.log(`\n📊 Total jobs collected: ${state.allJobs.length}`);

  // ============ STEP 4: Detail phase (skip URLs đã scrape) ============
  if (state.phase === 'detail') {
    const todo = state.allJobs.filter(j => !state.detailed[j.url]);
    const alreadyDone = state.allJobs.length - todo.length;
    console.log(`\n🔍 Scraping ${todo.length} details (${alreadyDone} đã có từ lần trước)`);

    const limit = pLimit(CONFIG.detailConcurrency);
    let done = 0;
    let lastSaveAt = 0;

    const tasks = todo.map(job => limit(async () => {
      if (shuttingDown) return;
      try {
        await sleep(500, 1500);
        const detail = await scrapeJobDetail(context, job);
        state.detailed[job.url] = detail;
      } catch (err) {
        console.error(`  ❌ ${job.title.slice(0, 40)}: ${err.message}`);
        state.detailed[job.url] = job; // fallback: basic data từ list
      }
      done++;
      if (done - lastSaveAt >= CONFIG.saveEvery) {
        saveState(state);
        lastSaveAt = done;
      }
      if (done % 10 === 0) {
        console.log(`  Progress: ${done}/${todo.length} (total done: ${Object.keys(state.detailed).length}/${state.allJobs.length})`);
      }
    }));

    await Promise.all(tasks);
    saveState(state);

    state.phase = 'done';
    saveState(state);
  }

  // ============ STEP 5: Final output + cleanup ============
  await context.storageState({ path: CONFIG.cookiesFile });
  await browser.close();

  const finalJobs = Object.values(state.detailed);
  fs.writeFileSync(CONFIG.outputFile, JSON.stringify(finalJobs, null, 2));
  console.log(`\n✅ Saved ${finalJobs.length} jobs to ${CONFIG.outputFile}`);
  console.log(`ℹ️ ${CONFIG.stateFile} vẫn giữ lại. Xóa nó nếu muốn scrape lại từ đầu.`);
  console.timeEnd('⏱️ Total time');
}

main().catch(err => {
  console.error('💥 Fatal:', err);
  console.log(`ℹ️ State đã được save tới page/job cuối cùng trước lỗi. Chạy lại để resume.`);
  process.exit(1);
});