"""The seed data, the seed/clean logic and the evaluation maths.

No Ollama or Qdrant is used: a fake indexer records what would be indexed.
Postgres rows live in the rolled-back `session` fixture.
"""

from app.api.dto.incident import IncidentStatus
from app.repository.incident_repository import IncidentRepository
from app.scripts.evaluate_search import QUESTIONS, evaluate
from app.scripts.seed_data import (
    SCENARIOS,
    SEED_TAG,
    build_seed_incidents,
    scenario_keys,
    scenario_of,
)
from app.scripts.seed_incidents import clean_incidents, seed_incidents
from app.services.incident_search_service import IncidentHit


class FakeIndexer:
    def __init__(self):
        self.indexed = []
        self.deleted = []

    def index(self, incident):
        self.indexed.append(incident.id)

    def delete(self, incident_id):
        self.deleted.append(incident_id)


# --- the data ---


def test_there_are_ten_scenarios_of_ten_incidents_each():
    incidents = build_seed_incidents()
    assert len(SCENARIOS) == 10
    assert len(incidents) == 100
    for key in scenario_keys():
        assert sum(scenario_of(i.tags) == key for i in incidents) == 10


def test_ids_are_unique_and_stable_between_calls():
    first = build_seed_incidents()
    second = build_seed_incidents()
    assert len({i.id for i in first}) == 100
    assert [i.id for i in first] == [i.id for i in second]
    assert first == second


def test_every_incident_is_tagged_as_seed_and_with_its_scenario():
    for incident in build_seed_incidents():
        assert SEED_TAG in incident.tags
        assert scenario_of(incident.tags) in scenario_keys()


def test_titles_are_unique():
    titles = [i.title for i in build_seed_incidents()]
    assert len(set(titles)) == len(titles)


def test_data_is_varied_so_filters_have_something_to_filter():
    incidents = build_seed_incidents()
    assert len({i.severity for i in incidents}) == 4
    assert {i.status for i in incidents} == set(IncidentStatus)
    assert len({i.service for i in incidents}) >= 10


def test_resolved_incidents_have_root_cause_and_resolution_others_do_not():
    for incident in build_seed_incidents():
        resolved = incident.status == IncidentStatus.RESOLVED
        assert (incident.root_cause is not None) == resolved
        assert (incident.resolution is not None) == resolved
        assert (incident.resolved_at is not None) == resolved


def test_scenario_of_non_seed_incident_is_other():
    assert scenario_of(["deploy"]) == "other"


# --- seed and clean ---


def test_seed_saves_all_incidents_in_postgres_and_indexes_them(session):
    repo, indexer = IncidentRepository(session), FakeIndexer()
    assert seed_incidents(repo, indexer) == 100
    expected = {i.id: i for i in build_seed_incidents()}
    assert repo.get_many(expected) == expected
    assert set(indexer.indexed) == set(expected)


def test_seeding_twice_does_not_duplicate_anything(session):
    repo, indexer = IncidentRepository(session), FakeIndexer()
    seed_incidents(repo, indexer)
    seed_incidents(repo, indexer)
    ids = [i.id for i in build_seed_incidents()]
    assert len(repo.get_many(ids)) == 100
    assert len(set(indexer.indexed)) == 100  # re-indexed (upsert), never new ids


def test_clean_removes_seed_incidents_from_postgres_and_qdrant(session):
    repo, indexer = IncidentRepository(session), FakeIndexer()
    seed_incidents(repo, indexer)
    assert clean_incidents(repo, indexer) == 100
    ids = [i.id for i in build_seed_incidents()]
    assert repo.get_many(ids) == {}
    assert set(indexer.deleted) == set(ids)


def test_clean_leaves_real_incidents_alone(session):
    from tests.test_incident_repository import make_incident  # reuse the helper

    repo, indexer = IncidentRepository(session), FakeIndexer()
    real = make_incident()
    repo.add(real)
    seed_incidents(repo, indexer)
    clean_incidents(repo, indexer)
    assert repo.get(real.id) == real


# --- evaluation maths ---


class FakeSearch:
    """Returns hits whose scenario is chosen per question."""

    def __init__(self, scenario_for):
        self.scenario_for = scenario_for
        self.by_scenario = {}
        for incident in build_seed_incidents():
            self.by_scenario.setdefault(scenario_of(incident.tags), []).append(incident)

    def search(self, question, limit):
        incidents = self.by_scenario[self.scenario_for(question)][:limit]
        return [IncidentHit(incident=i, score=0.9) for i in incidents]


def test_perfect_search_scores_100_percent():
    expected = dict(QUESTIONS)
    result = evaluate(FakeSearch(lambda q: expected[q]))
    assert result.top1_accuracy == 1.0
    assert result.mean_precision == 1.0


def test_always_wrong_search_scores_zero():
    result = evaluate(FakeSearch(lambda q: "dns" if dict(QUESTIONS)[q] != "dns" else "oom"))
    assert result.top1_accuracy == 0.0
    assert result.mean_precision == 0.0


def test_half_right_search_is_reported_as_half():
    expected = dict(QUESTIONS)
    questions = QUESTIONS[:2]  # both expect db-pool
    calls = {"n": 0}

    def scenario_for(q):
        calls["n"] += 1
        return expected[q] if calls["n"] == 1 else "oom"

    result = evaluate(FakeSearch(scenario_for), questions=questions)
    assert result.top1_accuracy == 0.5


def test_every_question_points_at_a_real_scenario():
    assert {e for _, e in QUESTIONS} <= set(scenario_keys())
    assert len(QUESTIONS) >= 20
