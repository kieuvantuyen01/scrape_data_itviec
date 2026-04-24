import requests
import cloudscraper
import time
import random
import re
import os
from bs4 import BeautifulSoup
from utils.constants import base_url
from utils.requests_helper import login, get_headers

def get_total_companies(soup):
    """Tìm tổng số company với nhiều fallback selector."""
    try:
        # Thử selector gốc
        container = soup.find("div", class_="icontainer-sm")
        if container:
            h1 = container.find("h1", class_="imy-6")
            if h1:
                nums = re.findall(r'\d+', h1.text)
                if nums:
                    return int(nums[0])

        # Fallback 1: tìm bất kỳ h1 nào chứa số + "companies"
        for h1 in soup.find_all('h1'):
            if 'compan' in h1.text.lower():
                nums = re.findall(r'\d+', h1.text)
                if nums:
                    print(f"  (found via h1 fallback: '{h1.text.strip()}')") 
                    return int(nums[0])

        # Fallback 2: tìm bất kỳ tag nào chứa pattern "N companies"
        text = soup.get_text()
        match = re.search(r'(\d+)\s+compan', text, re.IGNORECASE)
        if match:
            print(f"  (found via text regex fallback)")
            return int(match.group(1))

        # Fallback 3: đếm trực tiếp số company elements trên trang
        company_cards = soup.find_all('div', class_=re.compile(r'company', re.IGNORECASE))
        if company_cards:
            count = len(company_cards)
            print(f"  (fallback: found {count} company cards on page)")
            return count

        print("⚠ Could not determine total companies count")
        return 0
    except Exception as e:
        print(f"Error getting total number of companies: {e}")
        return 0

def click_see_more(session, headers):
    try:
        response = session.get(f"{base_url}/companies/review-company", headers=headers)
        soup = BeautifulSoup(response.content, 'html.parser')
        see_more_button = soup.find("div", class_="show-more text-center imt-3") or soup.find("span", text="See more")
        if see_more_button:
            see_more_url = see_more_button.parent['href']
            response = session.get(f"{base_url}{see_more_url}", headers=headers)
            return response.content
        else:
            return None
    except Exception as e:
        print(f"Error clicking 'See more': {e}")
        return None

def get_company_details_bs4(session, headers, company_url):
    response = session.get(company_url, headers=headers)
    soup = BeautifulSoup(response.content, 'html.parser')
    details = {}
    
    try:
        overview_tab = soup.find("a", {"data-controller": "utm-tracking", "class": "tab-link"}, text="Overview")
        if overview_tab:
            overview_url = f"{base_url}{overview_tab['href']}"
            response = session.get(overview_url, headers=headers)
            soup = BeautifulSoup(response.content, 'html.parser')
        
        name_tag = soup.find("div", class_="company__name")
        location_tag = soup.find("div", class_="company__location")
        type_tag = soup.find("div", class_="company__type")
        description_tag = soup.find("div", class_="company__description")

        if name_tag:
            details['Name'] = name_tag.text.strip()
        if location_tag:
            details['City'] = location_tag.text.strip()
        if type_tag:
            details['Type'] = type_tag.text.strip()
        if description_tag:
            details['Description'] = description_tag.text.strip()

        general_info_tag = soup.find("div", class_="company__general-info")
        overview_tag = soup.find("div", class_="company__overview")

        if general_info_tag:
            details['General Information'] = general_info_tag.text.strip()
        if overview_tag:
            details['Company Overview'] = overview_tag.text.strip()

        key_skills_tag = soup.find("div", class_="company__key-skills")
        location_tag = soup.find("div", class_="company__location")
        love_working_here_tag = soup.find("div", class_="company__love-working-here")

        if key_skills_tag:
            details['Our Key Skills'] = key_skills_tag.text.strip()
        if location_tag:
            details['Location'] = location_tag.text.strip()
        if love_working_here_tag:
            details['Why You\'ll Love Working Here'] = love_working_here_tag.text.strip()

    except Exception as e:
        print(f"Error extracting company details: {e}")

    return details

def scrape_companies_bs4():
    session = cloudscraper.create_scraper()
    login(session)
    headers = get_headers()
    
    print(f"📡 Fetching {base_url}/companies/review-company ...")
    response = session.get(f'{base_url}/companies/review-company', headers=headers)
    print(f"   Status: {response.status_code}, Size: {len(response.content)} bytes")
    
    # Debug: lưu HTML để kiểm tra (sẽ upload artifact trong CI)
    debug_dir = 'debug'
    os.makedirs(debug_dir, exist_ok=True)
    with open(f'{debug_dir}/companies-page.html', 'wb') as f:
        f.write(response.content)
    print(f"   Debug HTML saved to {debug_dir}/companies-page.html")
    
    soup = BeautifulSoup(response.content, 'html.parser')
    
    # Debug: in title để kiểm tra có bị redirect/block không
    title = soup.find('title')
    print(f"   Page title: {title.text.strip() if title else '(no title)'}")
    
    total_companies = get_total_companies(soup)
    print(f'Total number of companies to scrape: {total_companies}')
    
    companies_scraped = 0
    scraped_company_urls = set()
    companies = []
    
    while companies_scraped < total_companies:
        company_elements = soup.find_all('div', class_='company')
        
        for company in company_elements:
            company_link = company.find('a', class_='company__link')['href']
            if company_link in scraped_company_urls:
                continue
            scraped_company_urls.add(company_link)
            company_url = f'{base_url}{company_link}'
            
            company_name = company.find('div', class_='company__name').text.strip()
            print(f'Scraping {company_name} ({companies_scraped + 1}/{total_companies})')

            try:
                company_details = get_company_details_bs4(session, headers, company_url)
                if company_details:
                    companies.append(company_details)

                print(f"Scraped data for {company_name}")
                
                companies_scraped += 1
                if companies_scraped >= total_companies:
                    break
                
            except Exception as e:
                print(f'Failed to scrape {company_url}: {e}')
            
            time.sleep(random.randint(1, 10))  # Be respectful of the server; add delay between requests
        
        # Click "See more" to load more companies if needed
        if companies_scraped < total_companies:
            response_content = click_see_more(session, headers)
            if response_content:
                soup = BeautifulSoup(response_content, 'html.parser')
            else:
                break
    
    return companies
