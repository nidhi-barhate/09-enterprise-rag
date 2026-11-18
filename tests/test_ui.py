from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_ui_page_is_served_at_ui():
    response = client.get("/ui/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "OpsMind Search" in response.text


def test_root_redirects_to_the_ui():
    response = client.get("/", follow_redirects=False)
    assert response.status_code in (302, 307)
    assert response.headers["location"] == "/ui/"


def test_page_uses_the_real_api_endpoints():
    page = client.get("/ui/").text
    for path in ('"/search/"', '"/"', "tab-incidents", "tab-documents"):
        assert path in page
    # data is written with textContent, never injected as HTML
    assert "innerHTML" not in page


def test_page_does_not_load_anything_from_other_sites():
    page = client.get("/ui/").text
    assert "http://" not in page and "https://" not in page
