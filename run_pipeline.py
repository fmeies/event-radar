import asyncio
from app.logger import setup_logging
from app.search_pipeline import run_pipeline

if __name__ == "__main__":
    setup_logging()
    asyncio.run(run_pipeline())
