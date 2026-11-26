
from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.database import Base, engine

# Register database models
import backend.models

# Existing routers
from backend.routes.auth import router as auth_router
from backend.routes.documents import router as documents_router
from backend.routes.qa import router as qa_router

# Admin routers
from backend.routes.customer_management import (
    router as customer_management_router
)

from backend.routes.admin_dashboard import (
    router as admin_dashboard_router
)

from backend.routes.admin_data import (
    router as admin_data_router
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Starting Universal RAG API...")

    Base.metadata.create_all(bind=engine)

    print("Database tables initialized successfully.")
    print("Universal RAG API is ready.")

    yield

    print("Shutting down Universal RAG API...")


app = FastAPI(
    title="Universal RAG API",
    description="Customer Support and Agentic RAG System",
    version="1.0.0",
    lifespan=lifespan
)


# Register routers
app.include_router(auth_router)
app.include_router(documents_router)
app.include_router(qa_router)

app.include_router(customer_management_router)
app.include_router(admin_dashboard_router)
app.include_router(admin_data_router)


@app.get("/")
def root():
    return {
        "message": "Welcome to Universal RAG API",
        "status": "running",
        "version": "1.0.0"
    }


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "application": "Universal RAG API"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)