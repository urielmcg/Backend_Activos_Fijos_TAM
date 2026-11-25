import os
import sys

# 1. Ruta de tu proyecto
sys.path.insert(0, "/home/kqlurhnh/siaem")

# 2. Ruta de librerías
sys.path.insert(1, "/home/kqlurhnh/virtualenv/siaem/3.11/lib/python3.11/site-packages")

# 3. Configuración de Django
os.environ['DJANGO_SETTINGS_MODULE'] = 'core.settings'

# 4. Entrada de la aplicación
from core.wsgi import application