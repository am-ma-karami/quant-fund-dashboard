-- ثبت تعداد رکوردهایی که منبع (TSETMC) برای هر صندوق برمی‌گرداند.
-- بدون این فیلد، صندوق‌هایی که در منبع کمتر از ۹۰ رکورد دارند (صندوق‌های
-- تازه‌تأسیس و بازارگردانی) برای همیشه «ناقص» شمرده می‌شوند، در حالی که
-- بک‌فیل هر آنچه منبع دارد را ذخیره کرده است.
-- در اسکیمای تازه، create_all ستون را از ابتدا می‌سازد؛ نگهبان، اجرا را
-- روی هر دو حالت (قدیمی و تازه) امن می‌کند.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'history_backfill_state'
          AND column_name = 'source_count'
    ) THEN
        ALTER TABLE history_backfill_state ADD COLUMN source_count INTEGER;
    END IF;
END $$;
