from django.db import DatabaseError, connection
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_GET

from config.celery import app as celery_app

OK = "ok"
UNREACHABLE = "unreachable"


def check_database() -> bool:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT PostGIS_Lib_Version()")
    except DatabaseError:
        return False
    return True


def check_redis() -> bool:
    try:
        with celery_app.connection_for_write() as conn:
            conn.ensure_connection(max_retries=1, timeout=2)
    except Exception:
        return False
    return True


def check_worker() -> bool:
    try:
        replies = celery_app.control.ping(timeout=1.0)
    except Exception:
        return False
    return bool(replies)


@require_GET
def health(request: HttpRequest) -> JsonResponse:
    """Report whether PostGIS, Redis and a Celery worker are reachable."""
    components = {
        "database": check_database(),
        "redis": check_redis(),
        "worker": check_worker(),
    }
    all_ok = all(components.values())
    body = {"status": OK if all_ok else "error"} | {
        name: OK if up else UNREACHABLE for name, up in components.items()
    }
    return JsonResponse(body, status=200 if all_ok else 503)
