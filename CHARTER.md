# Open Thesis Sandbox — Charte de l'équipe d'agents

## 0. Acteurs
- **Humain** : marbofinance / Donald
- **CEO Agent** : Applique cette charte, revoit les PRs, merge selon politique semi-auto.

## 1. Zones interdites
- .env*
- docker-compose.yml
- main.py (routing & startup)
- core/dag_store.py (immutable schema)
- CHARTER.md

## 2. Scopes autorisés
- core/auto_research.py (signaux, backtests)
- public/** (frontend)
- tests/**
- README.md

## 3. Politique de merge
- CI verte
- Aucune zone interdite
- Scope §2 uniquement
- Diff < 400 lignes
