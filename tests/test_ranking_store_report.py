from __future__ import annotations

from jobbot.models import Match
from jobbot.ranking import eligibility, rank_job, rank_jobs, required_years, salary_max, title_level
from jobbot.report import build_entries, render_html, render_markdown
from jobbot.store import Store

from .conftest import make_job


def test_more_skill_matches_score_higher(profile, prefs):
    rich = rank_job(make_job(1, description="Go, Kotlin and AWS with PostgreSQL and Docker"), profile, prefs)
    poor = rank_job(make_job(2, description="We build things with Ruby"), profile, prefs)
    assert rich.score > poor.score + 20
    assert any("Go" in r for r in rich.reasons)


def test_skill_aliases_count(profile, prefs):
    with_alias = rank_job(make_job(1, title="Engineer", description="Golang services on k8s"), profile, prefs)
    without = rank_job(make_job(2, title="Engineer", description="Ruby services"), profile, prefs)
    assert with_alias.score > without.score


def test_short_skills_are_case_sensitive(profile, prefs):
    bad = rank_job(make_job(1, title="Engineer", description="a go-to person who will go far"), profile, prefs)
    good = rank_job(make_job(2, title="Engineer", description="We write Go services"), profile, prefs)
    assert good.score > bad.score


def test_junior_and_avoid_stack_penalize(profile, prefs):
    base = rank_job(make_job(1), profile, prefs)
    junior = rank_job(make_job(2, title="Junior Software Engineer"), profile, prefs)
    assert junior.score < base.score and junior.seniority_fit == "below"
    prefs.avoid_stack = ["PostgreSQL"]
    avoided = rank_job(make_job(3), profile, prefs)
    assert avoided.score < base.score and any("evitar" in g for g in avoided.gaps)


def test_required_years_gap(profile, prefs):
    job = make_job(1, description="Go and AWS. Requires 12+ years of experience in backend.")
    m = rank_job(job, profile, prefs)
    assert required_years(job.description) == 12
    assert m.seniority_fit == "above" and any("12" in g for g in m.gaps)
    assert m.score < rank_job(make_job(2), profile, prefs).score


def test_eligibility_rules(prefs):
    assert eligibility(make_job(1, location_restrictions=["USA Only"]), prefs)[0] == "no"
    assert eligibility(make_job(2, location_restrictions=["LATAM"]), prefs)[0] == "yes"
    assert eligibility(make_job(3, description="This role is US only."), prefs)[0] == "no"
    assert eligibility(make_job(4, description="You must be located in the United States."), prefs)[0] == "no"
    assert eligibility(make_job(5, description="Must be based in Canada or Argentina."), prefs)[0] == "yes"
    assert eligibility(make_job(6, description="Fully remote, work from anywhere in the world."), prefs)[0] == "yes"
    assert eligibility(make_job(7, description="Authorized to work in the US required."), prefs)[0] == "no"
    assert eligibility(make_job(8, location="", description="Great team and benefits."), prefs)[0] == "unclear"


def test_ineligible_score_is_capped(profile, prefs):
    m = rank_job(make_job(1, description="Go Kotlin AWS PostgreSQL Docker. US only."), profile, prefs)
    assert m.eligible == "no" and m.score <= 25


def test_helpers():
    assert title_level("Staff Engineer") == "expert" and title_level("Sr. Developer") == "senior"
    assert title_level("Backend Engineer") == ""
    assert salary_max("$100,000-150,000") == 150000 and salary_max("120k - 140k USD") == 140000


def test_rank_jobs_maps_ids(profile, prefs):
    out = rank_jobs([make_job(1), make_job(2)], profile, prefs)
    assert set(out) == {"src:1", "src:2"}


def test_store_status_and_new_ids():
    store = Store(":memory:")
    jobs = [make_job(1), make_job(2)]
    assert store.upsert_jobs(jobs) == {"src:1", "src:2"}
    assert store.upsert_jobs(jobs) == set()  # la 2ª vez ya no son nuevas

    assert store.set_status("src:1", "applied") and not store.set_status("nope", "applied")
    assert store.statuses(["src:1", "src:2"]) == {"src:1": "applied", "src:2": "new"}
    rows = store.list_jobs(status="applied")
    assert [(j.id, st) for j, st in rows] == [("src:1", "applied")]


def test_report_sorting_filters_and_escaping(profile, prefs):
    jobs = [make_job(1, title="<b>Eng</b>"), make_job(2), make_job(3)]
    matches = {
        "src:1": Match("src:1", 70, summary="<script>x</script>"),
        "src:2": Match("src:2", 90),
        "src:3": Match("src:3", 95, eligible="no"),
    }
    entries = build_entries(jobs, matches, {"src:2"}, min_score=60)
    assert [e.job.id for e in entries] == ["src:2", "src:1"]  # ordenado; no elegible oculto
    assert len(build_entries(jobs, matches, set(), 60, show_ineligible=True)) == 3
    assert [e.job.id for e in build_entries(jobs, matches, {"src:2"}, 60, only_new=True)] == ["src:2"]

    html = render_html(profile, prefs, entries, {})
    assert "<script>x" not in html and "&lt;script&gt;" in html
    md = render_markdown(profile, prefs, entries, {})
    assert "src:2" in md and "Fuente: Remotive" in md and "sin IA" in md
