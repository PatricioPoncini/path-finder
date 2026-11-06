from __future__ import annotations

from path_finder import config
from path_finder.models import Preferences, Profile, html_to_text
from path_finder.prefs import default_regions, normalize_seniority, preferences_from_profile, run_wizard
from path_finder.sources.arbeitnow import Arbeitnow
from path_finder.sources.base import search_queries
from path_finder.sources.himalayas import Himalayas
from path_finder.sources.jobicy import Jobicy
from path_finder.sources.remoteok import RemoteOK
from path_finder.sources.remotive import Remotive
from path_finder.sources.weworkremotely import WeWorkRemotely
from path_finder.sources.workingnomads import WorkingNomads

RSS = """<?xml version="1.0"?><rss><channel>
<item><title>Acme: Senior Go Engineer</title><region>USA Only</region><country></country>
<category>Back-End Programming</category><type>Full-Time</type>
<description>&lt;p&gt;Build &lt;b&gt;things&lt;/b&gt;&lt;/p&gt;</description>
<pubDate>Mon, 02 Nov 2026 10:00:00 +0000</pubDate><link>https://wwr.test/1</link><guid>https://wwr.test/1</guid></item>
<item><title>Globex: Backend Dev</title><region>Anywhere in the World</region>
<description>x</description><link>https://wwr.test/2</link><guid>https://wwr.test/2</guid></item>
</channel></rss>"""


def test_html_to_text():
    assert html_to_text("<p>Hola&nbsp;<b>mundo</b></p><ul><li>a</li><li>b</li></ul>") == "Hola mundo\n\n- a\n- b"


def test_remotive_parse():
    job = Remotive._parse({
        "id": 7, "url": "u", "title": " T ", "company_name": "C", "tags": ["go"], "salary": "$1",
        "publication_date": "2026-11-02T20:01:00", "candidate_required_location": "USA Only",
        "description": "<p>d</p>"})
    assert job.id == "remotive:7" and job.location_restrictions == ["USA Only"]
    assert job.posted_at.endswith("+00:00") and job.description == "d"


def test_remoteok_parse():
    job = RemoteOK._parse({"id": "9", "position": "A &amp; B", "company": "C", "url": "u",
                           "salary_min": 100000, "salary_max": 150000, "tags": ["go"], "date": "d"})
    assert job.title == "A & B" and job.salary == "$100,000-150,000" and job.location_restrictions == []


def test_himalayas_parse_short_id_and_restrictions():
    job = Himalayas._parse({"guid": "https://h/x", "title": "T", "companyName": "C", "applicationLink": "https://h/x",
                            "locationRestrictions": ["Argentina"], "pubDate": 1793837827, "categories": ["a"]})
    assert len(job.id) == len("himalayas:") + 10 and job.location_restrictions == ["Argentina"]
    assert job.posted_at.startswith("2026-")


def test_arbeitnow_parse():
    job = Arbeitnow._parse({"slug": "s", "title": "T", "company_name": "C", "url": "u", "remote": True,
                            "location": "Berlin", "created_at": 1793835037, "tags": ["x"], "job_types": ["y"]})
    assert job.id == "arbeitnow:s" and job.remote is True and job.tags == ["x", "y"]


def test_wwr_parse_feed():
    jobs = WeWorkRemotely.parse_feed(RSS)
    assert [j.company for j in jobs] == ["Acme", "Globex"]
    assert jobs[0].title == "Senior Go Engineer" and jobs[0].location_restrictions == ["USA Only"]
    assert jobs[1].location_restrictions == [] and jobs[0].description == "Build things"


def test_jobicy_parse_geo_and_lists():
    job = Jobicy._parse({"id": "159", "url": "https://jobicy.com/jobs/159", "jobTitle": "Python Dev", "companyName": "Doc",
                         "jobIndustry": "['Software Engineering']", "jobType": "['Full-Time']", "jobGeo": "LATAM,  Canada,  USA",
                         "jobLevel": "Senior", "jobDescription": "<p>x</p>", "pubDate": "2026-11-05T20:05:49+00:00"})
    assert job.id == "jobicy:159" and job.location_restrictions == ["LATAM", "Canada", "USA"]
    assert job.tags == ["Software Engineering", "Full-Time", "Senior"] and job.description == "x"
    assert Jobicy._parse({"id": "1", "jobGeo": "Anywhere"}).location_restrictions == []
    # la API real manda listas, no texto
    real = Jobicy._parse({"id": "2", "jobTitle": "X", "jobIndustry": ["Software Engineering"], "jobType": ["Full-Time"],
                          "jobGeo": ["Mexico", "LATAM"], "jobLevel": "Any"})
    assert real.tags == ["Software Engineering", "Full-Time"] and real.location_restrictions == ["Mexico", "LATAM"]


def test_workingnomads_parse():
    base = {"url": "https://www.workingnomads.com/job/go/1996233/", "title": "Dev", "company_name": "C",
            "tags": "go,aws", "category_name": "Development", "pub_date": "2026-11-05T03:10:45-05:00", "description": "<p>d</p>"}
    job = WorkingNomads._parse(dict(base, location="Europe, LATAM, APAC"))
    assert job.id == "workingnomads:1996233" and job.location_restrictions == ["Europe, LATAM, APAC"]
    assert job.tags == ["go", "aws", "Development"] and job.remote is True
    assert WorkingNomads._parse(dict(base, location="Global")).location_restrictions == []


def test_no_source_needs_keys_or_config():
    from path_finder.sources import SOURCES
    assert "adzuna" not in SOURCES and not any(hasattr(s, "requires_key") for s in SOURCES.values())


def test_search_queries_strip_seniority():
    prefs = Preferences(target_roles=["Senior Backend Engineer", "Sr Software Engineer", "backend engineer"])
    assert search_queries(prefs) == ["Backend Engineer", "Software Engineer"]
    assert search_queries(Preferences(target_roles=[], search_queries=["x"])) == ["x"]


def test_default_regions_and_seniority_aliases():
    assert "latam" in default_regions("Argentina") and "europe" in default_regions("Spain")
    assert "japan" in default_regions("Japan") and "latam" not in default_regions("Japan")
    assert normalize_seniority(["ssr", "SR", "semi-senior", "nope"]) == ["mid", "senior"]


def test_preferences_from_profile_and_wizard():
    profile = Profile(country="Argentina", seniority_level="mid", primary_stack=["Go"], roles_suited=["Backend Engineer"])
    prefs = preferences_from_profile(profile)
    assert prefs.seniority == ["mid", "senior"] and prefs.candidate_country == "Argentina"

    answers = {"Puestos": "Data Engineer", "Seniority": "sr", "Modalidad": "remote, hybrid", "País": "Chile"}

    def ask(question, default):
        for key, value in answers.items():
            if question.startswith(key):
                return value
        return default

    prefs = run_wizard(prefs, ask)
    assert prefs.target_roles == ["Data Engineer"] and prefs.seniority == ["senior"]
    assert prefs.work_modes == ["remote", "hybrid"] and "latam" in prefs.eligible_regions  # regiones recalculadas


def test_prefs_roundtrip_and_old_fields_ignored(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH_FINDER_HOME", str(tmp_path))
    prefs = Preferences(target_roles=["Data Analyst"], preferred_stack=["SQL"])
    config.save_prefs(prefs)
    loaded = config.load_prefs()
    assert loaded.target_roles == ["Data Analyst"] and loaded.preferred_stack == ["SQL"]
    # un preferences.yaml de la versión con Claude (model, notes...) sigue cargando
    config.prefs_path().write_text("target_roles: [QA]\nmodel: claude-haiku-5-5\nnotes: x\n", encoding="utf-8")
    assert config.load_prefs().target_roles == ["QA"]
