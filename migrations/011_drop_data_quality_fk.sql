-- حذف کلید خارجی از جدول ممیزی data_quality_issues
-- (ایجادشده در 010) — رکورد قرنطینه‌شده عمداً در funds ذخیره نمی‌شود،
-- پس ممیزی باید بتواند بدون وجود ردیف صندوق، تخلف را ثبت کند. در
-- Postgres این کلید خارجی هنگام ثبت تخلفِ صندوقِ تازه‌دیده‌شده خطای
-- یکپارچگی می‌داد و rollback کل چرخه سینک زنده را رقم می‌زد.
ALTER TABLE data_quality_issues
    DROP CONSTRAINT IF EXISTS data_quality_issues_fund_reg_no_fkey;
