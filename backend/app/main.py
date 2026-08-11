import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

from app.auth import access_gate  # noqa: E402
from app.db import init_db  # noqa: E402
from app.routers import agents, catalog, oauth  # noqa: E402


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Forge", lifespan=lifespan)

# The token gate is registered first so it wraps everything, including the
# CORS layer's own responses.
app.middleware("http")(access_gate)

# The dev server proxies /api, so the browser calls the app's own origin and
# these entries only matter for a frontend served from somewhere else. Extra
# origins can be added with FORGE_ALLOWED_ORIGINS (comma-separated).
_extra_origins = [
    origin.strip()
    for origin in os.environ.get("FORGE_ALLOWED_ORIGINS", "").split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", *_extra_origins],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(agents.router)
app.include_router(catalog.router)
app.include_router(oauth.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
