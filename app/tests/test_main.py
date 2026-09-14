import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import main  # noqa: E402


def client():
    main.app.config["TESTING"] = True
    with main._config_lock:
        main._config_store.clear()
    return main.app.test_client()


def test_health():
    c = client()
    resp = c.get("/health")
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok"}


def test_version():
    c = client()
    resp = c.get("/version")
    assert resp.status_code == 200
    assert resp.get_json() == {"version": "1.0.0"}


def test_env_default():
    c = client()
    os.environ.pop("ENVIRONMENT", None)
    resp = c.get("/env")
    assert resp.status_code == 200
    assert resp.get_json() == {"environment": "unknown"}


def test_env_set(monkeypatch):
    c = client()
    monkeypatch.setenv("ENVIRONMENT", "staging")
    resp = c.get("/env")
    assert resp.get_json() == {"environment": "staging"}


def test_config_crud():
    c = client()

    resp = c.post("/config", json={"name": "database_url", "value": "postgres://example"})
    assert resp.status_code == 201
    assert resp.get_json() == {"name": "database_url", "value": "postgres://example"}

    resp = c.get("/config/database_url")
    assert resp.status_code == 200
    assert resp.get_json() == {"name": "database_url", "value": "postgres://example"}

    resp = c.delete("/config/database_url")
    assert resp.status_code == 200
    assert resp.get_json() == {"deleted": True}

    resp = c.get("/config/database_url")
    assert resp.status_code == 404


def test_config_not_found():
    c = client()
    resp = c.get("/config/does_not_exist")
    assert resp.status_code == 404


def test_config_delete_missing_is_false():
    c = client()
    resp = c.delete("/config/does_not_exist")
    assert resp.status_code == 200
    assert resp.get_json() == {"deleted": False}


def test_config_bad_payload():
    c = client()
    resp = c.post("/config", json={"name": "only_name"})
    assert resp.status_code == 400
