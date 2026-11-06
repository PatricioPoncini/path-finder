from __future__ import annotations

from datetime import datetime, timezone

from path_finder.filters import apply_filters, contains_term, role_phrases

from .conftest import make_job

NOW = datetime(2026, 11, 4, tzinfo=timezone.utc)


def kept_titles(jobs, profile, prefs):
    return [j.title for j in apply_filters(jobs, profile, prefs, now=NOW).kept]


def test_role_phrases_strip_seniority_and_swap_engineer_developer(prefs):
    phrases = role_phrases(prefs)
    assert "software engineer" in phrases and "software developer" in phrases
    assert "backend developer" in phrases


def test_title_must_match_roles(profile, prefs):
    jobs = [make_job(1), make_job(2, title="Marketing Manager")]
    assert kept_titles(jobs, profile, prefs) == ["Senior Software Engineer"]


def test_stack_in_title_rescues_generic_dev_title(profile, prefs):
    jobs = [make_job(1, title="Go Developer"), make_job(2, title="Ruby Developer")]
    assert kept_titles(jobs, profile, prefs) == ["Go Developer"]


def test_junior_dropped_unless_wanted(profile, prefs):
    jobs = [make_job(1, title="Junior Software Engineer")]
    assert kept_titles(jobs, profile, prefs) == []
    prefs.seniority = ["junior", "mid"]
    assert kept_titles(jobs, profile, prefs) == ["Junior Software Engineer"]


def test_region_filter(profile, prefs):
    jobs = [
        make_job(1, location_restrictions=["USA Only"]),
        make_job(2, location_restrictions=["Worldwide"]),
        make_job(3, location_restrictions=["Americas, Europe"]),
        make_job(4, location_restrictions=[]),
    ]
    result = apply_filters(jobs, profile, prefs, now=NOW)
    assert [j.id for j in result.kept] == ["src:2", "src:3", "src:4"]
    assert result.dropped["restricción geográfica"] == 1
    prefs.strict_region_filter = False
    assert len(apply_filters(jobs, profile, prefs, now=NOW).kept) == 4


def test_not_remote_and_old_dropped(profile, prefs):
    jobs = [make_job(1, remote=False), make_job(2, posted_at="2026-01-01T00:00:00+00:00"), make_job(3)]
    assert [j.id for j in apply_filters(jobs, profile, prefs, now=NOW).kept] == ["src:3"]


def test_dedupe_by_id_and_company_title(profile, prefs):
    jobs = [make_job(1), make_job(1), make_job(2, company="Co1")]
    assert len(apply_filters(jobs, profile, prefs, now=NOW).kept) == 1


def test_exclude_keywords(profile, prefs):
    prefs.exclude_keywords = ["manager"]
    jobs = [make_job(1, title="Software Engineering Manager (Software Engineer track)")]
    assert kept_titles(jobs, profile, prefs) == []


def test_contains_term_word_boundaries():
    assert contains_term("Remote, EU only", "eu")
    assert not contains_term("Venezuela", "eu")
    assert contains_term("Latin America", "latin america")
