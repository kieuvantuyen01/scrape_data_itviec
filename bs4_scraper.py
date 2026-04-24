import requests
import cloudscraper
import time
import random
import re
import os
from bs4 import BeautifulSoup
from utils.constants import base_url
from utils.requests_helper import login, get_headers

def get_company_urls_from_listing(session, headers):
    """Thu thập tất cả URL company từ trang review-company.
    
    Trang listing hiện tại dùng JS button 'See more' nên chỉ
    scrape được các featured companies trên trang đầu tiên
    bằng requests. Để lấy thêm, ta duyệt thêm trang 
    /companies/review-company?page=N
    """
    all_urls = set()
    page = 1
    
    while True:
        url = f'{base_url}/companies/review-company?page={page}'
        print(f'📡 Fetching page {page}: {url}')
        
        response = session.get(url, headers=headers)
        if response.status_code != 200:
            print(f'   ⚠ Status {response.status_code}, stopping.')
            break
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Tìm tất cả company cards (cấu trúc mới: <a class="featured-company" href="...">)
        company_cards = soup.find_all('a', class_='featured-company')
        
        if not company_cards:
            print(f'   No more companies found on page {page}.')
            break
        
        new_count = 0
        for card in company_cards:
            href = card.get('href', '')
            if '/companies/' in href:
                # Chuyển /companies/xxx/review → /companies/xxx
                company_slug = href.replace('/review', '')
                full_url = f'{base_url}{company_slug}'
                if full_url not in all_urls:
                    all_urls.add(full_url)
                    new_count += 1
        
        print(f'   Found {len(company_cards)} cards, {new_count} new. Total: {len(all_urls)}')
        
        if new_count == 0:
            print('   No new companies, stopping pagination.')
            break
        
        page += 1
        time.sleep(random.randint(1, 3))
    
    return list(all_urls)


def get_company_details_bs4(session, headers, company_url):
    """Scrape chi tiết từng company từ trang overview."""
    response = session.get(company_url, headers=headers)
    soup = BeautifulSoup(response.content, 'html.parser')
    details = {}
    
    try:
        # Thử tìm Overview tab và navigate tới
        overview_tab = soup.find("a", {"data-controller": "utm-tracking", "class": "tab-link"})
        if overview_tab and 'overview' in overview_tab.get('href', '').lower():
            overview_url = f"{base_url}{overview_tab['href']}"
            response = session.get(overview_url, headers=headers)
            soup = BeautifulSoup(response.content, 'html.parser')
        
        # Company name: thử h1, h4, hoặc div
        name_tag = (soup.find("h1", class_=re.compile(r'company.*name', re.IGNORECASE)) or
                    soup.find("h4", class_=re.compile(r'company.*name', re.IGNORECASE)) or
                    soup.find("div", class_="company__name"))
        
        if name_tag:
            details['Name'] = name_tag.text.strip()
        
        # Location / City
        city_tag = (soup.find("span", class_=re.compile(r'company.*city', re.IGNORECASE)) or
                    soup.find("div", class_="company__location"))
        if city_tag:
            details['City'] = city_tag.text.strip()
        
        # Company type
        type_tag = soup.find("div", class_="company__type")
        if type_tag:
            details['Type'] = type_tag.text.strip()
        
        # Description
        description_tag = soup.find("div", class_="company__description")
        if description_tag:
            details['Description'] = description_tag.text.strip()

        # General info
        general_info_tag = soup.find("div", class_="company__general-info")
        if general_info_tag:
            details['General Information'] = general_info_tag.text.strip()
        
        # Overview
        overview_tag = soup.find("div", class_="company__overview")
        if overview_tag:
            details['Company Overview'] = overview_tag.text.strip()

        # Key skills
        key_skills_tag = soup.find("div", class_="company__key-skills")
        if key_skills_tag:
            details['Our Key Skills'] = key_skills_tag.text.strip()
        
        # Location (full)
        location_tag = soup.find("div", class_="company__location")
        if location_tag:
            details['Location'] = location_tag.text.strip()
        
        # Why you'll love working here
        love_working_here_tag = soup.find("div", class_="company__love-working-here")
        if love_working_here_tag:
            details["Why You'll Love Working Here"] = love_working_here_tag.text.strip()

        # Star rating
        star_tag = soup.find("span", class_="company__star-rate")
        if star_tag:
            details['Rating'] = star_tag.text.strip()
        
        # URL
        details['URL'] = company_url

    except Exception as e:
        print(f"Error extracting company details: {e}")
    
    return details


def scrape_companies_bs4():
    session = cloudscraper.create_scraper()
    login(session)
    headers = get_headers()
    
    # Debug: lưu HTML để kiểm tra (sẽ upload artifact trong CI)
    debug_dir = 'debug'
    os.makedirs(debug_dir, exist_ok=True)
    
    # Bước 1: Thu thập tất cả company URLs
    print('=' * 50)
    print('📋 Step 1: Collecting company URLs...')
    print('=' * 50)
    company_urls = get_company_urls_from_listing(session, headers)
    
    if not company_urls:
        # Fallback: lưu HTML debug
        response = session.get(f'{base_url}/companies/review-company', headers=headers)
        with open(f'{debug_dir}/companies-page.html', 'wb') as f:
            f.write(response.content)
        print('❌ No company URLs found. Debug HTML saved.')
        return []
    
    print(f'\n✅ Found {len(company_urls)} unique companies')
    
    # Bước 2: Scrape chi tiết từng company
    print('=' * 50)
    print('📋 Step 2: Scraping company details...')
    print('=' * 50)
    
    companies = []
    for i, url in enumerate(company_urls, 1):
        print(f'  [{i}/{len(company_urls)}] {url}')
        try:
            details = get_company_details_bs4(session, headers, url)
            if details and details.get('Name'):
                companies.append(details)
                print(f'    ✅ {details["Name"]}')
            else:
                print(f'    ⚠ No data extracted')
        except Exception as e:
            print(f'    ❌ Error: {e}')
        
        # Be respectful: delay giữa các request
        time.sleep(random.randint(1, 3))
    
    print(f'\n✅ Scraped {len(companies)} companies successfully')
    return companies
