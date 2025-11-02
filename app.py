import os
from flask import Flask, redirect, url_for, session, request, render_template
from google_auth_oauthlib.flow import Flow
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from dotenv import load_dotenv
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1' # Solo para desarrollo local (HTTP), con render quitamos esto

load_dotenv() # Cargar variables de .env

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY")

# Configuración de Google OAuth
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
REDIRECT_URI = "http://127.0.0.1:5000/auth/callback" # Debe coincidir con la consola de Google

#Definir el "flow" de OAuth
flow = Flow.from_client_config(
    client_config={
        "web": {
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [REDIRECT_URI],
        }
    },
    scopes=["openid", "https://www.googleapis.com/auth/userinfo.email", "https://www.googleapis.com/auth/userinfo.profile"],
    redirect_uri=REDIRECT_URI
)

#---------------------------------------------------

@app.route("/login")
def login():
    # Genera la URL a la que el usuario será redirigido
    authorization_url, state = flow.authorization_url()
    session["state"] = state # Guarda el 'state' para verificarlo en el callback (seguridad CSRF) CSRF es Cross-Site Request Forgery
    return redirect(authorization_url)


#---------------------------------------------------

@app.route("/auth/callback")
def callback():
    # Verifica el 'state' para prevenir ataques CSRF
    if request.args.get("state") != session.get("state"):
        return "Error: State mismatch", 400

    # Intercambia el código de autorización por un token de acceso
    flow.fetch_token(authorization_response=request.url)

    # Obtiene las credenciales (incluido el id_token)
    credentials = flow.credentials

    # Verifica el id_token para obtener la información del usuario
    try:
        id_info = id_token.verify_oauth2_token(
            credentials.id_token, google_requests.Request(), GOOGLE_CLIENT_ID
        )
    except ValueError:
        return "Error: Invalid token", 400

    # Guarda la información del usuario en la sesión de Flask
    session["user_info"] = {
        "name": id_info.get("name"),
        "email": id_info.get("email"),
        "picture": id_info.get("picture"),
    }

    return redirect(url_for("profile"))


#---------------------------------------------------

@app.route("/")
def index():
    if "user_info" in session:
        return f'¡Hola, {session["user_info"]["name"]}! <a href="/logout">Cerrar sesión</a>'
    return 'No has iniciado sesión. <a href="/login">Iniciar con Google</a>'

@app.route("/profile")
def profile():
    if "user_info" not in session:
        return redirect(url_for("login")) # Si no está en sesión, lo mandamos a login

    user = session["user_info"]
    return f'<h1>Perfil de {user["name"]}</h1><p>Email: {user["email"]}</p><img src="{user["picture"]}"><br><a href="/logout">Cerrar sesión</a>'

@app.route("/logout")
def logout():
    session.pop("user_info", None) # Limpia la sesión
    return redirect(url_for("index"))

if __name__ == "__main__":
    app.run(debug=True, port=5000)