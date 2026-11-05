from __future__ import annotations

from jobbot.matcher import _clean, build_system, estimate_tokens, heuristic_match, score_jobs
from jobbot.models import Match
from jobbot.report import build_entries, render_html, render_markdown
from jobbot.store import Store

from .conftest import FakeClaude, make_job


def test_score_jobs_batches_and_maps_ids(profile, prefs):
    jobs = [make_job(i) for i in range(1, 6)]  # batch_size=2 -> 3 llamadas
    fake = FakeClaude(scores={1: 90, 2: 70})
    matches, failed = score_jobs(fake, profile, prefs, jobs)
    assert fake.calls == 3 and not failed
    by_id = {m.job_id: m.score for m in matches}
    assert by_id["src:1"] == 90 and by_id["src:2"] == 70 and by_id["src:3"] == 90


def test_incomplete_response_is_retried_once(profile, prefs):
    fake = FakeClaude(drop_first=True)
    matches, failed = score_jobs(fake, profile, prefs, [make_job(1), make_job(2)])
    assert len(matches) == 2 and not failed and fake.calls == 2


def test_clean_caps_ineligible_and_clamps(profile):
    m = _clean({"score": 150, "eligible": "no", "seniority_fit": "good"}, make_job(1))
    assert m.score == 25
    m = _clean({"score": "abc", "eligible": "weird", "seniority_fit": "x"}, make_job(1))
    assert m.score == 0 and m.eligible == "unclear" and m.seniority_fit == "unclear"


def test_system_prompt_is_generic_and_includes_user_data(profile, prefs):
    system = build_system(profile, prefs)
    assert "Argentina" in system and "Ada Test" in system and "Spanish" in system


def test_estimate_tokens(profile, prefs):
    calls, tin, tout = estimate_tokens(build_system(profile, prefs), [make_job(i) for i in range(5)], 2)
    assert calls == 3 and tin > 0 and tout > 0


def test_heuristic_short_skills_are_case_sensitive(profile, prefs):
    good = heuristic_match(make_job(1, description="We write Go services on AWS"), profile, prefs)
    bad = heuristic_match(make_job(2, description="a go-to person who will go far", title="Engineer"), profile, prefs)
    assert good.score > bad.score and good.method == "heuristic"


def test_store_cache_status_and_new_ids():
    store = Store(":memory:")
    jobs = [make_job(1), make_job(2)]
    assert store.upsert_jobs(jobs) == {"src:1", "src:2"}
    assert store.upsert_jobs(jobs) == set()  # la 2ª vez ya no son nuevas

    store.save_scores([Match("src:1", 88)], "k1")
    assert set(store.get_scores(["src:1", "src:2"], "k1")) == {"src:1"}
    assert store.get_scores(["src:1"], "otra-clave") == {}  # cambiar perfil/prefs invalida la caché

    assert store.set_status("src:1", "applied") and not store.set_status("nope", "applied")
    assert store.statuses(["src:1", "src:2"]) == {"src:1": "applied", "src:2": "new"}
    rows = store.list_jobs(status="applied", cache_key="k1")
    assert rows[0][0].id == "src:1" and rows[0][2].score == 88


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
    assert "src:2" in md and "Fuente: Remotive" in md
