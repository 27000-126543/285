from contextlib import contextmanager
from sqlalchemy.orm import Session
from .models import init_db
import logging

logger = logging.getLogger(__name__)

SessionLocal = None
engine = None

def initialize_database(db_path='data/fund_pool.db'):
    global SessionLocal, engine
    SessionLocal, engine = init_db(db_path)
    logger.info("Database initialized successfully")

@contextmanager
def get_db():
    db: Session = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Database error: {e}")
        raise
    finally:
        db.close()

def bulk_insert(db, model, data_list, batch_size=1000):
    for i in range(0, len(data_list), batch_size):
        batch = data_list[i:i + batch_size]
        db.bulk_insert_mappings(model, batch)
    db.commit()
