def test_health_reports_llm_offline(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["llm"]["available"] is False


def test_meta_lists_seeded_catalogue(client):
    meta = client.get("/api/meta").json()
    assert {p["code"] for p in meta["products"]} == {"AC-X1", "TV-S2", "REF-C3"}
    assert meta["regions"] == ["East", "North", "South", "West"]


def test_overview_and_fva_layers(client):
    ov = client.get("/api/overview").json()
    assert len(ov["series"]) == 12
    layers = [m["layer"] for m in ov["portfolio_accuracy"]]
    assert layers == ["naive", "baseline", "context", "final"]
    fva = client.get("/api/fva").json()
    context = next(m for m in fva["portfolio"] if m["layer"] == "context")
    naive = next(m for m in fva["portfolio"] if m["layer"] == "naive")
    assert context["wape"] < naive["wape"]  # business context should beat the naive benchmark


def test_forecast_shape_and_intervals(client):
    d = client.get("/api/forecast/TV-S2/North", params={"horizon": 6, "service_level": 0.9}).json()
    assert len(d["forecast"]) == 6
    for p in d["forecast"]:
        assert p["p10"] <= p["final"] <= p["p90"]
    assert d["stock"]["service_level"] == 0.9


def test_unknown_series_is_404(client):
    r = client.get("/api/forecast/NOPE/North")
    assert r.status_code == 404
    assert "NOPE" in r.json()["detail"]


def test_event_crud_is_audited(client):
    body = {
        "name": "Test promo",
        "event_type": "promotion",
        "product_code": "AC-X1",
        "start_date": "2030-01-01",
        "end_date": "2030-01-07",
        "multiplier": 1.2,
    }
    created = client.post("/api/events", json=body, headers={"X-User": "tester"})
    assert created.status_code == 201
    event_id = created.json()["id"]
    bad = client.post("/api/events", json={**body, "end_date": "2029-12-01"})
    assert bad.status_code == 422
    assert client.delete(f"/api/events/{event_id}", headers={"X-User": "tester"}).status_code == 204
    log = client.get("/api/audit", params={"entity_type": "event"}).json()
    assert log[0]["actor"] == "tester" and log[0]["action"] == "delete"


def test_override_changes_final_forecast(client):
    first = client.get("/api/forecast/REF-C3/West", params={"horizon": 3}).json()["forecast"][1]
    r = client.post(
        "/api/overrides",
        json={
            "product_code": "REF-C3",
            "region": "West",
            "week_start": first["week"],
            "value": 999,
            "reason": "Bulk order",
        },
        headers={"X-User": "tester"},
    )
    assert r.status_code == 201
    assert r.json()["system_value"] is not None
    after = client.get("/api/forecast/REF-C3/West", params={"horizon": 3}).json()["forecast"][1]
    assert after["final"] == 999 and after["override"]["reason"] == "Bulk order"


def test_scenario_promo_raises_demand(client):
    start = client.get("/api/forecast/AC-X1/West", params={"horizon": 1}).json()["forecast"][0]["week"]
    r = client.post(
        "/api/scenarios/simulate",
        json={
            "product_code": "AC-X1",
            "region": "West",
            "horizon": 4,
            "events": [{"start_date": start, "end_date": start, "multiplier": 1.5}],
        },
    ).json()
    assert r["total_scenario"] > r["total_current"]


def test_chat_returns_503_when_llm_offline(client):
    r = client.post("/api/chat", json={"message": "How is TV-S2 doing in the North?"})
    assert r.status_code == 503
