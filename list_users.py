from app.database import SessionLocal
from app.models import User

db = SessionLocal()
users = db.query(User).order_by(User.id).all()
print(f"{len(users)} user(s)\n")
for u in users:
    status = "verified" if bool(u.is_verified) else "unverified"
    search = "active" if bool(u.search_enabled) else "paused"
    print(f"[{u.id}] {u.email}  ({status}, {search})  location: {u.location or '—'}")
    terms = [t.term for t in u.search_terms]
    print(f"  Search terms ({len(terms)}): {', '.join(terms) if terms else '—'}")
    sites = [s.site for s in u.search_sites]
    print(f"  Search sites ({len(sites)}): {', '.join(sites) if sites else '—'}")
    print()
db.close()
