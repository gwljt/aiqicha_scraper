import sqlite3
import csv
import os
import re

db_path = "companies.db"
txt_path = "company_names.txt"
csv_path = "exported_companies.csv"

def parse_district(text):
    if not text or text == '-' or text == '待抓取详情或注销' or text == '未收录本库':
        return '-', '-', '-'
    
    prov, city, dist = '-', '-', '-'
    
    # 匹配省份/直辖市
    prov_match = re.match(r'^(.*?省|.*?自治区|北京市|天津市|上海市|重庆市)', text)
    if prov_match:
        prov = prov_match.group(1)
        text = text[len(prov):]
    
    # 匹配城市 (直辖市的省和市一样)
    if prov in ['北京市', '天津市', '上海市', '重庆市']:
        city = prov
    else:
        city_match = re.match(r'^(.*?市|.*?自治州|.*?地区|.*?盟)', text)
        if city_match:
            city = city_match.group(1)
            text = text[len(city):]
            
    # 剩下的作为区县
    dist = text if text else '-'
    
    return prov, city, dist

# 读取待查公司名词单
with open(txt_path, 'r', encoding='utf-8') as f:
    names = [line.strip() for line in f if line.strip()]

conn = sqlite3.connect(db_path)
c = conn.cursor()

results = []
for name in names:
    # 1. 优先通过基础名称和曾用名从 companies 表查找 aiqicha_id
    c.execute("SELECT aiqicha_id FROM companies WHERE company_name = ? OR former_name = ?", (name, name))
    row = c.fetchone()
    
    if row:
        a_id = row[0]
        # 2. 从详情表 company_details 取出 对应的代码和地区
        c.execute("SELECT entName, unifiedCode, district FROM company_details WHERE aiqicha_id = ?", (a_id,))
        det_row = c.fetchone()
        
        if det_row:
            ent_name = det_row[0] if det_row[0] and det_row[0] != '-' else name
            unified_code = det_row[1] if det_row[1] else '-'
            district_str = det_row[2] if det_row[2] else '-'
            
            prov, city, dist = parse_district(district_str)
            
            results.append({
                '源搜索名': name,
                '实际企业名': ent_name,
                '统一社会信用代码': unified_code,
                '省': prov,
                '市': city,
                '区': dist
            })
        else:
            results.append({
                '源搜索名': name,
                '实际企业名': '待抓取详情或注销',
                '统一社会信用代码': '-',
                '省': '-', '市': '-', '区': '-'
            })
    else:
        results.append({
            '源搜索名': name,
            '实际企业名': '未收录本库',
            '统一社会信用代码': '-',
            '省': '-', '市': '-', '区': '-'
        })

conn.close()

# 输出为带 BOM 的 UTF-8 格式，防止 Excel 双击打开乱码
with open(csv_path, 'w', encoding='utf-8-sig', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=['源搜索名', '实际企业名', '统一社会信用代码', '省', '市', '区'])
    writer.writeheader()
    writer.writerows(results)

print(f"提取完成！共处理 {len(results)} 条数据，已保存至 {csv_path}")
