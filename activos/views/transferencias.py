import io
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import FileResponse
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication
from django_filters.rest_framework import DjangoFilterBackend
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT

from ..models import (
    Transferencia, Activo, Designacion,
    Regional, Gerencia, Cargo, Ubicacion, User
)
from ..serializers import TransferenciaSerializer
from ..permissions import EsAdminRegionalOSuperior
from ..utils_seguridad import exigir_turnstile
from .auditoria import AuditoriaApiMixin

class TransferenciaViewSet(AuditoriaApiMixin, viewsets.ModelViewSet):
    authentication_classes = [JWTAuthentication]
    permission_classes = [EsAdminRegionalOSuperior]
    
    queryset = Transferencia.objects.select_related(
        'activo', 'emisor', 'receptor', 'ubicacion_origen', 'ubicacion_destino'
    ).all().order_by('-fecha')
    
    serializer_class = TransferenciaSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['activo__codigo_tamep', 'tipo']
    search_fields = ['num_acta', 'activo__codigo_tamep', 'emisor__username', 'receptor__username']

    @action(detail=False, methods=['get'], url_path='buscar-activo')
    def buscar_activo_por_codigo(self, request):
        """
        Búsqueda Robusta: Valida existencia y retorna la jerarquía completa del custodio actual.
        """
        codigo_tamep = request.query_params.get('codigo')
        if not codigo_tamep:
            return Response({'error': 'Código TAMEP requerido'}, status=400)
        
        try:

            asignacion = Designacion.objects.select_related(
                'activo', 'usuario', 'regional', 'gerencia', 'cargo', 'ubicacion'
            ).get(activo__codigo_tamep=codigo_tamep, esta_activa=True)

            return Response({
                "activo_id": asignacion.activo.id,
                "descripcion": f"{asignacion.activo.nombre_especifico} | S/N: {asignacion.activo.serie}",
                "codigo_tamep": asignacion.activo.codigo_tamep,
                "ubicacion_actual_id": asignacion.ubicacion.id if asignacion.ubicacion else None,
                "ubicacion_actual_nombre": asignacion.ubicacion.nombre_sala if asignacion.ubicacion else "Sin Ubicación",
                

                "emisor": {
                    "id": asignacion.usuario.id,
                    "nombre": asignacion.usuario.get_full_name(),
                    "regional": asignacion.regional.nombre if asignacion.regional else None,
                    "gerencia": asignacion.gerencia.nombre if asignacion.gerencia else None,
                    "cargo": asignacion.cargo.nombre if asignacion.cargo else None,
                }
            })
            
        except Designacion.DoesNotExist:

            if Activo.objects.filter(codigo_tamep=codigo_tamep).exists():
                return Response({'error': 'El activo está en almacén (Disponible). Use Designación Directa.'}, status=400)
            return Response({'error': 'Activo no encontrado en el sistema.'}, status=404)

    def create(self, request, *args, **kwargs):
        # Turnstile antes de cualquier escritura (POST /api/transferencias/).
        guard = exigir_turnstile(request)
        if guard:
            return guard
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        """
        Lógica de Negocio Atómica:
        La atomicidad está en Transferencia.save() (transaction.atomic interno).
        Aquí capturamos excepciones para retornar JSON en vez de 500 HTML.
        """
        from rest_framework.exceptions import ValidationError as DRFValidationError
        from django.db import IntegrityError
        try:
            # super() == AuditoriaApiMixin: serializer.save() + LogEntry.
            super().perform_create(serializer)
        except DjangoValidationError as e:
            if hasattr(e, 'message_dict'):
                raise DRFValidationError(e.message_dict)
            raise DRFValidationError({'detail': e.messages if hasattr(e, 'messages') else [str(e)]})
        except IntegrityError as e:
            raise DRFValidationError({'detail': str(e)})
        except (ValueError, TypeError, AttributeError) as e:
            raise DRFValidationError({'detail': str(e)})


    
    @action(detail=True, methods=['get'])
    def generar_pdf(self, request, pk=None):
        """Genera el Acta de Entrega-Recepción en PDF."""
        trans = self.get_object()

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter,
                                topMargin=2*cm, bottomMargin=2*cm,
                                leftMargin=2*cm, rightMargin=2*cm)

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle('Title2', parent=styles['Title'],
                                     fontSize=14, alignment=TA_CENTER, spaceAfter=6)
        subtitle_style = ParagraphStyle('Sub', parent=styles['Normal'],
                                        fontSize=10, alignment=TA_CENTER,
                                        textColor=colors.grey, spaceAfter=12)
        heading_style = ParagraphStyle('Head', parent=styles['Heading3'],
                                       fontSize=11, spaceAfter=4, spaceBefore=10,
                                       textColor=colors.HexColor('#1a237e'))
        normal = styles['Normal']
        normal.fontSize = 9
        normal.leading = 12

        elements = []

        # Encabezado
        elements.append(Paragraph("ACTA DE ENTREGA - RECEPCIÓN", title_style))
        tipo_label = "TRANSFERENCIA" if trans.tipo == 'TR' else "DEVOLUCIÓN"
        elements.append(Paragraph(f"{tipo_label} DE ACTIVOS — {trans.num_acta}", subtitle_style))
        elements.append(Spacer(1, 0.3*cm))

        # Datos del activo
        elements.append(Paragraph("1. Identificación del Bien", heading_style))
        activo_data = [
            ['Código TAMEP', trans.activo.codigo_tamep if trans.activo else 'N/A'],
            ['Descripción', trans.activo.nombre_especifico if trans.activo else 'N/A'],
            ['Nro. Serie', trans.activo.serie if trans.activo and trans.activo.serie else 'S/N'],
        ]
        t = Table(activo_data, colWidths=[4*cm, 13*cm])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#e8eaf6')),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('PADDING', (0, 0), (-1, -1), 6),
        ]))
        elements.append(t)
        elements.append(Spacer(1, 0.4*cm))

        # Emisor y Receptor
        elements.append(Paragraph("2. Partes Involucradas", heading_style))
        partes_data = [
            ['', 'EMISOR (Entrega)', 'RECEPTOR (Recibe)'],
            ['Funcionario',
             trans.emisor.get_full_name() if trans.emisor else 'N/A',
             trans.receptor.get_full_name() if trans.receptor else 'N/A'],
            ['Regional',
             trans.reg_emisor.nombre if trans.reg_emisor else 'N/A',
             trans.reg_receptor.nombre if trans.reg_receptor else 'N/A'],
            ['Gerencia',
             trans.ger_emisor.nombre if trans.ger_emisor else 'N/A',
             trans.ger_receptor.nombre if trans.ger_receptor else 'N/A'],
            ['Cargo',
             trans.car_emisor.nombre if trans.car_emisor else 'N/A',
             trans.car_receptor.nombre if trans.car_receptor else 'N/A'],
        ]
        t2 = Table(partes_data, colWidths=[3*cm, 7*cm, 7*cm])
        t2.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a237e')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('BACKGROUND', (0, 1), (0, -1), colors.HexColor('#e8eaf6')),
            ('FONTNAME', (0, 1), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('PADDING', (0, 0), (-1, -1), 6),
        ]))
        elements.append(t2)
        elements.append(Spacer(1, 0.4*cm))

        # Detalles de la transferencia
        elements.append(Paragraph("3. Detalles del Movimiento", heading_style))
        fecha_str = trans.fecha.strftime('%d/%m/%Y %H:%M') if trans.fecha else 'N/A'
        detalle_data = [
            ['Tipo de Operación', tipo_label],
            ['Fecha', fecha_str],
            ['Ubicación Origen', trans.ubicacion_origen.nombre_sala if trans.ubicacion_origen else 'N/A'],
            ['Ubicación Destino', trans.ubicacion_destino.nombre_sala if trans.ubicacion_destino else 'N/A'],
            ['Motivo / Justificación', trans.motivo or 'N/A'],
        ]
        t3 = Table(detalle_data, colWidths=[4*cm, 13*cm])
        t3.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#e8eaf6')),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('PADDING', (0, 0), (-1, -1), 6),
        ]))
        elements.append(t3)
        elements.append(Spacer(1, 1.5*cm))

        # Firmas
        elements.append(Paragraph("4. Firmas de Conformidad", heading_style))
        elements.append(Spacer(1, 1.5*cm))
        firma_data = [
            ['_________________________', '_________________________', '_________________________'],
            [trans.emisor.get_full_name() if trans.emisor else 'Emisor',
             trans.receptor.get_full_name() if trans.receptor else 'Receptor',
             'Vo. Bo. Administración'],
            ['ENTREGA', 'RECIBE', 'AUTORIZA'],
        ]
        t4 = Table(firma_data, colWidths=[5.6*cm, 5.6*cm, 5.6*cm])
        t4.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('FONTNAME', (0, 2), (-1, 2), 'Helvetica-Bold'),
            ('TOPPADDING', (0, 0), (-1, 0), 0),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 2),
        ]))
        elements.append(t4)

        doc.build(elements)
        buffer.seek(0)

        filename = f"Acta_{trans.num_acta}.pdf"
        return FileResponse(buffer, as_attachment=False, filename=filename,
                            content_type='application/pdf')

    @action(detail=False, methods=['get'])
    def estructura_personal(self, request):
        """Devuelve el personal con anotaciones de jerarquía usando F()"""
        personal = User.objects.filter(is_active=True).annotate(
            reg_id=F('perfil__regional_id'),
            reg_nom=F('perfil__regional__nombre'),
            ger_id=F('perfil__gerencia_id'),
            ger_nom=F('perfil__gerencia__nombre')
        ).values('id', 'first_name', 'last_name', 'reg_id', 'reg_nom', 'ger_id', 'ger_nom')
        
        return Response(list(personal))

    @action(detail=False, methods=['get'])
    def listar_ubicaciones(self, request):
        return Response(list(Ubicacion.objects.values('id', 'nombre_sala')))
    @action(detail=False, methods=['get'])
    def regionales(self, request):
        # list() explícito: JSONRenderer serializa un ValuesQuerySet igual,
        # pero devolver el queryset crudo deja `response.data` sin materializar
        # (rompe los dropdowns que consumen el array plano).
        return Response(list(Regional.objects.values('id', 'nombre')))

    @action(detail=False, methods=['get'])
    def gerencias(self, request):
        reg_id = request.query_params.get('regional')
        return Response(list(Gerencia.objects.filter(regional_id=reg_id).values('id', 'nombre')))

    @action(detail=False, methods=['get'])
    def cargos(self, request):
        ger_id = request.query_params.get('gerencia')
        return Response(list(Cargo.objects.filter(gerencia_id=ger_id).values('id', 'nombre')))

    @action(detail=False, methods=['get'])
    def usuarios(self, request):
        cargo_id = request.query_params.get('cargo')
        users = User.objects.filter(perfil__cargo_id=cargo_id, is_active=True)
        data = [{"id": u.id, "nombre_completo": u.get_full_name()} for u in users]
        return Response(data)