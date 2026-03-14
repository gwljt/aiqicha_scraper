import nodriver as uc
import asyncio
import os

async def login():
    print("正在启动浏览器进行登录...")
    user_data_dir = os.path.abspath("./nodriver_data")
    
    # 启动浏览器，使用与爬虫一致的数据目录以保存登录状态
    browser = await uc.start(user_data_dir=user_data_dir, sandbox=False)
    page = await browser.get("https://www.aiqicha.com/")
    
    print("\n" + "="*50)
    print("请在打开的浏览器中完成登录操作 (扫码或短信登录)。")
    print("完成登录后，请回到终端按 Enter 键退出并保存状态。")
    print("="*50 + "\n")
    
    # 保持页面开启，等待用户在终端按回车
    await asyncio.to_thread(input, "登录完成后按回车键退出...")
    
    print("正在关闭浏览器并保存 Session...")
    browser.stop()
    print("登录状态已保存。你现在可以重新运行爬虫脚本了。")

if __name__ == '__main__':
    uc.loop().run_until_complete(login())
