#!/usr/bin/env python
"""
Setup script to initialize the project.
"""
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.core.database import engine, Base
from backend.core.config import settings
from backend.models import Document, DocumentChunk, User, Conversation, Message


def create_tables():
    """Create all database tables."""
    print("Creating database tables...")
    try:
        Base.metadata.create_all(bind=engine)
        print("✓ Database tables created successfully")
    except Exception as e:
        print(f"✗ Error creating tables: {e}")
        return False
    return True


def verify_connection():
    """Verify database connection."""
    print("Verifying database connection...")
    try:
        with engine.connect() as conn:
            print(f"✓ Connected to database: {settings.DATABASE_URL}")
    except Exception as e:
        print(f"✗ Database connection failed: {e}")
        return False
    return True


def create_admin_user():
    """Create default admin user."""
    from backend.core.database import SessionLocal
    from passlib.hash import bcrypt
    
    print("Creating admin user...")
    session = SessionLocal()
    try:
        # Check if admin exists
        admin = session.query(User).filter(User.username == "admin").first()
        if admin:
            print("✓ Admin user already exists")
            return True
        
        # Create admin user
        admin = User(
            username="admin",
            email="admin@infohub-ai.com",
            password_hash=bcrypt.hash("changeme"),  # CHANGE IN PRODUCTION!
            full_name="System Administrator",
            role="admin",
            is_active=True,
        )
        session.add(admin)
        session.commit()
        print("✓ Admin user created (username: admin, password: changeme)")
        print("  ⚠ IMPORTANT: Change the admin password in production!")
    except Exception as e:
        print(f"✗ Error creating admin user: {e}")
        session.rollback()
        return False
    finally:
        session.close()
    return True


def main():
    """Main setup function."""
    print("=" * 60)
    print("InfoHub AI Tax Advisor - Project Setup")
    print("=" * 60)
    print()
    
    # Verify connection
    if not verify_connection():
        print("\n✗ Setup failed: Cannot connect to database")
        print(f"  Check DATABASE_URL in .env file")
        return 1
    
    # Create tables
    if not create_tables():
        print("\n✗ Setup failed: Cannot create tables")
        return 1
    
    # Create admin user
    if not create_admin_user():
        print("\n✗ Setup failed: Cannot create admin user")
        return 1
    
    print()
    print("=" * 60)
    print("✓ Setup completed successfully!")
    print("=" * 60)
    print()
    print("Next steps:")
    print("1. Update .env file with your API keys")
    print("2. Start the backend: python -m backend.api.main")
    print("3. Access API docs: http://localhost:8000/docs")
    print()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
