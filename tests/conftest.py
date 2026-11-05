from __future__ import annotations

import pytest

from jobbot.models import Job, Preferences, Profile


@pytest.fixture
def profile() -> Profile:
    return Profile(
        name="Ada Test", headline="Backend Engineer", country="Argentina", years_experience=5,
        seniority_level="senior", skills=["Go", "Kotlin", "AWS", "PostgreSQL", "Docker"],
        primary_stack=["Go", "Kotlin", "AWS"], roles_suited=["Backend Engineer"],
    )


@pytest.fixture
def prefs() -> Preferences:
    return Preferences(
        target_roles=["Senior Software Engineer", "Backend Engineer"], seniority=["mid", "senior"],
        work_modes=["remote"], candidate_country="Argentina",
        eligible_regions=["worldwide", "anywhere", "argentina", "latam", "americas"],
        preferred_stack=["Go"], batch_size=2, max_age_days=30,
    )


def make_job(i: int = 1, **kw) -> Job:
    base = dict(
        id="src:%d" % i, source="remotive", title="Senior Software Engineer", company="Co%d" % i,
        url="https://example.com/%d" % i, location="Worldwide", remote=True,
        description="We use Go and AWS with PostgreSQL.", posted_at="2026-11-01T00:00:00+00:00",
    )
    base.update(kw)
    return Job(**base)


class FakeClaude:
    """Imita Claude.tool_call: puntúa cada oferta del lote con un score fijo por id."""

    def __init__(self, scores=None, drop_first=False):
        self.scores = scores or {}
        self.calls = 0
        self.drop_first = drop_first

    def tool_call(self, system, user, tool, max_tokens=4096):
        self.calls += 1
        n = user.count("### JOB ")
        ids = list(range(1, n + 1))
        if self.drop_first and self.calls == 1:
            ids = ids[1:]  # simula una respuesta incompleta
        return {"matches": [
            {"id": str(i), "score": self.scores.get(i, 80), "eligible": "yes", "seniority_fit": "good",
             "summary": "ok", "reasons": ["r"], "gaps": []} for i in ids
        ]}
