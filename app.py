import os
from flask import Flask, redirect, url_for, session, request, render_template
from google_auth_oauthlib.flow import Flow
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from dotenv import load_dotenv
from werkzeug.utils import secure_filename
from models import db, User, Photo
import boto3

# -----------------------------------------------------
# CARGA DE VARIABLES DE ENTORNO
# -----------------------------------------------------
load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY")

# -----------------------------------------------------
# CONFIGURACIÓN DE LA BASE DE DATOS (SQLite)
# -----------------------------------------------------
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///users.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db.init_app(app)

# -----------------------------------------------------
# CONFIGURACIÓN DE GOOGLE OAUTH 2.0
# -----------------------------------------------------
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
REDIRECT_URI = "http://127.0.0.1:5000/auth/callback"
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"  # Solo para desarrollo local

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
    scopes=[
        "openid",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile",
    ],
    redirect_uri=REDIRECT_URI,
)

# -----------------------------------------------------
# CONFIGURACIÓN DE AWS S3
# -----------------------------------------------------
AWS_ACCESS_KEY_ID = os.environ.get("ACCESS_KEY_S3")
AWS_SECRET_ACCESS_KEY = os.environ.get("SECRET_KEY_ACCESS_S3")
AWS_S3_BUCKET_NAME = "da-vinci-ejemplo1"

s3 = boto3.client(
    "s3",
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
)

# -----------------------------------------------------
# RUTAS
# -----------------------------------------------------

@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("profile"))
    return render_template("index.html")


@app.route("/login")
def login():
    authorization_url, state = flow.authorization_url()
    session["state"] = state
    return redirect(authorization_url)


@app.route("/auth/callback")
def callback():
    if request.args.get("state") != session.get("state"):
        return render_template("error.html", message="El parámetro 'state' no coincide")

    flow.fetch_token(authorization_response=request.url)
    credentials = flow.credentials

    try:
        id_info = id_token.verify_oauth2_token(
            credentials.id_token, google_requests.Request(), GOOGLE_CLIENT_ID
        )
    except ValueError:
        return render_template("error.html", message="Token inválido")

    google_id = id_info.get("sub")
    user = User.query.filter_by(google_id=google_id).first()

    if not user:
        user = User(
            google_id=google_id,
            email=id_info.get("email"),
            name=id_info.get("name"),
            picture=id_info.get("picture"),
        )
        db.session.add(user)
        db.session.commit()

    session["user_id"] = user.id
    return redirect(url_for("profile"))


@app.route("/profile")
def profile():
    if "user_id" not in session:
        return redirect(url_for("login"))
    user = db.get_or_404(User, session["user_id"])
    return render_template("profile.html", user=user)


@app.route("/logout")
def logout():
    session.pop("user_id", None)
    return redirect(url_for("index"))


# -----------------------------------------------------
# SUBIDA DE FOTOS
# -----------------------------------------------------
@app.route("/upload", methods=["GET", "POST"])
def upload_file():
    if "user_id" not in session:
        return redirect(url_for("login"))

    user = db.get_or_404(User, session["user_id"])

    if request.method == "POST":
        file = request.files.get("file")
        if not file:
            return render_template("upload.html", user=user, error="No seleccionaste ningún archivo")

        filename = secure_filename(file.filename)
        if not filename:
            return render_template("upload.html", user=user, error="Nombre de archivo inválido")

        try:
            s3.upload_fileobj(file, AWS_S3_BUCKET_NAME, filename)
            file_url = f"https://{AWS_S3_BUCKET_NAME}.s3.amazonaws.com/{filename}"

            new_photo = Photo(url=file_url, user_id=user.id)
            db.session.add(new_photo)
            db.session.commit()

            return render_template("upload.html", user=user, success=True, file_url=file_url)

        except Exception as e:
            print("Error al subir el archivo:", e)
            return render_template("upload.html", user=user, error=str(e))

    return render_template("upload.html", user=user)


# -----------------------------------------------------
# GALERÍA
# -----------------------------------------------------
@app.route("/gallery")
def gallery():
    if "user_id" not in session:
        return redirect(url_for("login"))

    user = db.get_or_404(User, session["user_id"])
    photos = Photo.query.filter_by(user_id=user.id).all()

    return render_template("gallery.html", user=user, photos=photos)


# -----------------------------------------------------
# INICIO DE LA APP
# -----------------------------------------------------
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True, port=5000)
