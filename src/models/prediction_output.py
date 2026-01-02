"""
予測出力モジュール

確率ベース、ランキング形式、順位分布、信頼度スコアを出力
"""

import numpy as np
from typing import Dict, List, Any, Tuple
from dataclasses import dataclass
from scipy.special import softmax


@dataclass
class HorsePrediction:
    """馬ごとの予測結果"""
    horse_number: int
    horse_name: str
    predicted_rank: int           # 予測順位
    raw_score: float              # モデル出力スコア
    win_probability: float        # 1着確率
    place_probability: float      # 3着以内確率
    position_dist: Dict[str, float]  # 順位分布 {1st, 2nd, 3rd, 4th+}
    confidence: float             # 信頼度スコア


@dataclass
class RacePrediction:
    """レース全体の予測結果"""
    race_code: str
    race_name: str
    horses: List[HorsePrediction]
    race_confidence: float        # レース全体の予測信頼度
    pace_prediction: str          # 展開予想


def scores_to_probabilities(scores: np.ndarray, temperature: float = 1.0) -> np.ndarray:
    """
    回帰スコアを確率分布に変換

    Args:
        scores: モデルの予測スコア（小さいほど良い=着順予測）
        temperature: softmax温度パラメータ（高いほど均一化）

    Returns:
        確率分布（合計1）
    """
    # スコアを反転（小さいスコア=高い確率）
    inverted = -scores / temperature
    return softmax(inverted)


def calculate_position_distribution(
    score: float,
    all_scores: np.ndarray,
    horse_idx: int
) -> Dict[str, float]:
    """
    各順位の確率分布を計算

    順位の確率をモンテカルロシミュレーションで推定
    """
    n_horses = len(all_scores)

    # スコアの標準偏差を使って不確実性をモデル化
    score_std = np.std(all_scores) * 0.5  # 不確実性の大きさ

    # シミュレーション
    n_simulations = 1000
    position_counts = {1: 0, 2: 0, 3: 0, 4: 0}  # 4は4着以下

    np.random.seed(42)  # 再現性のため
    for _ in range(n_simulations):
        # ノイズを加えたスコア
        noisy_scores = all_scores + np.random.normal(0, score_std, n_horses)
        # 順位を決定
        rank = np.argsort(noisy_scores).tolist().index(horse_idx) + 1

        if rank <= 3:
            position_counts[rank] += 1
        else:
            position_counts[4] += 1

    # 確率に変換
    return {
        '1st': position_counts[1] / n_simulations,
        '2nd': position_counts[2] / n_simulations,
        '3rd': position_counts[3] / n_simulations,
        '4th+': position_counts[4] / n_simulations,
    }


def calculate_confidence(
    horse_scores: np.ndarray,
    predicted_ranks: np.ndarray
) -> Tuple[float, List[float]]:
    """
    予測の信頼度を計算

    Returns:
        (レース全体の信頼度, 各馬の信頼度リスト)
    """
    # スコアの分散が小さいほど馬間の差が明確
    score_range = np.max(horse_scores) - np.min(horse_scores)
    score_std = np.std(horse_scores)

    # 信頼度指標:
    # 1. スコア範囲が大きいほど差が明確
    # 2. TOP3とそれ以外のスコア差
    sorted_scores = np.sort(horse_scores)
    top3_gap = sorted_scores[3] - sorted_scores[2] if len(sorted_scores) > 3 else 0

    # レース全体の信頼度（0-100%）
    race_confidence = min(100, max(0,
        30 + score_range * 10 + top3_gap * 20
    ))

    # 各馬の信頼度（順位による減衰）
    horse_confidences = []
    for i, rank in enumerate(predicted_ranks):
        # 上位ほど信頼度が高い
        rank_factor = 1.0 / (1 + rank * 0.1)
        # スコアギャップによる補正
        if rank < len(sorted_scores) - 1:
            gap = sorted_scores[rank] - sorted_scores[rank - 1] if rank > 0 else sorted_scores[1] - sorted_scores[0]
        else:
            gap = 0

        conf = min(100, max(0, rank_factor * (50 + gap * 30)))
        horse_confidences.append(conf)

    return race_confidence, horse_confidences


def create_race_prediction(
    race_code: str,
    race_name: str,
    horse_numbers: List[int],
    horse_names: List[str],
    model_scores: np.ndarray,
    pace_info: Dict = None
) -> RacePrediction:
    """
    レースの予測結果を生成

    Args:
        race_code: レースコード
        race_name: レース名
        horse_numbers: 馬番リスト
        horse_names: 馬名リスト
        model_scores: モデルの予測スコア
        pace_info: 展開予想情報

    Returns:
        RacePrediction オブジェクト
    """
    n_horses = len(horse_numbers)

    # 予測順位を計算
    predicted_ranks = np.argsort(model_scores) + 1
    rank_order = np.argsort(model_scores)

    # 勝率分布を計算（softmax）
    win_probs = scores_to_probabilities(model_scores, temperature=1.5)

    # 3着以内確率を計算
    place_probs = []
    for i in range(n_horses):
        pos_dist = calculate_position_distribution(model_scores[i], model_scores, i)
        place_prob = pos_dist['1st'] + pos_dist['2nd'] + pos_dist['3rd']
        place_probs.append(place_prob)

    # 信頼度計算
    race_conf, horse_confs = calculate_confidence(model_scores, predicted_ranks)

    # 各馬の予測結果を生成
    horses = []
    for i in range(n_horses):
        pos_dist = calculate_position_distribution(model_scores[i], model_scores, i)

        horse_pred = HorsePrediction(
            horse_number=horse_numbers[i],
            horse_name=horse_names[i],
            predicted_rank=int(np.where(rank_order == i)[0][0] + 1),
            raw_score=float(model_scores[i]),
            win_probability=float(win_probs[i]),
            place_probability=float(place_probs[i]),
            position_dist=pos_dist,
            confidence=float(horse_confs[i])
        )
        horses.append(horse_pred)

    # 予測順位でソート
    horses.sort(key=lambda x: x.predicted_rank)

    # 展開予想
    pace_str = "ミドル"
    if pace_info:
        pace_type = pace_info.get('pace_type', 2)
        pace_str = {1: 'スロー', 2: 'ミドル', 3: 'ハイ'}.get(pace_type, 'ミドル')

    return RacePrediction(
        race_code=race_code,
        race_name=race_name,
        horses=horses,
        race_confidence=race_conf,
        pace_prediction=pace_str
    )


def format_prediction_for_discord(prediction: RacePrediction) -> str:
    """
    Discord通知用にフォーマット
    """
    lines = []
    lines.append(f"**{prediction.race_name}**")
    lines.append(f"展開予想: {prediction.pace_prediction}ペース")
    lines.append(f"予測信頼度: {prediction.race_confidence:.0f}%")
    lines.append("")
    lines.append("**予測ランキング:**")
    lines.append("```")
    lines.append(f"{'順':>2} {'馬番':>3} {'馬名':<12} {'勝率':>6} {'複勝':>6} {'信頼':>5}")
    lines.append("-" * 45)

    for h in prediction.horses[:8]:  # TOP8まで表示
        lines.append(
            f"{h.predicted_rank:>2} "
            f"{h.horse_number:>3} "
            f"{h.horse_name[:10]:<12} "
            f"{h.win_probability*100:>5.1f}% "
            f"{h.place_probability*100:>5.1f}% "
            f"{h.confidence:>4.0f}%"
        )

    lines.append("```")
    lines.append("")
    lines.append("**順位確率分布 (TOP3):**")
    lines.append("```")
    lines.append(f"{'馬番':>3} {'1着':>6} {'2着':>6} {'3着':>6} {'4着↓':>6}")
    lines.append("-" * 32)

    for h in prediction.horses[:3]:
        pd = h.position_dist
        lines.append(
            f"{h.horse_number:>3} "
            f"{pd['1st']*100:>5.1f}% "
            f"{pd['2nd']*100:>5.1f}% "
            f"{pd['3rd']*100:>5.1f}% "
            f"{pd['4th+']*100:>5.1f}%"
        )

    lines.append("```")

    return "\n".join(lines)


def format_prediction_summary(prediction: RacePrediction) -> Dict[str, Any]:
    """
    API/JSON用のサマリー形式
    """
    return {
        'race_code': prediction.race_code,
        'race_name': prediction.race_name,
        'race_confidence': prediction.race_confidence,
        'pace_prediction': prediction.pace_prediction,
        'rankings': [
            {
                'rank': h.predicted_rank,
                'horse_number': h.horse_number,
                'horse_name': h.horse_name,
                'win_probability': round(h.win_probability * 100, 1),
                'place_probability': round(h.place_probability * 100, 1),
                'position_distribution': {
                    '1st': round(h.position_dist['1st'] * 100, 1),
                    '2nd': round(h.position_dist['2nd'] * 100, 1),
                    '3rd': round(h.position_dist['3rd'] * 100, 1),
                    '4th_or_below': round(h.position_dist['4th+'] * 100, 1),
                },
                'confidence': round(h.confidence, 0)
            }
            for h in prediction.horses
        ]
    }
