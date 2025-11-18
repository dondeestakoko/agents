import pandas as pd
from sklearn.metrics import confusion_matrix, classification_report
import seaborn as sns
import matplotlib.pyplot as plt


# -------------------------------------------------------------
# 1. Charger les fichiers
# -------------------------------------------------------------
pred = pd.read_json("emails_classified.json")    # ton fichier JSON
gt = pd.read_csv("ground_truth.csv")       # ton fichier CSV


# -------------------------------------------------------------
# 2. Normaliser les colonnes pour faciliter la comparaison
# -------------------------------------------------------------
pred["subject_norm"] = pred["subject"].str.strip().str.lower()
gt["subjects_norm"] = gt["subjects"].str.strip().str.lower()


# -------------------------------------------------------------
# 3. Fusionner les données grâce au "subject"
# -------------------------------------------------------------
merged = pd.merge(
    gt,
    pred,
    left_on="subjects_norm",
    right_on="subject_norm",
    how="inner"
)

print("Nombre de correspondances trouvées :", len(merged))
print(merged[["subjects", "subject", "urgence_x", "urgence_y", "categories", "categorie"]])


# -------------------------------------------------------------
# 4. Matrice de confusion : URGENCE
# -------------------------------------------------------------
cm_urgence = confusion_matrix(merged["urgence_x"], merged["urgence_y"])

plt.figure(figsize=(7,5))
sns.heatmap(cm_urgence, annot=True, fmt="d", cmap="Blues")
plt.title("Matrice de confusion – URGENCE (GT vs Prédiction)")
plt.xlabel("Prédiction")
plt.ylabel("Ground Truth")
plt.show()

print("\nClassification Report (URGENCE) :")
print(classification_report(merged["urgence_x"], merged["urgence_y"]))


# -------------------------------------------------------------
# 5. Matrice de confusion : CATEGORIE
# -------------------------------------------------------------
cm_cat = confusion_matrix(merged["categories"], merged["categorie"])

plt.figure(figsize=(10,6))
sns.heatmap(cm_cat, annot=True, fmt="d", cmap="Greens")
plt.title("Matrice de confusion – CATEGORIES (GT vs Prédiction)")
plt.xlabel("Prédiction")
plt.ylabel("Ground Truth")
plt.show()

print("\nClassification Report (CATEGORIE) :")
print(classification_report(merged["categories"], merged["categorie"]))
