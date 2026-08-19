import asyncio
import json
from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = BASE_DIR / "data.json"
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(
    title="Northstar Core Banking Operations Simulator",
    description="Deterministic legacy banking application simulator for computer-use automation testing",
    version="1.0.0",
)

# Mount static files
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Initialize templates
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def load_member_data() -> Dict[str, Any]:
    """Load member records and scenario configurations from data.json."""
    if not DATA_FILE.exists():
        return {}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


@app.get("/", response_class=HTMLResponse)
async def get_dashboard(request: Request):
    """Internal employee dashboard view."""
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={"active_page": "dashboard"},
    )


@app.get("/members/search", response_class=HTMLResponse)
async def get_member_search(request: Request):
    """Member search query page."""
    return templates.TemplateResponse(
        request=request,
        name="member_search.html",
        context={"active_page": "search"},
    )


@app.post("/members/search")
async def post_member_search(member_id: str = Form(...)):
    """Process UI search form submission and navigate to member detail."""
    clean_id = member_id.strip()
    return RedirectResponse(url=f"/members/{clean_id}", status_code=303)


@app.get("/members/{member_id}", response_class=HTMLResponse)
async def get_member_detail(member_id: str, request: Request):
    """Display member profile or appropriate scenario state."""
    data = load_member_data()
    clean_id = member_id.strip()

    # Unknown or explicit not_found scenario
    if clean_id not in data or data[clean_id].get("scenario") == "not_found":
        return templates.TemplateResponse(
            request=request,
            name="member_not_found.html",
            context={"member_id": clean_id, "active_page": "search"},
            status_code=200,
        )

    member_record = data[clean_id]
    scenario = member_record.get("scenario", "success")

    # Scenario 3: PERMISSION_DENIED
    if scenario == "permission_denied":
        return templates.TemplateResponse(
            request=request,
            name="permission_denied.html",
            context={"member_id": clean_id, "active_page": "search"},
            status_code=200,
        )

    # Scenario 4: MANUAL_VERIFICATION / HUMAN_REQUIRED
    if scenario == "manual_verification":
        cookie_key = f"verified_{clean_id}"
        if request.cookies.get(cookie_key) != "1":
            return templates.TemplateResponse(
                request=request,
                name="manual_verification.html",
                context={"member_id": clean_id, "active_page": "search"},
                status_code=200,
            )

    # Optional Scenario: TRANSIENT SLOW LOAD
    if scenario == "slow_load":
        delay = member_record.get("delay_seconds", 1.0)
        await asyncio.sleep(delay)

    # Standard Member Profile View
    return templates.TemplateResponse(
        request=request,
        name="member_detail.html",
        context={
            "member_id": clean_id,
            "member": member_record,
            "active_page": "search",
        },
    )


@app.post("/members/{member_id}/verify")
async def post_verify_member(member_id: str):
    """Complete manual verification for restricted member and persist in session cookie."""
    clean_id = member_id.strip()
    response = RedirectResponse(url=f"/members/{clean_id}", status_code=303)
    response.set_cookie(
        key=f"verified_{clean_id}",
        value="1",
        httponly=True,
        samesite="lax",
        max_age=3600,
    )
    return response


@app.get("/members/{member_id}/accounts/savings", response_class=HTMLResponse)
async def get_savings_account_detail(member_id: str, request: Request):
    """Display savings account balance and transaction detail for target member."""
    data = load_member_data()
    clean_id = member_id.strip()

    if clean_id not in data or data[clean_id].get("scenario") == "not_found":
        return templates.TemplateResponse(
            request=request,
            name="member_not_found.html",
            context={"member_id": clean_id, "active_page": "search"},
            status_code=200,
        )

    member_record = data[clean_id]
    scenario = member_record.get("scenario", "success")

    if scenario == "permission_denied":
        return templates.TemplateResponse(
            request=request,
            name="permission_denied.html",
            context={"member_id": clean_id, "active_page": "search"},
            status_code=200,
        )

    if scenario == "manual_verification":
        cookie_key = f"verified_{clean_id}"
        if request.cookies.get(cookie_key) != "1":
            return templates.TemplateResponse(
                request=request,
                name="manual_verification.html",
                context={"member_id": clean_id, "active_page": "search"},
                status_code=200,
            )

    accounts = member_record.get("accounts", {})
    savings_account = accounts.get("savings")

    if not savings_account:
        raise HTTPException(status_code=404, detail="Savings account record not found.")

    return templates.TemplateResponse(
        request=request,
        name="account_detail.html",
        context={
            "member_id": clean_id,
            "member": member_record,
            "account": savings_account,
            "active_page": "search",
        },
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
