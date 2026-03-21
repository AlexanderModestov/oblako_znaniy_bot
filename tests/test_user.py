from src.core.services.user import UserService


def test_user_service_has_required_methods():
    service = UserService()
    assert hasattr(service, "get_by_telegram_id")
    assert hasattr(service, "create_user")
    assert hasattr(service, "search_regions")
    assert hasattr(service, "search_schools")
    assert hasattr(service, "get_user_count")
