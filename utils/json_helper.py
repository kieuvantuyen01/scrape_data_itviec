import json

def save_to_json(companies):
    if not companies:
        print("No companies found to save.")
        return

    import os
    os.makedirs('public', exist_ok=True)
    with open('public/companies_detailed.json', 'w', encoding='utf-8') as file:
        json.dump(companies, file, ensure_ascii=False, indent=4)
