# NCCU 畢業離校檢核 通識體育版

FastAPI + SQLAlchemy + Alembic + Bootstrap 5.

## Requirements
- Python 3.10+
- MySQL

## Setup
1. Create and activate a virtual environment.
2. Install dependencies:
   - `pip install -r requirements.txt`
3. Set `DATABASE_URL` (example):
   - `mysql+pymysql://user:password@localhost:3306/nccu_grad`
4. Run migrations:
   - `alembic upgrade head`
5. Start the server:
   - `uvicorn app.main:app --reload`

## Notes
- Default templates: login, dashboard, details.
- Password hashing uses SHA-256 for demo only. Replace for production.
