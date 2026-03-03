import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes_notes import router as notes_router
from src.api.routes_search import router as search_router
from src.api.routes_tags import router as tags_router

openapi_tags = [
    {"name": "health", "description": "Service health and basic connectivity checks."},
    {"name": "notes", "description": "CRUD operations for notes, including tag assignment."},
    {"name": "tags", "description": "CRUD operations for tags."},
    {"name": "search", "description": "Search notes by text and tag filters."},
]

app = FastAPI(
    title="NoteMaster Backend API",
    description=(
        "Backend API for NoteMaster (notes + tags + search). "
        "Uses PostgreSQL for persistence. "
        "Configure DB with POSTGRES_URL, and configure allowed frontend origin via FRONTEND_ORIGIN."
    ),
    version="1.0.0",
    openapi_tags=openapi_tags,
)

# CORS:
# - Prefer FRONTEND_ORIGIN for a strict origin in deployments
# - Allow '*' for local/dev if not configured
frontend_origin = os.getenv("FRONTEND_ORIGIN", "*")
allow_origins = [frontend_origin] if frontend_origin != "*" else ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(notes_router)
app.include_router(tags_router)
app.include_router(search_router)


@app.get(
    "/",
    tags=["health"],
    summary="Health check",
    description="Simple health check endpoint to verify the API server is running.",
    operation_id="health_check",
)
def health_check():
    return {"message": "Healthy"}
