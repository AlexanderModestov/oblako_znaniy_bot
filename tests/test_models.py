from src.core.models import User, Region, School, Subject, Lesson


def test_user_model_has_required_fields():
    assert hasattr(User, "telegram_id")
    assert hasattr(User, "full_name")
    assert hasattr(User, "phone")
    assert hasattr(User, "email")
    assert hasattr(User, "region_id")
    assert hasattr(User, "school_id")
    assert hasattr(User, "subjects")


def test_lesson_model_has_required_fields():
    assert hasattr(Lesson, "subject_id")
    assert hasattr(Lesson, "grade")
    assert hasattr(Lesson, "section")
    assert hasattr(Lesson, "topic")
    assert hasattr(Lesson, "title")
    assert hasattr(Lesson, "lesson_type")
    assert hasattr(Lesson, "url")
    assert hasattr(Lesson, "search_vector")
    assert hasattr(Lesson, "embedding")


def test_region_model():
    assert hasattr(Region, "name")


def test_school_model():
    assert hasattr(School, "region_id")
    assert hasattr(School, "name")


def test_subject_model():
    assert hasattr(Subject, "name")
