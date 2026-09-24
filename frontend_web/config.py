import os

from dotenv import load_dotenv

# Se carga aqui porque Config se lee ANTES de importar backend_web (que es
# donde db.py hacia load_dotenv en el monolito plano). Sin esto, SECRET_KEY
# tomaria el valor de desarrollo sin avisar.
load_dotenv()


class Config:
    # Mismo secreto para la cookie de flash() y para firmar el JWT, como en app.py.
    SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "dev-secret-cambiar-en-despliegue")
