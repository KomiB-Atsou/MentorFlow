from bson.objectid import ObjectId
from flask import Flask, jsonify, request
from flask_pymongo import PyMongo
import re
from datetime import datetime

# Initialisation de l'application Flask
app = Flask(__name__)

# --- Configuration de la connexion à MongoDB ---
# Assurez-vous que votre serveur MongoDB est en cours d'exécution sur le port par défaut (27017).
# Remplacez "db_timesheets" par le nom de votre base de données.
app.config["MONGO_URI"] = "mongodb://localhost:27017/db_timesheets"

# Pour une connexion à MongoDB Atlas, le format de l'URI serait :
# app.config["MONGO_URI"] = "mongodb+srv://<username>:<password>@<cluster-url>/db_timesheets?retryWrites=true&w=majority"

# Initialisation de PyMongo
mongo = PyMongo(app)

# --- Algorithme de catégorisation (placeholder) ---
def categorize_task(title, description):
    """Applique une logique pour déterminer la catégorie d'une tâche."""
    # Ceci est un exemple simple. Vous devrez implémenter votre propre logique ici.
    title_lower = title.lower()
    if "réunion" in title_lower or "meeting" in title_lower:
        return "Réunions"
    if "développement" in title_lower or "dev" in title_lower:
        return "Développement"
    return "Non catégorisé"

# --- Logique de parsing pour les notes Notion ---

def parse_notion_note(title, content):
    """
    Parse le contenu texte d'une note Notion pour en extraire une feuille de temps structurée.
    """
    # 1. Extraire l'année du titre de la note
    year_match = re.search(r'\b(20\d{2})\b', title)
    if not year_match:
        raise ValueError("L'année n'a pas pu être trouvée dans le titre de la note.")
    year = int(year_match.group(1))

    # Dictionnaire pour mapper les mois en français à leur numéro
    month_map = {
        'jan': 1, 'janv': 1, 'fév': 2, 'mar': 3, 'avr': 4, 'mai': 5, 'juin': 6,
        'juil': 7, 'aoû': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'déc': 12
    }

    # 2. Séparer le contenu en blocs journaliers (séparés par au moins une ligne vide)
    day_blocks = re.split(r'\n\s*\n', content.strip())

    parsed_days = []
    for block in day_blocks:
        lines = block.strip().split('\n')
        header = lines[0].strip() if lines else ''

        # 3. Parser l'en-tête du jour (ex: "Lun 15 janv")
        day_match = re.match(r'(\w+)\s+(\d{1,2})\s+([a-zéûû\.]+)', header.lower())
        if day_match:
            day_name = day_match.group(1)
            day_number = int(day_match.group(2))
            month_abbr = day_match.group(3).replace('.', '') # Gère "janv."

            month_number = month_map.get(month_abbr)
            if not month_number:
                continue # Ignore les blocs qui ne correspondent pas à un jour

            try:
                date_obj = datetime(year, month_number, day_number)
                parsed_tasks = []

                # 4. Parser chaque ligne de tâche pour ce jour
                for task_line in lines[1:]:
                    task_line = task_line.strip()
                    # Regex pour "07h00 08h30 Titre. Description"
                    task_match = re.match(r'(\d{2})h(\d{2})\s+(\d{2})h(\d{2})\s+(.*)', task_line)
                    if not task_match:
                        continue

                    start_hour, start_min, end_hour, end_min, full_title = map(str.strip, task_match.groups())

                    start_time = date_obj.replace(hour=int(start_hour), minute=int(start_min))
                    end_time = date_obj.replace(hour=int(end_hour), minute=int(end_min))
                    duration = (end_time - start_time).total_seconds() / 60

                    # Séparer le titre de la description
                    title_parts = full_title.split('.', 1)
                    task_title = title_parts[0].strip()
                    description = title_parts[1].strip() if len(title_parts) > 1 else ""

                    parsed_tasks.append({
                        "start_time": start_time,
                        "end_time": end_time,
                        "duration_minutes": duration,
                        "title": task_title,
                        "description": description,
                        "category": categorize_task(task_title, description), # Catégorisation à la volée
                        "raw_task_line": task_line
                    })
                
                if parsed_tasks:
                    parsed_days.append({
                        "date": date_obj,
                        "day_name": day_name,
                        "tasks": parsed_tasks
                    })
            except ValueError:
                # Gère les dates invalides (ex: 30 fév)
                continue

    return {
        "note_title": title,
        "year": year,
        "raw_content": content,
        "days": parsed_days,
        "imported_at": datetime.utcnow()
    }

# --- Définition des routes de l'API ---

@app.route('/import/notion', methods=['POST'])
def import_from_notion():
    """Importe une feuille de temps depuis une note Notion."""
    data = request.get_json()
    if not data or 'title' not in data or 'content' not in data:
        return jsonify({'error': 'Les champs "title" et "content" sont requis'}), 400

    try:
        timesheet_data = parse_notion_note(data['title'], data['content'])
        if not timesheet_data['days']:
            return jsonify({'error': 'Aucun jour valide n\'a pu être parsé dans le contenu fourni.'}), 400
            
        # Insertion dans la collection 'timesheets'
        timesheet_id = mongo.db.timesheets.insert_one(timesheet_data).inserted_id
        
        # Récupération du document inséré pour le retourner dans la réponse
        new_timesheet = mongo.db.timesheets.find_one({'_id': timesheet_id})
        
        # Conversion des ObjectId et datetime en str pour la réponse JSON
        new_timesheet['_id'] = str(new_timesheet['_id'])
        new_timesheet['imported_at'] = new_timesheet['imported_at'].isoformat()
        for day in new_timesheet['days']:
            day['date'] = day['date'].isoformat()
            for task in day['tasks']:
                task['start_time'] = task['start_time'].isoformat()
                task['end_time'] = task['end_time'].isoformat()

        return jsonify(new_timesheet), 201

    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': f'Une erreur inattendue est survenue: {e}'}), 500

@app.route('/timesheets', methods=['GET'])
def get_timesheets():
    """Récupère toutes les feuilles de temps."""
    timesheets_collection = mongo.db.timesheets
    all_timesheets = []
    # Le deuxième argument de find() permet d'exclure des champs (ici, le contenu brut)
    for ts in timesheets_collection.find({}, {'raw_content': 0}):
        ts['_id'] = str(ts['_id'])
        # Simplification pour la liste, on ne convertit pas toutes les dates ici
        all_timesheets.append(ts)
    return jsonify(all_timesheets), 200

@app.route('/timesheets/<timesheet_id>', methods=['GET'])
def get_timesheet(timesheet_id):
    """Récupère une feuille de temps spécifique par son ID."""
    timesheets_collection = mongo.db.timesheets
    try:
        ts = timesheets_collection.find_one_or_404({'_id': ObjectId(timesheet_id)})
        ts['_id'] = str(ts['_id'])
        # Conversion des dates en string pour la réponse JSON
        ts['imported_at'] = ts['imported_at'].isoformat()
        for day in ts['days']:
            day['date'] = day['date'].isoformat()
            for task in day['tasks']:
                task['start_time'] = task['start_time'].isoformat()
                task['end_time'] = task['end_time'].isoformat()
        return jsonify(ts), 200
    except Exception:
        return jsonify({'error': 'Feuille de temps non trouvée ou ID invalide'}), 404

# Point d'entrée pour exécuter l'application
if __name__ == '__main__':
    # Le mode debug ne doit pas être utilisé en production
    app.run(debug=True)
