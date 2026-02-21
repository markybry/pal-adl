# Streamlit Dashboard Deployment Guide (dashboard_v2)

## 🚀 Quick Deploy to Streamlit Community Cloud (FREE)

### Step 1: Prepare Your Repository

1. **Create a GitHub repository** (if you haven't already):
   - Go to https://github.com/new
   - Name it (e.g., `pal-weekly-checks`)
   - Make it **Public** (required for free Streamlit Cloud)

2. **Push your code** to GitHub:
   ```bash
   cd C:/Users/marky/code/pal-adl
   git init
   git add .
   git commit -m "Deploy dashboard_v2"
   git branch -M main
   git remote add origin https://github.com/YOUR_USERNAME/pal-adl.git
   git push -u origin main
   ```

### Step 2: Deploy to Streamlit Cloud

1. **Go to**: https://share.streamlit.io/
2. **Sign in** with your GitHub account
3. **Click "New app"**
4. **Configure**:
   - Repository: `YOUR_USERNAME/pal-adl`
   - Branch: `main`
   - Main file path: `src/dashboard_v2.py`
5. **Click "Deploy"**

🎉 Your app will be live at: `https://YOUR_USERNAME-pal-adl.streamlit.app`

---

## 🔐 Handling Sensitive Data

**IMPORTANT**: Your `logs.csv` contains resident data. Options:

### Option A: Use Secrets Management (Recommended)
1. Upload `logs.csv` to a secure cloud storage (Google Drive, Dropbox)
2. Use Streamlit secrets to store access credentials
3. Load data from cloud in `src/dashboard_v2.py`

### Option B: Deploy Locally/Privately
- Use Docker + your own server
- Deploy to Azure/AWS with authentication
- Keep on local network only

---

## 🐳 Option 2: Docker Deployment (Self-Hosted)

### Create Dockerfile:
```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

EXPOSE 8501

CMD ["streamlit", "run", "src/dashboard_v2.py", "--server.port=8501", "--server.address=0.0.0.0"]
```

### Build and Run:
```bash
docker build -t pal-dashboard .
docker run -p 8501:8501 pal-dashboard
```

Access at: `http://localhost:8501`

---

## ☁️ Option 3: Cloud Platforms

### Heroku (Free tier available)
```bash
# Install Heroku CLI
# Create setup.sh and Procfile
heroku create your-app-name
git push heroku main
```

### Azure App Service
- Use Azure Portal
- Create Web App
- Deploy from GitHub
- Set Python runtime

### AWS (EC2/Elastic Beanstalk)
- Launch EC2 instance
- Install dependencies
- Run Streamlit
- Configure security groups

---

## 🔒 Security Checklist Before Deploying

- [ ] Remove any hardcoded passwords/API keys
- [ ] Review data sensitivity in `logs.csv`
- [ ] Add authentication if needed
- [ ] Use environment variables for config
- [ ] Enable HTTPS
- [ ] Restrict access to authorized users only

---

## 📝 Notes

## ✅ dashboard_v2 runtime checklist

- Ensure `.env` contains PostgreSQL connection values (`DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`)
- Use `DB_USER=care_app_ro` for the dashboard app (read-only)
- Reserve `care_app_rw` for ETL/import jobs that require writes
- Ensure `fact_resident_domain_score` has current scores for your selected period
- Verify login hash in Streamlit secrets (or use local default for testing only)
- Confirm drilldown navigation works (Layer 1 → Layer 2 → Layer 3)
- Confirm CSV export buttons work on all layers
- Rotate any default DB role passwords before production use

**For CQC compliance**: Ensure any public deployment complies with:
- GDPR data protection requirements
- NHS Data Security and Protection Toolkit (if applicable)
- Information Commissioner's Office (ICO) guidelines
- Resident consent for data use

**Recommendation**: For production use with real resident data, deploy on a **private, authenticated platform** rather than public Streamlit Cloud.
