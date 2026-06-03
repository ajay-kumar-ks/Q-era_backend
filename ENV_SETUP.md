# Backend Environment Setup

## Overview
The QERA backend uses a single `.env` file for all environment configuration. This file is loaded by `config.py` on startup using Pydantic Settings.

## File Structure

- `.env` - **Main development environment file** (loaded automatically)
- `.env.example` - Example template with all available variables
- `.env.production` - Production environment template (reference only)
- `config.py` - Loads and validates all environment variables

## How It Works

1. **Loading**: `config.py` automatically loads `.env` using Pydantic's `BaseSettings`
2. **Validation**: All environment variables are validated with type checking
3. **Parsing**: Special handling for comma-separated values (e.g., `ALLOWED_ORIGIN`)
4. **Usage**: Throughout the backend, import `settings` from `config.py`

```python
from backend.config import settings
# Access variables as:
settings.SECRET_KEY
settings.ALLOWED_ORIGINS  # Note: parsed as list
settings.DEBUG
settings.CLOUDINARY_URL
```

## Environment Variables

### Required
- `SECRET_KEY` - FastAPI secret key for session management
- `ALLOWED_ORIGIN` - CORS allowed origins (comma-separated for multiple)

### Database
- `DB_PATH` - Path to SQLite database (default: `../database/qera.db`)
- `DATABASE_URL` - PostgreSQL connection string (optional, overrides SQLite)

### Cloudinary (Optional)
- `CLOUDINARY_URL` - Full Cloudinary URL with credentials
- `CLOUDINARY_CLOUD_NAME` - Cloud name (auto-extracted from URL if provided)
- `CLOUDINARY_API_KEY` - API key (optional, for manual config)
- `CLOUDINARY_API_SECRET` - API secret (optional, for manual config)
- `CLOUDINARY_UPLOAD_FOLDER` - Folder for uploads (default: `questions`)

### Development
- `DEBUG` - Enable debug mode (true/false, default: true)

## Usage Patterns

### In main.py
```python
from backend.config import settings

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,  # Already parsed as list
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### In services/routers
```python
from config import settings

if settings.DEBUG:
    print("Debug mode enabled")

cloudinary.config(
    cloud_name=settings.CLOUDINARY_CLOUD_NAME,
    api_key=settings.CLOUDINARY_API_KEY,
    api_secret=settings.CLOUDINARY_API_SECRET
)
```

## Production Deployment

For production, set environment variables directly in your deployment platform:

```bash
# Docker/Kubernetes
ENV SECRET_KEY="production-secret-key"
ENV DEBUG="false"
ENV DATABASE_URL="postgresql://user:pass@host:5432/qera"
ENV ALLOWED_ORIGIN="https://q-era-frontend.vercel.app"
```

Or create a `.env` in production with secured values.

## Important Notes

- **NEVER commit `.env` to version control** (add to `.gitignore`)
- Always keep `.env.example` updated with all available variables
- Multiple CORS origins use comma-separated format: `http://localhost:5173,https://example.com`
- The field is named `ALLOWED_ORIGIN` (singular) in `.env`, but parsed as `ALLOWED_ORIGINS` (plural) in settings
