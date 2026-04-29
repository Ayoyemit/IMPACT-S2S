from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timezone
import uuid

db = SQLAlchemy()


def _normalize_implementation_level_token(token):
    if token == 'Patient':
        return 'Client'
    return token


class Strategy(db.Model):
    """Strategies/choices that users compare in pairs."""
    __tablename__ = 'strategies'

    id = db.Column(db.Integer, primary_key=True)
    original_id = db.Column(db.Float, nullable=True)  # ID from CSV
    choice = db.Column(db.Text, nullable=False)
    actor_level = db.Column(db.String(100), nullable=True)  # Socioecological Level (Actor)
    recipient_level = db.Column(db.String(100), nullable=True)  # Socioecological Level (Recipient)
    level = db.Column(db.String(200), nullable=False)  # e.g. "Organization, Provider"
    primary_eric = db.Column(db.String(200), nullable=True)
    secondary_eric = db.Column(db.String(500), nullable=True)
    evidence_based_practice = db.Column(db.String(200), nullable=True)
    source = db.Column(db.String(200), nullable=True)
    other_source = db.Column(db.String(200), nullable=True)
    help_text = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    is_user_submitted = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    # Last admin sign-off (Edit All Strategies); no history retained
    last_signoff_initials = db.Column(db.String(32), nullable=True)
    last_signoff_at = db.Column(db.DateTime, nullable=True)
    last_signoff_comment = db.Column(db.Text, nullable=True)

    def get_levels(self):
        """Return list of levels this strategy belongs to.

        CSV data uses 'Patient' for the inner socioecological level; the survey UI
        uses 'Client'. Treat them as equivalent for filtering and pairing.
        """
        raw = [l.strip() for l in (self.level or '').split(',') if l.strip()]
        return [_normalize_implementation_level_token(l) for l in raw]

    def to_dict(self):
        return {
            'id': self.id,
            'choice': self.choice,
            'level': self.level,
            'levels': self.get_levels(),
            'primary_eric': self.primary_eric,
            'help_text': self.help_text,
        }


class Session(db.Model):
    """Each browser visit creates a fresh session."""
    __tablename__ = 'sessions'

    id = db.Column(db.String(50), primary_key=True)
    role = db.Column(db.String(50), nullable=False)
    consented = db.Column(db.Boolean, default=True)
    started_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    ended_at = db.Column(db.DateTime, nullable=True)
    last_activity = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    comparisons = db.relationship('Comparison', backref='session', lazy='dynamic')
    cant_decides = db.relationship('CantDecide', backref='session', lazy='dynamic')
    submitted_ideas = db.relationship('SubmittedIdea', backref='session', lazy='dynamic')

    @staticmethod
    def generate_id():
        return f"s_{uuid.uuid4().hex[:10]}"

    @property
    def duration_seconds(self):
        end = self.ended_at or self.last_activity
        if end and self.started_at:
            return (end - self.started_at).total_seconds()
        return 0

    def to_dict(self):
        return {
            'id': self.id,
            'role': self.role,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'ended_at': self.ended_at.isoformat() if self.ended_at else None,
            'duration_seconds': self.duration_seconds,
            'total_votes': self.comparisons.count(),
        }


class Comparison(db.Model):
    """Records each pairwise vote."""
    __tablename__ = 'comparisons'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    session_id = db.Column(db.String(50), db.ForeignKey('sessions.id'), nullable=False)
    winner_id = db.Column(db.Integer, db.ForeignKey('strategies.id'), nullable=False)
    loser_id = db.Column(db.Integer, db.ForeignKey('strategies.id'), nullable=False)
    level_context = db.Column(db.String(50), nullable=False)  # Which tab user was on
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    winner = db.relationship('Strategy', foreign_keys=[winner_id])
    loser = db.relationship('Strategy', foreign_keys=[loser_id])


class CantDecide(db.Model):
    """Records 'I can't decide' actions."""
    __tablename__ = 'cant_decides'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    session_id = db.Column(db.String(50), db.ForeignKey('sessions.id'), nullable=False)
    strategy_a_id = db.Column(db.Integer, db.ForeignKey('strategies.id'), nullable=False)
    strategy_b_id = db.Column(db.Integer, db.ForeignKey('strategies.id'), nullable=False)
    reason = db.Column(db.String(50), nullable=False)  # 'too_similar', 'unclear', or 'other'
    other_reason = db.Column(db.Text, nullable=True)  # free text when reason == 'other'
    level_context = db.Column(db.String(50), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    strategy_a = db.relationship('Strategy', foreign_keys=[strategy_a_id])
    strategy_b = db.relationship('Strategy', foreign_keys=[strategy_b_id])


class SubmittedIdea(db.Model):
    """User-submitted strategy ideas for admin review."""
    __tablename__ = 'submitted_ideas'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    session_id = db.Column(db.String(50), db.ForeignKey('sessions.id'), nullable=False)
    idea_text = db.Column(db.Text, nullable=False)
    user_role = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, approved, rejected, duplicate
    assigned_level = db.Column(db.String(200), nullable=True)
    assigned_primary_eric = db.Column(db.String(200), nullable=True)
    assigned_secondary_eric = db.Column(db.String(500), nullable=True)
    assigned_evidence_based = db.Column(db.String(200), nullable=True)
    assigned_help_text = db.Column(db.Text, nullable=True)
    duplicate_of_id = db.Column(db.Integer, db.ForeignKey('strategies.id'), nullable=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    # Last admin sign-off (review decision or pending edit save); no history retained
    last_signoff_initials = db.Column(db.String(32), nullable=True)
    last_signoff_at = db.Column(db.DateTime, nullable=True)
    last_signoff_comment = db.Column(db.Text, nullable=True)

    duplicate_of = db.relationship('Strategy', foreign_keys=[duplicate_of_id])


class ExposureCount(db.Model):
    """Tracks how many times each strategy has been shown (for algorithm Stage 3)."""
    __tablename__ = 'exposure_counts'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    strategy_id = db.Column(db.Integer, db.ForeignKey('strategies.id'), nullable=False, unique=True)
    count = db.Column(db.Integer, default=0)

    strategy = db.relationship('Strategy')


class AlgorithmLog(db.Model):
    """Full audit trail for every pair selection the algorithm makes."""
    __tablename__ = 'algorithm_logs'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    session_id = db.Column(db.String(50), nullable=False)
    level_context = db.Column(db.String(50), nullable=False)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    # Pair selection details
    focal_id = db.Column(db.Integer, db.ForeignKey('strategies.id'), nullable=True)
    focal_sampling_prob = db.Column(db.Float, nullable=True)
    opponent_id = db.Column(db.Integer, db.ForeignKey('strategies.id'), nullable=True)
    opponent_strength_diff = db.Column(db.Float, nullable=True)
    displayed_left_id = db.Column(db.Integer, db.ForeignKey('strategies.id'), nullable=False)
    displayed_right_id = db.Column(db.Integer, db.ForeignKey('strategies.id'), nullable=False)

    # Algorithm state at time of selection
    proxy_type = db.Column(db.String(20), nullable=True)  # 'exposure' or 'top_heavy'
    num_comparisons_used = db.Column(db.Integer, nullable=True)
    was_cold_start = db.Column(db.Boolean, default=False)

    # MAP refit details (JSON-serialized)
    map_strengths_json = db.Column(db.Text, nullable=True)  # {strategy_id: beta_value}
    exposure_counts_json = db.Column(db.Text, nullable=True)  # {strategy_id: count}
    uncertainty_weights_json = db.Column(db.Text, nullable=True)  # {strategy_id: weight}
    map_converged = db.Column(db.Boolean, nullable=True)
    map_iterations = db.Column(db.Integer, nullable=True)

    # Outcome (filled after user responds)
    outcome = db.Column(db.String(20), nullable=True)  # 'vote', 'cant_decide', or null if abandoned
    winner_id = db.Column(db.Integer, db.ForeignKey('strategies.id'), nullable=True)

    focal = db.relationship('Strategy', foreign_keys=[focal_id])
    opponent = db.relationship('Strategy', foreign_keys=[opponent_id])


class AppSettings(db.Model):
    """Singleton app-wide settings (row id=1)."""
    __tablename__ = 'app_settings'

    id = db.Column(db.Integer, primary_key=True)
    quick_guide_video_url = db.Column(db.Text, nullable=True)
    quick_guide_video_title = db.Column(db.String(500), nullable=True)


class StrategyChangeLog(db.Model):
    """Audit trail for admin strategy edits and creations."""
    __tablename__ = 'strategy_change_logs'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    strategy_id = db.Column(db.Integer, db.ForeignKey('strategies.id'), nullable=False)
    action_type = db.Column(db.String(20), nullable=False)  # create, wording_edit, metadata_edit
    old_choice = db.Column(db.Text, nullable=True)
    new_choice = db.Column(db.Text, nullable=True)
    changed_by_initials = db.Column(db.String(32), nullable=False)
    change_comment = db.Column(db.Text, nullable=False)
    changed_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    strategy = db.relationship('Strategy')

