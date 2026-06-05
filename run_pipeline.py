import argparse
import asyncio
import sys

from app.database import SessionLocal
from app.logger import setup_logging
from app.models import User
from app.search_pipeline import run_for_user, run_pipeline

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the event search pipeline.")
    parser.add_argument("--user", metavar="EMAIL", help="Run for a single user only")
    args = parser.parse_args()

    setup_logging()

    if args.user:
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.email == args.user).first()
        finally:
            db.close()
        if not user:
            print(f"User not found: {args.user}", file=sys.stderr)
            sys.exit(1)
        asyncio.run(run_for_user(user.id))
    else:
        asyncio.run(run_pipeline())
