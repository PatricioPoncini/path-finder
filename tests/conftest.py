from __future__ import annotations

import pytest

from path_finder.models import Job, Preferences, Profile


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
        preferred_stack=["Go"], max_age_days=30,
    )


def make_job(i: int = 1, **kw) -> Job:
    base = dict(
        id="src:%d" % i, source="remotive", title="Senior Software Engineer", company="Co%d" % i,
        url="https://example.com/%d" % i, location="Worldwide", remote=True,
        description="We use Go and AWS with PostgreSQL.", posted_at="2026-11-01T00:00:00+00:00",
    )
    base.update(kw)
    return Job(**base)

