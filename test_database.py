from backend.database import engine, Base
from backend.models import Document


try:
    # Create all tables defined in our models
    Base.metadata.create_all(bind=engine)

    print("Database tables created successfully!")

except Exception as error:
    print("Error creating database tables:")
    print(error)