#!/usr/bin/env bash
# Demarrage de l'application de pronostics.
# Aucune dependance a installer : Python stdlib + numpy/scipy/pandas uniquement.
set -e
cd "$(dirname "$0")"

echo "== Application Pronos Foot =="

# ./lancer.sh test  -> verifie l'interface sans demarrer le serveur
if [ "${1:-}" = "test" ]; then
  echo "-> Tests d'interface (serveur deja lance sur le port 8000 requis)"
  exec node test_interface.js
fi

# 1. Les donnees sont-elles la ?
if [ ! -d data ] || [ "$(ls data/2*_*.csv 2>/dev/null | wc -l)" -lt 10 ]; then
  echo "-> Telechargement des donnees (gratuit, sans cle API)..."
  echo "   Premier lancement : environ 2 minutes."
  python3 maj.py
fi

# 2. Les modeles sont-ils entraines ?
if [ ! -f data/modeles.json ]; then
  echo "-> Entrainement des modeles (35 s environ)..."
  python3 entraine.py
fi

# 2b. Le backtest des marches secondaires a-t-il ete fait ?
if [ ! -f data/backtest_secondaires.json ]; then
  echo "-> Backtest des marches secondaires (27 s environ)..."
  python3 backtest_secondaires.py
fi

# 3. Fraicheur des donnees
python3 - <<'PY'
import json, datetime
d = json.load(open('data/modeles.json'))
g = datetime.date.fromisoformat(d['genere_le'][:10])
age = (datetime.date.today() - g).days
print(f"-> Modeles entraines le {g} ({age} jour(s)).")
if age >= 3:
    print("   Pour rafraichir :  python3 maj.py   (une seule commande fait tout)")
PY

echo "-> Demarrage du serveur sur le port ${PORT:-8000}"
exec python3 serveur.py
