from __future__ import annotations

from datetime import date

import pytest

from jobbot.config import SetupError
from jobbot.prefs import review_profile
from jobbot.profile import (detect_country, detect_name, detect_roles, detect_skills, experience_months,
                            extract_profile, read_cv)

CV = """JUAN PEREZ
Backend Engineer
Córdoba, Argentina | juan@example.com

EXPERIENCIA
Acme Corp - Backend Engineer          Mar 2021 - Presente
Built microservices in Golang and Kotlin on AWS (Lambda, DynamoDB). Docker, Kubernetes. Go services.
Globex - Software Developer           2019 - 2021
Node.js APIs with PostgreSQL, Redis. Overlaps with Acme in 2020 - 2021 side project: 2020 - 2021

EDUCACIÓN
Universidad Nacional de Córdoba      2013 - 2018
Ingeniería en Sistemas
"""
TODAY = date(2026, 11, 1)


def test_detect_skills_aliases_and_order():
    skills = detect_skills(CV)
    assert skills[0] == "Go"  # 'Golang' + 'Go services'
    for expected in ("Kotlin", "AWS", "Docker", "Kubernetes", "PostgreSQL", "Node.js", "DynamoDB", "Lambda"):
        assert expected in skills
    assert "Java" not in skills and "JavaScript" not in skills  # 'Kotlin'/'Node.js' no arrastran falsos positivos


def test_experience_merges_overlaps_and_skips_education():
    months = experience_months(CV, TODAY)
    # 2019-01 -> 2026-11 con el solapamiento de 2020-2021 unido; la universidad (2013-2018) no cuenta
    assert 7.5 * 12 <= months <= 8 * 12
    assert experience_months("Estudios\nUniversidad 2010 - 2015", TODAY) == 0


def test_roles_name_country():
    assert detect_roles(CV)[0] == "Backend Engineer"
    assert detect_name(CV) == "Juan Perez"
    assert detect_country(CV) == "Argentina"


def test_extract_profile_from_txt_and_errors(tmp_path):
    cv = tmp_path / "cv.txt"
    cv.write_text(CV, encoding="utf-8")
    p = extract_profile(cv, linkedin_url="https://linkedin.com/in/x", today=TODAY)
    assert p.name == "Juan Perez" and p.country == "Argentina" and p.seniority_level == "senior"
    assert "Go" in p.primary_stack and len(p.primary_stack) <= 8 and p.linkedin_url.endswith("/x")
    assert p.cv_hash
    with pytest.raises(SetupError):
        read_cv(tmp_path / "nope.pdf")
    bad = tmp_path / "cv.docx"
    bad.write_text("x")
    with pytest.raises(SetupError):
        read_cv(bad)


def test_review_profile_applies_answers(profile):
    answers = {"Tecnologías": "Go, Rust", "Stack principal": "Rust", "Años": "3,5", "Puestos": "Backend Engineer"}

    def ask(question, default):
        for key, value in answers.items():
            if question.startswith(key):
                return value
        return default

    p = review_profile(profile, ask)
    assert p.skills == ["Go", "Rust"] and p.primary_stack == ["Rust"]
    assert p.years_experience == 3.5 and p.seniority_level == "mid"
