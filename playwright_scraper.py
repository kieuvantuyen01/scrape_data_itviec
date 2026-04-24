import re
import os
import time
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from utils.constants import base_url
from credentials import username, password


def login_playwright(page):
    """Login vào ITviec bằng Playwright."""
    try:
        if username == 'username' or password == 'password':
            print("⚠ No credentials — crawling anonymously.")
            return False

        page.goto(f'{base_url}/sign_in', wait_until='domcontentloaded', timeout=60000)

        # Điền form login
        page.fill('input[name="user[email]"]', username)
        page.fill('input[name="user[password]"]', password)
        page.click('input[type="submit"], button[type="submit"]')
        page.wait_for_load_state('domcontentloaded', timeout=30000)

        if 'sign_in' not in page.url:
            print("✅ Login successful!")
            return True
        else:
            print("⚠ Login failed — crawling anonymously.")
            return False
    except Exception as e:
        print(f"⚠ Login error: {e} — crawling anonymously.")
        return False


def click_see_more_until_done(page, max_clicks=100):
    """Click nút 'See more' cho đến khi không còn."""
    clicks = 0
    while clicks < max_clicks:
        try:
            see_more_btn = page.locator("button[data-action='popular-companies#showMore']")
            if see_more_btn.count() == 0:
                print(f"   No 'See more' button found. Done.")
                break

            # Kiểm tra button có visible không
            if not see_more_btn.first.is_visible():
                print(f"   'See more' button hidden. Done.")
                break

            see_more_btn.first.click()
            clicks += 1

            # Đợi content load
            page.wait_for_timeout(1500)

            if clicks % 10 == 0:
                # Đếm companies hiện tại
                count = page.locator('a.featured-company').count()
                print(f"   Clicked {clicks} times, {count} companies loaded...")

        except Exception as e:
            print(f"   See more click failed: {e}")
            break

    return clicks


def extract_companies_from_html(html_content):
    """Parse HTML và trích xuất tất cả company cards."""
    soup = BeautifulSoup(html_content, 'html.parser')
    companies = []

    cards = soup.find_all('a', class_='featured-company')

    for card in cards:
        company = {}

        # URL
        href = card.get('href', '')
        if href:
            company['URL'] = f'{base_url}{href}'

        # Name
        name_tag = card.find('h4', class_='company__name')
        if name_tag:
            company['Name'] = name_tag.text.strip()

        # Rating
        rating_tag = card.find('span', class_='company__star-rate')
        if rating_tag:
            company['Rating'] = rating_tag.text.strip()

        # City
        city_tag = card.find('span', class_='company__footer-city')
        if city_tag:
            company['City'] = city_tag.text.strip()

        # Footer: jobs & reviews count
        footer = card.find('footer', class_='company__footer')
        if footer:
            for span in footer.find_all('span'):
                text = span.get_text(strip=True)
                if 'job' in text.lower():
                    nums = re.findall(r'\d+', text)
                    if nums:
                        company['Jobs'] = int(nums[0])
                if 'review' in text.lower():
                    nums = re.findall(r'\d+', text)
                    if nums:
                        company['Reviews'] = int(nums[0])

        # Best about
        rated = card.find('div', class_='company__rated')
        if rated:
            rated_text = rated.get_text(separator=' ', strip=True)
            rated_text = re.sub(r'^Best\s+about\s*', '', rated_text, flags=re.IGNORECASE).strip()
            if rated_text:
                company['Best About'] = rated_text

        # Description
        info_div = card.find('div', class_='company__info')
        if info_div:
            header = info_div.find('header')
            footer_tag = info_div.find('footer')
            if header and footer_tag:
                desc_parts = []
                for sibling in header.next_siblings:
                    if sibling == footer_tag:
                        break
                    text = sibling.string if sibling.string else ''
                    text = text.strip()
                    if text:
                        desc_parts.append(text)
                if desc_parts:
                    company['Description'] = ' '.join(desc_parts)

        if company.get('Name'):
            companies.append(company)

    return companies


def scrape_companies_playwright():
    """Scrape TẤT CẢ companies bằng Playwright (click See more)."""
    debug_dir = 'debug'
    os.makedirs(debug_dir, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080}
        )
        page = context.new_page()

        # Login
        print('🔐 Logging in...')
        login_playwright(page)

        # Navigate to companies page
        print(f'\n📡 Loading {base_url}/companies/review-company ...')
        page.goto(f'{base_url}/companies/review-company', wait_until='domcontentloaded', timeout=60000)
        time.sleep(5)

        # Đếm companies ban đầu
        initial_count = page.locator('a.featured-company').count()
        print(f'   Initial: {initial_count} companies')

        # Click "See more" cho đến khi hết
        print('\n🔄 Clicking "See more" to load all companies...')
        clicks = click_see_more_until_done(page)
        print(f'   Clicked "See more" {clicks} times')

        # Đếm tổng companies sau khi load xong
        final_count = page.locator('a.featured-company').count()
        print(f'   Total companies loaded: {final_count}')

        # Lấy HTML
        html_content = page.content()

        # Lưu debug
        with open(f'{debug_dir}/companies-full.html', 'w', encoding='utf-8') as f:
            f.write(html_content)

        browser.close()

    # Parse HTML
    print('\n📋 Extracting company data...')
    companies = extract_companies_from_html(html_content)
    print(f'✅ Extracted {len(companies)} companies')

    # In 10 company đầu tiên
    for i, c in enumerate(companies[:10], 1):
        print(f'   {i}. {c.get("Name", "?")} ({c.get("City", "?")}) ⭐{c.get("Rating", "?")}')
    if len(companies) > 10:
        print(f'   ... and {len(companies) - 10} more')

    return companies
