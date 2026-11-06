from __future__ import annotations

from jobbot.filters import apply_filters, norm_title, role_phrases
from jobbot.lang import detect_language, normalize_languages
from jobbot.sources import active_sources
from jobbot.sources.getonbrd import GetOnBoard, spanish_queries

from .conftest import make_job

ES = ("Buscamos un desarrollador backend con experiencia en Go y AWS para sumarse a nuestro equipo. "
      "Requisitos: más de tres años de experiencia, conocimientos de bases de datos y trabajo en equipo. "
      "Ofrecemos un entorno remoto para toda la región.")
EN = ("We are looking for a backend engineer with experience in Go and AWS to join our team. "
      "Requirements: more than three years of experience, knowledge of databases and a passion for the work "
      "that you will do with us in a remote environment.")
IT = ("Cerchiamo uno sviluppatore backend con esperienza in Go e AWS per entrare nel nostro team. "
      "Requisiti: più di tre anni di esperienza, conoscenza dei database e lavoro di squadra nella nostra azienda.")


def test_detect_language():
    assert detect_language(ES) == "es" and detect_language(EN) == "en" and detect_language(IT) == "it"
    assert detect_language("Go AWS") == ""  # muy corto: sin veredicto
    assert normalize_languages(["Español", "english", "xx", "ES"]) == ["es", "en"]


def test_language_filter_drops_other_languages_but_keeps_unknown(profile, prefs):
    prefs.job_languages = ["es"]
    jobs = [make_job(1, description=ES), make_job(2, description=EN), make_job(3, description=IT),
            make_job(4, description="Go AWS")]
    res = apply_filters(jobs, profile, prefs)
    assert [j.id for j in res.kept] == ["src:1", "src:4"]
    assert res.dropped["idioma de la oferta (en)"] == 1 and res.dropped["idioma de la oferta (it)"] == 1
    prefs.job_languages = []  # sin preferencia: no filtra
    assert len(apply_filters(jobs, profile, prefs).kept) == 4


def test_spanish_titles_and_backend_hyphen(profile, prefs):
    assert norm_title("Back-end Engineer") == "backend engineer"
    prefs.job_languages = ["es"]
    assert {"desarrollador backend", "ingeniero de software"} <= role_phrases(prefs)
    jobs = [make_job(1, title="Desarrollador Backend", description=ES),
            make_job(2, title="Back-end Engineer", description=ES),
            make_job(3, title="Diseñador Gráfico", description=ES)]
    assert [j.id for j in apply_filters(jobs, profile, prefs).kept] == ["src:1", "src:2"]


def test_getonbrd_parse_and_auto_activation(prefs):
    job = GetOnBoard._parse({
        "id": "senior-go-acme", "links": {"public_url": "https://www.getonbrd.com/jobs/senior-go-acme"},
        "attributes": {
            "title": "Senior Go", "description": "<p>Hola</p>", "functions": "<p>Hacer cosas</p>",
            "remote_modality": "fully_remote", "countries": ["Remote"], "lang": "es",
            "min_salary": 3000, "max_salary": 4000, "published_at": 1793880347,
            "tags": {"data": [{"attributes": {"name": "Go"}}]},
            "company": {"data": {"attributes": {"name": "Acme"}}}}})
    assert job.id == "getonbrd:senior-go-acme" and job.company == "Acme" and job.tags == ["Go"]
    assert job.remote is True and job.language == "es" and job.salary == "US$3000-4000/mes"
    assert job.description == "Hola\n\nHacer cosas" and job.posted_at.startswith("2026-")

    prefs.sources = ["remotive"]
    assert active_sources(prefs) == ["remotive"]
    prefs.job_languages = ["es"]
    assert active_sources(prefs) == ["remotive", "getonbrd"]
    assert spanish_queries(prefs) == ["desarrollador software", "desarrollador backend"]
