import requests
import cloudscraper
import time
import random
import re
import os
from bs4 import BeautifulSoup
from utils.constants import base_url
from utils.requests_helper import login, get_headers


def extract_companies_from_page(soup):
    """Trích xuất thông tin company trực tiếp từ cards trên trang listing."""
    companies = []
    
    # Cấu trúc: <a class="featured-company" href="/companies/xxx/review">
    cards = soup.find_all('a', class_='featured-company')
    
    for card in cards:
        company = {}
        
        # URL
        href = card.get('href', '')
        if href:
            company['URL'] = f'{base_url}{href}'
            # Slug: /companies/xxx/review → xxx
            slug = href.replace('/companies/', '').replace('/review', '')
            company['Slug'] = slug
        
        # Name: <h4 class='company__name'>
        name_tag = card.find('h4', class_='company__name')
        if name_tag:
            company['Name'] = name_tag.text.strip()
        
        # Rating: <span class='company__star-rate'>
        rating_tag = card.find('span', class_='company__star-rate')
        if rating_tag:
            company['Rating'] = rating_tag.text.strip()
        
        # City: <span class='company__footer-city'>
        city_tag = card.find('span', class_='company__footer-city')
        if city_tag:
            company['City'] = city_tag.text.strip()
        
        # Footer spans contain jobs count and reviews count
        footer = card.find('footer', class_='company__footer')
        if footer:
            spans = footer.find_all('span')
            for span in spans:
                text = span.get_text(strip=True)
                if 'job' in text.lower():
                    nums = re.findall(r'\d+', text)
                    if nums:
                        company['Jobs'] = int(nums[0])
                if 'review' in text.lower():
                    nums = re.findall(r'\d+', text)
                    if nums:
                        company['Reviews'] = int(nums[0])
        
        # Best about (highly rated field)
        rated = card.find('div', class_='company__rated')
        if rated:
            rated_text = rated.get_text(separator=' ', strip=True)
            # Remove "Best about" prefix
            rated_text = re.sub(r'^Best\s+about\s*', '', rated_text, flags=re.IGNORECASE).strip()
            if rated_text:
                company['Best About'] = rated_text
        
        # Company description (text after header, before footer)
        info_div = card.find('div', class_='company__info')
        if info_div:
            # Text trực tiếp trong company__info (không thuộc header/footer)
            header = info_div.find('header')
            footer_tag = info_div.find('footer')
            if header and footer_tag:
                # Lấy text giữa header và footer
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


def scrape_company_detail(session, headers, company_url):
    """Scrape thêm chi tiết từ trang company riêng (overview)."""
    details = {}
    try:
        response = session.get(company_url, headers=headers)
        if response.status_code != 200:
            return details
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Tìm overview tab
        overview_link = None
        for a in soup.find_all('a'):
            href = a.get('href', '')
            text = a.get_text(strip=True).lower()
            if 'overview' in text and '/companies/' in href:
                overview_link = href
                break
        
        if overview_link:
            if not overview_link.startswith('http'):
                overview_link = f'{base_url}{overview_link}'
            response = session.get(overview_link, headers=headers)
            soup = BeautifulSoup(response.content, 'html.parser')
        
        # Tìm tất cả các thông tin có thể
        # Duyệt tất cả text blocks có class chứa "company__"
        for div in soup.find_all(['div', 'section', 'p'], class_=re.compile(r'company__')):
            cls = ' '.join(div.get('class', []))
            text = div.get_text(separator='\n', strip=True)
            if not text or len(text) < 5:
                continue
            
            if 'overview' in cls:
                details['Company Overview'] = text
            elif 'general-info' in cls:
                details['General Information'] = text
            elif 'key-skills' in cls or 'tech-stack' in cls:
                details['Key Skills'] = text
            elif 'love-working' in cls or 'why-love' in cls:
                details["Why You'll Love Working Here"] = text
            elif 'location' in cls and 'Location' not in details:
                details['Location'] = text
            elif 'description' in cls and 'Description' not in details:
                details['Description'] = text
            elif 'type' in cls:
                details['Type'] = text
        
    except Exception as e:
        print(f'      Detail error: {e}')
    
    return details


def scrape_companies_bs4():
    session = cloudscraper.create_scraper()
    login(session)
    headers = get_headers()
    
    # Debug directory
    debug_dir = 'debug'
    os.makedirs(debug_dir, exist_ok=True)
    
    # ══════════════════════════════════════════════════
    # Step 1: Lấy danh sách companies từ listing page
    # ══════════════════════════════════════════════════
    print('=' * 50)
    print('📋 Step 1: Extracting companies from listing...')
    print('=' * 50)
    
    response = session.get(f'{base_url}/companies/review-company', headers=headers)
    print(f'   Status: {response.status_code}, Size: {len(response.content)} bytes')
    
    # Lưu debug HTML
    with open(f'{debug_dir}/companies-page.html', 'wb') as f:
        f.write(response.content)
    
    soup = BeautifulSoup(response.content, 'html.parser')
    title = soup.find('title')
    print(f'   Page title: {title.text.strip() if title else "(no title)"}')
    
    companies = extract_companies_from_page(soup)
    print(f'   ✅ Extracted {len(companies)} companies from listing page')
    
    for c in companies:
        print(f'      - {c.get("Name", "?")} ({c.get("City", "?")}) ⭐{c.get("Rating", "?")}')
    
    if not companies:
        print('❌ No companies found on listing page.')
        return []
    
    # ══════════════════════════════════════════════════
    # Step 2: Lấy thêm chi tiết từ từng company page
    # ══════════════════════════════════════════════════
    print('\n' + '=' * 50)
    print('📋 Step 2: Enriching with company page details...')
    print('=' * 50)
    
    for i, company in enumerate(companies, 1):
        slug = company.get('Slug', '')
        if not slug:
            continue
        
        detail_url = f'{base_url}/companies/{slug}'
        print(f'  [{i}/{len(companies)}] {company.get("Name", "?")}...')
        
        # Debug: lưu HTML company page đầu tiên
        if i == 1:
            try:
                debug_response = session.get(detail_url, headers=headers)
                with open(f'{debug_dir}/company-detail-sample.html', 'wb') as f:
                    f.write(debug_response.content)
                print(f'      Debug HTML saved for first company')
            except Exception:
                pass
        
        extra = scrape_company_detail(session, headers, detail_url)
        if extra:
            company.update(extra)
            print(f'      ✅ +{len(extra)} fields')
        else:
            print(f'      ℹ  No extra details')
        
        time.sleep(random.randint(1, 3))
    
    # Xoá slug khỏi output (internal use only)
    for c in companies:
        c.pop('Slug', None)
    
    print(f'\n✅ Total: {len(companies)} companies scraped')
    return companies
