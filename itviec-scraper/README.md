# ITviec Scraper + Dashboard

Scrape toàn bộ IT job listings từ [itviec.com/it-jobs](https://itviec.com/it-jobs) bằng Playwright + Cheerio, có stealth mode để bypass Cloudflare. Kèm dashboard HTML để khám phá + xuất report.

## Features

- Crawl full pagination (auto-detect total pages từ DOM).
- Parse list page → summary (title, company, location, salary, skills, posted time, label).
- Parse detail page → reasons to join, job description, requirements, benefits, company info.
- Parallel detail scraping với concurrency configurable (`p-limit`).
- **Resume** sau khi crash/Ctrl+C: state checkpoint sau mỗi list page + mỗi N detail jobs.
- Graceful shutdown với SIGINT/SIGTERM: save state + cookies trước khi exit.
- Cookie persistence để tái sử dụng session (bypass Cloudflare + lấy salary thật).
- Helper `build-cookies.js` convert raw Cookie header → Playwright `storageState`.
- Stealth plugin (`puppeteer-extra-plugin-stealth`) qua `playwright-extra`.
- Dedupe jobs theo URL.
- **Dashboard HTML** (zero-dep): stats, filters, charts, search, salary histogram, posted-freshness buckets, copy-as-markdown report.

## Requirements

- Node.js 18+
- ~1–2 GB RAM (Chromium)

## Install

```bash
npm install
npx playwright install chromium
```

## Quick start

```bash
node scraper.js              # scrape (có resume)
# xem kết quả:
npx serve .                  # mở http://localhost:3000/dashboard.html
```

## Usage

### 1. Scrape

```bash
node scraper.js
```

Output: `itviec-jobs.json`. Checkpoint: `itviec-state.json`. Cookies: `itviec-cookies.json`.

Nếu bị gián đoạn (crash, mạng, Cloudflare, Ctrl+C) → chỉ cần chạy lại lệnh, scraper tự resume từ page/job dở.

Muốn scrape lại từ đầu → xoá `itviec-state.json`.

### 2. Login cookies (để lấy salary thật)

Không login, `salary` luôn là `"Sign in to view salary"`. Để lấy salary thật:

1. Login itviec.com trên Chrome thường (Google OAuth OK).
2. Mở DevTools → Network tab → click bất kỳ request → **copy header `Cookie`**.
3. Paste đè vào `cookies-raw.txt`.
4. Chạy:
   ```bash
   node build-cookies.js
   ```
   Script convert raw cookie string → `itviec-cookies.json` (Playwright `storageState` format).
5. Scraper sẽ tự load cookie này ở lần chạy tiếp.

Cookies ITviec thường sống vài tuần; khi hết hạn (salary quay lại `"Sign in to view salary"`) → lặp lại bước trên.

> **Bảo mật**: `cookies-raw.txt`, `itviec-cookies.json`, `itviec-state.json`, `itviec-jobs.json` đều trong `.gitignore`. Đừng commit hay share — chúng chứa session token của account.

### 3. Dashboard

Dashboard là single file `dashboard.html`, không build, không deps. Vì `fetch('itviec-jobs.json')` bị chặn qua `file://`, cần serve:

```bash
npx serve .
# rồi mở http://localhost:3000/dashboard.html
```

hoặc `python -m http.server 8000`. Fallback: click **Load JSON file…** ở header để chọn file thủ công.

Features: 6 stat cards, filter (search/location/mode/has-salary/HOT), clickable charts (top 15 skills, top 10 companies, working mode breakdown), sort (Recent / Salary ↓ / A–Z), 25/page, click job → modal full detail với reasons/description/requirements/benefits/company info, collapsible **Summary report** section với salary histogram + posted freshness + copy-as-markdown button.

## Config

Chỉnh trong [scraper.js](scraper.js) ở object `CONFIG`:

| Key | Default | Ý nghĩa |
|---|---|---|
| `baseUrl` | `https://itviec.com/it-jobs` | List endpoint |
| `maxPages` | `null` | `null` = tất cả, hoặc số page tối đa |
| `outputFile` | `itviec-jobs.json` | Nơi ghi kết quả cuối |
| `cookiesFile` | `itviec-cookies.json` | Nơi lưu session |
| `stateFile` | `itviec-state.json` | Resume checkpoint; xoá để scrape lại từ đầu |
| `headless` | `true` | `false` khi dev để xem browser |
| `detailConcurrency` | `3` | Số detail page parse song song |
| `saveEvery` | `5` | Save state sau mỗi N detail jobs |

## Resume mechanism

- State file có 3 phase: `list` → `detail` → `done`.
- Sau mỗi list page scrape xong → save state (atomic write: `.tmp` → rename).
- Trong detail phase → save mỗi `saveEvery` jobs + khi nhận SIGINT/SIGTERM.
- Fail một list page → giữ phase `list`, lần chạy sau tự retry các page còn thiếu trước khi chuyển sang detail.
- Muốn bỏ qua page fail → edit `itviec-state.json` và đổi `phase` sang `"detail"` thủ công.

## Output schema

```jsonc
{
  "jobKey": "db9273ac-452e-4463-b6fd-3fcf97c1bb9b",
  "slug": "lead-data-engineer-vnggames-3901",
  "title": "Lead Data Engineer",
  "url": "https://itviec.com/it-jobs/lead-data-engineer-vnggames-3901",
  "company": "VNGGames",
  "companySlug": "vnggames",
  "salary": "1,100 - 2,000 USD",             // "Sign in to view salary" nếu chưa login
  "workingMode": "At office",                 // At office | Hybrid | Remote
  "location": "Ho Chi Minh",
  "tags": ["Data Engineer", "MongoDB", "..."],
  "postedTime": "Posted 30 minutes ago",      // chỉ relative; xem section dưới
  "label": "HOT",                             // HOT | SUPER HOT | ""
  "skills": ["...", "..."],                   // merge from list + detail
  "reasons": "- ...\n- ...\n- ...",
  "jobDescription": "- ...\n- ...",
  "requirements": "- ...\n- ...",
  "benefits": "- ...\n- ...",
  "companyInfo": {
    "name": "VNGGames",
    "Company type": "IT Product",
    "Company industry": "Game",
    "Company size": "501-1000 employees",
    "Country": "Vietnam",
    "Working days": "Monday - Friday",
    "Overtime policy": "No OT"
  },
  "scrapedAt": "2026-04-22T14:37:35.050Z"
}
```

## Files

| File | Purpose | Gitignored? |
|---|---|---|
| [scraper.js](scraper.js) | Main scraper với resume | no |
| [build-cookies.js](build-cookies.js) | Raw Cookie header → storageState | no |
| [dashboard.html](dashboard.html) | Single-file dashboard | no |
| `itviec-jobs.json` | Output cuối | yes |
| `itviec-state.json` | Resume checkpoint | yes |
| `itviec-cookies.json` | Playwright storageState | yes |
| `cookies-raw.txt` | Raw cookie header input | yes |

## Notes

- **Salary parsing**: `"1,100 - 2,000 USD"`, `"500 - 600 USD"`, `"Up to 3,000 USD"` đều parse được. Skip: `"Sign in to view salary"`, `"You'll love it"`, `"Very attractive!!!"`, `"Negotiable"`, `"Competitive"`.
- **Posted time**: ITviec chỉ expose relative text (`"Posted X minutes/hours/days ago"`) — **không có absolute timestamp** trên HTML public (detail page có `datePosted` trong JSON-LD nhưng chỉ precision ngày). Dashboard convert `scrapedAt - relativeDelta` để hiển thị `DD/MM/YYYY HH:mm`; giờ/phút đáng tin khi relative ở mức minute/hour, trở thành ước tính khi relative là days/weeks/months.
- **Scale**: ~43 pages × 20 jobs/page ≈ 860 jobs. List ~2 phút, detail (concurrency 3) ~15–25 phút.
- **Cloudflare**: nếu bị challenge liên tục, giảm `detailConcurrency` xuống `1–2` và tăng delay trong `scrapeJobDetail`.
- **Selector drift**: ITviec có thể đổi DOM. Nếu `parseJobList` trả về 0 jobs, uncomment block DEBUG trong `scrapeListPage` để dump `debug-page1.html` và cập nhật selectors trong [scraper.js](scraper.js).
- **`cf_clearance` cookie** gắn với User-Agent + IP. UA hardcoded trong [scraper.js](scraper.js); nếu browser bạn copy cookie có UA khác → Cloudflare có thể reject, cập nhật `userAgent` trong `setupBrowser()` cho match.

## Tech stack

- [`playwright-extra`](https://github.com/berstend/puppeteer-extra/tree/master/packages/playwright-extra) — Playwright wrapper
- [`puppeteer-extra-plugin-stealth`](https://github.com/berstend/puppeteer-extra/tree/master/packages/puppeteer-extra-plugin-stealth) — anti-bot evasion
- [`cheerio`](https://cheerio.js.org/) — HTML parsing
- [`p-limit`](https://github.com/sindresorhus/p-limit) — concurrency control

Dashboard: vanilla HTML/CSS/JS, zero deps.

## License

ISC. Chỉ dùng cho mục đích học tập / phân tích dữ liệu cá nhân. Tuân thủ [ITviec ToS](https://itviec.com/terms) và `robots.txt`.
