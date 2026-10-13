"""Start-up script used on Hugging Face.

Hugging Face gives the app its settings as "secrets" (environment variables). Streamlit's
Microsoft sign-in reads its settings from .streamlit/secrets.toml, so this script writes that
file from the variables, then starts the app.
"""
import os
import sys
from pathlib import Path

REQUIRED = ["MS_TENANT_ID", "MS_CLIENT_ID", "MS_CLIENT_SECRET", "APP_URL", "COOKIE_SECRET"]

# Preview mode must never be active on a deployed Space.
if os.environ.get("SPACE_ID"):
    os.environ.pop("PREVIEW_USER", None)

missing = [k for k in REQUIRED if not os.environ.get(k)]
if missing:
    print(f"Microsoft sign-in is not set up. Missing secrets: {', '.join(missing)}", flush=True)
else:
    def q(v: str) -> str:
        return '"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"'

    url = os.environ["APP_URL"].rstrip("/")
    tenant = os.environ["MS_TENANT_ID"]
    toml = "\n".join([
        "[auth]",
        f"redirect_uri = {q(url + '/oauth2callback')}",
        f"cookie_secret = {q(os.environ['COOKIE_SECRET'])}",
        f"client_id = {q(os.environ['MS_CLIENT_ID'])}",
        f"client_secret = {q(os.environ['MS_CLIENT_SECRET'])}",
        f"server_metadata_url = {q(f'https://login.microsoftonline.com/{tenant}/v2.0/.well-known/openid-configuration')}",
        'client_kwargs = { prompt = "select_account" }',
        "",
    ])
    path = Path(".streamlit/secrets.toml")
    path.parent.mkdir(exist_ok=True)
    path.write_text(toml)
    path.chmod(0o600)
    print("Microsoft sign-in configured.", flush=True)

port = os.environ.get("PORT", "8501")
os.execvp(sys.executable, [sys.executable, "-m", "streamlit", "run", "app.py",
                           "--server.port", port, "--server.address", "0.0.0.0"])
