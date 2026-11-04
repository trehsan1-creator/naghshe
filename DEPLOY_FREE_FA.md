# راه‌اندازی رایگان سروی‌پرو

## ۱) API روی Render

1. مخزن GitHub را در Render به‌عنوان Blueprint وصل کنید و فایل `render.yaml` را انتخاب کنید.
2. سرویس `naghshe-api` با طرح Free ساخته می‌شود؛ پس از Deploy، آدرس شبیه `https://naghshe-api.onrender.com` را از داشبورد Render بردارید.
3. مسیر سلامت را بررسی کنید: `https://<render-host>/api/v1/health`.

**محدودیت مهم داده‌ها:** سرویس رایگان Render فایل‌سیستم پایدار ندارد. این تنظیم پیش‌فرض SQLite برای نمایش و آزمایش است؛ پایگاه‌داده، فایل‌های بارگذاری‌شده و خروجی‌ها ممکن است هنگام راه‌اندازی مجدد، خواب یا استقرار مجدد از بین بروند. برای دادهٔ نقشه‌برداری واقعی، پیش از استفاده یک پایگاه‌دادهٔ پایدار سازگار (PostgreSQL با PostGIS) و فضای ذخیره‌سازی پایدار تنظیم کنید. آدرس DB باید به قالب `postgresql+asyncpg://...` باشد. هرگز دادهٔ کاری مهم را با تنظیم پیش‌فرض نگه ندارید.

سرویس Free ممکن است پس از بی‌کاری به خواب برود و درخواست نخست پس از آن دیر پاسخ دهد.

## ۲) رابط کاربری روی Vercel

1. در Vercel مخزن `trehsan1-creator/naghshe` را Import کنید.
2. **Root Directory** را `frontend` بگذارید؛ Framework: Vite، Build Command: `npm run build`، Output Directory: `dist`.
3. پس از آماده‌شدن Render، در Vercel → Project → Settings → Environment Variables مقدار زیر را برای Production و Preview اضافه کنید:
   - Key: `VITE_API_BASE`
   - Value: `https://<render-host>/api/v1` (بدون اسلش انتهایی)
4. یک‌بار Redeploy کنید. فایل `frontend/vercel.json` مسیرهای برنامهٔ تک‌صفحه‌ای را به `index.html` برمی‌گرداند.

CORS در Blueprint باز است تا آدرس پیش‌نمایش Vercel هم کار کند؛ اگر سرویس را عمومی نمی‌خواهید، پس از Deploy مقدار `SURVEYPRO_CORS_ORIGINS` را به دامنه‌های دقیق Vercel خود محدود کنید.
