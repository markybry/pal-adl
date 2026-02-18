# Care Analytics System

**Risk Intelligence & Audit Layer for Care Log Analytics**

---

## 🎯 System Overview

This is a **risk intelligence and audit layer** built on top of exported care logs. It provides:

- **Dual Risk Scoring**: Care Risk Score (CRS) + Documentation Compliance Score (DCS)
- **Three-Layer Dashboard**: Executive Grid → Client View → Resident Deep Dive
- **Star Schema Database**: Scalable architecture supporting multiple clients
- **Audit-Ready**: Transparent calculations with full traceability

---

## 📁 Project Structure

```
pal-adl/
├── src/                    # Python source code
│   ├── scoring_engine.py
│   ├── dashboard_queries.py
│   ├── dashboard.py
│   └── weeklyCareLogChecks.py
│
├── database/               # Database files
│   ├── schema.sql
│   ├── seed_company.sql
│   └── migrations/
│
├── tests/                  # Test files
│   └── test_scoring_engine.py
│
├── docs/                   # Documentation
│   ├── SYSTEM_DESIGN.md
│   ├── DESIGN_COMPLETE.md
│   ├── IMPLEMENTATION_ROADMAP.md
│   ├── QUICK_START.md
│   ├── DEPLOYMENT.md
│   └── PASSWORD_SETUP.md
│
├── config/                 # Configuration
│   ├── secrets.toml.example
│   └── generate_password.py
│
├── requirements.txt
├── Dockerfile
└── run_dashboard.bat
```

---

## 📚 Documentation

### New System Design (February 2026)

**Start here**:
- 📋 **[DESIGN_COMPLETE.md](docs/DESIGN_COMPLETE.md)** - Overview of the complete system
- 📐 **[SYSTEM_DESIGN.md](docs/SYSTEM_DESIGN.md)** - Detailed design specification (140+ pages)
- 🚀 **[IMPLEMENTATION_ROADMAP.md](docs/IMPLEMENTATION_ROADMAP.md)** - Step-by-step migration guide

**Implementation Files**:
- 🗄️ **[schema.sql](database/schema.sql)** - PostgreSQL star schema DDL
- 🏢 **[seed_company.sql](database/seed_company.sql)** - Company/client seed data template
- 🧮 **[scoring_engine.py](src/scoring_engine.py)** - Dual scoring system (CRS + DCS)
- 📊 **[dashboard_queries.py](src/dashboard_queries.py)** - SQL query builder for all layers
- ✅ **[test_scoring_engine.py](tests/test_scoring_engine.py)** - Complete test suite (31 tests)

### Current System (Legacy)

- 📱 **[dashboard.py](src/dashboard.py)** - Current Streamlit dashboard (CSV-based)
- 🔍 **[weeklyCareLogChecks.py](src/weeklyCareLogChecks.py)** - Current analysis logic
- 🔐 **[PASSWORD_SETUP.md](docs/PASSWORD_SETUP.md)** - Authentication configuration

---

## 🚀 Quick Start

### Current System (CSV-based)

```bash
streamlit run src/dashboard.py
```

### New System (After Migration)

See [IMPLEMENTATION_ROADMAP.md](docs/IMPLEMENTATION_ROADMAP.md) for complete setup instructions.

---

## 🔐 Security

**Password Protected** - Dashboard requires authentication to access sensitive resident data.

- **Default password:** `admin123` (⚠️ Change immediately!)
- See [PASSWORD_SETUP.md](docs/PASSWORD_SETUP.md) for configuration
---

## ✨ Key Features

### New System Design

**Dual Scoring Framework**:
- **Care Risk Score (CRS)**: Refusal frequency + Gap analysis + Dependency trends
- **Documentation Compliance Score (DCS)**: Completeness vs expected frequencies
- Fixed thresholds (GREEN/AMBER/RED) with no drift

**Three-Layer Dashboard**:
1. **Executive Grid**: Client × Domain matrix with traffic lights
2. **Client View**: Resident breakdown with trend analysis
3. **Resident Deep Dive**: Event timeline with full score explanations

**Star Schema Database**:
- Multi-client support
- Historical scoring (7, 14, 30 day windows)
- Pre-aggregated for performance (<1s queries)

### Current System

- 📊 **Interactive Filters**: Date ranges, ADL domains, risk levels
- 🎯 **Risk-Based Overview**: RED/AMBER/GREEN assessments
- 📋 **Domain Analysis**: Deep dive into each ADL category
- 👤 **Resident Tabs**: Individual resident views with detailed metrics
- 📈 **Visual Analytics**: Charts showing assistance level breakdowns

---

## 📊 Scoring Logic

### Fixed Thresholds (No Drift)

**Refusals**:
- 0-1 refusals: GREEN
- 2-3 refusals: AMBER (monitoring required)
- 4+ refusals: RED (immediate review)

**Documentation Compliance**:
- 90-100%: GREEN (compliant)
- 60-89%: AMBER (gaps in recording)
- <60%: RED (non-compliant)

**Time Gaps**: Domain-specific thresholds
- Toileting: 12h amber, 24h red
- Oral Care: 16h amber, 24h red
- Washing/Bathing: 24h amber, 48h red
- Dressing: 24h amber, 48h red
- Grooming: 48h amber, 96h red

**Dependency Trends**: Detected when assistance level increases over baseline

---

## 🏗️ Architecture

### Current System
```
logs.csv → pandas → weeklyCareLogChecks.py → dashboard.py
```

### New System
```
logs.csv → ETL → PostgreSQL (star schema) → scoring_engine.py → 
fact_resident_domain_score → dashboard v2 (3 layers)
```

---

## 🧪 Testing

Run the complete test suite:

```bash
python test_scoring_engine.py
```

Expected output:
```
Ran 31 tests in 0.004s
✅ ALL TESTS PASSED - Scoring engine is working correctly!
```

---

## 📈 Migration Path

**Phase 1: Database Setup** (Week 1)
- Install PostgreSQL
- Run `database/schema.sql`
- Populate dimensions

**Phase 2: Data Import** (Week 1-2)
- ETL CSV → fact_adl_event
- Calculate initial scores
- Validate against current system

**Phase 3: Dashboard** (Week 3-4)
- Build all three layers
- Test with stakeholders
- Deploy to production

**Phase 4: Go Live** (Week 5)
- Switch to new system
- Automated nightly scoring
- Decommission legacy system

See [IMPLEMENTATION_ROADMAP.md](docs/IMPLEMENTATION_ROADMAP.md) for detailed steps.

---

## 🎓 Design Principles

1. **Fixed Thresholds**: No dynamic adjustment, prevents normalization of poor care
2. **Dual Scoring**: Separate care delivery from documentation quality
3. **Transparency**: Every score component must be explainable
4. **Domain-Specific**: Different ADL domains have different expectations
5. **Audit-Ready**: Full traceability to raw events

---

## 📋 System Requirements

### Current System
- Python 3.8+
- Streamlit
- Pandas
- logs.csv file

### New System
- Python 3.8+
- PostgreSQL 14+
- Streamlit (for dashboard)
- psycopg2 or SQLAlchemy

---

## 🤝 Support

- **Design Questions**: See [SYSTEM_DESIGN.md](docs/SYSTEM_DESIGN.md)
- **Implementation Help**: See [IMPLEMENTATION_ROADMAP.md](docs/IMPLEMENTATION_ROADMAP.md)
- **Testing**: Run [test_scoring_engine.py](tests/test_scoring_engine.py)

---

## 📄 License & Usage

This is a risk intelligence system for care providers. Ensure compliance with:
- Data Protection Act / GDPR
- CQC regulations
- Local information governance policies

---

**Ready to migrate?** Start with [DESIGN_COMPLETE.md](docs/DESIGN_COMPLETE.md) for an overview, then follow [IMPLEMENTATION_ROADMAP.md](docs/IMPLEMENTATION_ROADMAP.md).

