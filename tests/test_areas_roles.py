from __future__ import annotations

import re
from pathlib import Path

import httpx
import pytest

from path_finder import areas as areas_mod
from path_finder import config
from path_finder.config import SetupError
from path_finder.filters import apply_filters, role_forms_split, role_in_title
from path_finder.models import Preferences, Profile
from path_finder.prefs import menu_presets, pick_roles, run_wizard
from path_finder.profile import detect_areas, extract_profile
from path_finder.ranking import rank_job
from path_finder.roles import level_fit, resolve_role, resolve_roles, title_level
from path_finder.sources.base import search_queries
from path_finder.sources.getonbrd import GetOnBoard
from path_finder.sources.remoteok import RemoteOK
from path_finder.sources.weworkremotely import GENERAL_FEED, feeds_for

from .conftest import make_job

FIX = Path(__file__).parent / "fixtures"
PM_DESC = ("Own the product roadmap and discovery for our B2B SaaS platform. Run A/B testing, define OKRs, "
           "prioritization and backlog with stakeholders. SQL and Amplitude a plus.")


def pm_setup():
    profile = extract_profile(FIX / "cv_pm.txt")
    prefs = Preferences(target_roles=["Product Manager", "Product Owner"], seniority=["senior"],
                        candidate_country="Argentina", areas=["product"],
                        eligible_regions=["worldwide", "anywhere", "argentina", "latam"])
    return profile, prefs


# --- paquetes de área ---------------------------------------------------------------------------
def test_builtin_areas_are_valid():
    found = areas_mod.load_areas()
    assert {"tech", "product", "design", "data"} <= set(found)
    alias_to_name = {}
    for area in found.values():
        assert area.skills and area.roles and set(area.weights) == {"primary", "other", "preferred", "title", "seniority"}
        assert area.concepts <= set(area.skills), "%s: concepts fuera de skills: %s" % (area.id, area.concepts - set(area.skills))
        for role in area.roles:
            assert role.patterns, "%s/%s sin patterns" % (area.id, role.title)
            for p in role.patterns:
                re.compile(p)
        for name, aliases in area.skills.items():
            for term in [name] + aliases:
                owner = alias_to_name.setdefault(term.lower(), name)
                assert owner == name, "alias %r apunta a %r y a %r" % (term, owner, name)


def test_user_areas_add_and_override(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH_FINDER_HOME", str(tmp_path))
    areas_mod.clear_cache()
    (tmp_path / "areas").mkdir()
    (tmp_path / "areas" / "legal.yaml").write_text(
        "id: legal\nlabel: Legal\nskills: {Contratos: [contratos comerciales]}\n"
        "roles:\n  - title: Abogado\n    patterns: ['abogad[oa]']\n", encoding="utf-8")
    try:
        loaded = areas_mod.load_areas()
        assert "legal" in loaded and "tech" in loaded
        assert "Contratos" in areas_mod.vocabulary()[0]
        (tmp_path / "areas" / "bad.yaml").write_text("id: bad\nlabel: x\n", encoding="utf-8")
        areas_mod.clear_cache()
        with pytest.raises(SetupError):
            areas_mod.load_areas()
    finally:
        areas_mod.clear_cache()


# --- niveles y roles comunes ---------------------------------------------------------------------
def test_resolve_common_roles():
    r = resolve_role("Sr PM")
    assert (r.title, r.level, r.area) == ("Product Manager", "senior", "product")
    assert resolve_role("PO").title == "Product Owner" and resolve_role("Sr PO").level == "senior"
    assert (resolve_role("TL").title, resolve_role("TL").level) == ("Tech Lead", "lead")
    assert (resolve_role("Expert").title, resolve_role("Expert").level) == ("Software Engineer", "expert")
    assert (resolve_role("Sr Software Engineer").title, resolve_role("Sr Software Engineer").level) == ("Software Engineer", "senior")
    assert resolve_role("semi senior pm").level == "mid"
    r = resolve_role("Chef de cocina")
    assert r.title == "Chef de cocina" and not r.known
    assert resolve_roles(["Sr PM", "PO"]) == (["Product Manager", "Product Owner"], ["senior"], ["product"])


def test_title_level_does_not_treat_manager_as_level():
    assert title_level("Product Manager") == "" and title_level("Senior Product Manager") == "senior"
    assert title_level("Staff Software Engineer") == "expert" and title_level("Tech Lead") == "lead"
    assert title_level("Engineering Manager") == "lead" and title_level("Director of Product") == "head"
    assert title_level("Semi Senior Backend") == "mid" and title_level("Desarrollador SSR") == "mid"
    assert title_level("Junior QA") == "junior"
    assert level_fit("expert", ["mid", "senior"]) == ("above", 2)
    assert level_fit("junior", ["mid", "senior"]) == ("below", 1)
    assert level_fit("", ["senior"])[0] == "unclear"


def test_search_queries_keep_role_names_that_look_like_levels():
    prefs = Preferences(target_roles=["Tech Lead", "Head of Product", "Sr Software Engineer"])
    assert search_queries(prefs) == ["Tech Lead", "Head of Product", "Software Engineer"]


def test_pick_roles_from_menu_and_text():
    menu = menu_presets(["product"])
    assert [p.area for p in menu] == ["product"] * len(menu)
    sr_pm = next(i for i, p in enumerate(menu, 1) if p.label == "Sr PM")
    titles, levels, found, unleveled = pick_roles([str(sr_pm), "PO"], menu)
    assert titles == ["Product Manager", "Product Owner"] and levels == ["senior"] and unleveled


def test_wizard_roles_areas_and_seniority(prefs):
    answers = {"Áreas": "product", "Puestos": "Sr PM", "Modalidad": "remote", "País": "Chile"}

    def ask(question, default):
        for key, value in answers.items():
            if question.startswith(key):
                return value
        return default

    out = run_wizard(prefs, ask)
    assert out.areas == ["product"] and out.target_roles == ["Product Manager"]
    assert out.seniority == ["senior"]  # "Sr PM" fija el nivel y ninguna respuesta lo pisa


# --- perfil por áreas ----------------------------------------------------------------------------
@pytest.mark.parametrize("cv,area,role,skill", [
    ("cv_pm.txt", "product", "Product Manager", "Roadmapping"),
    ("cv_designer.txt", "design", "Product Designer", "Figma"),
    ("cv_data.txt", "data", "Data Scientist", "Python"),
])
def test_profile_detects_area_role_and_skills(cv, area, role, skill):
    p = extract_profile(FIX / cv)
    assert p.areas[0] == area and role in p.roles_suited and skill in p.skills
    assert p.primary_stack and len(p.primary_stack) <= 8
    assert p.country in ("Argentina", "Uruguay")


def test_dev_cv_is_still_tech(tmp_path):
    cv = tmp_path / "cv_dev.txt"
    cv.write_text("ANA DEV\nBackend Engineer\nCórdoba, Argentina\n\nEXPERIENCIA\nAcme - Backend Engineer   2019 - Presente\n"
                  "Go, Kotlin, AWS Lambda, DynamoDB, Docker, Kubernetes, PostgreSQL y microservicios. Go services.\n",
                  encoding="utf-8")
    p = extract_profile(cv)
    assert p.areas == ["tech"] and "Go" in p.primary_stack and "Microservices" not in p.primary_stack
    assert detect_areas("nada que ver", []) == []


def test_suggested_terms_are_proposed_not_added():
    text = "Trabajé con HubSpot y con Salesforce. Usamos HubSpot a diario; luego Salesforce y SAP, SAP y más. " * 2
    p = extract_profile_text(text)
    assert {"HubSpot", "Salesforce"} <= set(p.suggested_terms) and "HubSpot" not in p.skills


def extract_profile_text(text):
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "cv.txt"
        f.write_text("NOMBRE APELLIDO\nAnalista\n\n" + text, encoding="utf-8")
        return extract_profile(f)


# --- ranking y filtros para otras áreas ---------------------------------------------------------
def test_pm_title_is_not_penalized_as_lead_and_beats_unrelated_job():
    profile, prefs = pm_setup()
    good = rank_job(make_job(1, title="Senior Product Manager", description=PM_DESC), profile, prefs)
    assert good.seniority_fit == "good" and not any("seniority" in g for g in good.gaps)
    assert good.score >= 70
    weak = rank_job(make_job(2, title="Senior Product Manager", description="Join us. Great culture."), profile, prefs)
    assert good.score > weak.score + 20


def test_must_have_missing_penalizes_and_present_rewards():
    profile, prefs = pm_setup()
    base = rank_job(make_job(1, title="Product Manager", description=PM_DESC), profile, prefs)
    prefs.must_have = ["Fintech"]
    missing = rank_job(make_job(1, title="Product Manager", description=PM_DESC), profile, prefs)
    present = rank_job(make_job(1, title="Product Manager", description=PM_DESC + " Fintech payments."), profile, prefs)
    assert missing.score < base.score < present.score
    assert any("imprescindibles" in g for g in missing.gaps)


def test_title_weight_comes_from_the_area():
    profile, prefs = pm_setup()
    dev_profile = Profile(skills=["Go"], primary_stack=["Go"], years_experience=5)
    dev_prefs = Preferences(target_roles=["Software Engineer"], seniority=["senior"], areas=["tech"],
                            eligible_regions=["worldwide"])
    pm = rank_job(make_job(1, title="Product Manager", description="x"), profile, prefs)
    dev = rank_job(make_job(2, title="Software Engineer", description="x"), dev_profile, dev_prefs)
    assert pm.score - dev.score == 10 + 0  # title 20 (product) vs 10 (tech); mismo resto


def test_role_aliases_and_short_alias_case_sensitivity():
    prefs = Preferences(target_roles=["Product Manager", "Product Owner"], areas=["product"], job_languages=["es"])
    phrases, shorts = role_forms_split(prefs)
    assert "gerente de producto" in phrases and {"PM", "PO"} <= shorts
    assert role_in_title("Outsystems Consultant / PM", phrases, shorts)
    assert role_in_title("Gerente de Producto Senior", phrases, shorts)
    assert not role_in_title("Software Development Manager", phrases, shorts)  # 'pm' dentro de 'development'


def test_product_filter_does_not_keep_sales_or_support_managers():
    profile, prefs = pm_setup()
    prefs.primary = None
    profile.primary_stack = ["SaaS", "B2B"]
    jobs = [make_job(1, title="Senior Product Manager", description=PM_DESC),
            make_job(2, title="Customer Success Manager SaaS", description=PM_DESC),
            make_job(3, title="Sales Manager B2B", description=PM_DESC),
            make_job(4, title="Fintech Product Lead", description=PM_DESC)]
    prefs.must_have = ["Fintech"]
    kept = [j.title for j in apply_filters(jobs, profile, prefs).kept]
    assert kept == ["Senior Product Manager", "Fintech Product Lead"]


# --- fuentes por área -----------------------------------------------------------------------------
def test_wwr_feeds_follow_areas():
    assert feeds_for(Preferences(areas=["product"])) == [GENERAL_FEED, "https://weworkremotely.com/categories/remote-product-jobs.rss"]
    tech = feeds_for(Preferences(areas=[]))
    assert any("programming" in u for u in tech) and not any("product" in u for u in tech)
    both = feeds_for(Preferences(areas=["product", "design"]))
    assert any("design" in u for u in both) and any("product" in u for u in both)


def test_remoteok_requests_one_query_per_area_tag():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.params.get("tag"))
        return httpx.Response(200, json=[{"legal": "x"}, {"id": "1", "position": "PM", "company": "C", "url": "u"}])

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        jobs = RemoteOK().fetch(Preferences(areas=["product"]), client)
    assert seen == [None, "product-manager"] and [j.id for j in jobs] == ["remoteok:1"]


def test_getonbrd_categories_and_modality():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        item = lambda i, mod: {"id": "j%s" % i, "links": {"public_url": "u"}, "attributes": {
            "title": "Diseñador UX", "remote_modality": mod, "countries": ["Chile"]}}
        return httpx.Response(200, json={"data": [item(1, "fully_remote"), item(2, "hybrid"), item(3, "remote_local")],
                                         "meta": {"total_pages": 1}})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        jobs = GetOnBoard().fetch(Preferences(areas=["design"], target_roles=["UX/UI Designer"]), client)
    assert any(p.endswith("/categories/design-ux/jobs") for p in seen)
    by_id = {j.id: j.remote for j in jobs}
    assert by_id == {"getonbrd:j1": True, "getonbrd:j2": False, "getonbrd:j3": None}
