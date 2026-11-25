import qrcode
from io import BytesIO
from django.core.files import File

def generar_qr_activo(activo):
    # Definimos la URL que será consultada (Dinámica)
    # Ejemplo: http://tamep.bo/activos/detalle/123/
    url_acceso = f"https://tamep-gestion.bo/detalle/{activo.id}/"
    
    # Creamos el código QR
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(url_acceso)
    qr.make(fit=True)
    
    # Guardamos la imagen en memoria para asociarla al activo
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    
    # Guardamos en el campo 'imagen_qr' del modelo Activo
    filename = f"qr-{activo.codigo_tamep}.png"
    activo.imagen_qr.save(filename, File(buffer), save=True)