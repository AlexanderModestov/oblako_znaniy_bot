from src.config import get_settings
from sqlalchemy import create_engine, text

engine = create_engine(get_settings().sync_database_url)
with engine.connect() as conn:
    conn.execute(text("DROP SCHEMA public CASCADE"))
    conn.execute(text("CREATE SCHEMA public"))
    conn.commit()
print("Done - schema reset")
