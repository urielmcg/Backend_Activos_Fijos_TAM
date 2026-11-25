from rest_framework.pagination import PageNumberPagination


class PaginacionEstandar(PageNumberPagination):
    """
    Paginación por número de página para las listas/tablas de la API.

    - Tamaño por defecto: REST_FRAMEWORK["PAGE_SIZE"] (50).
    - El cliente puede pedir otro tamaño con ?page_size=N, pero nunca más de
      max_page_size (100) para impedir volcados de tablas completas.
    - Los viewsets que alimentan dropdowns o que el frontend consume como
      array plano quedan con pagination_class = None (ver views/*.py).
    """

    page_size_query_param = "page_size"
    max_page_size = 100
