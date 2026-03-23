from src.core.services.content import ContentService


def test_content_service_has_required_methods():
    service = ContentService()
    assert hasattr(service, "get_subjects")
    assert hasattr(service, "get_grades_for_subject")
    assert hasattr(service, "get_sections")
    assert hasattr(service, "get_topics")
    assert hasattr(service, "get_all_lessons")
    assert hasattr(service, "get_lessons")
