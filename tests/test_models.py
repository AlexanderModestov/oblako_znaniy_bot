from src.core.models import User, Region, School, Subject, Course, Section, Topic, Lesson, LessonLink


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
    assert hasattr(Lesson, "course_id")
    assert hasattr(Lesson, "section")
    assert hasattr(Lesson, "topic")
    assert hasattr(Lesson, "title")
    assert hasattr(Lesson, "url")
    assert hasattr(Lesson, "description")
    assert hasattr(Lesson, "search_vector")
    assert hasattr(Lesson, "embedding")


def test_region_model():
    assert hasattr(Region, "name")


def test_school_model():
    assert hasattr(School, "region_id")
    assert hasattr(School, "municipality")
    assert hasattr(School, "name")
    assert hasattr(School, "inn")


def test_subject_model():
    assert hasattr(Subject, "name")
    assert hasattr(Subject, "code")


def test_course_model():
    assert hasattr(Course, "name")
    assert hasattr(Course, "description")
    assert hasattr(Course, "actual")
    assert hasattr(Course, "deleted")
    assert hasattr(Course, "status_msh")


def test_section_model():
    assert hasattr(Section, "course_id")
    assert hasattr(Section, "name")
    assert hasattr(Section, "standard")


def test_topic_model():
    assert hasattr(Topic, "section_id")
    assert hasattr(Topic, "name")
    assert not hasattr(Topic, "standard")


def test_lesson_link_model():
    assert hasattr(LessonLink, "lesson_id")
    assert hasattr(LessonLink, "url")
