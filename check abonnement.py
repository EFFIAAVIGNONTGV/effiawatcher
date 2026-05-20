#!/usr/bin/env python3
"""
Vérificateur de disponibilité d'abonnement EFFIA - Parkings Avignon TGV
Surveille P2/P3, P4, P5, P6, P7 et alerte dès qu'un abonnement se libère.
"""

import os
import sys
import smtplib
import urllib.request
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

# ─── Parkings à surveiller (abonnements uniquement) ───────────────────────────
PARKINGS = [
    {
        "nom": "P2/P3 – Avignon TGV (couvert, 7j/7 24h/24)",
        "url": "https://www.effia.com/parking/parking-gare-davignon-tgv-p2-p3-effia",
    },
    {
        "nom": "P4 – Avignon TGV (réservé abonnements)",
        "url": "https://www.effia.com/parking/parking-gare-davignon-tgv-p4-effia",
    },
    {
        "nom": "P5 – Avignon TGV (réservé abonnements)",
        "url": "https://www.effia.com/parking/parking-gare-davignon-tgv-p5-effia",
    },
    {
        "nom": "P6 – Avignon TGV",
        "url": "https://www.effia.com/parking/parking-gare-davignon-tgv-p6-effia",
    },
    {
        "nom": "P7 – Avignon TGV (extérieur, tarif réduit)",
        "url": "https://www.effia.com/parking/parking-gare-davignon-tgv-p7-effia",
    },
]

# ─── Texte présent sur la page quand l'abonnement est INDISPONIBLE ────────────
TEXTE_INDISPONIBLE = "Abonnement non disponible"

# ─── Variables d'environnement (configurées dans GitHub Actions Secrets) ──────
EMAIL_EXPEDITEUR   = os.environ.get("EMAIL_EXPEDITEUR", "")
EMAIL_DESTINATAIRE = os.environ.get("EMAIL_DESTINATAIRE", "")
EMAIL_MOT_DE_PASSE = os.environ.get("EMAIL_MOT_DE_PASSE", "")
EMAIL_SMTP_HOST    = os.environ.get("EMAIL_SMTP_HOST", "smtp.gmail.com")
EMAIL_SMTP_PORT    = int(os.environ.get("EMAIL_SMTP_PORT", "587"))
NTFY_TOPIC         = os.environ.get("NTFY_TOPIC", "")  # ex: avignon-parking-seb


def verifier_parking(parking: dict) -> dict:
    """Vérifie si un abonnement est disponible pour un parking donné."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "fr-FR,fr;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    try:
        req = urllib.request.Request(parking["url"], headers=headers)
        with urllib.request.urlopen(req, timeout=20) as resp:
            contenu = resp.read().decode("utf-8", errors="ignore")

        disponible = TEXTE_INDISPONIBLE not in contenu
        return {"nom": parking["nom"], "url": parking["url"],
                "disponible": disponible, "erreur": None}

    except Exception as e:
        return {"nom": parking["nom"], "url": parking["url"],
                "disponible": False, "erreur": str(e)}


def envoyer_email(disponibles: list):
    """Envoie une alerte email pour les parkings dont un abonnement est libre."""
    if not EMAIL_EXPEDITEUR or not EMAIL_MOT_DE_PASSE:
        print("⚠️  Email non configuré — alerte ignorée.")
        return

    sujet = f"🅿️ ABONNEMENT DISPONIBLE – Parking Avignon TGV ({len(disponibles)} parking(s))"

    lignes_html = ""
    for p in disponibles:
        lignes_html += f"""
        <tr>
          <td style="padding:8px 12px; font-weight:bold;">{p['nom']}</td>
          <td style="padding:8px 12px;">
            <a href="{p['url']}" style="color:#1a73e8;">Souscrire maintenant</a>
          </td>
        </tr>"""

    corps_html = f"""
    <html><body style="font-family:Arial,sans-serif; color:#333;">
      <h2 style="color:#d32f2f;">🅿️ Place d'abonnement disponible !</h2>
      <p>Une ou plusieurs places d'abonnement viennent de se libérer sur les parkings EFFIA d'Avignon TGV :</p>
      <table border="0" cellpadding="0" cellspacing="0"
             style="border-collapse:collapse; background:#f9f9f9; border-radius:6px;">
        <thead>
          <tr style="background:#1a73e8; color:white;">
            <th style="padding:10px 12px; text-align:left;">Parking</th>
            <th style="padding:10px 12px; text-align:left;">Action</th>
          </tr>
        </thead>
        <tbody>{lignes_html}</tbody>
      </table>
      <p style="margin-top:20px; color:#777; font-size:12px;">
        Vérification automatique du {datetime.now().strftime('%d/%m/%Y à %H:%M')} — Script EFFIA Watcher
      </p>
    </body></html>"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = sujet
    msg["From"]    = EMAIL_EXPEDITEUR
    msg["To"]      = EMAIL_DESTINATAIRE
    msg.attach(MIMEText(corps_html, "html"))

    try:
        with smtplib.SMTP(EMAIL_SMTP_HOST, EMAIL_SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.login(EMAIL_EXPEDITEUR, EMAIL_MOT_DE_PASSE)
            server.sendmail(EMAIL_EXPEDITEUR, EMAIL_DESTINATAIRE, msg.as_string())
        print(f"✅ Email envoyé à {EMAIL_DESTINATAIRE}")
    except Exception as e:
        print(f"❌ Erreur envoi email : {e}")


def envoyer_notification_ntfy(disponibles: list):
    """Envoie une notification push via ntfy.sh (gratuit, sans compte requis)."""
    if not NTFY_TOPIC:
        return

    noms = ", ".join(p["nom"].split("–")[0].strip() for p in disponibles)
    message = f"Abonnement dispo sur : {noms} — Rendez-vous sur effia.com !"

    try:
        req = urllib.request.Request(
            f"https://ntfy.sh/{NTFY_TOPIC}",
            data=message.encode("utf-8"),
            method="POST",
            headers={
                "Title": "Parking Avignon TGV – Abonnement libre !",
                "Priority": "urgent",
                "Tags": "parking,car,bell",
                "Click": disponibles[0]["url"],
            },
        )
        urllib.request.urlopen(req, timeout=10)
        print(f"✅ Notification ntfy.sh envoyée (topic: {NTFY_TOPIC})")
    except Exception as e:
        print(f"❌ Erreur ntfy.sh : {e}")


def main():
    print(f"\n{'='*62}")
    print(f"  Vérification EFFIA Avignon TGV — {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print(f"{'='*62}")

    disponibles = []
    for parking in PARKINGS:
        result = verifier_parking(parking)
        if result["erreur"]:
            print(f"  ⚠️  {result['nom'][:42]:<42} ERREUR: {result['erreur']}")
        elif result["disponible"]:
            print(f"  🟢 {result['nom'][:42]:<42} ABONNEMENT DISPONIBLE !")
            disponibles.append(result)
        else:
            print(f"  🔴 {result['nom'][:42]:<42} Complet")

    print(f"{'='*62}")

    if disponibles:
        print(f"\n🎉 {len(disponibles)} abonnement(s) disponible(s) ! Envoi des alertes...")
        envoyer_email(disponibles)
        envoyer_notification_ntfy(disponibles)
    else:
        print("\nAucun abonnement disponible aujourd'hui.")

    sys.exit(0)


if __name__ == "__main__":
    main()
