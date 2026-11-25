import io
import re

from django.db import IntegrityError, transaction
from django.db.models import Max
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.html import escape
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER

from ..models import Activo, Designacion, Regional, BajaActivo, User
from ..serializers import BajaActivoSerializer, RegionalSerializer
from ..permissions import EsAdminOSuperior
from ..utils_seguridad import exigir_turnstile
from .auditoria import AuditoriaApiMixin
from django.contrib.admin.models import ADDITION


def generar_num_baja():
    """
    Correlativo del acta de baja: BJA-2026-0001.
    Sigue el mismo patrón que el ticket de SolicitudServicio (TKT-2026-XXXX).
    """
    anio = timezone.now().year
    ultimo = (
        BajaActivo.objects.filter(num_baja__contains=f"-{anio}-")
        .aggregate(Max("num_baja"))["num_baja__max"]
    )
    if ultimo:
        match = re.search(r"-(\d+)$", ultimo)
        numero = int(match.group(1)) + 1 if match else 1
    else:
        numero = 1
    return f"BJA-{anio}-{str(numero).zfill(4)}"


class BajaActivoViewSet(AuditoriaApiMixin, viewsets.ModelViewSet):
    authentication_classes = [JWTAuthentication]
    permission_classes = [EsAdminOSuperior]
    queryset = BajaActivo.objects.select_related('activo', 'solicitante').all()
    serializer_class = BajaActivoSerializer

    @action(detail=False, methods=['get'])
    def datos_formulario(self, request):
        """
        Carga masiva de parámetros para Vue.
        """
        regionales = Regional.objects.all()
        encargados = User.objects.filter(is_active=True, is_staff=True).select_related('perfil')

        return Response({
            "regionales": RegionalSerializer(regionales, many=True).data,
            "usuarios": [
                {
                    "id": u.id,
                    "nombre_completo": u.get_full_name() or u.username,
                    # El frontend filtra los usuarios por esta regional.
                    # Si el perfil no tiene regional asignada, el usuario no
                    # aparecerá en ningún filtro.
                    "regional_id": u.perfil.regional_id if hasattr(u, "perfil") else None,
                }
                for u in encargados
            ]
        })

    @transaction.atomic
    def perform_create(self, serializer):
        """
        PROCESO ROBUSTO DE DESINCORPORACIÓN:
        1. Crea el registro de Baja.
        2. Cierra cualquier Designación/Custodia activa.
        3. Cambia el estado del Activo a 'Baja'.

        super() == AuditoriaApiMixin: serializer.save() + LogEntry.
        """
        super().perform_create(serializer)

    @action(detail=True, methods=['post'])
    def procesar_baja(self, request, pk=None):
        """
        POST /api/operacion-baja/{id}/procesar_baja/

        Desincorporación definitiva del activo (frontend: RealizarBaja.vue).

        OJO: el `pk` de la URL es el ID del ACTIVO (no el del registro de baja)
        y el payload llega en multipart con los nombres del frontend:
        regional_id, usuario_id, motivo y documento (PDF, opcional).

        Efectos de dominio (atómicos, vía BajaActivo.save()):
        1. Crea el registro de baja con su correlativo.
        2. Cierra la designación/custodia activa.
        3. Pasa el activo a situación 'Baja', estado físico 'Malo' y sin ubicación.
        4. La señal registrar_historial_estado deja el rastro en el historial.
        """
        guard = exigir_turnstile(request)
        if guard:
            return guard

        # No usamos self.get_object(): el queryset es de BajaActivo y el
        # frontend envía el id del Activo.
        activo = get_object_or_404(Activo, pk=pk)

        if activo.situacion_activo == "Baja" or BajaActivo.objects.filter(activo=activo).exists():
            return Response(
                {"detail": f"El activo {activo.codigo_tamep} ya ha sido desincorporado del sistema."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        errores = {}
        regional_id = request.data.get("regional_id")
        usuario_id = request.data.get("usuario_id")
        motivo = (request.data.get("motivo") or "").strip()
        documento = request.data.get("documento")

        if not regional_id:
            errores["regional_id"] = ["La regional administrativa es obligatoria."]
        if not usuario_id:
            errores["usuario_id"] = ["El responsable que autoriza la baja es obligatorio."]
        if not motivo:
            errores["motivo"] = ["El motivo de la baja es obligatorio."]

        regional = None
        if regional_id:
            try:
                regional = Regional.objects.get(pk=regional_id)
            except (Regional.DoesNotExist, TypeError, ValueError):
                errores["regional_id"] = ["La regional administrativa indicada no existe."]

        usuario = None
        if usuario_id:
            try:
                usuario = User.objects.get(pk=usuario_id)
            except (User.DoesNotExist, TypeError, ValueError):
                errores["usuario_id"] = ["El responsable de la baja indicado no existe."]
            else:
                if not usuario.is_active:
                    errores["usuario_id"] = ["El responsable de la baja está inactivo."]
                elif (
                    regional
                    and hasattr(usuario, "perfil")
                    and usuario.perfil.regional_id
                    and usuario.perfil.regional_id != regional.id
                ):
                    errores["usuario_id"] = [
                        "El responsable no pertenece a la regional administrativa indicada."
                    ]

        if documento in (None, ""):
            documento = None
        elif not getattr(documento, "name", "").lower().endswith(".pdf"):
            errores["documento"] = ["El documento de respaldo debe ser un archivo PDF."]

        if errores:
            return Response(errores, status=status.HTTP_400_BAD_REQUEST)

        descripcion_tecnica = (
            f"Baja autorizada por {usuario.get_full_name() or usuario.username} "
            f"(Regional {regional.nombre}).\nJustificación técnica: {motivo}"
        )

        try:
            baja = BajaActivo.objects.create(
                activo=activo,
                solicitante=usuario,
                num_baja=generar_num_baja(),
                motivo=motivo,
                descripcion_tecnica=descripcion_tecnica,
                documento_respaldo=documento or "",
            )
        except IntegrityError:
            return Response(
                {"detail": "No se pudo registrar la baja: correlativo o registro duplicado."},
                status=status.HTTP_409_CONFLICT,
            )

        # Auditoría: acción custom, no pasa por perform_create.
        self.registrar_auditoria(
            ADDITION,
            baja,
            {
                "num_baja": baja.num_baja,
                "motivo": motivo,
                "regional_id": regional.id,
                "autoriza_id": usuario.id,
                "documento": getattr(documento, "name", "") or "sin documento",
            },
            detalle=(
                f"Desincorporación del activo {activo.codigo_tamep}; "
                f"designación cerrada y situación del activo en 'Baja'"
            ),
        )

        return Response(
            {
                "detail": "Activo dado de baja y desvinculado correctamente.",
                "baja": BajaActivoSerializer(baja).data,
                "activo": {
                    "id": activo.id,
                    "codigo_tamep": activo.codigo_tamep,
                    "situacion_activo": activo.situacion_activo,
                    "estado_actual": activo.estado_actual,
                },
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=['get'])
    def imprimir_acta_baja(self, request, pk=None):
        """
        GET /api/operacion-baja/{id_baja}/imprimir_acta_baja/

        Acta de desincorporación en PDF (respaldo legal), con el mismo
        criterio visual que el acta de transferencia (transferencias.py,
        generar_pdf): carta, márgenes de 2 cm, secciones numeradas y
        firmas al pie.

        El `pk` de la URL es el ID del registro de baja (detalle=True),
        igual que el resto de acciones de este viewset.

        Devuelve FileResponse con as_attachment=False, igual que
        generar_pdf: el navegador muestra el PDF y permite imprimirlo.
        """
        baja = self.get_object()
        activo = baja.activo

        # La designación que cerró BajaActivo.save() (esta_activa=False con
        # "CIERRE POR BAJA - REF: <num_baja>"). Sin ella, la última por
        # fecha_inicio: es la custodia vigente al momento de la baja.
        designacion = (
            Designacion.objects.filter(activo=activo)
            .filter(observaciones__contains=f"CIERRE POR BAJA - REF: {baja.num_baja}")
            .select_related('usuario', 'regional', 'gerencia', 'cargo', 'ubicacion')
            .first()
            or Designacion.objects.filter(activo=activo)
            .select_related('usuario', 'regional', 'gerencia', 'cargo', 'ubicacion')
            .first()
        )

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            topMargin=2 * cm,
            bottomMargin=2 * cm,
            leftMargin=2 * cm,
            rightMargin=2 * cm,
        )

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'Title2', parent=styles['Title'],
            fontSize=14, alignment=TA_CENTER, spaceAfter=6,
        )
        subtitle_style = ParagraphStyle(
            'Sub', parent=styles['Normal'],
            fontSize=10, alignment=TA_CENTER,
            textColor=colors.grey, spaceAfter=12,
        )
        heading_style = ParagraphStyle(
            'Head', parent=styles['Heading3'],
            fontSize=11, spaceAfter=4, spaceBefore=10,
            textColor=colors.HexColor('#1a237e'),
        )
        normal = styles['Normal']
        normal.fontSize = 9
        normal.leading = 12

        # Escapa el texto de usuario (el XML de Paragraph se rompe con
        # '&' o '<') y conserva los saltos de línea de los textos libres.
        def texto(valor):
            return escape(valor or '').replace('\n', '<br/>')

        def nombre(user):
            if not user:
                return 'N/A'
            return user.get_full_name() or user.username

        def filas(pares):
            return [
                [etiqueta, valor]
                for etiqueta, valor in pares
            ]

        elements = []

        # Encabezado
        elements.append(Paragraph("ACTA DE BAJA DE ACTIVOS", title_style))
        elements.append(
            Paragraph(f"DESINCORPORACIÓN DEFINITIVA DE BIEN — {baja.num_baja}", subtitle_style)
        )
        elements.append(Spacer(1, 0.3 * cm))

        # 1. Identificación del bien
        elements.append(Paragraph("1. Identificación del Bien", heading_style))
        tipo = activo.tipo_activo
        activo_data = filas([
            ('Código TAMEP', activo.codigo_tamep or 'N/A'),
            ('Descripción', texto(activo.nombre_especifico)),
            ('Nro. Serie', activo.serie or 'S/N'),
            ('Tipo de Activo', tipo.nombre if tipo else 'N/A'),
            (
                'Grupo Contable',
                tipo.grupo_contable.nombre if tipo and tipo.grupo_contable else 'N/A',
            ),
            (
                'Ubicación de Origen',
                activo.ubicacion_base.nombre_sala if activo.ubicacion_base else 'N/A',
            ),
            (
                'Fecha de Adquisición',
                activo.fecha_adquisicion.strftime('%d/%m/%Y')
                if activo.fecha_adquisicion else 'N/A',
            ),
        ])
        t = Table(activo_data, colWidths=[4 * cm, 13 * cm])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#e8eaf6')),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('PADDING', (0, 0), (-1, -1), 6),
        ]))
        elements.append(t)
        elements.append(Spacer(1, 0.4 * cm))

        # 2. Datos de la baja
        elements.append(Paragraph("2. Datos de la Baja", heading_style))
        detalle_data = filas([
            ('Nro. de Acta', baja.num_baja or 'N/A'),
            ('Fecha', baja.fecha.strftime('%d/%m/%Y %H:%M') if baja.fecha else 'N/A'),
            ('Motivo', texto(baja.motivo)),
            ('Justificación Técnica', texto(baja.descripcion_tecnica)),
            (
                'Documento de Respaldo',
                'Adjunto' if baja.documento_respaldo else 'Sin documento',
            ),
        ])
        t2 = Table(detalle_data, colWidths=[4 * cm, 13 * cm])
        t2.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#e8eaf6')),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('PADDING', (0, 0), (-1, -1), 6),
        ]))
        elements.append(t2)
        elements.append(Spacer(1, 0.4 * cm))

        # 3. Custodia al momento de la baja
        elements.append(Paragraph("3. Custodia al Momento de la Baja", heading_style))
        custodio = designacion.usuario if designacion else None
        custodia_data = filas([
            ('Funcionario (Custodio)', nombre(custodio)),
            (
                'Regional',
                designacion.regional.nombre
                if designacion and designacion.regional else 'N/A',
            ),
            (
                'Gerencia',
                designacion.gerencia.nombre
                if designacion and designacion.gerencia else 'N/A',
            ),
            (
                'Cargo',
                designacion.cargo.nombre
                if designacion and designacion.cargo else 'N/A',
            ),
            ('Tipo de Designación', designacion.tipo if designacion else 'Sin designación'),
            (
                'Fecha de Asignación',
                designacion.fecha_inicio.strftime('%d/%m/%Y')
                if designacion and designacion.fecha_inicio else 'N/A',
            ),
            (
                'Fecha de Cierre',
                designacion.fecha_fin_real.strftime('%d/%m/%Y %H:%M')
                if designacion and designacion.fecha_fin_real else 'N/A',
            ),
        ])
        t3 = Table(custodia_data, colWidths=[4 * cm, 13 * cm])
        t3.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#e8eaf6')),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('PADDING', (0, 0), (-1, -1), 6),
        ]))
        elements.append(t3)
        elements.append(Spacer(1, 1.5 * cm))

        # 4. Firmas
        elements.append(Paragraph("4. Firmas de Conformidad", heading_style))
        elements.append(Spacer(1, 1.5 * cm))
        firma_data = [
            ['_________________________', '_________________________', '_________________________'],
            [nombre(custodio), nombre(baja.solicitante), 'Vo. Bo. Administración'],
            ['DEVUELVE / CUSTODIA', 'AUTORIZA LA BAJA', 'REGISTRA'],
        ]
        t4 = Table(firma_data, colWidths=[5.6 * cm, 5.6 * cm, 5.6 * cm])
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

        filename = f"Acta_Baja_{baja.num_baja}.pdf"
        return FileResponse(
            buffer,
            as_attachment=False,
            filename=filename,
            content_type='application/pdf',
        )
