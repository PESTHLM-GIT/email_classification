from types import SimpleNamespace

from src.auth import require_login
from src.config import ALLOWED_USER_EMAIL


def make_request(
    principal_name=None,
    url="https://emailclassification-cdcwb3a9f6hkaxar.swedencentral-01.azurewebsites.net/api/dashboard",
):
    return SimpleNamespace(headers={"X-MS-CLIENT-PRINCIPAL-NAME": principal_name} if principal_name else {}, url=url)


def test_allows_matching_user():
    req = make_request(principal_name=ALLOWED_USER_EMAIL)
    assert require_login(req) is None


def test_allows_matching_user_case_insensitive():
    req = make_request(principal_name=ALLOWED_USER_EMAIL.upper())
    assert require_login(req) is None


def test_rejects_missing_principal_with_401():
    req = make_request(principal_name=None)
    response = require_login(req)
    assert response is not None
    assert response.status_code == 401


def test_redirects_missing_principal_when_requested():
    req = make_request(principal_name=None)
    response = require_login(req, redirect_if_missing=True)
    assert response is not None
    assert response.status_code == 302
    assert "/.auth/login/aad" in response.headers["Location"]


def test_rejects_wrong_user_with_403():
    req = make_request(principal_name="nagon.annan@movedigital.se")
    response = require_login(req)
    assert response is not None
    assert response.status_code == 403
