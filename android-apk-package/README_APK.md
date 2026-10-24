# Application Android (APK) & PWA — ALJ Escalade Compétitions

Cette application regroupe l'ensemble des fonctionnalités de la PWA mobile des compétitions de l'**Amicale Laïque de Jonage Escalade** :
- Consultation et gestion des compétitions en temps réel
- Sélection des compétiteurs et suivi des inscriptions
- Pointage des paiements HelloAsso et paiements directs
- Envoi des convocations et modèles d'e-mails
- Fonctionnement hors-ligne via Service Worker et IndexedDB (cache local)

---

## Méthode 1 : Installation directe sous Android (WebAPK officiel Google)

Grâce au standard **PWA / WebAPK** supporté nativement par Android et Google Play Services :
1. Ouvrez l'application sur votre smartphone Android avec Google Chrome :
   `https://ais-pre-ymsoame44dpxezzviuao6d-968086448026.europe-west2.run.app/competitions`
2. Cliquez sur le bouton bleu **📲 APK** dans l'en-tête (ou ouvrez le menu Chrome `⋮` > **Installer l'application**).
3. Android génère et installe automatiquement l'**APK natif (WebAPK)** :
   - L'application apparaît dans votre tiroir d'applications et sur votre écran d'accueil avec son icône officielle ALJ Escalade.
   - Elle s'ouvre en plein écran sans aucune barre de navigateur, comme une application téléchargée sur le Play Store.
   - Les données restent consultables hors-connexion.

---

## Méthode 2 : Génération d'un fichier .APK autonome (Google Bubblewrap / PWABuilder)

Si vous souhaitez distribuer un fichier installable `.apk` signé ou le publier sur le Google Play Store :

### Option A : En 1 clic avec PWABuilder (Recommandé)
1. Rendez-vous sur [PWABuilder.com](https://www.pwabuilder.com/).
2. Entrez l'URL :
   `https://ais-pre-ymsoame44dpxezzviuao6d-968086448026.europe-west2.run.app/competitions`
3. Cliquez sur **Package for stores** > **Android**.
4. Téléchargez directement le fichier `.apk` prêt à installer ou le `.aab` pour le Play Store !

### Option B : En ligne de commande avec Bubblewrap (CLI Google officielle)
```bash
# 1. Installer le CLI Google Bubblewrap
npm install -g @bubblewrap/cli

# 2. Initialiser le projet à partir de l'URL
bubblewrap init --manifest=https://ais-pre-ymsoame44dpxezzviuao6d-968086448026.europe-west2.run.app/manifest.webmanifest

# 3. Compiler l'APK Android signé
bubblewrap build
```
Le fichier `app-release-signed.apk` généré peut être installé directement sur n'importe quel smartphone Android par simple transfert ou téléchargement.
