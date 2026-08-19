import pytest
from fastapi.testclient import TestClient
from demo_bank.app import app

@pytest.fixture
def client():
    return TestClient(app)

def test_dashboard(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Northstar Core" in r.text
    assert "Banking Operations Portal" in r.text
    assert "Member Search" in r.text

def test_member_search_form(client):
    r = client.get("/members/search")
    assert r.status_code == 200
    assert "Member Search" in r.text
    assert 'name="member_id"' in r.text

    post_resp = client.post("/members/search", data={"member_id": "M-10428"}, follow_redirects=False)
    assert post_resp.status_code == 303
    assert post_resp.headers["location"] == "/members/M-10428"

def test_scenario_success_m10428(client):
    # Member detail
    r_detail = client.get("/members/M-10428")
    assert r_detail.status_code == 200
    assert "Alex Morgan" in r_detail.text
    assert "View Savings" in r_detail.text

    # Savings account detail
    r_savings = client.get("/members/M-10428/accounts/savings")
    assert r_savings.status_code == 200
    assert "Current Savings Balance" in r_savings.text
    assert "$4283.42" in r_savings.text

def test_scenario_not_found_m00000(client):
    r = client.get("/members/M-00000")
    assert r.status_code == 200
    assert "Member Not Found" in r.text
    assert "No member found for Member ID" in r.text

def test_scenario_permission_denied_m99999(client):
    r = client.get("/members/M-99999")
    assert r.status_code == 200
    assert "Access Denied" in r.text
    assert "You do not have permission to view this member" in r.text

def test_scenario_manual_verification_m88888(client):
    # Initial unverified access shows interstitial
    r_initial = client.get("/members/M-88888")
    assert r_initial.status_code == 200
    assert "Additional Verification Required" in r_initial.text
    assert "Verify &amp; Continue" in r_initial.text or "Verify & Continue" in r_initial.text

    # Submit verification
    r_verify = client.post("/members/M-88888/verify", follow_redirects=False)
    assert r_verify.status_code == 303
    assert r_verify.headers["location"] == "/members/M-88888"

    # Access with session cookie set
    client.cookies.set("verified_M-88888", "1")
    r_verified = client.get("/members/M-88888")
    assert r_verified.status_code == 200
    assert "Jordan Lee" in r_verified.text
    assert "View Savings" in r_verified.text

    # View Savings for M-88888
    r_savings = client.get("/members/M-88888/accounts/savings")
    assert r_savings.status_code == 200
    assert "Current Savings Balance" in r_savings.text
    assert "$5125.75" in r_savings.text

def test_scenario_slow_load_m77777(client):
    r = client.get("/members/M-77777")
    assert r.status_code == 200
    assert "Casey Wright" in r.text
