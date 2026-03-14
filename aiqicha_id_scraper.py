import nodriver as uc
import browser_cookie3
import asyncio
import os
import re
import sqlite3
import urllib.parse
import random
import sys

# ============================================================
# SQLite 数据库工具函数
# ============================================================

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "companies.db")

def init_db():
    """初始化数据库，创建表（如果不存在）"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS companies (
            aiqicha_id TEXT PRIMARY KEY,
            company_name TEXT NOT NULL,
            former_name TEXT DEFAULT ''
        )
    """)
    # 为 company_name 和 former_name 建索引，加速查询
    c.execute("CREATE INDEX IF NOT EXISTS idx_company_name ON companies(company_name)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_former_name ON companies(former_name)")
    conn.commit()
    conn.close()
    print(f"[DB] 数据库已就绪: {DB_PATH}")

def check_exists_in_db(search_name):
    """检查搜索名是否已作为 company_name 或 former_name 存在于数据库中"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # 精确匹配 company_name 或 former_name
    c.execute("""
        SELECT aiqicha_id, company_name, former_name FROM companies
        WHERE company_name = ? OR former_name = ?
    """, (search_name, search_name))
    rows = c.fetchall()
    conn.close()
    return rows

def insert_company(aiqicha_id, company_name, former_name=''):
    """插入公司数据，如果 aiqicha_id 已存在则跳过（去重）"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("""
            INSERT OR IGNORE INTO companies (aiqicha_id, company_name, former_name)
            VALUES (?, ?, ?)
        """, (aiqicha_id, company_name, former_name))
        conn.commit()
        inserted = c.rowcount > 0
    except Exception as e:
        print(f"    [DB] 入库失败: {e}")
        inserted = False
    conn.close()
    return inserted

def get_db_stats():
    """获取数据库当前记录数"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM companies")
    count = c.fetchone()[0]
    conn.close()
    return count

# ============================================================
# HTML 解析函数
# ============================================================

def extract_companies_from_html(html_content):
    """从爱企查搜索结果 HTML 中提取公司信息列表"""
    if 'company-list' not in html_content:
        return []
    
    # 按 a.card 分段
    card_blocks = re.split(
        r'(?=<a[^>]*?data-log-title="item-\d+"[^>]*?class="card")',
        html_content
    )
    
    companies = []
    seen_ids = set()
    
    for block in card_blocks:
        # 提取 h3.title 下的 a 标签里的 title 和 data-log-title
        # title 在前
        m = re.search(
            r'class="title"[^>]*>\s*<a[^>]*?title="([^"]+)"[^>]*?data-log-title="(item-\d+)"',
            block
        )
        if not m:
            # data-log-title 在前
            m = re.search(
                r'class="title"[^>]*>\s*<a[^>]*?data-log-title="(item-\d+)"[^>]*?title="([^"]+)"',
                block
            )
            if m:
                cid = m.group(1).replace('item-', '')
                name = m.group(2).strip()
            else:
                continue
        else:
            name = m.group(1).strip()
            cid = m.group(2).replace('item-', '')
        
        if not name or len(name) < 2 or cid in seen_ids:
            continue
        seen_ids.add(cid)
        
        # 提取曾用名
        former_name = ''
        fm = re.search(r'曾用名：</span>\s*<span[^>]*class="legal-txt"[^>]*>(.*?)</span>', block)
        if fm:
            former_name = re.sub(r'<[^>]+>', '', fm.group(1)).strip()
        
        companies.append({
            'name': name,
            'id': cid,
            'former_name': former_name
        })
    
    return companies

# ============================================================
# 主流程
# ============================================================

async def main():
    print("Attempting to load cookies from browsers...")
    print("Note: You may be prompted for your Mac password to access Keychain for Chrome/Safari cookies.")
    
    cookies = []
    for domain in ['aiqicha.com', 'baidu.com']:
        try:
            cj = browser_cookie3.load(domain_name=domain)
            for c in cj:
                cookies.append({
                    'name': c.name,
                    'value': c.value,
                    'domain': c.domain,
                    'path': c.path,
                    'secure': bool(c.secure),
                    'expires': float(c.expires) if c.expires else None
                })
        except Exception as e:
            print(f"Warning: Could not load cookies for {domain} - {e}")
    
    user_data_dir = os.path.abspath("./nodriver_data")
    print(f"Starting nodriver with profile: {user_data_dir}")
    browser = await uc.start(user_data_dir=user_data_dir, sandbox=False)
    
    if cookies:
        print(f"Applying {len(cookies)} cookies to nodriver session...")
        for c in cookies:
            try:
                kwargs = {
                    'name': c['name'],
                    'value': c['value'],
                    'domain': c['domain'],
                    'path': c['path'],
                    'secure': c['secure']
                }
                if c['expires']:
                    kwargs['expires'] = c['expires']
                
                await browser.send(uc.cdp.network.set_cookie(**kwargs))
            except Exception as e:
                pass
    else:
        print("No related cookies found. Will proceed without injecting cookies.")

    # 初始化数据库
    init_db()
    print(f"[DB] 当前数据库已有 {get_db_stats()} 条记录")

    # 读取公司列表
    print("Loading companies from company_names.txt...")
    try:
        with open("company_names.txt", "r", encoding="utf-8") as f:
            companies_to_search = [line.strip() for line in f if line.strip()]
    except Exception as e:
        print(f"Failed to read company_names.txt: {e}")
        return
        
    print(f"Found {len(companies_to_search)} companies to search.")

    skipped = 0
    crawled = 0
    not_found = 0

    for idx, target_company in enumerate(companies_to_search, 1):
        print(f"\n[{idx}/{len(companies_to_search)}] 搜索: {target_company}")
        
        # ========== 先查库，看是否已存在 ==========
        existing = check_exists_in_db(target_company)
        if existing:
            print(f"    -> [跳过] 数据库中已存在 {len(existing)} 条匹配记录:")
            for row in existing[:3]:  # 最多显示3条
                print(f"       ID={row[0]}, 公司={row[1]}, 曾用名={row[2]}")
            skipped += 1
            continue
        
        # ========== 数据库没有，开始爬取 ==========
        encoded_company = urllib.parse.quote(target_company)
        url = f"https://www.aiqicha.com/s?q={encoded_company}&t=0"
        
        try:
            page = await browser.get(url)
            await asyncio.sleep(3)
        except Exception as e:
            print(f"    -> 页面加载失败: {e}")
            continue
            
        found_target = False
        captcha_or_block = False
        
        # 轮询最多 6 次（约 12 秒）
        for i in range(6):
            try:
                curr_url = page.url
                if i == 0:
                    print(f"    -> URL: {curr_url}")
                
                # 被重定向到主页 = 被拦截
                if curr_url.strip('/') == "https://www.aiqicha.com":
                    print("    -> [Warning] 被重定向到主页，可能被拦截。")
                    captcha_or_block = True
                    break

                html_content = await page.get_content()
                
                # 验证码检测
                if '安全验证' in html_content or '验证码' in html_content:
                    captcha_or_block = True
                    break
                
                # 明确无结果 → 秒跳
                if 'class="no-data"' in html_content or '没有找到相关结果' in html_content:
                    print(f"    -> 页面明确提示无结果，跳过。")
                    not_found += 1
                    found_target = True
                    break
                
                # 提取公司列表
                companies = extract_companies_from_html(html_content)
                
                if companies:
                    new_count = 0
                    for comp in companies:
                        inserted = insert_company(comp['id'], comp['name'], comp['former_name'])
                        if inserted:
                            new_count += 1
                    print(f"    -> 找到 {len(companies)} 条结果，新入库 {new_count} 条。")
                    found_target = True
                    crawled += 1
                    break
                
                # 第 5 次仍没结果，保存 HTML 排查
                if i == 5:
                    with open("debug_extraction.html", "w", encoding="utf-8") as f:
                        f.write(html_content)
                    print("    -> [Debug] 已保存页面源码到 debug_extraction.html")

            except Exception as e:
                print(f"    -> Error: {e}")
                
            await asyncio.sleep(2)
            
        if captcha_or_block:
            print("\n[!!!] 警告：可能触发了防爬虫安全验证码！")
            print("脚本已暂停。请在浏览器窗口中**手动完成验证码验证**。")
            print("完成后输入 'y' 继续，'n' 跳过此公司: ")
            def get_input():
                return sys.stdin.readline().strip()
            user_input = await asyncio.to_thread(get_input)
            
            if user_input.lower() == 'y':
                print(f"继续下一个公司...")
            else:
                print(f"跳过 {target_company}...")

        elif not found_target:
            print(f"    -> 超时未找到结果: {target_company}")
            not_found += 1
                
        # 随机休眠 4~8 秒
        sleep_time = random.uniform(4, 8)
        print(f"    -> 休眠 {sleep_time:.1f}s ...")
        await asyncio.sleep(sleep_time)

    # 打印统计
    total_db = get_db_stats()
    print(f"\n{'='*50}")
    print(f"抓取流程全部结束！")
    print(f"  本次搜索: {len(companies_to_search)} 个公司")
    print(f"  跳过(已存在): {skipped}")
    print(f"  爬取成功: {crawled}")
    print(f"  未找到: {not_found}")
    print(f"  数据库总记录: {total_db}")
    print(f"  数据库路径: {DB_PATH}")
    print(f"{'='*50}")
    
    # 保持浏览器打开
    try:
        await asyncio.sleep(600)
    except KeyboardInterrupt:
        pass
    finally:
        browser.stop()

if __name__ == '__main__':
    uc.loop().run_until_complete(main())
