"""Initialize database tables for file manager"""
from files.db.database import Base, engine
from files.models.user import User
from files.models.file_metadata import Folder, FileMetadata, folder_permissions

def init_db():
    """Create all tables"""
    print("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    print("Tables created successfully!")

if __name__ == "__main__":
    init_db()
