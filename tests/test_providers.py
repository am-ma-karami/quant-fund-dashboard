from services.providers import TSETMCProvider

def test_fetch_funds_by_type_success(mocker):
    # ماک کردن متد requests.get
    mock_get = mocker.patch("services.providers.requests.get")
    
    # تنظیم دیتای بازگشتی فیک (Fake Response)
    mock_response = mocker.Mock()
    mock_response.json.return_value = {"funds": [{"regNo": 1234}]}
    mock_get.return_value = mock_response
    
    provider = TSETMCProvider()
    result = provider.fetch_funds_by_type(6)
    
    # بررسی صحت عملکرد
    mock_get.assert_called_once()
    assert len(result) == 1
    assert result[0]["regNo"] == 1234

def test_fetch_funds_by_type_error(mocker):
    # شبیه‌سازی خطای سرور (TimeOut یا 500)
    mock_get = mocker.patch(
        "services.providers.requests.get",
        side_effect=Exception("Timeout")
    )

    provider = TSETMCProvider()
    result = provider.fetch_funds_by_type(6)

    # وقتی بورس خطا بدهد، کد ما نباید کرش کند، باید لیست خالی برگرداند
    assert result == []