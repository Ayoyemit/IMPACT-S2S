import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'impact-s2s-secret-key-change-in-production')
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///wiki_survey.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    ADMIN_CODE = os.environ.get('ADMIN_CODE', 'admin2026')

    # SURVEY_MODE: 'example' = 25 example strategies + random pairs
    #              'production' = real CSV strategies + Bradley-Terry adaptive algorithm
    SURVEY_MODE = os.environ.get('SURVEY_MODE', 'example')

    # Path to the real strategies CSV (used when SURVEY_MODE=production)
    STRATEGIES_CSV = os.environ.get('STRATEGIES_CSV', 'data/Strategies.csv')

    # Bradley-Terry hyperparameter: prior variance for MAP (higher = less shrinkage)
    BT_SIGMA2 = float(os.environ.get('BT_SIGMA2', '1.0'))

    # Which proxy to use: 'exposure' (Proxy A) or 'top_heavy' (Proxy B)
    BT_PROXY = os.environ.get('BT_PROXY', 'top_heavy')
