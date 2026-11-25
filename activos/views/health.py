from django.http import JsonResponse
from django.db import connection


def health_check(request):
    """
    Endpoint ligero para health checks y cron de keep-alive (Render no duerme).
    Verifica conectividad a la base de datos; si falla, devuelve 503.
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        db_ok = True
    except Exception:
        db_ok = False

    status_code = 200 if db_ok else 503
    return JsonResponse(
        {"status": "ok" if db_ok else "degraded", "database": db_ok},
        status=status_code,
    )
