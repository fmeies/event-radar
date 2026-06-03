import os

# Set dummy env vars before any app module is imported
os.environ.setdefault("SECRET_KEY", "test-secret-key-32-chars-xxxxxxxxx")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-api-key")
os.environ.setdefault("SMTP_HOST", "localhost")
os.environ.setdefault("FROM_EMAIL", "test@example.com")
