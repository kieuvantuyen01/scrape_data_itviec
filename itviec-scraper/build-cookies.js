// Convert raw Cookie header string → Playwright storageState JSON.
//
// Usage:
//   1. Copy từ DevTools (Application → Cookies → Copy giá trị header `Cookie`
//      hoặc từ Network tab → Request Headers → Cookie) vào file cookies-raw.txt
//   2. node build-cookies.js
//   3. Script ghi ra itviec-cookies.json

import fs from 'fs';

const RAW_FILE = 'cookies-raw.txt';
const OUT_FILE = 'itviec-cookies.json';
const DOMAIN = '.itviec.com';

if (!fs.existsSync(RAW_FILE)) {
  console.error(`❌ Không tìm thấy ${RAW_FILE}. Paste raw cookie header vào file này rồi chạy lại.`);
  process.exit(1);
}

const raw = fs.readFileSync(RAW_FILE, 'utf8').trim();

// Split theo "; " nhưng phải careful vì cookie value có thể chứa ";".
// ITviec cookies thực tế không có ";" trong value, nên split đơn giản là đủ.
const pairs = raw.split(/;\s*/);

// Mỗi cookie: chỉ split ở dấu "=" ĐẦU TIÊN (value có thể chứa "=").
const cookies = pairs
  .filter(Boolean)
  .map(pair => {
    const eq = pair.indexOf('=');
    if (eq === -1) return null;
    const name = pair.slice(0, eq).trim();
    const value = pair.slice(eq + 1);
    if (!name) return null;
    return {
      name,
      value,
      domain: DOMAIN,
      path: '/',
      expires: 2000000000,        // ~2033, đủ xa cho session dài
      httpOnly: false,
      secure: true,
      sameSite: 'Lax',
    };
  })
  .filter(Boolean);

const storageState = { cookies, origins: [] };
fs.writeFileSync(OUT_FILE, JSON.stringify(storageState, null, 2));

console.log(`✅ Wrote ${cookies.length} cookies → ${OUT_FILE}`);
console.log(`Names: ${cookies.map(c => c.name).join(', ')}`);
