
from uuid import uuid4
from getpass import getpass

from backend.database import SessionLocal
from backend.models import User
from backend.services.auth_service import hash_password


def create_admin():

    db = SessionLocal()

    try:

        print("\n===== CREATE ADMIN ACCOUNT =====")

        username = input("Enter admin username: ").strip()
        email = input("Enter admin email: ").strip()

        password = getpass("Enter admin password: ")
        confirm_password = getpass("Confirm admin password: ")

        # Validate inputs
        if not username or not email or not password:
            print("All fields are required.")
            return

        if len(password) < 8:
            print("Password must contain at least 8 characters.")
            return

        if password != confirm_password:
            print("Passwords do not match.")
            return

        # Check whether username or email already exists
        existing_user = (
            db.query(User)
            .filter(
                (User.username == username) |
                (User.email == email)
            )
            .first()
        )

        if existing_user:
            print("Username or email already exists.")
            return

        # Create admin account
        admin = User(
            id=str(uuid4()),
            username=username,
            email=email,
            hashed_password=hash_password(password),
            role="admin",
            is_active=True
        )

        db.add(admin)
        db.commit()

        print("\nAdmin account created successfully!")
        print("Username:", username)
        print("Role: admin")

    except Exception as error:

        db.rollback()
        print("Error creating admin:", error)

    finally:
        db.close()


if __name__ == "__main__":
    create_admin()
