#!/usr/bin/env bash
# ============================================================================
# Installe la mise à jour automatique quotidienne — Mac et Linux
# ============================================================================
# Sur Mac    : crée un agent launchd (rattrape l'exécution si la machine était
#              éteinte à l'heure prévue — c'est son avantage sur cron)
# Sur Linux  : crée une ligne cron
#
# Usage :  ./installer_auto.sh          installe à 07:00
#          ./installer_auto.sh 06:30    installe à une autre heure
#          ./installer_auto.sh --retirer   désinstalle
# ============================================================================
set -e
cd "$(dirname "$0")"
DIR="$(pwd)"

HEURE="${1:-07:00}"
PY="$(command -v python3 || true)"

if [ -z "$PY" ]; then
  echo "ERREUR : python3 est introuvable."
  echo "Installe Python d'abord, puis relance ce script."
  exit 1
fi

echo "== Installation de la mise à jour automatique =="
echo "   dossier  : $DIR"
echo "   python   : $PY"
echo "   heure    : $HEURE"
echo

# ---------------------------------------------------------------- désinstallation
if [ "$HEURE" = "--retirer" ]; then
  if [ "$(uname)" = "Darwin" ]; then
    PLIST="$HOME/Library/LaunchAgents/com.pronosfoot.maj.plist"
    launchctl unload "$PLIST" 2>/dev/null || true
    rm -f "$PLIST"
    echo "-> agent launchd retiré"
  else
    if command -v crontab >/dev/null 2>&1; then
      crontab -l 2>/dev/null | grep -v "pronos-foot/maj.py" | crontab - || true
      echo "-> ligne cron retirée"
    else
      echo "-> cron n'est pas installé sur cette machine : rien à retirer."
    fi
  fi
  exit 0
fi

# ---------------------------------------------------------------- vérification
if ! echo "$HEURE" | grep -Eq '^([01][0-9]|2[0-3]):[0-5][0-9]$'; then
  echo "ERREUR : heure invalide « $HEURE ». Format attendu : HH:MM entre 00:00 et 23:59"
  exit 1
fi
HH="${HEURE%%:*}"; MM="${HEURE##*:}"

# vérifie que les dépendances sont là (numpy, scipy, pandas)
if ! "$PY" -c "import numpy, scipy, pandas" 2>/dev/null; then
  echo "ERREUR : les bibliothèques numpy / scipy / pandas manquent."
  echo "Installe-les avec :"
  echo "    $PY -m pip install numpy scipy pandas"
  exit 1
fi
echo "   dépendances numpy / scipy / pandas : OK"

# --------------------------------------------------------------------- Mac
if [ "$(uname)" = "Darwin" ]; then
  mkdir -p "$HOME/Library/LaunchAgents"
  PLIST="$HOME/Library/LaunchAgents/com.pronosfoot.maj.plist"
  cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
 "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>              <string>com.pronosfoot.maj</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PY</string>
    <string>$DIR/maj.py</string>
  </array>
  <key>WorkingDirectory</key>   <string>$DIR</string>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>     <integer>$((10#$HH))</integer>
    <key>Minute</key>   <integer>$((10#$MM))</integer>
  </dict>
  <key>RunAtLoad</key>          <false/>
  <key>StandardOutPath</key>    <string>$DIR/data/maj-stdout.log</string>
  <key>StandardErrorPath</key>  <string>$DIR/data/maj-stderr.log</string>
</dict>
</plist>
EOF
  launchctl unload "$PLIST" 2>/dev/null || true
  launchctl load "$PLIST"
  echo
  echo "-> Agent launchd installé : $PLIST"
  echo "   La mise à jour tournera tous les jours à $HEURE."
  echo "   Si le Mac est éteint à cette heure, elle sera rattrapée au réveil."

# ------------------------------------------------------------------- Linux
elif ! command -v crontab >/dev/null 2>&1; then
  echo
  echo "ERREUR : ni launchd (Mac) ni cron (Linux) n'est disponible ici."
  echo "Cette machine ne peut pas planifier la mise à jour toute seule."
  echo "Tu peux toujours la lancer à la main :  $PY maj.py"
  exit 1
else
  CRON="$((10#$MM)) $((10#$HH)) * * * cd $DIR && $PY maj.py >> $DIR/data/maj-stdout.log 2>&1"
  # retire l'ancienne ligne s'il y en a une, puis ajoute la nouvelle
  ( crontab -l 2>/dev/null | grep -v "pronos-foot/maj.py" ; echo "$CRON" ) | crontab -
  echo
  echo "-> Ligne cron installée : $CRON"
  echo "   La mise à jour tournera tous les jours à $HEURE."
  echo "   Attention : cron ne rattrape PAS une exécution manquée si la machine"
  echo "   était éteinte. Si c'est ton cas, préfère une heure où elle est allumée."
fi

cat <<EOF

== Vérification ==
   Test immédiat (sans attendre demain) :
       cd $DIR && $PY maj.py --check

   Voir ce qui s'est passé :
       tail -30 $DIR/data/maj.log

   Choisir où déposer le fichier pour ton téléphone :
       cd $DIR && $PY maj.py --config

== Désinstallation ==
       ./installer_auto.sh --retirer
EOF
