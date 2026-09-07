from services.preprocessing import clean_fund_data

def test_clean_fund_data_valid():
    raw_data = {
        "regNo": "12345",
        "navStat": 150000.5,
        "mfName": " صندوق تست ",
        "portfolioStock": 45.5,
        "day30Return": 2.5
    }
    
    cleaned = clean_fund_data(raw_data)
    
    assert cleaned["reg_no"] == 12345
    assert cleaned["name"] == "صندوق تست" # باید فاصله‌های اضافی پاک شده باشد
    assert cleaned["nav_stat"] == 150000.5
    assert cleaned["portfolio_stock"] == 45.5
    assert cleaned["day30_return"] == 2.5

def test_clean_fund_data_nulls_and_outliers():
    raw_data = {
        "regNo": None, # Null ID
        "portfolioStock": 150, # درصد بالای 100
        "portfolioBond": -10,  # درصد زیر 0
    }
    
    cleaned = clean_fund_data(raw_data)
    
    assert cleaned["reg_no"] == 0
    assert cleaned["nav_stat"] == 0.0 # Null باید 0 شود
    assert cleaned["portfolio_stock"] == 100.0 # باید روی 100 قفل شود
    assert cleaned["portfolio_bond"] == 0.0    # باید روی 0 قفل شود
    assert cleaned["name"] == "نامشخص"