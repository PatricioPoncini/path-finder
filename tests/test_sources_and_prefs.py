from __future__ import annotations

from jobbot import config
from jobbot.models import Preferences, Profile, html_to_text
from jobbot.prefs import default_regions, normalize_seniority, preferences_from_profile, run_wizard
from jobbot.sources.arbeitnow import Arbeitnow
from jobbot.sources.base import search_queries
from jobbot.sources.himalayas import Himalayas
from jobbot.sources.remoteok import RemoteOK
from jobbot.sources.remotive import Remotive
from jobbot.sources.weworkremotely import WeWorkRemotely

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


def test_prefs_roundtrip_and_cache_fingerprint(tmp_path, monkeypatch):
    monkeypatch.setenv("JOBBOT_HOME", str(tmp_path))
    prefs = Preferences(target_roles=["Data Analyst"], notes="solo startups")
    config.save_prefs(prefs)
    loaded = config.load_prefs()
    assert loaded.target_roles == ["Data Analyst"] and loaded.notes == "solo startups"
    other = Preferences(target_roles=["Data Analyst"], notes="otra cosa")
    assert loaded.scoring_fingerprint() != other.scoring_fingerprint()
    # campos que no afectan el scoring no invalidan la caché
    loaded.min_score = 99
    assert loaded.scoring_fingerprint() == prefs.scoring_fingerprint()
