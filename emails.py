import json
import base64
import requests
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
import os

# -------------------------------------------------------------
# CONFIGURATION
# -------------------------------------------------------------
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly"
]

# The key should be set in your environment as MISTRAL_API_KEY
MISTRAL_KEY = os.getenv("MISTRAL_API_KEY") 

# -------------------------------------------------------------
# AUTHENTIFICATION GOOGLE
# -------------------------------------------------------------
def google_auth():
    """Authentifie Gmail via OAuth (mode Test).
    Doit lire le fichier config.json
    """
    # Correction: Use the conventional config.json name 
    # and load its content for from_client_config
    try:
        with open("config.json") as f:
            config = json.load(f)
    except FileNotFoundError:
        print("Erreur: Le fichier 'config.json' est introuvable.")
        print("Veuillez le télécharger depuis Google Cloud Console.")
        raise

    flow = InstalledAppFlow.from_client_config(config, SCOPES)
    creds = flow.run_local_server(port=0)
    gmail_service = build("gmail", "v1", credentials=creds)
    return gmail_service

# -------------------------------------------------------------
# FONCTION RÉCURSIVE POUR LE CORPS DE L'EMAIL
# -------------------------------------------------------------
def get_email_body_recursive(part):
    """Parcourt récursivement les parties de l'email pour trouver le texte brut."""
    
    # 1. Cas simple: C'est le corps de l'email en text/plain
    if part["mimeType"] == "text/plain":
        data = part["body"].get("data")
        if data:
            return base64.urlsafe_b64decode(data).decode("utf-8")
        return ""

    # 2. Cas des parties imbriquées (multipart)
    if "parts" in part:
        for sub_part in part["parts"]:
            body = get_email_body_recursive(sub_part)
            # On retourne la première partie text/plain trouvée
            if body:
                return body
    
    return ""

# -------------------------------------------------------------
# RÉCUPÉRER LES EMAILS
# -------------------------------------------------------------
def get_emails(service, max_results=20):
    """Récupère les emails Gmail (sujet + texte brut)."""
    # maxResults cannot exceed 500. We cap it here to 500.
    max_results = min(max_results, 500) 
    
    results = service.users().messages().list(
        userId="me",
        maxResults=max_results
    ).execute()
    messages = results.get("messages", [])
    emails = []
    
    for msg in messages:
        # Request full message data
        msg_data = service.users().messages().get(
            userId="me",
            id=msg["id"],
            format="full"
        ).execute()
        
        payload = msg_data["payload"]
        
        # ---- SUJET ----
        subject = ""
        for header in payload["headers"]:
            if header["name"] == "Subject":
                subject = header["value"]
                break # Subject found, no need to check other headers
        
        # ---- CORPS ----
        # Correction: Use the recursive function to handle complex message structures
        if "parts" in payload:
            # Multi-part message
            body = get_email_body_recursive(payload)
        else:
            # Single-part message (often simple text or non-standard)
            data = payload["body"].get("data")
            if data:
                # The payload body data often needs base64 decoding
                try:
                    body = base64.urlsafe_b64decode(data).decode("utf-8")
                except:
                    body = "[Erreur de décodage du corps de l'email]"
            else:
                body = "" # No body data found
                
        emails.append({"subject": subject, "body": body})
        
    return emails

# -------------------------------------------------------------
# CLASSIFICATION VIA MISTRAL (MODIFIED FOR ERROR HANDLING)
# -------------------------------------------------------------
def classify_email(subject, body):
    """Retourne catégorie, urgence, résumé.
    
    La logique a été modifiée pour gérer les erreurs HTTP (comme l'API Key invalide)
    avant d'essayer de décoder la réponse JSON.
    """
    # Check for the API key availability
    if not MISTRAL_KEY:
        print("Erreur: La clé API Mistral n'est pas définie (MISTRAL_API_KEY non trouvé dans les variables d'environnement).")
        return {"categorie": "Non classifié", "urgence": "Non classée", "synthese": "Clé API manquante pour la classification."}

    prompt = f"""
Tu es un système interne de tri des tickets email. Ton objectif est de classer les emails de manière stricte et sans biais.

--- Instructions Clés ---
1. **Distingue clairement Anodine de Faible.**
2. Utilise 'Anodine' uniquement pour les emails qui ne nécessitent **AUCUNE intervention humaine** ou qui sont des notifications standard sans impact négatif (ex: newsletter, accusé de réception, notification de maintenance réussie, réponse automatique, spam).
3. Utilise 'Faible' pour tout ce qui nécessite une action future, mais qui n'est pas urgent.
---

Catégories :
- Problème technique informatique
- Demande administrative
- Problème d’accès / authentification
- Demande de support utilisateur
- Bug ou dysfonctionnement d’un service
Urgence :
- Critique
- Élevée
- Modérée
- Faible
- Anodine
Réponds uniquement du JSON :
{{
  "categorie": "",
  "urgence": "",
  "synthese": ""
}}
Email :
Sujet : {subject}
Contenu : {body}
"""
    response = requests.post(
        "https://api.mistral.ai/v1/chat/completions",  # Mistral endpoint
        headers={
            "Authorization": f"Bearer {MISTRAL_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "model": "mistral-tiny",  # or "mistral-small", depending on your plan
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0
        }
    )
    
    # NEW: Handle HTTP errors (4xx or 5xx) before attempting JSON decoding
    try:
        response.raise_for_status() 
    except requests.exceptions.HTTPError as err:
        print(f"Erreur HTTP de l'API Mistral: {err}")
        # Try to extract a meaningful error from the response text
        error_message = response.text[:100] if response.text else "Aucun détail d'erreur dans la réponse."
        return {
            "categorie": "ERREUR API", 
            "urgence": "Critique", 
            "synthese": f"Échec de l'appel API Mistral (Status {response.status_code}). Vérifiez la clé ou les limites. Détail: {error_message}..."
        }

    # Proceed to JSON decoding only if the HTTP request was successful (Status 200)
    try:
        resp_json = response.json()
    except requests.exceptions.JSONDecodeError as e:
        print("Erreur de décodage JSON après un statut 200: Le corps de la réponse était inattendu.")
        print(f"Réponse brute : {response.text[:200]}...")
        return {
            "categorie": "ERREUR DÉCODAGE", 
            "urgence": "Critique", 
            "synthese": f"Erreur de décodage JSON après succès HTTP. Vérifiez la structure JSON attendue. Erreur: {e}"
        }

    # Existing logic for processing the successful JSON response
    if "choices" in resp_json and len(resp_json["choices"]) > 0:
        result = resp_json["choices"][0]["message"]["content"]
        try:
            return json.loads(result)
        except json.JSONDecodeError:
            print("Impossible de parser le JSON :", result)
            return {"categorie": "Non classifié", "urgence": "Non classée", "synthese": result}
    else:
        # Improved error message to include API details
        error_detail = resp_json.get("error", {}).get("message", "Détails non disponibles")
        print(f"Réponse inattendue de l'API Mistral: {error_detail}")
        print(json.dumps(resp_json, indent=2))
        return {"categorie": "Non classifié", "urgence": "Non classée", "synthese": f"Erreur API: {error_detail}"}

# -------------------------------------------------------------
# SAUVEGARDE JSON (No changes needed)
# -------------------------------------------------------------
def save_to_json(filename, data):
    """Enregistre la liste de dictionnaires dans un fichier JSON."""
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# -------------------------------------------------------------
# PIPELINE PRINCIPAL
# -------------------------------------------------------------
def process_all_emails():
    """Pipeline complet : Gmail → IA → JSON"""
    print("Authentification Google...")
    try:
        gmail_service = google_auth()
    except Exception as e:
        print(f"Échec de l'authentification Google: {e}")
        return # Exit the pipeline if auth fails

    print("Récupération des emails...")
    # Correction: maxResults capped at 500 (Gmail API limit)
    emails = get_emails(gmail_service, max_results=500) 
    print(f"{len(emails)} emails trouvés.")
    
    if not emails:
        print("Aucun email à traiter. Fin du pipeline.")
        return

    print("Classification en cours...\n")
    all_emails = []
    for mail in emails:
        subject = mail["subject"]
        body = mail["body"]
        print(f"--- Email : {subject}")
        
        classification = classify_email(subject, body)
        
        # Safely access classification results (in case of API error)
        categorie = classification.get("categorie", "Non classifié")
        urgence = classification.get("urgence", "Non classée")
        synthese = classification.get("synthese", "Erreur de classification")
        
        print("Catégorie :", categorie)
        print("Urgence :", urgence)
        print("Résumé :", synthese)
        print("→ Ajout dans la liste.\n")
        
        all_emails.append({
            "categorie": categorie,
            "subject": subject,
            "urgence": urgence,
            "synthese": synthese
        })
        
    save_to_json("emails_classified.json", all_emails)
    print("✔️ Tous les emails ont été traités et enregistrés dans 'emails_classified.json' !")

# -------------------------------------------------------------
# MAIN
# -------------------------------------------------------------
if __name__ == "__main__":
    process_all_emails()