import json
import os
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.exceptions import DefaultCredentialsError

# -------------------------------------------------------------
# CONFIGURATION
# -------------------------------------------------------------
# Scope requis pour lire et écrire dans Google Sheets
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# ID de votre Google Sheet
SPREADSHEET_ID = "12U1O2_Q4I5E0ZfsN0Vc0W67zRmjZfZO7Wb8pxoo_rmg"

# Mappage des catégories d'emails aux noms des feuilles (assumant que les noms correspondent)
CATEGORY_SHEET_MAP = {
    "Problème technique informatique": "Problème technique informatique",
    "Demande administrative": "Demande administrative",
    "Problème d’accès / authentification": "Problème d’accès / authentification",
    "Demande de support utilisateur": "Demande de support utilisateur",
    "Bug ou dysfonctionnement d’un service": "Bug ou dysfonctionnement d’un service",
    # Gère la catégorie d'erreur si l'API Mistral échoue
    "ERREUR API": "Erreurs de Classification", 
    "ERREUR DÉCODAGE": "Erreurs de Classification", 
    "Non classifié": "Erreurs de Classification", 
}
# Feuille de secours pour les cas non classifiés
FALLBACK_SHEET_NAME = "Erreurs de Classification"

# En-têtes pour chaque feuille
HEADERS = ["Sujet", "Urgence", "Synthèse"]

# -------------------------------------------------------------
# AUTHENTIFICATION GOOGLE SHEETS
# -------------------------------------------------------------
def sheets_auth():
    """Authentifie l'accès à Google Sheets via OAuth."""
    
    # Le fichier de configuration doit être présent (config.json ou client_secrets.json)
    try:
        with open("config.json") as f:
            config = json.load(f)
    except FileNotFoundError:
        print("Erreur: Le fichier 'config.json' est introuvable. Veuillez l'utiliser pour l'authentification Sheets.")
        raise

    flow = InstalledAppFlow.from_client_config(config, SCOPES)
    creds = flow.run_local_server(port=0)
    sheets_service = build("sheets", "v4", credentials=creds)
    return sheets_service

# -------------------------------------------------------------
# LECTURE DES DONNÉES CLASSIFIÉES
# -------------------------------------------------------------
def load_classified_emails(filename="emails_classified.json"):
    """Charge les emails classifiés à partir du fichier JSON."""
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Erreur: Le fichier '{filename}' est introuvable. Veuillez exécuter le script de classification d'abord.")
        return None
    except json.JSONDecodeError:
        print(f"Erreur: Le fichier '{filename}' n'est pas un JSON valide.")
        return None

# -------------------------------------------------------------
# VÉRIFICATION ET CRÉATION DES FEUILLES
# -------------------------------------------------------------
def ensure_sheets_exist(service, spreadsheet_id, required_sheet_names):
    """Vérifie l'existence des feuilles requises et les crée si elles manquent."""
    
    # 1. Récupérer les feuilles existantes
    try:
        spreadsheet = service.spreadsheets().get(
            spreadsheetId=spreadsheet_id, 
            fields='sheets.properties.title'
        ).execute()
    except Exception as e:
        print(f"Erreur lors de la récupération des métadonnées de la feuille de calcul: {e}")
        return

    existing_titles = {sheet['properties']['title'] for sheet in spreadsheet.get('sheets', [])}
    
    requests = []
    missing_sheets = []

    # 2. Identifier les feuilles manquantes et préparer les requêtes de création
    for sheet_name in required_sheet_names:
        if sheet_name not in existing_titles:
            missing_sheets.append(sheet_name)
            requests.append({
                'addSheet': {
                    'properties': {
                        'title': sheet_name
                    }
                }
            })

    if not requests:
        print("Toutes les feuilles requises existent déjà.")
        return

    # 3. Exécuter la mise à jour par lots pour créer les feuilles
    body = { 'requests': requests }
    try:
        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id, 
            body=body
        ).execute()
        print(f"Feuilles créées avec succès : {', '.join(missing_sheets)}")
    except Exception as e:
        print(f"Erreur lors de la création des feuilles : {e}")


# -------------------------------------------------------------
# ÉCRITURE DANS GOOGLE SHEETS
# -------------------------------------------------------------
def write_results_to_sheets():
    """Pipeline principal pour charger les emails et écrire les résultats
    dans les feuilles de calcul Google Sheets correspondantes."""

    print("Chargement des emails classifiés...")
    emails = load_classified_emails()
    if not emails:
        return

    print("Authentification Google Sheets...")
    try:
        sheets_service = sheets_auth()
    except Exception as e:
        print(f"Échec de l'authentification Google Sheets: {e}")
        return
        
    required_sheets = set(CATEGORY_SHEET_MAP.values())
    ensure_sheets_exist(sheets_service, SPREADSHEET_ID, required_sheets)

    # 1. Grouper les emails par catégorie
    grouped_emails = {sheet_name: [] for sheet_name in required_sheets}
    
    for email in emails:
        category = email.get("categorie", "Non classifié")
        sheet_name = CATEGORY_SHEET_MAP.get(category, FALLBACK_SHEET_NAME)
        
        # Créer la ligne de données [Sujet, Urgence, Synthèse]
        row_data = [
            email.get("subject", ""),
            email.get("urgence", ""),
            email.get("synthese", "")
        ]
        grouped_emails[sheet_name].append(row_data)

    print(f"Début de l'écriture dans la feuille de calcul : {SPREADSHEET_ID}")

    for sheet_name, data_rows in grouped_emails.items():
        if not data_rows:
            print(f"-> Aucune donnée pour la feuille '{sheet_name}'. Ignoré.")
            continue
        
        # 2. Préparer les données pour l'API Sheets (Headers + Data)
        all_data = [HEADERS] + data_rows
        
        # 3. Définir la plage d'écriture (ex: 'NomDeLaFeuille!A1')
        range_name = f"'{sheet_name}'!A1"

        # 4. Nettoyer la feuille avant d'écrire pour éviter les doublons/données obsolètes
        # Nous allons effacer toute la colonne A à C, y compris les en-têtes
        clear_range = f"'{sheet_name}'!A1:C" 

        try:
            # Effacement
            sheets_service.spreadsheets().values().clear(
                spreadsheetId=SPREADSHEET_ID,
                range=clear_range
            ).execute()
            
            # Écriture
            body = {
                'values': all_data
            }
            sheets_service.spreadsheets().values().update(
                spreadsheetId=SPREADSHEET_ID,
                range=range_name,
                valueInputOption="USER_ENTERED", # Conserver les formats simples
                body=body
            ).execute()

            print(f"-> Écriture réussie de {len(data_rows)} lignes dans la feuille '{sheet_name}'.")

        except Exception as e:
            print(f"!!! ERREUR lors de l'écriture dans la feuille '{sheet_name}' : {e}")
            print("Veuillez vérifier que le nom de la feuille est correct et que le service est activé.")

    print("\n Processus d'écriture dans Google Sheets terminé.")

# -------------------------------------------------------------
# MAIN
# -------------------------------------------------------------
if __name__ == "__main__":
    write_results_to_sheets()