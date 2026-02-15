from src.restart.scholarly_ingestion import ScholarlyIngestionHub


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload
        self.status_code = 200

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_openalex_normalization(monkeypatch):
    hub = ScholarlyIngestionHub()

    def fake_get(*args, **kwargs):
        return _FakeResponse(
            {
                "results": [
                    {
                        "title": "Sample Title",
                        "abstract": "Sample Abstract",
                        "doi": "10.1000/test",
                        "primary_location": {"landing_page_url": "https://example.com"},
                    }
                ]
            }
        )

    monkeypatch.setattr(hub.session, "get", fake_get)
    items = hub.search_openalex("query", per_page=1)
    assert items[0]["source"] == "openalex"
    assert items[0]["title"] == "Sample Title"
