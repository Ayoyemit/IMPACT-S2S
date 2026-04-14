"""Load real strategies from the CSV file into the database."""
import csv
import os
from models import db, Strategy, _normalize_implementation_level_token


def _normalize_level_field(level_str):
    """Map CSV 'Patient' tokens to 'Client' to match survey implementation levels."""
    parts = [p.strip() for p in (level_str or '').split(',') if p.strip()]
    return ', '.join(_normalize_implementation_level_token(p) for p in parts)


def load_csv_strategies(csv_path):
    """
    Load strategies from the real CSV file.
    Skips rows with empty Choice field.
    Returns the number of strategies loaded.
    """
    if not os.path.exists(csv_path):
        print(f"WARNING: CSV file not found at {csv_path}")
        return 0

    if Strategy.query.filter_by(is_user_submitted=False).count() > 0:
        count = Strategy.query.filter_by(is_user_submitted=False).count()
        print(f"Database already has {count} strategies. Skipping CSV load.")
        return count

    loaded = 0
    with open(csv_path, 'r', encoding='cp1252') as f:
        reader = csv.DictReader(f)
        for row in reader:
            choice = row.get('Choice', '').strip()
            if not choice:
                continue  # Skip empty rows

            level = _normalize_level_field(row.get('Level', '').strip())
            if not level:
                continue  # Skip rows with no level

            # Parse original ID
            original_id = None
            id_str = row.get('Id #', '').strip()
            if id_str:
                try:
                    original_id = float(id_str)
                except ValueError:
                    pass

            strategy = Strategy(
                original_id=original_id,
                choice=choice,
                actor_level=row.get('Socioecological Level (Actor)', '').strip(),
                recipient_level=row.get('Socioecological Level (Recipient)', '').strip(),
                level=level,
                primary_eric=row.get('Primary ERIC Strategy', '').strip(),
                secondary_eric=row.get('Secondary ERIC Strategies', '').strip(),
                evidence_based_practice=row.get('Evidence-Based Practice', '').strip(),
                source=row.get('Source', '').strip(),
                other_source=row.get('Other source', '').strip(),
                help_text=row.get('Help Text', '').strip(),
                is_active=True,
                is_user_submitted=False,
            )
            db.session.add(strategy)
            loaded += 1

    db.session.commit()
    print(f"Loaded {loaded} strategies from CSV.")
    return loaded
