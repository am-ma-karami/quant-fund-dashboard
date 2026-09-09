# ۶. روند توسعه — نقشه راه از روی تاریخچه Git

این سند، مسیر واقعی توسعه پروژه را از روی تاریخچه git بازسازی می‌کند — نه از روی حافظه. دلیل این کار: تاریخچه commitها **مدرک رفتار واقعی توسعه‌دهنده** است، نه ادعای او. ترتیب تصمیم‌ها، سبک commitها، و واکنش به مشکلات، همگی قابل راستی‌آزمایی هستند.

## ۶.۱ روش‌شناسی

- **Conventional Commits**: هر commit با برچسب نوع تغییر (`feat`، `fix`، `refactor`، `perf`، `security`، `chore`، `test`) — این فقط سبک‌نویسی نیست؛ تاریخچه را برای تحلیل «چه نوع کاری در چه مرحله‌ای غالب بوده» قابل جستجو می‌کند.
- **commitهای کوچک و اتمیک**: هر commit یک تغییر معنایی واحد (مثلاً «نرمال‌سازی وزن پرتفوی» جدا از «نگاشت فازی ETF»). نتیجه: هر نقطه از تاریخچه قابل بازگشت است.
- **این سند + `git log` = نقشه راه کامل**: جدول زیر فازها را نشان می‌دهد؛ برای جزئیات دقیق هر قدم: `git log --oneline --date=short`

## ۶.۲ فازهای توسعه (۴ روز، ۸ فاز)

### فاز ۰ — زیرساخت و اثبات کارایی (۱۴ شهریور، ساعت ۰۲:۱۲–۰۳:۱۸)

| Commit | محتوا |
|---|---|
| `chore: setup project structure, docker, and dependencies` | اسکلت پروژه + Docker |
| `feat: add database configuration and SQLAlchemy models` | مدل‌های داده |
| `feat: implement TSETMC client and cron job` | کلاینت منبع داده + زمان‌بند |
| `ui: add responsive Bootstrap dashboard` | UI اولیه |
| `feat: setup FastAPI routes and APScheduler` | روترها + زمان‌بندی |
| `fix: wait for postgres to be healthy` | وابستگی سلامت دیتابیس |
| `feat: add real-time ETF market board` | تابلوی ETF |
| `security: move sensitive db credentials to environment variables` | امنیت credentialها |

**تفکر پشت این فاز:** اول یک **برش عمودی کامل** بساز: داده از منبع واقعی وارد شود، در دیتابیس بنشیند، و روی صفحه دیده شود — هرچند زشت. چرا؟ چون بزرگ‌ترین ریسک پروژه، «ناشناخته بودن API منبع داده» است. اگر در ساعت اول ثابت نشود که داده در دسترس است، هیچ معماری زیبایی ارزش ندارد. به همین دلیل حتی security (env vars) در همان فاز صفر آمد — عادت باید از روز اول باشد، نه بازسازی آخر کار.

### فاز ۱ — معماری‌سازی (۱۴ شهریور، ۱۹:۴۷–۲۳:۲۶)

| Commit | محتوا |
|---|---|
| `refactor: restructure project to modular MVC-like architecture` | شکستن تک‌فایل به ماژول |
| `feat: integrate data preprocessing and cleansing pipeline` | لایه پاک‌سازی |
| `architecture: implement Repository and Provider patterns for DDD and loose coupling` | الگوهای Repository/Provider |
| `test: add comprehensive unit, mock, and integration test suites` | اولین مجموعه تست |

**تفکر پشت این فاز:** برش عمودی جواب داد (داده می‌رسد)؛ حالا زمان ساختاردهی است — **قبل از اینکه کد بزرگ شود**. اصل: «بازسازی ارزان، وقتی انجام شود که هنوز کوچک است». الگوی Repository/Provider انتخابی آگاهانه بود (سند ۱) و بلافاصله تست‌ها آمدند — نه در پایان پروژه.

### فاز ۲ — رابط کاربری و تجربه تحلیلی (۱۵ شهریور، ۱۲:۰۹–۲۰:۰۳)

| Commit | محتوا |
|---|---|
| `feat(ui): implement live updates and ETF detail views` | به‌روزرسانی زنده |
| `feat(ui): add market pulse dashboard and fund screener` | نبض بازار + فیلترنویس |
| `feat: enhance Fund Detail page (Performance, Risk Profile, Volume/AUM)` | صفحه جزئیات کامل |
| `refactor(core): implement observed_at for historical data tracking` | مفهوم «زمان مشاهده» |
| `fix(api): add default timestamps and error handling for charts` | استحکام API |
| `refactor(services): improve data ingestion robustness and provider reliability` | مقاوم‌سازی دریافت |

**تفکر پشت این فاز:** محصول برای کاربر معنا پیدا می‌کند. توجه به ترتیب: اول داده، بعد ساختار، بعد رابط کاربری. و نکته ظریف: در همین فاز، تمایز `observed_at` (زمان ثبت داده در بورس) از `created_at` (زمان ثبت در سیستم ما) برقرار شد — این تمایز مفهومی، بعداً ستون فقرات تحلیل سری زمانی شد.

### فاز ۳ — قابلیت اطمینان و تاریخچه (۱۶ شهریور، ۰۰:۴۳–۰۲:۳۲)

| Commit | محتوا |
|---|---|
| `feat(core): implement infrastructure for sync tracking and caching` | ردیابی سینک + کش |
| `refactor(services): enhance data reliability and implement history backfilling` | بک‌فیل تاریخچه |

**تفکر:** داده لحظه‌ای داریم؛ اما تحلیل مالی به **عمق تاریخی** نیاز دارد (نوسان، شارپ، دراودان با ۲ رکورد محاسبه نمی‌شوند). و هر چرخه سینک باید «قابل ردیابی» باشد — سلامت سیستم باید خودش را نشان دهد، نه اینکه کاربر حدس بزند.

### فاز ۴ — ارتقای بصری‌سازی (۱۶ شهریور، ۱۴:۵۳–۱۶:۰۸)

| Commit | محتوا |
|---|---|
| `feat(ui): upgrade dashboard and fund charts with improved data visualization` | نمودارها |
| `perf(db): optimize fund history upserts and simplify backfill logic` | بهینه‌سازی upsert |
| `feat(ui): enhance ETF premium analysis and fund chart visualization` | تحلیل پریمیوم |

**تفکر:** بعد از اینکه داده عمیق شد، نمودارها باید از آن استفاده کنند. نکته `perf`: upsert سطری → upsert بومی Postgres (`ON CONFLICT`) — بهبود کارایی وقتی که داده واقعی نشان داد مسیر کند است، نه حدس پیشاپیش.

### فاز ۵ — موتور تحلیل (۱۶ شهریور، ۱۶:۳۶–۱۷:۴۶)

| Commit | محتوا |
|---|---|
| `feat(models): expand ETF market data and risk metrics` | اسکیمای ریسک |
| `feat(providers): capture complete ETF market data and history endpoints` | پوشش کامل‌تر منبع |
| `feat(analytics): add ETF premium, returns, and risk metrics engine` | موتور محاسبات |
| `feat(quality): preserve nulls, validate percentages, and track sync coverage` | کیفیت داده |
| `feat(ui): surface ETF premium, fund risk metrics, and data quality` | نمایش به کاربر |

**تفکر:** «پردازش‌های مالی» به‌صورت یک موتور مستقل و تست‌شده ساخته شد (سند ۴) و هم‌زمان، **کیفیت داده** ارتقا یافت — حفظ NULL (نه تبدیل به صفر)، اعتبارسنجی درصدها، و ردیابی پوشش. این سه commit پشت‌سرهم نشان‌دهنده یک اصل است: تحلیل درست فقط روی داده درست ممکن است.

### فاز ۶ — شاخص بازار، متادیتا و نگاشت ETF↔صندوق (۱۶ شهریور، ۲۰:۰۰–۲۰:۵۴)

| Commit | محتوا |
|---|---|
| `feat(core): implement benchmark tracking, instrument metadata, and data quality scoring` | شاخص + متادیتا |
| `fix: normalize portfolio weights to 100%, add 'other' assets class, and implement fuzzy matching for accurate ETF-to-Fund mapping` | نرمال‌سازی + نگاشت فازی |
| `fix: ... and secure quant metrics` | ایمن‌سازی معیارهای کوانت |

**تفکر:** دو حلقه مفقوده تکمیل شد: (۱) **نگاشت ETF به صندوق متناظرش** — داده دو منبع (تابلوی ETF و فهرست صندوق‌ها) باید به هم متصل می‌شدند و تطبیق نام فارسی فازی (`نرمال‌سازی نام` در `preprocessing.py`) این پل را زد؛ (۲) **شاخص کل** برای سنجش بازده مازاد. کشف وزن‌های پرتفوی نامعتبر (جمع ≠ ۱۰۰) و کلاس «سایر» نیز از مشاهده داده واقعی آمد، نه از فرض.

### فاز ۷ — سخت‌سازی در برابر واقعیت (۱۶ شهریور، ۲۱:۲۴ – ۱۷ شهریور، ۰۱:۳۳)

| Commit | محتوا |
|---|---|
| `feat(dashboard): show 30-day history backfill progress per fund` | پیشرفت بک‌فیل در UI |
| `fix: isolate flaky TSETMC endpoints (500 errors) to prevent circuit breaker poisoning and implement graceful degradation` | ایزوله‌سازی endpointهای خراب |
| `fix: restore fetch_fund_history_detail and isolate flaky TSETMC endpoints` | بازیابی endpoint |
| `fix: batch backfill, align ETF history with NAV, and harden TSETMC calls` | بچ‌سازی + هم‌ترازی |
| `fix: show accurate backfill progress with total records and funds with history` | پیشرفت دقیق |

**تفکر:** این فاز پاسخ سیستم به **مشکلات واقعی محیط عملیاتی** است: endpointهای TSETMC خطای 500 تصادفی می‌دادند و کل مدار را مسموم می‌کردند. راه‌حل: ایزوله‌سازی (شکست یک endpoint نباید بقیه را بکشد) + graceful degradation (ادامه با آخرین داده معتبر). همچنین نمایش پیشرفت بک‌فیل در خود داشبورد — کاربر باید ببیند سیستم در چه وضعیتی است.

### فاز ۸ — دیباگ سیستماتیک (۱۷ شهریور — commit `415d8f9`)

این فاز به‌صورت مطالعه موردی در بخش ۶.۴ مستند شده است: رفع ریشه‌ای حلقه بی‌نهایت بک‌فیل که خودش را در لاگ‌ها «موفق» نشان می‌داد — همراه با بازسازی `history_bootstrap.py` (فعال‌سازی جدول state، پارسر تاریخ مقاوم)، تست‌های regression، و اصلاحات Docker (`.dockerignore`، سیاست‌های restart).

### فاز ۹ — اسناد و تکمیل «تصویر بزرگ» (۱۷ شهریور — commitهای `e733582`، `5ebd44a`، `3811f07`)

| Commit | محتوا |
|---|---|
| `docs: add Persian documentation set and README` | مستندات کامل فارسی (این اسناد) |
| `feat(analytics): add benchmark sync and derived series` | جمع‌آوری شاخص کل + توابع خالص دراودان/جریان پول/نرمال‌سازی |
| `feat(ui): benchmark comparison, drawdown, flows, premium series, and risk/return scatter` | پنج نمودار تحلیلی تکمیل‌کننده تصویر بزرگ |

**تفکر:** مستندات **همزمان با توسعه** نوشته شدند، نه در پایان — تا چرایی تصمیم‌ها از حافظه بازسازی نشود (اصلی که در این فازها اعمال شد). سپس حلقه مفقوده تحلیل بسته شد: **شاخص کل** (که از فاز ۶ اسکیما و پیکربندی‌اش آماده بود اما جمع‌آوری نمی‌شد) اکنون هر ۱۵ دقیقه به‌صورت افزایشی sync می‌شود و نمودارهای مشتق — مقایسه با شاخص، منحنی دراودان، جریان پول، نقشه ریسک/بازده و سری روزانه پریمیوم — لایه «تصویر بزرگ» تسک را کامل می‌کنند. تمام محاسبات جدید توابع **خالص** هستند (تست‌پذیر، بدون وابستگی به دیتابیس/شبکه) و مجموعه تست از ۴۵ به ۶۰ رسید.

## ۶.۳ الگوهای تفکر در این نقشه راه

اگر این نقشه راه را یک‌جا ببینیم، پنج الگوی سیستماتیک تکرار شده‌اند:

1. **برش عمودی اول** (فاز ۰): بزرگ‌ترین ریسک را اول از بین ببر — دسترسی به منبع داده.
2. **ساختار قبل از رشد** (فاز ۱): بازسازی وقتی ارزان است، نه وقتی مجبوری.
3. **داده قبل از نمایش** (فاز ۲ و ۳): عمق تاریخی قبل از نمودارهای تحلیلی.
4. **تحلیل فقط روی داده درست** (فاز ۵): موتور محاسبات و تضمین کیفیت داده هم‌زمان ساختند.
5. **سخت‌سازی از تجربه واقعی** (فاز ۶ و ۷): مشکلات واقعی منبع داده و داده واقعی، جهت کار را تعیین کردند — نه فرض‌های تئوریک.

## ۶.۴ مطالعه موردی: دیباگ حلقه بی‌نهایت بک‌فیل

**نشانه:** لاگ‌های worker هر ۱۰ ثانیه «Successfully backfilled history for Fund X» می‌گفتند، اما نوار پیشرفت بک‌فیل در داشبورد صفر می‌ماند.

**مسیر دیباگ (مستند شده برای مصاحبه):**

1. **مشاهده:** لاگ‌ها می‌گفتند موفق؛ داشبورد می‌گفت هیچ‌چیز پیشرفت نکرده. تناقض یعنی یکی از این دو دروغ می‌گوید.
2. **راستی‌آزمایی در دیتابیس:** `SELECT COUNT(*) FROM fund_histories WHERE fund_reg_no = 10872` → فقط ۲ ردیف، در حالی که لاگ ادعای بک‌فیل «۴۳۹۳ رکورد دریافت‌شده» داشت. نتیجه: لاگ دروغ می‌گفت — داده‌ها دریافت می‌شدند اما ذخیره نمی‌شدند.
3. **فرضیه:** پارس تاریخ شکست می‌خورد. تست مستقیم منبع: `curl GetFundInDetail/10872` → `recordDate` به شکل ISO (`"2012-09-23T00:00:00"`) است، در حالی که پارسر فقط `YYYYMMDD` هشت‌رقمی می‌فهمید. هر ۴۰۰۰ رکورد بی‌صدا دور ریخته می‌شد.
4. **چرا بی‌صدا؟** حلقه پارس، رکوردهای نامعتبر را بدون هشدار رد می‌کرد و پیام موفقیت بر اساس «تعداد دریافت‌شده» صادر می‌شد، نه «تعداد ذخیره‌شده».
5. **ریشه عمیق‌تر:** چرا این ماژول تست نداشت؟ چون بک‌فیل جزو «زیرساخت» بود و تست‌ها روی فرمول‌های مالی متمرکز بودند. درس: هر مسیر داده‌ای که «می‌تواند بی‌صدا شکست بخورد» باید تست شود.
6. **رفع:** پارسر واحد برای هر دو قالب تاریخ + فعال‌سازی جدول `history_backfill_state` (که از قبل طراحی شده بود ولی هرگز استفاده نمی‌شد) + ۹ تست regression که این باگ را برای همیشه زندانی می‌کنند.
7. **اثبات:** قبل از رفع: ۶۰۸ ردیف تاریخچه کل سیستم. بعد از رفع: بیش از ۹۰۰۰ ردیف در چند دقیقه و صعودی.

**درس‌های این مطالعه موردی (قابل گفتن در مصاحبه):**
- «موفقیت لاگ‌شده» با «داده ذخیره‌شده» یکی نیست — هر پیام موفقیت باید از اثر واقعی (تعداد ردیف ذخیره‌شده) صادر شود.
- جدول‌های طراحی‌شده‌ولی‌استفاده‌نشده، نشانه نیمه‌کاره بودن هستند — یا استفاده شوند یا حذف.
- تست‌ها حافظه باگ‌ها هستند: هر باگ مهم باید یک تست دائمی داشته باشد.
