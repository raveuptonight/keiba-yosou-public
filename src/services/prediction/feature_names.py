"""
Feature Display Names and Mark Assignment

Provides Japanese display names for ML features (used in video export / SHAP explanation)
and mark assignment logic for race predictions.
"""

# Mark symbols assigned by prediction rank
MARKS = ["◎", "○", "▲", "△", "△", "×", "×", "☆"]

FEATURE_DISPLAY_NAMES: dict[str, str] = {
    # Basic information
    "umaban": "馬番",
    "wakuban": "枠番",
    "age": "馬齢",
    "sex": "性別",
    "kinryo": "斤量",
    "horse_weight": "馬体重",
    "weight_diff": "馬体重増減",
    "blinker": "ブリンカー",
    # Past performance
    "speed_index_avg": "スピード指数(平均)",
    "speed_index_max": "スピード指数(最大)",
    "speed_index_recent": "スピード指数(直近)",
    "last3f_time_avg": "上がり3F平均",
    "last3f_rank_avg": "上がり3F順位平均",
    "running_style": "脚質",
    "position_avg_3f": "位置取り(3角平均)",
    "position_avg_4f": "位置取り(4角平均)",
    "win_rate": "勝率",
    "place_rate": "複勝率",
    "win_count": "勝利数",
    "days_since_last_race": "休養日数",
    # Jockey / Trainer
    "jockey_win_rate": "騎手勝率",
    "jockey_place_rate": "騎手複勝率",
    "trainer_win_rate": "調教師勝率",
    "trainer_place_rate": "調教師複勝率",
    "jockey_horse_runs": "騎手馬コンビ出走数",
    "jockey_horse_wins": "騎手馬コンビ勝利数",
    "jockey_change": "騎手乗り替わり",
    "jockey_recent_win_rate": "騎手直近勝率",
    "jockey_recent_place_rate": "騎手直近複勝率",
    "jockey_recent_runs": "騎手直近出走数",
    "jockey_recent_confidence": "騎手直近信頼度",
    "jockey_maiden_win_rate": "騎手未勝利勝率",
    "jockey_maiden_place_rate": "騎手未勝利複勝率",
    "jockey_maiden_runs": "騎手未勝利出走数",
    # Training
    "training_score": "調教評価",
    "training_time_4f": "調教4Fタイム",
    "training_count": "調教本数",
    "training_intensity": "調教強度",
    "training_efficiency": "調教効率",
    "high_volume_training": "追い切り量",
    "training_time_3f": "調教3Fタイム",
    "training_lap_1f": "調教1Fラップ",
    "training_finishing_accel": "調教終い加速",
    "training_lap_quality": "調教ラップ質",
    "training_days_before": "調教最終日",
    # Course
    "is_turf": "芝/ダート",
    "turf_win_rate": "芝勝率",
    "dirt_win_rate": "ダート勝率",
    "class_change": "クラス変動",
    "avg_time_diff": "平均タイム差",
    "best_finish": "最高着順",
    "course_fit_score": "コース適性",
    "distance_fit_score": "距離適性",
    "class_rank": "クラスランク",
    "field_size": "出走頭数",
    "waku_bias": "枠バイアス",
    "baba_win_rate": "馬場勝率",
    "baba_place_rate": "馬場複勝率",
    "baba_runs": "馬場出走数",
    "baba_condition": "馬場状態",
    # Distance / Track condition
    "distance_cat_win_rate": "距離カテゴリ勝率",
    "distance_cat_place_rate": "距離カテゴリ複勝率",
    "distance_cat_runs": "距離カテゴリ出走数",
    "turn_direction_rate": "回り適性率",
    "turn_direction_confidence": "回り信頼度",
    # Pace / Strategy
    "pace_maker_count": "逃げ馬数",
    "senkou_count": "先行馬数",
    "sashi_count": "差し馬数",
    "pace_type": "ペースタイプ",
    "style_pace_compatibility": "脚質ペース適性",
    "inner_nige_count": "内枠逃げ数",
    "inner_senkou_count": "内枠先行数",
    "waku_style_advantage": "枠脚質有利度",
    # Interval / Rest
    "interval_win_rate": "間隔勝率",
    "interval_place_rate": "間隔複勝率",
    "interval_runs": "間隔出走数",
    "interval_category": "間隔カテゴリ",
    # Pedigree
    "sire_id_hash": "父馬ID",
    "broodmare_sire_id_hash": "母父ID",
    "sire_win_rate": "父勝率",
    "sire_place_rate": "父複勝率",
    "sire_runs": "父出走数",
    "sire_confidence": "父信頼度",
    "sire_maiden_win_rate": "父未勝利勝率",
    "sire_maiden_place_rate": "父未勝利複勝率",
    "sire_maiden_runs": "父未勝利出走数",
    # Venue
    "venue_win_rate": "コース勝率",
    "venue_place_rate": "コース複勝率",
    "venue_runs": "コース出走数",
    # Track type
    "small_track_rate": "小回り率",
    "large_track_rate": "大回り率",
    "track_type_fit": "コースタイプ適性",
    # Previous race (zenso)
    "zenso1_chakujun": "前走着順",
    "zenso1_ninki": "前走人気",
    "zenso1_agari": "前走上がり3F",
    "zenso1_corner_avg": "前走コーナー平均",
    "zenso1_distance": "前走距離",
    "zenso1_grade": "前走グレード",
    "zenso2_chakujun": "2走前着順",
    "zenso3_chakujun": "3走前着順",
    "zenso_chakujun_trend": "着順トレンド",
    "zenso_agari_trend": "上がりトレンド",
    "zenso1_agari_rank": "前走上がり順位",
    "zenso2_agari_rank": "2走前上がり順位",
    "avg_agari_rank_3": "上がり順位平均(3走)",
    "zenso1_position_up_1to2": "前走位置変動(1-2角)",
    "zenso1_position_up_2to3": "前走位置変動(2-3角)",
    "zenso1_position_up_3to4": "前走位置変動(3-4角)",
    "zenso1_early_position_avg": "前走前半位置平均",
    "zenso1_late_position_avg": "前走後半位置平均",
    "late_push_tendency": "末脚傾向",
    "zenso1_distance_diff": "前走距離差",
    "zenso1_class_diff": "前走クラス差",
    # Season
    "race_month": "開催月",
    "month_sin": "季節(sin)",
    "month_cos": "季節(cos)",
    "kaisai_week": "開催週",
    "growth_period": "成長期",
    "is_winter": "冬季",
    # Experience
    "race_count": "出走回数",
    "experience_category": "経験カテゴリ",
}


def assign_marks(ranked_horses: list[dict]) -> list[dict]:
    """Assign marks (印) to horses based on prediction rank.

    Args:
        ranked_horses: List of horse dicts with "pred_rank" key.

    Returns:
        Same list with "mark" key added to each horse.
    """
    sorted_horses = sorted(ranked_horses, key=lambda h: h["pred_rank"])
    for i, horse in enumerate(sorted_horses):
        horse["mark"] = MARKS[i] if i < len(MARKS) else "☆"
    return sorted_horses
