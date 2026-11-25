from django.db import models
from django.contrib.auth.models import User
import uuid
from django.shortcuts import render, get_object_ some_list_or_object
from .models import Activo, Intervencion
from django.db.models.functions import ExtractMonth, ExtractYear
from django.db.models import Count, Sum
# --- ESTRUCTURA ORGANIZACIONAL ---
class Regional(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    def __str__(self): return self.nombre

class Ubicacion(models.Model):
    nombre = models.CharField(max_length=100)
    regional = models.ForeignKey(Regional, on_delete=models.CASCADE)
    # Datos para Lógica Difusa
    temperatura_avg = models.DecimalField(max_digits=5, decimal_places=2)
    humedad_avg = models.DecimalField(max_digits=5, decimal_places=2)
    altitud = models.IntegerField(help_text="Metros sobre el nivel del mar")
    def __str__(self): return f"{self.nombre} ({self.regional})"

# --- MÓDULO 1: REGISTRO DEL ACTIVO ---
class Activo(models.Model):
    codigo_tamep = models.CharField(max_length=50, unique=True)
    nombre = models.CharField(max_length=255)
    serie = models.CharField(max_length=100, unique=True)
    categoria = models.CharField(max_length=100, choices=[('SRV', 'Servidor'), ('RAD', 'Radio'), ('PC', 'Computadora')])
    fecha_adquisicion = models.DateField()
    vida_util_meses = models.IntegerField(default=60)
    estado_fisico = models.CharField(max_length=50, default="Nuevo")
    ubicacion_fisica = models.ForeignKey(Ubicacion, on_delete=models.PROTECT)
    qr_token = models.UUIDField(default=uuid.uuid4, editable=False)
    
    # Estado de flujo
    disponible = models.BooleanField(default=True) 

    def __str__(self): return f"{self.codigo_tamep} - {self.nombre}"

# --- MÓDULO 2: DESIGNACIÓN (ASIGNACIÓN) ---
class Designacion(models.Model):
    activo = models.ForeignKey(Activo, on_delete=models.CASCADE)
    responsable = models.ForeignKey(User, on_delete=models.CASCADE)
    fecha_entrega = models.DateTimeField(auto_now_add=True)
    observaciones_entrega = models.TextField()
    acta_pdf = models.FileField(upload_to='actas/', null=True, blank=True)
    activa = models.BooleanField(default=True) # Para saber si es el poseedor actual

# --- MÓDULO 3: MANTENIMIENTO E INFORMÁTICA ---
class SolicitudServicio(models.Model):
    activo = models.ForeignKey(Activo, on_delete=models.CASCADE)
    solicitante = models.ForeignKey(User, on_delete=models.CASCADE, related_name='solicitudes')
    descripcion_problema = models.TextField()
    fecha_reporte = models.DateTimeField(auto_now_add=True)
    prioridad = models.CharField(max_length=20, choices=[('H', 'Alta'), ('M', 'Media'), ('L', 'Baja')])

class Intervencion(models.Model):
    solicitud = models.OneToOneField(SolicitudServicio, on_delete=models.CASCADE)
    tecnico = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    tipo_mant = models.CharField(max_length=50, choices=[('PREV', 'Preventivo'), ('CORR', 'Correctivo')])
    fecha_inicio = models.DateTimeField()
    fecha_fin = models.DateTimeField()
    costo = models.DecimalField(max_digits=10, decimal_places=2)
    trabajo_realizado = models.TextField()

# --- MÓDULO IA: RESULTADOS ---
class MetricasIA(models.Model):
    activo = models.OneToOneField(Activo, on_delete=models.CASCADE)
    mtbf = models.FloatField(default=0.0) # Mean Time Between Failures
    rul = models.FloatField(default=0.0)  # Remaining Useful Life
    probabilidad_falla_rf = models.FloatField(default=0.0) # Random Forest
    salud_fuzzy = models.FloatField(default=100.0)        # Lógica Difusa
    ultima_actualizacion = models.DateTimeField(auto_now=True)
class HistorialActivo(models.Model):
    activo = models.ForeignKey(Activo, on_delete=models.CASCADE, related_name='historial')
    fecha = models.DateTimeField(auto_now_add=True)
    
    # Vinculamos con el proceso de soporte
    solicitud = models.ForeignKey(SolicitudServicio, on_delete=models.SET_NULL, null=True)
    intervencion = models.ForeignKey(Intervencion, on_delete=models.SET_NULL, null=True)
    
    # Datos consolidados para el reporte y la IA
    tipo_evento = models.CharField(max_length=50) # Ej: "Mantenimiento Correctivo"
    observacion_tecnica = models.TextField()
    costo_total = models.DecimalField(max_digits=10, decimal_places=2)
    
    def __str__(self):
        return f"Evento {self.fecha} - {self.activo.codigo_tamep}"
    def obtener_hoja_vida(self):
        """Retorna todas las intervenciones, fallas y soluciones del equipo"""
        return Intervencion.objects.filter(solicitud__activo=self).order_by('-fecha_inicio')
    