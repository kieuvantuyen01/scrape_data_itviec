import cloudscraper
scraper = cloudscraper.create_scraper()
res = scraper.get('https://itviec.com/it-companies')
print(res.status_code, len(res.text))
if res.status_code == 200:
    with open('debug_it_companies.html', 'w') as f:
        f.write(res.text)
