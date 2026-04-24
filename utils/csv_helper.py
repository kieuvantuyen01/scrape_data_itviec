import csv

def save_to_csv(companies):
    if not companies:
        print("No companies found to save.")
        return

    # Lấy toàn bộ keys từ tất cả các company (thay vì chỉ company đầu tiên)
    all_keys = []
    
    # Định nghĩa thứ tự ưu tiên cho các cột quan trọng
    priority_keys = ['Name', 'URL', 'Rating', 'City', 'Location', 'Jobs', 'Reviews', 'Type', 'Best About', 'Description', 'Company Overview', 'General Information', 'Key Skills', "Why You'll Love Working Here"]
    
    # Gom tất cả các key có xuất hiện
    seen_keys = set()
    for company in companies:
        seen_keys.update(company.keys())
        
    # Thêm các key ưu tiên trước
    for pk in priority_keys:
        if pk in seen_keys:
            all_keys.append(pk)
            
    # Thêm các key còn lại
    for k in seen_keys:
        if k not in all_keys:
            all_keys.append(k)

    with open('companies_detailed.csv', 'w', newline='', encoding='utf-8') as file:
        writer = csv.DictWriter(file, fieldnames=all_keys)
        writer.writeheader()
        writer.writerows(companies)
