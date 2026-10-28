# pip install google-api-python-client google-auth-oauthlib google-auth-httplib2

from google.colab import auth
import google.auth

# Réinitialise l'authentification de base de Colab sans argument invalide
auth.authenticate_user(clear_output=True)

from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/youtube.readonly"]

# Configuration du flux OAuth à partir de votre fichier secret
flow = InstalledAppFlow.from_client_secrets_file(
    "client_secret.json",
    SCOPES
)

# Utilisation du mode console (qui ne nécessite pas de lancer un navigateur local sur le serveur)
# Cela va vous donner un lien à copier-coller dans votre navigateur, puis un code de validation à insérer ici.
try:
    credentials = flow.run_console()
except AttributeError:
    # Si run_console n'est pas disponible dans votre version, on utilise le flux local standard adapté
    credentials = flow.run_local_server(port=0, open_browser=False)

# 3. Construction du service YouTube
youtube = build(
    "youtube",
    "v3",
    credentials=credentials
)

request = youtube.playlists().list(
    part="snippet,status",
    mine=True,
    maxResults=50
)

while request:
    response = request.execute()

    for item in response["items"]:
        if item["status"]["privacyStatus"] == "private":
            print(item["snippet"]["title"])

    request = youtube.playlists().list_next(
        request,
        response
    )
