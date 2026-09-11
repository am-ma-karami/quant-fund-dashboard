-- تبدیل ستون is_etf از رشته ('true'/'false') به boolean.
-- در اسکیمای فعلی، create_all ستون را از ابتدا boolean می‌سازد؛ بنابراین
-- این مهاجرت فقط روی دیتابیس‌های قدیمی (که ستون هنوز متنی است) باید
-- عمل کند. نگهبان، اجرای آن را روی هر دو حالت امن می‌کند.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'funds'
          AND column_name = 'is_etf'
          AND data_type IN ('character varying', 'text')
    ) THEN
        ALTER TABLE funds ALTER COLUMN is_etf DROP DEFAULT;
        ALTER TABLE funds ALTER COLUMN is_etf TYPE BOOLEAN
            USING (COALESCE(LOWER(is_etf) = 'true', FALSE));
        ALTER TABLE funds ALTER COLUMN is_etf SET DEFAULT FALSE;
        ALTER TABLE funds ALTER COLUMN is_etf SET NOT NULL;
    END IF;
END $$;
