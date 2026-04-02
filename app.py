from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from config import Config
from models import (db, Strategy, Session as UserSession, Comparison, CantDecide,
                    SubmittedIdea, ExposureCount, AlgorithmLog, AppSettings)
from seed_data import seed_example_data
from load_csv import load_csv_strategies
from algorithm import AdaptivePairSelector, get_bt_score
from datetime import datetime, timezone
from urllib.parse import urlparse, parse_qs
from sqlalchemy import inspect, text
import random
import json
import re

app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)

# ── Mode and algorithm setup ───────────────────────────────────────────────────
SURVEY_MODE = app.config.get('SURVEY_MODE', 'example')

pair_selector = AdaptivePairSelector(
    sigma2=app.config.get('BT_SIGMA2', 1.0),
    proxy=app.config.get('BT_PROXY', 'top_heavy'),
)

# Role -> default first level mapping
ROLE_LEVEL_ORDER = {
    'Provider': ['Provider', 'Organization', 'System', 'Client'],
    'Implementation Scientist': ['Organization', 'Provider', 'System', 'Client'],
    'Patient/Family': ['Client', 'Provider', 'Organization', 'System'],
    'Policy/Advocacy': ['System', 'Organization', 'Provider', 'Client'],
}

LEVEL_COLORS = {
    'Provider': {'border': '#f472b6', 'bg': 'rgba(244,114,182,0.30)'},
    'Organization': {'border': '#fde68a', 'bg': 'rgba(253,230,138,0.30)'},
    'Client': {'border': '#3b82f6', 'bg': 'rgba(59,130,246,0.28)'},
    'System': {'border': '#a7f3d0', 'bg': 'rgba(167,243,208,0.26)'},
}


def migrate_app_settings_schema():
    """Align app_settings with models: drop columns removed from AppSettings."""
    try:
        inspector = inspect(db.engine)
        if 'app_settings' not in inspector.get_table_names():
            return
    except Exception as exc:
        print(f'[IMPACT S2S] app_settings schema inspect skipped: {exc}')
        return

    col_names = {c['name'] for c in inspector.get_columns('app_settings')}
    if 'quick_guide_video_filename' not in col_names:
        return

    dialect = db.engine.dialect.name
    if dialect == 'postgresql':
        stmt = text('ALTER TABLE app_settings DROP COLUMN IF EXISTS quick_guide_video_filename')
    else:
        stmt = text('ALTER TABLE app_settings DROP COLUMN quick_guide_video_filename')

    try:
        with db.engine.begin() as conn:
            conn.execute(stmt)
        print('[IMPACT S2S] app_settings: dropped deprecated column quick_guide_video_filename')
    except Exception as exc:
        print(f'[IMPACT S2S] app_settings schema cleanup skipped (e.g. SQLite < 3.35): {exc}')


# ─── Initialize DB ─────────────────────────────────────────────────────────────
with app.app_context():
    db.create_all()
    migrate_app_settings_schema()
    if AppSettings.query.get(1) is None:
        db.session.add(AppSettings(id=1))
        db.session.commit()
    if SURVEY_MODE == 'production':
        csv_path = app.config.get('STRATEGIES_CSV', 'data/Strategies.csv')
        load_csv_strategies(csv_path)
        print(f"[IMPACT S2S] Running in PRODUCTION mode (BT adaptive algorithm)")
    else:
        seed_example_data()
        print(f"[IMPACT S2S] Running in EXAMPLE mode (random pair selection)")


# ─── Helpers ────────────────────────────────────────────────────────────────────

def _normalize_http_url(url):
    """Ensure urlparse sees a scheme (paste often omits https://)."""
    u = (url or '').strip()
    if not u:
        return u
    if not re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*:', u):
        u = 'https://' + u
    return u


def _youtube_video_id(url):
    if not url:
        return None
    u = _normalize_http_url(url.strip())
    parsed = urlparse(u)
    host = (parsed.netloc or '').lower()
    path = parsed.path or ''
    if 'youtu.be' in host:
        vid = path.lstrip('/').split('/')[0]
        vid = vid.split('?')[0] if vid else None
        if vid:
            return vid
    if 'youtube.com' in host or 'youtube-nocookie.com' in host:
        if path.startswith('/embed/'):
            return path.split('/embed/')[-1].split('/')[0]
        if path.startswith('/shorts/'):
            return path.split('/shorts/')[-1].split('/')[0]
        qs = parse_qs(parsed.query)
        if 'v' in qs:
            return qs['v'][0]
    # Fallback: recover ID from messy pastes (extra params, redirects, etc.)
    m = re.search(
        r'(?:youtube\.com/embed/|youtube-nocookie\.com/embed/|youtu\.be/|youtube\.com/shorts/)'
        r'([a-zA-Z0-9_-]{6,})|[?&]v=([a-zA-Z0-9_-]{6,})',
        u,
    )
    if m:
        return m.group(1) or m.group(2)
    return None


def _vimeo_video_id(url):
    if not url:
        return None
    u = _normalize_http_url(url.strip())
    m = re.search(r'vimeo\.com/(?:video/)?(\d+)', u)
    return m.group(1) if m else None


def build_quick_guide_context(settings):
    """Build template context for the Quick Guide video area."""
    default_title = 'How to use the project app — A walkthrough'
    title = (settings.quick_guide_video_title or '').strip() or default_title

    raw_url = (settings.quick_guide_video_url or '').strip()
    if not raw_url:
        return {'type': 'placeholder', 'video_src': None, 'embed_src': None, 'title': title}

    raw_url = _normalize_http_url(raw_url)

    yt = _youtube_video_id(raw_url)
    if yt:
        return {
            'type': 'embed',
            'video_src': None,
            'embed_src': f'https://www.youtube-nocookie.com/embed/{yt}',
            'title': title,
        }
    vm = _vimeo_video_id(raw_url)
    if vm:
        return {
            'type': 'embed',
            'video_src': None,
            'embed_src': f'https://player.vimeo.com/video/{vm}',
            'title': title,
        }
    return {
        'type': 'video',
        'video_src': raw_url,
        'embed_src': None,
        'title': title,
    }


def get_session_level_counts(sid):
    counts = {}
    for level in ['Provider', 'Organization', 'System', 'Client']:
        counts[level] = Comparison.query.filter_by(session_id=sid, level_context=level).count()
    return counts


def get_exposure_counts_for_level(level):
    strategies = Strategy.query.filter(Strategy.is_active == True).all()
    level_strategies = [s for s in strategies if level in s.get_levels()]
    exposures = {}
    for s in level_strategies:
        ec = ExposureCount.query.filter_by(strategy_id=s.id).first()
        exposures[s.id] = ec.count if ec else 0
    return exposures


def get_comparisons_for_level(level):
    strategies = Strategy.query.filter(Strategy.is_active == True).all()
    level_sids = set(s.id for s in strategies if level in s.get_levels())
    all_comparisons = Comparison.query.all()
    return [(c.winner_id, c.loser_id) for c in all_comparisons
            if c.winner_id in level_sids and c.loser_id in level_sids]


def increment_exposure(strategy_a_id, strategy_b_id):
    for sid in [strategy_a_id, strategy_b_id]:
        ec = ExposureCount.query.filter_by(strategy_id=sid).first()
        if ec:
            ec.count += 1
        else:
            db.session.add(ExposureCount(strategy_id=sid, count=1))


def save_algorithm_log(log_data, session_id, level):
    algo_log = AlgorithmLog(
        session_id=session_id,
        level_context=level,
        focal_id=log_data.get('focal_id'),
        focal_sampling_prob=log_data.get('focal_sampling_prob'),
        opponent_id=log_data.get('opponent_id'),
        opponent_strength_diff=log_data.get('opponent_strength_diff'),
        displayed_left_id=log_data.get('displayed_left_id'),
        displayed_right_id=log_data.get('displayed_right_id'),
        proxy_type=log_data.get('proxy_type'),
        num_comparisons_used=log_data.get('num_comparisons'),
        was_cold_start=log_data.get('was_cold_start', False),
        map_strengths_json=json.dumps(log_data.get('map_strengths', {})),
        exposure_counts_json=json.dumps(log_data.get('exposure_counts', {})),
        uncertainty_weights_json=json.dumps(log_data.get('uncertainty_weights', {})),
        map_converged=log_data.get('map_converged'),
        map_iterations=log_data.get('map_iterations'),
    )
    db.session.add(algo_log)
    db.session.flush()
    return algo_log.id


# ─── Page Routes ────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/survey')
def survey():
    sid = session.get('session_id')
    role = session.get('role')
    if not sid or not role:
        return redirect(url_for('index'))
    level_order = ROLE_LEVEL_ORDER.get(role, ['Provider', 'Organization', 'System', 'Client'])
    app_settings = AppSettings.query.get(1)
    quick_guide = build_quick_guide_context(app_settings) if app_settings else build_quick_guide_context(
        AppSettings()
    )
    return render_template('survey.html', role=role, level_order=level_order,
                           level_colors=LEVEL_COLORS, session_id=sid,
                           quick_guide=quick_guide)


@app.route('/admin')
def admin_gate():
    if session.get('is_admin'):
        return redirect('/admin/dashboard')
    resp = app.make_response(render_template('admin/login.html'))
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    resp.headers['Pragma'] = 'no-cache'
    return resp


@app.route('/admin/dashboard')
def admin_dashboard():
    if not session.get('is_admin'):
        return redirect('/admin')
    resp = app.make_response(render_template('admin/dashboard.html', survey_mode=SURVEY_MODE))
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    resp.headers['Pragma'] = 'no-cache'
    return resp


# ─── Survey API ─────────────────────────────────────────────────────────────────

@app.route('/api/start-session', methods=['POST'])
def start_session():
    data = request.json
    role = data.get('role')
    if role not in ROLE_LEVEL_ORDER:
        return jsonify({'error': 'Invalid role'}), 400

    sid = UserSession.generate_id()
    db.session.add(UserSession(id=sid, role=role, consented=True))
    db.session.commit()

    session['session_id'] = sid
    session['role'] = role
    return jsonify({'session_id': sid, 'role': role})


@app.route('/api/get-pair', methods=['POST'])
def get_pair():
    data = request.json
    level = data.get('level', 'Provider')
    sid = session.get('session_id')
    if not sid:
        return jsonify({'error': 'No active session'}), 400

    all_strategies = Strategy.query.filter(Strategy.is_active == True).all()
    level_strategies = [s for s in all_strategies if level in s.get_levels()]

    if len(level_strategies) < 2:
        return jsonify({'error': 'Not enough strategies for this level'}), 400

    strategy_map = {s.id: s for s in level_strategies}
    algo_log_id = None

    if SURVEY_MODE == 'production':
        # ── Bradley-Terry adaptive pair selection ──
        level_sids = [s.id for s in level_strategies]
        exposures = get_exposure_counts_for_level(level)
        comparisons = get_comparisons_for_level(level)

        log_data = pair_selector.select_pair(level_sids, comparisons, exposures)
        if log_data is None:
            return jsonify({'error': 'Could not select pair'}), 500

        left_id = log_data['displayed_left_id']
        right_id = log_data['displayed_right_id']

        increment_exposure(left_id, right_id)
        algo_log_id = save_algorithm_log(log_data, sid, level)
        db.session.commit()

        strategy_a = strategy_map[left_id]
        strategy_b = strategy_map[right_id]
    else:
        # ── Example mode: random pair ──
        pair = random.sample(level_strategies, 2)
        if random.random() < 0.5:
            pair = [pair[1], pair[0]]
        strategy_a, strategy_b = pair[0], pair[1]

    return jsonify({
        'strategy_a': strategy_a.to_dict(),
        'strategy_b': strategy_b.to_dict(),
        'algo_log_id': algo_log_id,
    })


@app.route('/api/vote', methods=['POST'])
def vote():
    data = request.json
    sid = session.get('session_id')
    if not sid:
        return jsonify({'error': 'No active session'}), 400

    winner_id = data.get('winner_id')
    loser_id = data.get('loser_id')
    level_context = data.get('level')
    algo_log_id = data.get('algo_log_id')

    if not all([winner_id, loser_id, level_context]):
        return jsonify({'error': 'Missing data'}), 400

    db.session.add(Comparison(session_id=sid, winner_id=winner_id,
                              loser_id=loser_id, level_context=level_context))

    # Update algorithm log with outcome
    if algo_log_id and SURVEY_MODE == 'production':
        algo_log = AlgorithmLog.query.get(algo_log_id)
        if algo_log:
            algo_log.outcome = 'vote'
            algo_log.winner_id = winner_id

    user_session = UserSession.query.get(sid)
    if user_session:
        user_session.last_activity = datetime.now(timezone.utc)

    db.session.commit()
    return jsonify({'success': True, 'level_counts': get_session_level_counts(sid)})


@app.route('/api/cant-decide', methods=['POST'])
def cant_decide():
    data = request.json
    sid = session.get('session_id')
    if not sid:
        return jsonify({'error': 'No active session'}), 400

    db.session.add(CantDecide(
        session_id=sid, strategy_a_id=data.get('strategy_a_id'),
        strategy_b_id=data.get('strategy_b_id'), reason=data.get('reason'),
        level_context=data.get('level')))

    algo_log_id = data.get('algo_log_id')
    if algo_log_id and SURVEY_MODE == 'production':
        algo_log = AlgorithmLog.query.get(algo_log_id)
        if algo_log:
            algo_log.outcome = 'cant_decide'

    user_session = UserSession.query.get(sid)
    if user_session:
        user_session.last_activity = datetime.now(timezone.utc)

    db.session.commit()
    return jsonify({'success': True})


@app.route('/api/submit-idea', methods=['POST'])
def submit_idea():
    data = request.json
    sid = session.get('session_id')
    role = session.get('role')
    if not sid:
        return jsonify({'error': 'No active session'}), 400

    idea_text = data.get('idea_text', '').strip()
    if not idea_text:
        return jsonify({'error': 'Idea text is required'}), 400

    db.session.add(SubmittedIdea(session_id=sid, idea_text=idea_text, user_role=role))

    user_session = UserSession.query.get(sid)
    if user_session:
        user_session.last_activity = datetime.now(timezone.utc)

    db.session.commit()
    return jsonify({'success': True, 'message': 'Your idea has been submitted for review. Thank you!'})


@app.route('/api/session-heartbeat', methods=['POST'])
def session_heartbeat():
    sid = session.get('session_id')
    if sid:
        user_session = UserSession.query.get(sid)
        if user_session:
            user_session.last_activity = datetime.now(timezone.utc)
            db.session.commit()
    return jsonify({'ok': True})


@app.route('/api/end-session', methods=['POST'])
def end_session():
    sid = session.get('session_id')
    if sid:
        user_session = UserSession.query.get(sid)
        if user_session:
            user_session.ended_at = datetime.now(timezone.utc)
            db.session.commit()
    return jsonify({'ok': True})


@app.route('/api/level-counts', methods=['GET'])
def level_counts():
    sid = session.get('session_id')
    if not sid:
        return jsonify({})
    return jsonify(get_session_level_counts(sid))


# ─── Admin API ──────────────────────────────────────────────────────────────────

@app.route('/api/admin/login', methods=['POST'])
def admin_login():
    data = request.json
    if data.get('code') == app.config['ADMIN_CODE']:
        session['is_admin'] = True
        return jsonify({'success': True, 'redirect': '/admin/dashboard'})
    return jsonify({'error': 'Invalid access code'}), 401


@app.route('/api/admin/rankings', methods=['GET'])
def admin_rankings():
    if not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 401

    filter_type = request.args.get('filter', 'overall')
    filter_value = request.args.get('value', '')

    if SURVEY_MODE == 'production':
        rankings = _bt_rankings(filter_type, filter_value)
    else:
        rankings = _simple_rankings(filter_type, filter_value)

    total_strategies = Strategy.query.filter_by(is_active=True).count()
    total_votes = Comparison.query.count()
    total_participants = UserSession.query.count()
    max_comp = total_strategies * (total_strategies - 1) // 2 if total_strategies > 1 else 0

    return jsonify({
        'rankings': rankings[:12],
        'all_rankings': rankings,
        'total_strategies': total_strategies,
        'total_votes': total_votes,
        'total_participants': total_participants,
        'max_comparisons': max_comp,
        'mode': SURVEY_MODE,
    })


def _bt_rankings(filter_type, filter_value):
    all_strategies = Strategy.query.filter_by(is_active=True).all()

    if filter_type == 'level' and filter_value:
        strategies = [s for s in all_strategies if filter_value in s.get_levels()]
    else:
        strategies = all_strategies

    strategy_ids = [s.id for s in strategies]
    strategy_map = {s.id: s for s in strategies}
    sid_set = set(strategy_ids)

    if filter_type == 'role' and filter_value:
        role_sids = {s.id for s in UserSession.query.filter_by(role=filter_value).all()}
        comparisons = [(c.winner_id, c.loser_id) for c in Comparison.query.all()
                       if c.session_id in role_sids and c.winner_id in sid_set and c.loser_id in sid_set]
    elif filter_type == 'eric' and filter_value:
        eric_ids = set(s.id for s in strategies if s.primary_eric == filter_value)
        comparisons = [(c.winner_id, c.loser_id) for c in Comparison.query.all()
                       if c.winner_id in eric_ids and c.loser_id in eric_ids]
        strategy_ids = list(eric_ids)
        strategy_map = {sid: strategy_map[sid] for sid in eric_ids if sid in strategy_map}
    else:
        comparisons = [(c.winner_id, c.loser_id) for c in Comparison.query.all()
                       if c.winner_id in sid_set and c.loser_id in sid_set]

    result = pair_selector.compute_rankings(strategy_ids, comparisons)
    rankings = []
    for sid, beta in result['rankings']:
        s = strategy_map.get(sid)
        if s:
            wins = sum(1 for w, l in comparisons if w == sid)
            appearances = sum(1 for w, l in comparisons if w == sid or l == sid)
            rankings.append({
                'id': s.id, 'choice': s.choice, 'level': s.level,
                'primary_eric': s.primary_eric, 'score': get_bt_score(beta),
                'beta': round(beta, 4), 'wins': wins, 'appearances': appearances,
            })
    return rankings


def _simple_rankings(filter_type, filter_value):
    comparisons = Comparison.query.all()
    stats = {}
    for c in comparisons:
        if filter_type == 'level' and filter_value and c.level_context != filter_value:
            continue
        if filter_type == 'role' and filter_value:
            s = UserSession.query.get(c.session_id)
            if not s or s.role != filter_value:
                continue
        for sid in [c.winner_id, c.loser_id]:
            if sid not in stats:
                stats[sid] = {'wins': 0, 'appearances': 0}
        stats[c.winner_id]['wins'] += 1
        stats[c.winner_id]['appearances'] += 1
        stats[c.loser_id]['appearances'] += 1

    rankings = []
    for strategy_id, s in stats.items():
        strategy = Strategy.query.get(strategy_id)
        if strategy and s['appearances'] > 0:
            rankings.append({
                'id': strategy.id, 'choice': strategy.choice, 'level': strategy.level,
                'primary_eric': strategy.primary_eric,
                'score': round(s['wins'] / s['appearances'] * 100, 1),
                'wins': s['wins'], 'appearances': s['appearances'],
            })
    rankings.sort(key=lambda x: x['score'], reverse=True)
    return rankings


@app.route('/api/admin/submitted-ideas', methods=['GET'])
def admin_submitted_ideas():
    if not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 401

    status_filter = request.args.get('status', 'all')
    query = SubmittedIdea.query.order_by(SubmittedIdea.created_at.desc())
    if status_filter != 'all':
        query = query.filter_by(status=status_filter)

    ideas = query.all()
    counts = {
        'pending': SubmittedIdea.query.filter_by(status='pending').count(),
        'approved': SubmittedIdea.query.filter_by(status='approved').count(),
        'rejected': SubmittedIdea.query.filter_by(status='rejected').count(),
        'duplicate': SubmittedIdea.query.filter_by(status='duplicate').count(),
        'total': SubmittedIdea.query.count(),
    }

    return jsonify({
        'ideas': [{
            'id': i.id, 'idea_text': i.idea_text, 'user_role': i.user_role,
            'status': i.status, 'assigned_level': i.assigned_level,
            'assigned_primary_eric': i.assigned_primary_eric,
            'assigned_secondary_eric': i.assigned_secondary_eric,
            'assigned_evidence_based': i.assigned_evidence_based,
            'assigned_help_text': i.assigned_help_text,
            'created_at': i.created_at.isoformat(),
            'reviewed_at': i.reviewed_at.isoformat() if i.reviewed_at else None,
        } for i in ideas],
        'counts': counts,
    })


@app.route('/api/admin/review-idea', methods=['POST'])
def admin_review_idea():
    if not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.json
    idea = SubmittedIdea.query.get(data.get('idea_id'))
    if not idea:
        return jsonify({'error': 'Idea not found'}), 404

    action = data.get('action')
    idea.status = action
    idea.reviewed_at = datetime.now(timezone.utc)
    idea.assigned_level = data.get('level', idea.assigned_level)
    idea.assigned_primary_eric = data.get('primary_eric', idea.assigned_primary_eric)
    idea.assigned_secondary_eric = data.get('secondary_eric', idea.assigned_secondary_eric)
    idea.assigned_evidence_based = data.get('evidence_based', idea.assigned_evidence_based)
    idea.assigned_help_text = data.get('help_text', idea.assigned_help_text)

    if action == 'approved' and idea.assigned_level:
        db.session.add(Strategy(
            choice=idea.idea_text, level=idea.assigned_level,
            primary_eric=idea.assigned_primary_eric or '',
            secondary_eric=idea.assigned_secondary_eric or '',
            evidence_based_practice=idea.assigned_evidence_based or '',
            help_text=idea.assigned_help_text or '',
            is_active=True, is_user_submitted=True))

    if action == 'duplicate':
        idea.duplicate_of_id = data.get('duplicate_of_id')

    db.session.commit()
    return jsonify({'success': True})


@app.route('/api/admin/cant-decides', methods=['GET'])
def admin_cant_decides():
    if not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 401

    records = CantDecide.query.order_by(CantDecide.created_at.desc()).all()
    return jsonify({
        'records': [{
            'id': r.id,
            'strategy_a': r.strategy_a.choice if r.strategy_a else 'N/A',
            'strategy_b': r.strategy_b.choice if r.strategy_b else 'N/A',
            'reason': r.reason, 'level': r.level_context,
            'user_role': UserSession.query.get(r.session_id).role if UserSession.query.get(r.session_id) else 'N/A',
            'created_at': r.created_at.isoformat(),
        } for r in records],
        'total': len(records),
        'by_reason': {
            'too_similar': CantDecide.query.filter_by(reason='too_similar').count(),
            'unclear': CantDecide.query.filter_by(reason='unclear').count(),
        }
    })


@app.route('/api/admin/participants', methods=['GET'])
def admin_participants():
    if not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 401

    sessions = UserSession.query.order_by(UserSession.started_at.desc()).all()
    participants = []
    for s in sessions:
        vote_count = Comparison.query.filter_by(session_id=s.id).count()
        idea_count = SubmittedIdea.query.filter_by(session_id=s.id).count()
        cant_decide_count = CantDecide.query.filter_by(session_id=s.id).count()
        level_votes = db.session.query(Comparison.level_context).filter_by(session_id=s.id).distinct().all()

        participants.append({
            'id': s.id, 'role': s.role,
            'started_at': s.started_at.isoformat() if s.started_at else None,
            'ended_at': s.ended_at.isoformat() if s.ended_at else None,
            'duration_seconds': s.duration_seconds,
            'votes': vote_count, 'ideas_submitted': idea_count,
            'cant_decides': cant_decide_count,
            'levels_interacted': [lv[0] for lv in level_votes],
        })

    return jsonify({
        'participants': participants, 'total': len(participants),
        'by_role': {role: UserSession.query.filter_by(role=role).count()
                    for role in ROLE_LEVEL_ORDER.keys()}
    })


# ─── Strategy Management API ───────────────────────────────────────────────────

@app.route('/api/admin/strategies', methods=['GET'])
def admin_strategies():
    """List all strategies with search and pagination."""
    if not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 401

    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    search = request.args.get('search', '').strip()

    query = Strategy.query.order_by(Strategy.id.asc())
    if search:
        query = query.filter(Strategy.choice.ilike(f'%{search}%'))

    total = query.count()
    strategies = query.offset((page - 1) * per_page).limit(per_page).all()

    return jsonify({
        'strategies': [{
            'id': s.id, 'original_id': s.original_id, 'choice': s.choice,
            'actor_level': s.actor_level, 'recipient_level': s.recipient_level,
            'level': s.level, 'primary_eric': s.primary_eric,
            'secondary_eric': s.secondary_eric,
            'evidence_based_practice': s.evidence_based_practice,
            'source': s.source, 'other_source': s.other_source,
            'help_text': s.help_text, 'is_active': s.is_active,
            'is_user_submitted': s.is_user_submitted,
        } for s in strategies],
        'total': total, 'page': page, 'per_page': per_page,
    })


@app.route('/api/admin/strategies/<int:strategy_id>', methods=['GET'])
def admin_get_strategy(strategy_id):
    if not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 401
    s = Strategy.query.get_or_404(strategy_id)
    return jsonify({
        'id': s.id, 'original_id': s.original_id, 'choice': s.choice,
        'actor_level': s.actor_level, 'recipient_level': s.recipient_level,
        'level': s.level, 'primary_eric': s.primary_eric,
        'secondary_eric': s.secondary_eric,
        'evidence_based_practice': s.evidence_based_practice,
        'source': s.source, 'other_source': s.other_source,
        'help_text': s.help_text, 'is_active': s.is_active,
        'is_user_submitted': s.is_user_submitted,
    })


@app.route('/api/admin/strategies/<int:strategy_id>', methods=['PUT'])
def admin_update_strategy(strategy_id):
    if not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 401
    s = Strategy.query.get_or_404(strategy_id)
    data = request.json

    s.choice = data.get('choice', s.choice)
    s.level = data.get('level', s.level)
    s.actor_level = data.get('actor_level', s.actor_level)
    s.recipient_level = data.get('recipient_level', s.recipient_level)
    s.primary_eric = data.get('primary_eric', s.primary_eric)
    s.secondary_eric = data.get('secondary_eric', s.secondary_eric)
    s.evidence_based_practice = data.get('evidence_based_practice', s.evidence_based_practice)
    s.source = data.get('source', s.source)
    s.other_source = data.get('other_source', s.other_source)
    s.help_text = data.get('help_text', s.help_text)
    s.is_active = data.get('is_active', s.is_active)

    db.session.commit()
    return jsonify({'success': True})


@app.route('/api/admin/strategies/<int:strategy_id>', methods=['DELETE'])
def admin_delete_strategy(strategy_id):
    if not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 401
    s = Strategy.query.get_or_404(strategy_id)

    # Check for references
    vote_refs = Comparison.query.filter(
        (Comparison.winner_id == strategy_id) | (Comparison.loser_id == strategy_id)
    ).count()
    cd_refs = CantDecide.query.filter(
        (CantDecide.strategy_a_id == strategy_id) | (CantDecide.strategy_b_id == strategy_id)
    ).count()
    dup_refs = SubmittedIdea.query.filter_by(duplicate_of_id=strategy_id).count()
    algo_refs = AlgorithmLog.query.filter(
        (AlgorithmLog.focal_id == strategy_id) | (AlgorithmLog.opponent_id == strategy_id) |
        (AlgorithmLog.displayed_left_id == strategy_id) | (AlgorithmLog.displayed_right_id == strategy_id)
    ).count()

    total_refs = vote_refs + cd_refs + dup_refs + algo_refs
    if total_refs > 0:
        return jsonify({
            'error': f'Cannot delete: strategy is referenced by {vote_refs} votes, '
                     f'{cd_refs} can\'t-decide records, {dup_refs} duplicate links, '
                     f'and {algo_refs} algorithm logs. Set it to Inactive instead.'
        }), 409

    db.session.delete(s)
    db.session.commit()
    return jsonify({'success': True})


@app.route('/api/admin/algorithm-logs', methods=['GET'])
def admin_algorithm_logs():
    """Full algorithm audit trail."""
    if not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 401

    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)

    query = AlgorithmLog.query.order_by(AlgorithmLog.timestamp.desc())
    total = query.count()
    logs = query.offset((page - 1) * per_page).limit(per_page).all()

    total_selections = AlgorithmLog.query.count()
    cold_starts = AlgorithmLog.query.filter_by(was_cold_start=True).count()
    votes = AlgorithmLog.query.filter_by(outcome='vote').count()
    cant_decides_algo = AlgorithmLog.query.filter_by(outcome='cant_decide').count()
    abandoned = AlgorithmLog.query.filter(AlgorithmLog.outcome == None).count()

    records = []
    for log in logs:
        focal_name = Strategy.query.get(log.focal_id).choice[:60] if log.focal_id and Strategy.query.get(log.focal_id) else '—'
        opponent_name = Strategy.query.get(log.opponent_id).choice[:60] if log.opponent_id and Strategy.query.get(log.opponent_id) else '—'
        winner_name = Strategy.query.get(log.winner_id).choice[:60] if log.winner_id and Strategy.query.get(log.winner_id) else '—'

        records.append({
            'id': log.id, 'timestamp': log.timestamp.isoformat(),
            'session_id': log.session_id, 'level': log.level_context,
            'focal': focal_name, 'focal_prob': log.focal_sampling_prob,
            'opponent': opponent_name, 'strength_diff': log.opponent_strength_diff,
            'proxy': log.proxy_type, 'was_cold_start': log.was_cold_start,
            'num_comparisons': log.num_comparisons_used,
            'map_converged': log.map_converged, 'map_iterations': log.map_iterations,
            'outcome': log.outcome or 'abandoned', 'winner': winner_name,
        })

    return jsonify({
        'records': records, 'total': total, 'page': page, 'per_page': per_page,
        'summary': {
            'total_selections': total_selections, 'cold_starts': cold_starts,
            'votes': votes, 'cant_decides': cant_decides_algo, 'abandoned': abandoned,
        }
    })


@app.route('/api/admin/algorithm-logs/export', methods=['GET'])
def export_algorithm_logs():
    """Export full algorithm logs as JSON for research analysis."""
    if not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 401

    logs = AlgorithmLog.query.order_by(AlgorithmLog.timestamp.asc()).all()
    return jsonify([{
        'id': log.id, 'timestamp': log.timestamp.isoformat(),
        'session_id': log.session_id, 'level': log.level_context,
        'focal_id': log.focal_id, 'focal_sampling_prob': log.focal_sampling_prob,
        'opponent_id': log.opponent_id, 'opponent_strength_diff': log.opponent_strength_diff,
        'displayed_left_id': log.displayed_left_id, 'displayed_right_id': log.displayed_right_id,
        'proxy_type': log.proxy_type, 'num_comparisons': log.num_comparisons_used,
        'was_cold_start': log.was_cold_start,
        'map_strengths': json.loads(log.map_strengths_json) if log.map_strengths_json else None,
        'exposure_counts': json.loads(log.exposure_counts_json) if log.exposure_counts_json else None,
        'uncertainty_weights': json.loads(log.uncertainty_weights_json) if log.uncertainty_weights_json else None,
        'map_converged': log.map_converged, 'map_iterations': log.map_iterations,
        'outcome': log.outcome, 'winner_id': log.winner_id,
    } for log in logs])


@app.route('/api/admin/logout', methods=['POST'])
def admin_logout():
    session.pop('is_admin', None)
    return jsonify({'success': True, 'redirect': '/admin'})


@app.route('/api/admin/quick-guide', methods=['GET', 'POST'])
def admin_quick_guide():
    if not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 401
    s = AppSettings.query.get(1)
    if not s:
        return jsonify({'error': 'Settings not initialized'}), 500

    if request.method == 'GET':
        return jsonify({
            'video_url': s.quick_guide_video_url or '',
            'video_title': s.quick_guide_video_title or '',
        })

    data = request.json or {}
    if 'video_url' in data:
        s.quick_guide_video_url = (data.get('video_url') or '').strip() or None
    if 'video_title' in data:
        t = (data.get('video_title') or '').strip()
        s.quick_guide_video_title = t or None
    db.session.commit()
    return jsonify({'success': True})


# ─── Run ────────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    app.run(debug=True, port=5001)
