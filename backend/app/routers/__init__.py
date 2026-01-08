"""Routers package for the backend."""
# Note: avoid importing routers that rely on missing/optional models during
# early startup. Services router references ServiceRequest which isn't defined
# in `app.models` in this branch, so omit it to allow the app to start.
from . import auth, projects, ai  # noqa: F401
