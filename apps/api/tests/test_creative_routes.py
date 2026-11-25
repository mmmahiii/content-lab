"""Creative generation routes and idea-plan wiring. No Postgres or network needed."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any

import pytest
from content_lab_intelligence import FakeLLMClient, LLMUnavailableError
from fastapi import FastAPI
from fastapi.testclient import TestClient

from content_lab_api.deps import get_db, get_llm_client
from content_lab_api.routes import api_router
from content_lab_api.routes.creative import router as creative_router
from content_lab_api.routes.runs import _idea_plan_payload

ORG_ID = uuid.uuid4()
PAGE_ID = uuid.uuid4()


def _page(**metadata: Any) -> SimpleNamespace:
    return SimpleNamespace(
        id=PAGE_ID,
        org_id=ORG_ID,
        display_name="Iron Habit",
        handle="ironhabit",
        metadata_={
            "niche": "fitness",
            "persona": {"label": "Coach", "audience": "new lifters", "content_pillars": ["form"]},
            **metadata,
        },
    )


class _Session:
    def __init__(self, page: SimpleNamespace) -> None:
        self.page = page

    def get(self, _model: object, ident: uuid.UUID) -> SimpleNamespace | None:
        return self.page if ident == self.page.id else None


def _client(page: SimpleNamespace, llm: FakeLLMClient | None) -> TestClient:
    app = FastAPI()
    app.include_router(creative_router)

    def _db() -> Iterator[_Session]:
        yield _Session(page)

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_llm_client] = lambda: llm
    return TestClient(app)


def _hooks_payload() -> dict[str, Any]:
    return {
        "hooks": [
            {
                "mechanism": mechanism,
                "overlay_text": text,
                "spoken_line": text,
                "visual_direction": "Side view of the squat.",
                "payoff_promise": "Show the depth fix working.",
            }
            for mechanism, text in [
                ("bold_claim", "Your squat depth is lying to you"),
                ("direct_question", "Why do your knees cave in?"),
                ("visual_first", "Watch the fix click into place"),
            ]
        ]
    }


def _hook() -> dict[str, Any]:
    return _hooks_payload()["hooks"][0]


def test_creative_routes_are_registered() -> None:
    paths = {getattr(route, "path", "") for route in api_router.routes}
    assert "/orgs/{org_id}/pages/{page_id}/hooks" in paths
    assert "/orgs/{org_id}/pages/{page_id}/quick-reel/branches" in paths
    assert "/orgs/{org_id}/pages/{page_id}/quick-reel/compose" in paths


def test_hooks_endpoint_uses_page_context_and_llm() -> None:
    llm = FakeLLMClient([_hooks_payload()])
    response = _client(_page(), llm).post(
        f"/orgs/{ORG_ID}/pages/{PAGE_ID}/hooks", json={"topic": "squat depth"}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["source"] == "llm"
    assert body["niche"] == "fitness"
    assert len(body["hooks"]) == 3
    prompt = llm.calls[0].prompt
    assert "Iron Habit" in prompt and "new lifters" in prompt and "squat depth" in prompt


def test_hooks_endpoint_falls_back_without_llm() -> None:
    response = _client(_page(), None).post(
        f"/orgs/{ORG_ID}/pages/{PAGE_ID}/hooks", json={"topic": "squat depth", "count": 4}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "fallback"
    assert body["fallback_reason"] == "llm_not_configured"
    assert len(body["hooks"]) == 4


def test_page_from_another_org_is_not_found() -> None:
    other_org_page = _page()
    other_org_page.org_id = uuid.uuid4()
    response = _client(other_org_page, None).post(f"/orgs/{ORG_ID}/pages/{PAGE_ID}/hooks", json={})
    assert response.status_code == 404


def test_branches_then_compose_round_trip() -> None:
    client = _client(_page(constraints={"required_disclosures": ["Not medical advice"]}), None)
    branches = client.post(
        f"/orgs/{ORG_ID}/pages/{PAGE_ID}/quick-reel/branches",
        json={"hook": _hook(), "topic": "squat depth", "duration_seconds": 15},
    )
    assert branches.status_code == 200, branches.text
    data = branches.json()
    assert data["source"] == "fallback"
    preview = data["preview"]
    assert preview["overlay_timeline"][0]["text"] == _hook()["overlay_text"]
    assert preview["overlay_timeline"][-1]["text"] == "Not medical advice"

    selection = {
        "structure": data["branches"]["structure"][1]["option_id"],
        "energy": data["branches"]["energy"][1]["option_id"],
        "ending": data["branches"]["ending"][2]["option_id"],
    }
    composed = client.post(
        f"/orgs/{ORG_ID}/pages/{PAGE_ID}/quick-reel/compose",
        json={
            "hook": data["hook"],
            "branches": data["branches"],
            "selection": selection,
            "duration_seconds": 15,
        },
    )
    assert composed.status_code == 200, composed.text
    reel = composed.json()
    assert reel["selection"] == selection
    assert reel["pace"] == "punchy"
    assert reel["overlay_timeline"][-1]["end_seconds"] == reel["duration_seconds"]
    assert reel["overlay_timeline"][-1]["emphasis"] == "disclosure"


def test_compose_rejects_unknown_option() -> None:
    client = _client(_page(), None)
    data = client.post(
        f"/orgs/{ORG_ID}/pages/{PAGE_ID}/quick-reel/branches", json={"hook": _hook()}
    ).json()
    response = client.post(
        f"/orgs/{ORG_ID}/pages/{PAGE_ID}/quick-reel/compose",
        json={
            "hook": data["hook"],
            "branches": data["branches"],
            "selection": {"structure": "nope", "energy": "chill", "ending": "reveal"},
        },
    )
    assert response.status_code == 422
    assert "unknown structure option" in response.json()["detail"]


def test_branches_reject_hooks_that_leak_creator_directions() -> None:
    hook = {**_hook(), "overlay_text": "Open with the squat from the side"}
    response = _client(_page(), None).post(
        f"/orgs/{ORG_ID}/pages/{PAGE_ID}/quick-reel/branches", json={"hook": hook}
    )
    assert response.status_code == 422


def _idea_payload() -> dict[str, Any]:
    return {
        "title": "Squat depth fix",
        "angle": "One cue that fixes shallow squats.",
        "hook_overlay": "Your squat depth is lying to you",
        "hook_spoken": "Your squat depth is probably lying to you.",
        "hook_direction": "Side view, bar on back.",
        "beats": [
            {
                "label": "Cue",
                "direction": "Close-up on hips.",
                "narration": "Sit back like there's a bench behind you.",
                "overlay_text": "Sit back, not down",
                "seconds": 4,
            },
            {
                "label": "Proof",
                "direction": "Side-by-side depth.",
                "narration": "Same lifter, real depth, one cue.",
                "overlay_text": "Real depth, one cue",
                "seconds": 4,
            },
        ],
        "caption_angles": ["One cue, real depth.", "Try this on your next set.", "Did it help?"],
    }


@pytest.mark.parametrize(
    ("llm", "source"),
    [
        (FakeLLMClient([_idea_payload()]), "llm"),
        (FakeLLMClient([LLMUnavailableError("down")]), "template"),
        (None, "template"),
    ],
)
def test_idea_plan_payload_uses_llm_with_template_fallback(
    llm: FakeLLMClient | None, source: str
) -> None:
    run_id = uuid.uuid4()
    payload = _idea_plan_payload(page=_page(), run_id=run_id, plan_number=2, llm_client=llm)
    plan = payload["plan"]
    assert plan["generation"]["source"] == source
    assert plan["package_intent"]["expected_outputs"][0] == "final_video"
    assert payload["plans"][0] == {
        "id": str(run_id),
        "label": "Plan 2",
        "title": plan["title"],
        "status": "ready_for_generation",
    }
    assert all("overlay_text" in beat and "narration" in beat for beat in plan["beats"])
    if source == "template":
        assert plan["title"] == "Iron Habit plan 2"
        assert plan["beats"][1]["overlay_text"] == "Useful shift"
