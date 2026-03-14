import nodriver as uc
import browser_cookie3
import asyncio
import os
import json
import sqlite3
import random
import sys
from datetime import datetime

# ============================================================
# 全局配置
# ============================================================
ENABLE_STEALTH_HACK = True  # 是否开启防指纹检测与暴力绕过验证码模式

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "companies.db")

def init_detail_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS company_details (
            aiqicha_id TEXT PRIMARY KEY,  -- 爱企查唯一独立ID
            entName TEXT,                 -- 企业名称
            legalPerson TEXT,             -- 法定代表人
            startDate TEXT,               -- 成立日期
            regCapital TEXT,              -- 注册资本
            districtCode TEXT,            -- 行政区划代码
            district TEXT,                -- 所属区域（省市区）
            regAddr TEXT,                 -- 详细注册地址
            scope TEXT,                   -- 经营范围
            qualification TEXT,           -- 纳税人资格/资质
            unifiedCode TEXT,             -- 统一社会信用代码
            openStatus TEXT,              -- 经营状态（如：开业、注销）
            industry TEXT,                -- 所属国标行业
            isClaim TEXT,                 -- 是否已被认领
            telephone TEXT,               -- 联系电话
            email TEXT,                   -- 联系电子邮箱
            insuranceInfo TEXT,           -- 社保人员及参保信息
            prevEntName TEXT,             -- 曾用名
            entType TEXT,                 -- 企业类型（如：有限责任公司）
            regNo TEXT,                   -- 工商注册号
            orgNo TEXT,                   -- 组织机构代码
            taxNo TEXT,                   -- 纳税人识别号
            compNum TEXT,                 -- 分支机构数量
            openTime TEXT,                -- 营业期限
            annualDate TEXT,              -- 最新核准日期
            authority TEXT,               -- 登记机关
            realCapital TEXT,             -- 实缴资本
            paidinCapital TEXT,           -- 实收资本
            orgType TEXT,                 -- 机构类型
            scale TEXT,                   -- 预估人员规模
            shares TEXT,                  -- 股票/上市信息
            licenseNumber TEXT,           -- 工商注册号/许可证号 (licenseNum)
            create_at TEXT,               -- 记录创建时间
            update_at TEXT                -- 记录最后更新时间
        )
    """)
    conn.commit()
    conn.close()

def get_pending_companies():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT aiqicha_id, company_name FROM companies 
        WHERE aiqicha_id NOT IN (SELECT aiqicha_id FROM company_details)
    """)
    rows = c.fetchall()
    conn.close()
    return rows

def insert_company_detail(aiqicha_id, detail_dict):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    def get_str(key):
        val = detail_dict.get(key)
        if isinstance(val, (dict, list)):
            return json.dumps(val, ensure_ascii=False)
        if val is None:
            return ""
        return str(val)

    fields = [
        "entName", "legalPerson", "startDate", "regCapital", "districtCode", "district", "regAddr",
        "scope", "qualification", "unifiedCode", "openStatus", "industry", "isClaim",
        "telephone", "email", "insuranceInfo", "prevEntName", "entType", "regNo",
        "orgNo", "taxNo", "compNum", "openTime", "annualDate", "authority", "realCapital",
        "paidinCapital", "orgType", "scale", "shares", "licenseNumber"
    ]
    
    values = [aiqicha_id] + [get_str(f) for f in fields] + [current_time, current_time]
    
    try:
        c.execute(f"""
            INSERT OR REPLACE INTO company_details (
                aiqicha_id, 
                {', '.join(fields)}, 
                create_at, update_at
            ) VALUES ({', '.join(['?'] * len(values))})
        """, values)
        conn.commit()
        inserted = True
    except Exception as e:
        print(f"    [DB Error] {e}")
        inserted = False
        
    conn.close()
    return inserted

# ============================================================
# Stealth 反爬对抗脚本
# ============================================================

async def apply_stealth_scripts(page):
    """抹除无头浏览器特征，降低被百度识别为爬虫的概率"""
    stealth_js = """
    (() => {
        // 抹除 navigator.webdriver 特征
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        // 伪造随机语言环境
        Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh', 'en'] });
        // 劫持 Chrome 相关变量
        window.chrome = { runtime: {} };
    })();
    """
    await page.evaluate(stealth_js)

async def force_kill_captcha_dom(page):
    """暴力从 DOM 层面移除验证码遮罩层并恢复页面滚动，辅助获取源码"""
    kill_js = """
    (() => {
        const selectors = ['#baiducaptcha-mask', '.ant-modal-mask', '.captcha-modal'];
        selectors.forEach(s => {
            const el = document.querySelector(s);
            if(el) el.remove();
        });
        document.body.style.overflow = 'auto'; // 恢复滚动
    })();
    """
    await page.evaluate(kill_js)

# ============================================================
# 主爬虫流程
# ============================================================

async def main():
    print("加载浏览器 Cookies ...")
    cookies = []
    for domain in ['aiqicha.com', 'baidu.com']:
        try:
            cj = browser_cookie3.load(domain_name=domain)
            for c in cj:
                cookies.append({
                    'name': c.name, 'value': c.value, 'domain': c.domain,
                    'path': c.path, 'secure': bool(c.secure),
                    'expires': float(c.expires) if c.expires else None
                })
        except:
            pass
            
    user_data_dir = os.path.abspath("./nodriver_data")
    browser = await uc.start(user_data_dir=user_data_dir, sandbox=False)
    
    if cookies:
        print(f"向浏览器注入 {len(cookies)} 个 Cookie ...")
        for c in cookies:
            try:
                kwargs = {'name': c['name'], 'value': c['value'], 'domain': c['domain'], 'path': c['path'], 'secure': c['secure']}
                if c['expires']: kwargs['expires'] = c['expires']
                await browser.send(uc.cdp.network.set_cookie(**kwargs))
            except:
                pass

    init_detail_db()
    pending_list = get_pending_companies()
    print(f"\n[任务] 发现 {len(pending_list)} 个企业详情等待抓取。")
    
    if not pending_list:
        print("所有企业详情已抓取完毕！")
        browser.stop()
        return

    page = browser.main_tab
    count_success = 0
    
    for idx, (aiqicha_id, comp_name) in enumerate(pending_list, 1):
        print(f"\n [{idx}/{len(pending_list)}] 开始获取详情: {comp_name} (ID: {aiqicha_id})")
        detail_url = f"https://www.aiqicha.com/company_detail_{aiqicha_id}"
        
        try:
            if ENABLE_STEALTH_HACK:
                await apply_stealth_scripts(page)
                
            await page.get(detail_url)
            await asyncio.sleep(2)  # 给页面一点加载的时间
            
            if ENABLE_STEALTH_HACK:
                await force_kill_captcha_dom(page)
            
            # 使用页面内部直接 Fetch，杜绝 nodriver XHR 拦截可能出现的 body 读取失败
            js_fetch = f"""
            (async () => {{
                try {{
                    let res = await fetch('/detail/basicAllDataAjax?pid={aiqicha_id}', {{
                        headers: {{
                            'accept': 'application/json, text/plain, */*',
                            'x-requested-with': 'XMLHttpRequest'
                        }}
                    }});
                    let text = await res.text();
                    return text;
                }} catch (e) {{
                    return "ERROR:" + e.message;
                }}
            }})();
            """
            
            result_text = await page.evaluate(js_fetch, await_promise=True)
            html_content = await page.get_content()
            curr_url = page.url
            
            # 从 HTML 提取 pageData 兜底
            pageData_result = {}
            idx = html_content.find('window.pageData = {')
            if idx != -1:
                # 简单平衡括号提取 JSON
                count = 0
                for i in range(idx + 18, len(html_content)):
                    if html_content[i] == '{': count += 1
                    elif html_content[i] == '}':
                        count -= 1
                        if count == 0:
                            json_str = html_content[idx + 18 : i + 1]
                            try:
                                pData = json.loads(json_str)
                                pageData_result = pData.get('result', {})
                            except Exception:
                                pass
                            break
                            
            # 尝试解析拿到的结果
            basic_data = {}
            api_success = False
            if result_text and result_text.startswith("{"):
                data = json.loads(result_text)
                if data.get("status") == 0 and "data" in data and "basicData" in data["data"]:
                    basic_data = data["data"]["basicData"]
                    api_success = True
                elif data.get("status") != 0:
                     print(f"    -> [提示] 接口业务返回：{data.get('msg', '未知错误')}")
            
            # 如果 API 失败，或者基础名是 -，我们必须融合 pageData_result
            if not api_success or basic_data.get("entName", "-") == "-":
                if pageData_result:
                    # 互补合并
                    for k, v in pageData_result.items():
                        if k not in basic_data or basic_data[k] in ["", "-", None]:
                            basic_data[k] = v

            # 验证码判断
            if '<title>百度安全验证</title>' in html_content or 'wappass.baidu.com' in curr_url or curr_url.strip('/') == "https://www.aiqicha.com":
                print("\n[!!!] 警告：遭遇百度安全验证/重定向拦截！")
                print("    -> 尝试 Hack: 自动刷新页面尝试绕过...")
                await page.reload()
                await asyncio.sleep(4)
                
                html_content2 = await page.get_content()
                if '<title>百度安全验证</title>' in html_content2 or 'wappass.baidu.com' in page.url:
                    print("    -> [拦截] 刷新无效，服务器已锁定您的 IP / 账号当前请求频率。")
                    print("    -> 由于这是百度企业级 WAF 验证码，强行 Hack 过点选/滑块不仅极慢且需要打码平台或视觉识别模型。")
                    print("    -> [请在浏览器中手动完成图形/滑块验证]。完成后输入 'y' 回车继续: ")
                    await asyncio.to_thread(sys.stdin.readline)
                else:
                    print("    -> [幸运] 刷新成功绕过验证码！(将在下一轮重新尝试获取数据)")
                continue

            if basic_data and basic_data.get("entName", "-") != "-":
                # 取出实际拿到的名称
                ent_name = basic_data.get("entName", "-")
                
                # 入库
                res = insert_company_detail(aiqicha_id, basic_data)
                if res:
                    print(f"    -> [成功] 获取并成功入库！(库内录入公司名: {ent_name})")
                    count_success += 1
                else:
                    print("    -> [失败] 数据解析虽成功，但入库异常。")
            else:
                print(f"    -> [失败] API 及页面变量皆无有效数据，可能已注销、或当前企业无公开信息。")
                    
        except Exception as e:
            print(f"    -> [致命错误] 执行出错: {e}")
            continue

        # 随机休眠防封禁，适当拉长时间防止频繁触发安全验证
        sleep_time = random.uniform(5, 10)
        print(f"    -> 休眠 {sleep_time:.1f} 秒...")
        await asyncio.sleep(sleep_time)

    print(f"\n{'='*50}")
    print("详情数据采集完毕！")
    print(f"本次采集列表总数: {len(pending_list)}")
    print(f"成功入库条数: {count_success}")
    print(f"{'='*50}")

    try:
        await asyncio.sleep(600)
    except KeyboardInterrupt:
        pass
    finally:
        browser.stop()

if __name__ == '__main__':
    uc.loop().run_until_complete(main())
