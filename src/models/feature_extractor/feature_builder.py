"""
Feature building module.

Contains the main feature construction logic that transforms raw data
into ML-ready feature vectors.
"""


import numpy as np

from .utils import (
    calc_days_since_last,
    calc_speed_index,
    calc_style_pace_compatibility,
    determine_class,
    determine_style,
    encode_sex,
    get_distance_category,
    get_interval_category,
    safe_float,
    safe_int,
    stable_hash,
)


def build_features(
    entry: dict,
    races: list[dict],
    past_stats: dict[str, dict],
    jockey_cache: dict[str, dict],
    trainer_cache: dict[str, dict],
    jockey_horse_stats: dict[str, dict] = None,
    distance_stats: dict[str, dict] = None,
    baba_stats: dict[str, dict] = None,
    training_stats: dict[str, dict] = None,
    interval_stats: dict[str, dict] = None,
    pace_predictions: dict[str, dict] = None,
    entries_by_race: dict[str, list[dict]] = None,
    pedigree_info: dict[str, dict] = None,
    venue_stats: dict[str, dict] = None,
    zenso_info: dict[str, dict] = None,
    jockey_recent: dict[str, dict] = None,
    sire_stats_turf: dict[str, dict] = None,
    sire_stats_dirt: dict[str, dict] = None,
    sire_maiden_stats: dict[str, dict] = None,
    jockey_maiden_stats: dict[str, dict] = None,
    year: int = None,
    small_track_venues: set[str] = None
) -> dict | None:
    """Build feature vector for a single horse entry.

    Constructs 100+ features from various data sources including:
    - Basic horse info (age, weight, sex)
    - Past performance (speed, finishing times, positions)
    - Jockey/trainer statistics
    - Track and distance preferences
    - Pedigree information
    - Race context (pace, field size)

    Args:
        entry: Horse entry data from umagoto_race_joho
        races: List of race info dictionaries
        past_stats: Past performance statistics by kettonum
        jockey_cache: Cached jockey statistics
        trainer_cache: Cached trainer statistics
        jockey_horse_stats: Jockey-horse combination stats
        distance_stats: Turf/dirt performance stats
        baba_stats: Track condition stats
        training_stats: Training workout data
        interval_stats: Rest interval stats
        pace_predictions: Predicted race pace
        entries_by_race: Entries grouped by race code
        pedigree_info: Pedigree data
        venue_stats: Venue-specific stats
        zenso_info: Previous race details
        jockey_recent: Jockey recent form
        sire_stats_turf: Sire turf stats
        sire_stats_dirt: Sire dirt stats
        sire_maiden_stats: Sire maiden race stats
        jockey_maiden_stats: Jockey maiden race stats
        year: Target year
        small_track_venues: Set of small track venue codes

    Returns:
        Feature dictionary or None if entry is invalid
    """
    if small_track_venues is None:
        small_track_venues = {'01', '02', '03', '06', '10'}

    # Skip entries without valid finishing position
    chakujun_str = entry.get('kakutei_chakujun', '')
    if not chakujun_str or not chakujun_str.isdigit():
        return None

    chakujun = int(chakujun_str)
    if chakujun > 18:
        return None

    # Get race info
    race_code = entry['race_code']
    race_info = next((r for r in races if r['race_code'] == race_code), {})

    kettonum = entry.get('ketto_toroku_bango', '')
    jockey_code = entry.get('kishu_code', '')
    past = past_stats.get(kettonum, {})

    features = {}

    # Race identifier (for grouping/evaluation, not a feature)
    features['race_code'] = race_code

    # ===== Basic Information =====
    features['umaban'] = safe_int(entry.get('umaban'), 0)
    features['wakuban'] = safe_int(entry.get('wakuban'), 0)
    features['age'] = safe_int(entry.get('barei'), 4)
    features['sex'] = encode_sex(entry.get('seibetsu_code', ''))
    features['kinryo'] = safe_float(entry.get('futan_juryo'), 550) / 10.0
    features['horse_weight'] = safe_int(entry.get('bataiju'), 480)
    features['weight_diff'] = safe_int(entry.get('zogen_sa'), 0)
    features['blinker'] = 1 if entry.get('blinker_shiyo_kubun') == '1' else 0

    # ===== Past Performance (Improved) =====
    features['speed_index_avg'] = calc_speed_index(past.get('avg_time'))
    features['speed_index_max'] = calc_speed_index(past.get('best_time'))
    features['speed_index_recent'] = calc_speed_index(past.get('recent_time'))
    features['last3f_time_avg'] = past.get('avg_last3f', 35.0)
    features['last3f_rank_avg'] = 5.0  # Default
    features['running_style'] = determine_style(past.get('avg_corner3', 8))
    features['position_avg_3f'] = past.get('avg_corner3', 8.0)
    features['position_avg_4f'] = past.get('avg_corner4', 8.0)
    features['win_rate'] = past.get('win_rate', 0.0)
    features['place_rate'] = past.get('place_rate', 0.0)
    features['win_count'] = past.get('win_count', 0)

    # Rest days (improved)
    features['days_since_last_race'] = calc_days_since_last(
        past.get('last_race_date'),
        race_info.get('kaisai_nen', ''),
        race_info.get('kaisai_gappi', '')
    )

    # ===== Jockey/Trainer =====
    jockey_stats = jockey_cache.get(jockey_code, {'win_rate': 0.08, 'place_rate': 0.25})
    features['jockey_win_rate'] = jockey_stats['win_rate']
    features['jockey_place_rate'] = jockey_stats['place_rate']

    trainer_code = entry.get('chokyoshi_code', '')
    trainer_stats = trainer_cache.get(trainer_code, {'win_rate': 0.08, 'place_rate': 0.25})
    features['trainer_win_rate'] = trainer_stats['win_rate']
    features['trainer_place_rate'] = trainer_stats['place_rate']

    # Jockey-horse combo (improved - weight suppression)
    # SHAP analysis showed negative impact, so apply minimum sample threshold and convert to win rate
    combo_key = f"{jockey_code}_{kettonum}"
    combo = jockey_horse_stats.get(combo_key, {}) if jockey_horse_stats else {}
    combo_runs = combo.get('runs', 0)
    combo_wins = combo.get('wins', 0)
    # Less than 3 runs = low reliability, treat as 0; scale to 0-1
    if combo_runs >= 3:
        features['jockey_horse_runs'] = min(combo_runs, 10) / 10.0  # Max 1.0
        features['jockey_horse_wins'] = combo_wins / combo_runs  # Convert to win rate
    else:
        features['jockey_horse_runs'] = 0.0
        features['jockey_horse_wins'] = 0.0

    # Jockey change detection (improved)
    last_jockey = past.get('last_jockey', '')
    features['jockey_change'] = 1 if last_jockey and last_jockey != jockey_code else 0

    # ===== Training Data (Improved) =====
    train = training_stats.get(kettonum, {}) if training_stats else {}
    features['training_score'] = train.get('score', 50.0)
    features['training_time_4f'] = train.get('time_4f', 52.0)
    features['training_count'] = train.get('count', 0)

    # Derived training features
    t_count = features['training_count']
    t_days = train.get('days_before', 7)
    t_score = features['training_score']
    # Training intensity (sessions per day)
    features['training_intensity'] = t_count / max(t_days, 1)
    # Training efficiency (score / count, normalized to ~0-1)
    features['training_efficiency'] = (t_score / max(t_count, 1)) / 50.0 if t_count > 0 else 0.0
    # High volume training flag
    features['high_volume_training'] = 1 if t_count >= 5 else 0
    features['distance_change'] = 0

    # ===== Course Information =====
    track_code = race_info.get('track_code', '')
    features['is_turf'] = 1 if track_code.startswith('1') else 0

    # Turf/dirt performance (improved)
    turf_key = f"{kettonum}_turf"
    dirt_key = f"{kettonum}_dirt"
    if distance_stats:
        turf_stats = distance_stats.get(turf_key, {})
        dirt_stats = distance_stats.get(dirt_key, {})
        features['turf_win_rate'] = turf_stats.get('win_rate', past.get('win_rate', 0.0))
        features['dirt_win_rate'] = dirt_stats.get('win_rate', past.get('win_rate', 0.0))
    else:
        features['turf_win_rate'] = past.get('win_rate', 0.0)
        features['dirt_win_rate'] = past.get('win_rate', 0.0)

    features['class_change'] = 0
    features['avg_time_diff'] = (past.get('avg_rank', 8) - 1) * 0.2
    features['best_finish'] = past.get('best_finish', 10)
    features['course_fit_score'] = 0.5
    features['distance_fit_score'] = 0.5
    features['class_rank'] = determine_class(race_info.get('grade_code', ''))

    # Field size (average default)
    features['field_size'] = 14

    features['waku_bias'] = (features['wakuban'] - 4.5) * 0.02

    # ===== Distance Category Stats (Improved) =====
    distance = safe_int(race_info.get('kyori'), 1600)
    dist_key = f"{kettonum}_{get_distance_category(distance)}"
    if distance_stats:
        d_stats = distance_stats.get(dist_key, {})
        features['distance_cat_win_rate'] = d_stats.get('win_rate', 0.0)
        features['distance_cat_place_rate'] = d_stats.get('place_rate', 0.0)
        features['distance_cat_runs'] = d_stats.get('runs', 0)
    else:
        features['distance_cat_win_rate'] = past.get('win_rate', 0.0)
        features['distance_cat_place_rate'] = past.get('place_rate', 0.0)
        features['distance_cat_runs'] = past.get('race_count', 0)

    # ===== Track Condition Stats (Improved) =====
    is_turf = track_code.startswith('1') if track_code else True
    baba_name = 'turf' if is_turf else 'dirt'
    baba_code = race_info.get('shiba_babajotai_code', '1') if is_turf else race_info.get('dirt_babajotai_code', '1')
    baba_suffix_map = {'1': 'ryo', '2': 'yayaomo', '3': 'omo', '4': 'furyo'}
    baba_suffix = baba_suffix_map.get(str(baba_code), 'ryo')
    baba_key = f"{kettonum}_{baba_name}_{baba_suffix}"

    if baba_stats and baba_key in baba_stats:
        b_stats = baba_stats.get(baba_key, {})
        features['baba_win_rate'] = b_stats.get('win_rate', 0.0)
        features['baba_place_rate'] = b_stats.get('place_rate', 0.0)
        features['baba_runs'] = b_stats.get('runs', 0)
    else:
        features['baba_win_rate'] = past.get('win_rate', 0.0)
        features['baba_place_rate'] = past.get('place_rate', 0.0)
        features['baba_runs'] = past.get('race_count', 0)

    # Track condition encoding (1=Good, 2=Slightly Heavy, 3=Heavy, 4=Bad)
    features['baba_condition'] = safe_int(baba_code, 1)

    # ===== Training Details =====
    features['training_time_3f'] = train.get('time_3f', 38.0)
    features['training_lap_1f'] = train.get('lap_1f', 12.5)
    features['training_days_before'] = train.get('days_before', 7)

    # Training quality indicators
    time_3f = features['training_time_3f']
    lap_1f = features['training_lap_1f']
    # Acceleration indicator: faster final 1F than average = positive
    avg_1f = time_3f / 3 if time_3f > 0 else 12.67
    features['training_finishing_accel'] = avg_1f - lap_1f  # Positive = accelerating
    # Training intensity (3F time basis, 36s = standard)
    features['training_intensity'] = max(0, (40.0 - time_3f) / 4.0)  # 0-1 scale
    # Final lap quality (12.5s basis)
    features['training_lap_quality'] = max(0, (13.5 - lap_1f) / 1.0)  # 0-1 scale

    # ===== Turn Direction Stats =====
    # Right-handed: Sapporo(01), Hakodate(02), Fukushima(03), Nakayama(06), Kyoto(08), Hanshin(09), Kokura(10)
    # Left-handed: Niigata(04), Tokyo(05), Chukyo(07)
    keibajo = race_info.get('keibajo_code', '')
    is_right_turn = keibajo in {'01', '02', '03', '06', '08', '09', '10'}
    right_rate = past.get('right_turn_rate', 0.25)
    left_rate = past.get('left_turn_rate', 0.25)
    right_runs = past.get('right_turn_runs', 0)
    left_runs = past.get('left_turn_runs', 0)

    # Bayesian smoothing based on sample size (prior: overall average 0.25)
    BASE_RATE = 0.25
    MIN_SAMPLES = 5  # Reliability threshold
    if is_right_turn:
        raw_rate = right_rate
        turn_runs = right_runs
    else:
        raw_rate = left_rate
        turn_runs = left_runs
    if turn_runs >= MIN_SAMPLES:
        features['turn_direction_rate'] = raw_rate
    elif turn_runs >= 2:
        # Bayesian blend with prior
        weight = turn_runs / MIN_SAMPLES
        features['turn_direction_rate'] = weight * raw_rate + (1 - weight) * BASE_RATE
    else:
        features['turn_direction_rate'] = BASE_RATE
    features['turn_direction_confidence'] = min(turn_runs / MIN_SAMPLES, 1.0)

    # ===== New Features =====

    # Interval category stats
    days_since = features['days_since_last_race']
    interval_cat = get_interval_category(days_since)
    interval_key = f"{kettonum}_{interval_cat}"
    if interval_stats and interval_key in interval_stats:
        i_stats = interval_stats.get(interval_key, {})
        features['interval_win_rate'] = i_stats.get('win_rate', 0.0)
        features['interval_place_rate'] = i_stats.get('place_rate', 0.0)
        features['interval_runs'] = i_stats.get('runs', 0)
    else:
        features['interval_win_rate'] = past.get('win_rate', 0.0)
        features['interval_place_rate'] = past.get('place_rate', 0.0)
        features['interval_runs'] = 0

    # Interval category encoding (1=rentou, 2=week1, 3=week2, 4=week3, 5=week4plus)
    interval_cat_map = {'rentou': 1, 'week1': 2, 'week2': 3, 'week3': 4, 'week4plus': 5}
    features['interval_category'] = interval_cat_map.get(interval_cat, 5)

    # Pace prediction (front runner count, pace type)
    pace_info = pace_predictions.get(race_code, {}) if pace_predictions else {}
    features['pace_maker_count'] = pace_info.get('pace_maker_count', 1)
    features['senkou_count'] = pace_info.get('senkou_count', 3)
    features['sashi_count'] = pace_info.get('sashi_count', 5)
    features['pace_type'] = pace_info.get('pace_type', 2)  # 1=Slow, 2=Middle, 3=High

    # Field size (actual value)
    if entries_by_race and race_code in entries_by_race:
        features['field_size'] = len(entries_by_race[race_code])
    else:
        features['field_size'] = 14

    # Running style x pace compatibility
    running_style = features['running_style']
    pace_type = features['pace_type']
    features['style_pace_compatibility'] = calc_style_pace_compatibility(running_style, pace_type)

    # ========================================
    # Extended Features (v2)
    # ========================================

    # --- 1. Pedigree Features ---
    pedigree = pedigree_info.get(kettonum, {}) if pedigree_info else {}
    sire_id = pedigree.get('sire_id', '')
    broodmare_sire_id = pedigree.get('broodmare_sire_id', '')

    # Sire ID hash (category feature) - stable hash for consistency
    features['sire_id_hash'] = stable_hash(sire_id) if sire_id else 0
    features['broodmare_sire_id_hash'] = stable_hash(broodmare_sire_id) if broodmare_sire_id else 0

    # Sire x turf/dirt stats (with confidence coefficient)
    is_turf = track_code.startswith('1') if track_code else True
    if is_turf and sire_stats_turf:
        sire_key = f"{sire_id}_turf"
        sire_stats = sire_stats_turf.get(sire_key, {'win_rate': 0.08, 'place_rate': 0.25, 'runs': 0})
    elif sire_stats_dirt:
        sire_key = f"{sire_id}_dirt"
        sire_stats = sire_stats_dirt.get(sire_key, {'win_rate': 0.08, 'place_rate': 0.25, 'runs': 0})
    else:
        sire_stats = {'win_rate': 0.08, 'place_rate': 0.25, 'runs': 0}

    # Confidence coefficient: log scale converging to 1.0 at 50+ samples
    sire_runs_raw = sire_stats['runs']
    SIRE_CONFIDENCE_THRESHOLD = 50
    BASE_WIN_RATE = 0.08
    BASE_PLACE_RATE = 0.25
    sire_confidence = min(1.0, np.log(sire_runs_raw + 1) / np.log(SIRE_CONFIDENCE_THRESHOLD + 1))
    # Blend with overall average when sample size is low
    features['sire_win_rate'] = sire_stats['win_rate'] * sire_confidence + BASE_WIN_RATE * (1 - sire_confidence)
    features['sire_place_rate'] = sire_stats['place_rate'] * sire_confidence + BASE_PLACE_RATE * (1 - sire_confidence)
    features['sire_runs'] = min(sire_runs_raw, 500)
    features['sire_confidence'] = sire_confidence  # Add confidence as feature

    # Sire maiden race stats (with confidence coefficient)
    SIRE_MAIDEN_BASE_WIN = 0.10
    SIRE_MAIDEN_BASE_PLACE = 0.30
    SIRE_MAIDEN_CONFIDENCE_THRESHOLD = 30
    if sire_maiden_stats and sire_id:
        sire_m_stats = sire_maiden_stats.get(sire_id, {})
        sire_m_runs = sire_m_stats.get('runs', 0)
        sire_m_confidence = min(1.0, np.log(sire_m_runs + 1) / np.log(SIRE_MAIDEN_CONFIDENCE_THRESHOLD + 1))
        raw_m_win = sire_m_stats.get('win_rate', SIRE_MAIDEN_BASE_WIN)
        raw_m_place = sire_m_stats.get('place_rate', SIRE_MAIDEN_BASE_PLACE)
        features['sire_maiden_win_rate'] = raw_m_win * sire_m_confidence + SIRE_MAIDEN_BASE_WIN * (1 - sire_m_confidence)
        features['sire_maiden_place_rate'] = raw_m_place * sire_m_confidence + SIRE_MAIDEN_BASE_PLACE * (1 - sire_m_confidence)
        features['sire_maiden_runs'] = min(sire_m_runs, 300)
    else:
        features['sire_maiden_win_rate'] = SIRE_MAIDEN_BASE_WIN
        features['sire_maiden_place_rate'] = SIRE_MAIDEN_BASE_PLACE
        features['sire_maiden_runs'] = 0

    # Horse experience (race count from past_stats, for maiden detection)
    race_count = past.get('race_count', 0)
    features['race_count'] = min(race_count, 20)
    # Experience category: 0=maiden, 1=inexperienced(1-2 runs), 2=experienced(3+ runs)
    if race_count == 0:
        features['experience_category'] = 0
    elif race_count <= 2:
        features['experience_category'] = 1
    else:
        features['experience_category'] = 2

    # --- 2. Previous Race (Zenso) Features ---
    zenso = zenso_info.get(kettonum, {}) if zenso_info else {}
    features['zenso1_chakujun'] = zenso.get('zenso1_chakujun', 10)
    features['zenso1_ninki'] = zenso.get('zenso1_ninki', 10)
    features['zenso1_agari'] = zenso.get('zenso1_agari', 35.0)
    features['zenso1_corner_avg'] = zenso.get('zenso1_corner_avg', 8.0)
    features['zenso1_distance'] = zenso.get('zenso1_distance', 1600)
    features['zenso1_grade'] = zenso.get('zenso1_grade', 3)
    features['zenso2_chakujun'] = zenso.get('zenso2_chakujun', 10)
    features['zenso3_chakujun'] = zenso.get('zenso3_chakujun', 10)
    features['zenso_chakujun_trend'] = zenso.get('zenso_chakujun_trend', 0)
    features['zenso_agari_trend'] = zenso.get('zenso_agari_trend', 0)

    # New: Final 3F ranking features
    features['zenso1_agari_rank'] = zenso.get('zenso1_agari_rank', 9)
    features['zenso2_agari_rank'] = zenso.get('zenso2_agari_rank', 9)
    features['avg_agari_rank_3'] = zenso.get('avg_agari_rank_3', 9.0)

    # New: Corner position progression features
    features['zenso1_position_up_1to2'] = zenso.get('zenso1_position_up_1to2', 0)
    features['zenso1_position_up_2to3'] = zenso.get('zenso1_position_up_2to3', 0)
    features['zenso1_position_up_3to4'] = zenso.get('zenso1_position_up_3to4', 0)
    features['zenso1_early_position_avg'] = zenso.get('zenso1_early_position_avg', 8.0)
    features['zenso1_late_position_avg'] = zenso.get('zenso1_late_position_avg', 8.0)
    features['late_push_tendency'] = zenso.get('late_push_tendency', 0.0)

    # Distance difference (current - previous)
    current_distance = safe_int(race_info.get('kyori'), 1600)
    features['zenso1_distance_diff'] = current_distance - features['zenso1_distance']

    # Class difference (current - previous)
    current_grade = determine_class(race_info.get('grade_code', ''))
    features['zenso1_class_diff'] = current_grade - features['zenso1_grade']

    # --- 3. Venue-specific Stats (with minimum sample threshold) ---
    venue_code = race_info.get('keibajo_code', '')
    surface_name = 'shiba' if is_turf else 'dirt'
    venue_key = f"{kettonum}_{venue_code}_{surface_name}"
    v_stats = venue_stats.get(venue_key, {}) if venue_stats else {}
    v_runs = v_stats.get('runs', 0)
    # Less than 3 runs = low reliability, treat as 0
    if v_runs >= 3:
        features['venue_win_rate'] = v_stats.get('win_rate', 0.0)
        features['venue_place_rate'] = v_stats.get('place_rate', 0.0)
        features['venue_runs'] = min(v_runs, 20) / 20.0  # Scale to 0-1
    else:
        features['venue_win_rate'] = 0.0
        features['venue_place_rate'] = 0.0
        features['venue_runs'] = 0.0

    # Small/large track aptitude
    features['small_track_rate'] = zenso.get('small_track_rate', 0.25)
    features['large_track_rate'] = zenso.get('large_track_rate', 0.25)

    # Track type fit for current race
    is_small_track = venue_code in small_track_venues
    features['track_type_fit'] = features['small_track_rate'] if is_small_track else features['large_track_rate']

    # --- 4. Pace Enhancement Features ---
    umaban = safe_int(entry.get('umaban'), 0)
    my_style = running_style

    # Count front runners inside this horse's position
    inner_nige = 0
    inner_senkou = 0
    if entries_by_race and race_code in entries_by_race:
        for e in entries_by_race[race_code]:
            e_umaban = safe_int(e.get('umaban'), 0)
            e_kettonum = e.get('ketto_toroku_bango', '')
            e_past = past_stats.get(e_kettonum, {})
            e_style = determine_style(e_past.get('avg_corner3', 8))
            if e_umaban < umaban:
                if e_style == 1:
                    inner_nige += 1
                elif e_style == 2:
                    inner_senkou += 1

    features['inner_nige_count'] = inner_nige
    features['inner_senkou_count'] = inner_senkou

    # Gate position x running style advantage
    waku_style_score = 0.0
    if my_style in (1, 2):  # Nige/Senkou
        if umaban <= 4:
            waku_style_score = 0.1
        elif umaban >= 13:
            waku_style_score = -0.1
    else:  # Sashi/Oikomi
        if umaban <= 4:
            waku_style_score = -0.05
        elif umaban >= 13:
            waku_style_score = 0.05
    features['waku_style_advantage'] = waku_style_score

    # --- 5. Jockey Recent Stats (with confidence weighting) ---
    jockey_code = entry.get('kishu_code', '')
    j_recent = jockey_recent.get(jockey_code, {}) if jockey_recent else {}
    JOCKEY_BASE_WIN = 0.08
    JOCKEY_BASE_PLACE = 0.25
    JOCKEY_RECENT_CONFIDENCE_THRESHOLD = 10  # 10 rides = confidence 1.0
    j_recent_runs = j_recent.get('runs', 0)
    j_recent_confidence = min(1.0, j_recent_runs / JOCKEY_RECENT_CONFIDENCE_THRESHOLD)
    j_raw_win = j_recent.get('win_rate', JOCKEY_BASE_WIN)
    j_raw_place = j_recent.get('place_rate', JOCKEY_BASE_PLACE)
    features['jockey_recent_win_rate'] = j_raw_win * j_recent_confidence + JOCKEY_BASE_WIN * (1 - j_recent_confidence)
    features['jockey_recent_place_rate'] = j_raw_place * j_recent_confidence + JOCKEY_BASE_PLACE * (1 - j_recent_confidence)
    features['jockey_recent_runs'] = min(j_recent_runs, 30)
    features['jockey_recent_confidence'] = j_recent_confidence

    # Jockey maiden race stats (with confidence weighting)
    JOCKEY_MAIDEN_CONFIDENCE_THRESHOLD = 30
    if jockey_maiden_stats and jockey_code:
        j_maiden = jockey_maiden_stats.get(jockey_code, {})
        j_maiden_runs = j_maiden.get('runs', 0)
        j_maiden_confidence = min(1.0, np.log(j_maiden_runs + 1) / np.log(JOCKEY_MAIDEN_CONFIDENCE_THRESHOLD + 1))
        j_m_raw_win = j_maiden.get('win_rate', JOCKEY_BASE_WIN)
        j_m_raw_place = j_maiden.get('place_rate', JOCKEY_BASE_PLACE)
        features['jockey_maiden_win_rate'] = j_m_raw_win * j_maiden_confidence + JOCKEY_BASE_WIN * (1 - j_maiden_confidence)
        features['jockey_maiden_place_rate'] = j_m_raw_place * j_maiden_confidence + JOCKEY_BASE_PLACE * (1 - j_maiden_confidence)
        features['jockey_maiden_runs'] = min(j_maiden_runs, 200)
    else:
        features['jockey_maiden_win_rate'] = JOCKEY_BASE_WIN
        features['jockey_maiden_place_rate'] = JOCKEY_BASE_PLACE
        features['jockey_maiden_runs'] = 0

    # --- 6. Seasonal Features ---
    gappi = race_info.get('kaisai_gappi', '0601')
    month = safe_int(gappi[:2], 6)
    features['race_month'] = month
    features['month_sin'] = np.sin(2 * np.pi * month / 12)
    features['month_cos'] = np.cos(2 * np.pi * month / 12)

    # Meet week
    nichime = safe_int(race_info.get('kaisai_nichiji', '01'), 1)
    if nichime <= 2:
        features['kaisai_week'] = 1
    elif nichime >= 7:
        features['kaisai_week'] = 3
    else:
        features['kaisai_week'] = 2

    # Growth period detection
    horse_age = features['age']
    if horse_age == 3 and 3 <= month <= 8:
        features['growth_period'] = 1
    elif horse_age == 4 and 1 <= month <= 6:
        features['growth_period'] = 1
    else:
        features['growth_period'] = 0

    # Winter flag
    features['is_winter'] = 1 if month in (12, 1, 2) else 0

    # ===== Target =====
    features['target'] = chakujun

    return features
