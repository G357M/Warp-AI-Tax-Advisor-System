# 🚀 Quick Start Guide
## InfoHub AI Tax Advisor

**Ready to test in 2 minutes!**

---

## ⚡ Super Quick Start

### 1. Start Backend (Terminal 1)
```bash
cd C:\New_Projects\Warp\Warp_INFOHUB.GE
.\backend\venv\Scripts\Activate.ps1
python -m backend.api.main
```
✅ Server running on **http://localhost:8000**

### 2. Start Frontend (Terminal 2)
```bash
cd C:\New_Projects\Warp\Warp_INFOHUB.GE\frontend
npm run dev
```
✅ App running on **http://localhost:3000**

### 3. Test It!
1. Open **http://localhost:3000** in browser
2. Type: `Какой размер НДС в Грузии?`
3. Click `Отправить запрос`
4. 🎉 **See the AI answer with sources!**

---

## 📚 What You Can Do

### Query in 3 Languages
- 🇷🇺 **Russian:** "Какой размер НДС в Грузии?"
- 🇬🇪 **Georgian:** "რა არის დღგ საქართველოში?"
- 🇬🇧 **English:** "What is the VAT rate in Georgia?"

### Use the API Directly
```bash
curl -X POST http://localhost:8000/api/v1/public/query \
  -H "Content-Type: application/json" \
  -d '{"query": "Какой размер НДС в Грузии?", "language": "ru"}'
```

### Check System Health
```bash
curl http://localhost:8000/api/v1/public/health
```

### Browse API Docs
Open **http://localhost:8000/docs** for Swagger UI

---

## 🕷️ Optional: Scrape Real Data

### Ingestion

Ingestion runs on the server via cron (`run_scraper.sh`). The old `/api/v1/scraper/*` API was removed; check the last run at `/admin/system` and the corpus at `/admin/corpus`.

---

## 📖 Documentation

- **Current State:** [docs/CURRENT_STATE.md](docs/CURRENT_STATE.md)
- **Historical reports:** [docs/archive/](docs/archive/README.md)
- **Architecture:** [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- **API Docs:** http://localhost:8000/docs (when running)

---

## ❓ Troubleshooting

### Backend won't start?
- Check PostgreSQL is running
- Check Redis is running
- Activate virtual environment first

### Frontend won't start?
- Run `npm install` first
- Check Node.js version (need 18+)

### No answers?
- Backend must be running first
- Check http://localhost:8000/api/v1/public/health
- Make sure OpenAI API key is in `.env`

### Database issues?
```bash
# Recreate database
psql -U postgres
DROP DATABASE IF EXISTS infohub_ai;
CREATE DATABASE infohub_ai;
\q
```

---

## 🎯 Current Test Data

The system has **5 test documents** about Georgian tax law:
- VAT rate (18%)
- VAT registration threshold
- Corporate tax rate
- Tax law basics
- Simplified taxation

**To add real data:** ingestion runs on the server via cron (`run_scraper.sh`); see "Ingestion" above.

---

## 🔗 Important Links

- **Frontend:** http://localhost:3000
- **Backend API:** http://localhost:8000
- **API Docs:** http://localhost:8000/docs
- **GitHub:** https://github.com/G357M/Warp-AI-Tax-Advisor-System
- **Health Check:** http://localhost:8000/api/v1/public/health

---

**Need help?** Check [docs/CURRENT_STATE.md](docs/CURRENT_STATE.md) for the current production state.

*Let's ship it! 🚀*
