# create_token.py
from google_auth_oauthlib.flow import InstalledAppFlow
import pickle, os

SCOPES = ["https://www.googleapis.com/auth/blogger", "https://www.googleapis.com/auth/documents"]

flow = InstalledAppFlow.from_client_secrets_file("client_secret.json", SCOPES)
creds = flow.run_local_server(port=0)

with open("token_blogger.pkl", "wb") as f:
    pickle.dump(creds, f)

print("token_blogger.pkl created. Keep this file safe.")
