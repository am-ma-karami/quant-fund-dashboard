from core.models import Fund, ETFMarket

def test_dashboard_home(client, db_session):
    # فراخوانی API صفحه اصلی
    response = client.get("/")
    
    # بررسی صحت پاسخ و کلماتی که الان واقعاً در صفحه اصلی هستند
    assert response.status_code == 200
    assert "داشبورد مانیتورینگ صندوق‌های سهامی" in response.text
    assert "سهامی (Stock)" in response.text

def test_category_page(client, db_session):
    # 1. اضافه کردن دیتای تستی
    fund = Fund(reg_no=111, name="صندوق تست سهامی", fund_type=6, nav_stat=15000)
    db_session.add(fund)
    db_session.commit()
    
    # 2. فراخوانی API صفحه دسته‌بندی 6 (سهامی)
    response = client.get("/category/6")
    
    # 3. اینجا باید نام صندوق در جدول رندر شده باشد
    assert response.status_code == 200
    assert "صندوق‌های سهامی (Stock)" in response.text
    assert "صندوق تست سهامی" in response.text
    assert "15,000" in response.text # چک کردن فرمت پولی

def test_etf_live_board(client, db_session):
    etf = ETFMarket(ins_code="999", symbol="تست‌یکم", name="صندوق ETF تست", closing_price=10000, price_change=150)
    db_session.add(etf)
    db_session.commit()
    
    response = client.get("/etf-live")
    
    assert response.status_code == 200
    assert "تست‌یکم" in response.text
    assert "10,000" in response.text