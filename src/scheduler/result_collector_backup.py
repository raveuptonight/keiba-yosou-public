"""
結果収集モジュール

レース終了後に結果を収集し、予想との比較を行う
- 当日21時: 当日のレース結果を収集
- DBから予想を読み込み、実際の結果と比較
"""

import logging
import json
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional

from src.db.connection import get_db

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ResultCollector:
    """レース結果収集クラス"""

    def __init__(self):
        self.keibajo_names = {
            '01': '札幌', '02': '函館', '03': '福島', '04': '新潟', '05': '東京',
            '06': '中山', '07': '中京', '08': '京都', '09': '阪神', '10': '小倉'
        }

    def get_race_results(self, target_date: date) -> List[Dict]:
        """指定日のレース結果を取得"""
        db = get_db()
        conn = db.get_connection()

        try:
            cur = conn.cursor()
            kaisai_gappi = target_date.strftime("%m%d")
            kaisai_nen = str(target_date.year)

            # 確定結果または速報成績のあるレースを取得
            # data_kubun: 6=速報(全馬+通過順), 7=確定成績
            cur.execute('''
                SELECT DISTINCT r.race_code, r.keibajo_code, r.race_bango,
                       r.kyori, r.track_code
                FROM race_shosai r
                WHERE r.kaisai_nen = %s
                  AND r.kaisai_gappi = %s
                  AND r.data_kubun IN ('6', '7')
                ORDER BY r.race_code
            ''', (kaisai_nen, kaisai_gappi))

            races = []
            for row in cur.fetchall():
                race_code = row[0]

                # 各レースの着順・人気を取得（速報または確定）
                cur.execute('''
                    SELECT umaban, kakutei_chakujun, bamei, tansho_ninkijun
                    FROM umagoto_race_joho
                    WHERE race_code = %s
                      AND data_kubun IN ('6', '7')
                    ORDER BY kakutei_chakujun::int
                ''', (race_code,))

                results = []
                for r in cur.fetchall():
                    ninki = None
                    if r[3] and r[3].strip():
                        try:
                            ninki = int(r[3])
                        except:
                            pass
                    results.append({
                        'umaban': r[0],
                        'chakujun': int(r[1]) if r[1] else 99,
                        'bamei': r[2],
                        'ninki': ninki,  # 単勝人気順
                    })

                races.append({
                    'race_code': race_code,
                    'keibajo': self.keibajo_names.get(row[1], row[1]),
                    'race_number': row[2],
                    'kyori': row[3],
                    'track': '芝' if row[4] and row[4].startswith('1') else 'ダ',
                    'results': results
                })

            cur.close()
            return races

        finally:
            conn.close()

    def get_payouts(self, target_date: date) -> Dict[str, Dict]:
        """指定日の払戻データを取得"""
        db = get_db()
        conn = db.get_connection()

        try:
            cur = conn.cursor()
            kaisai_gappi = target_date.strftime("%m%d")
            kaisai_nen = str(target_date.year)

            # 払戻を取得（単勝・複勝のみ）
            # data_kubun: '1'=登録/速報, '2'=速報, '7'=確定（確定優先）
            cur.execute('''
                SELECT DISTINCT ON (race_code) race_code,
                       tansho1_umaban, tansho1_haraimodoshikin,
                       fukusho1_umaban, fukusho1_haraimodoshikin,
                       fukusho2_umaban, fukusho2_haraimodoshikin,
                       fukusho3_umaban, fukusho3_haraimodoshikin
                FROM haraimodoshi
                WHERE kaisai_nen = %s
                  AND kaisai_gappi = %s
                  AND data_kubun IN ('1', '2', '7')
                ORDER BY race_code, data_kubun DESC
            ''', (kaisai_nen, kaisai_gappi))

            payouts = {}
            for row in cur.fetchall():
                race_code = row[0]

                # 単勝払戻
                tansho_umaban = row[1].strip() if row[1] else None
                tansho_payout = int(row[2]) if row[2] and row[2].strip() else 0

                # 複勝払戻（最大3頭）
                fukusho = []
                for i in range(3):
                    umaban = row[3 + i * 2]
                    payout = row[4 + i * 2]
                    if umaban and umaban.strip():
                        fukusho.append({
                            'umaban': umaban.strip(),
                            'payout': int(payout) if payout and payout.strip() else 0
                        })

                payouts[race_code] = {
                    'tansho_umaban': tansho_umaban,
                    'tansho_payout': tansho_payout,
                    'fukusho': fukusho,
                }

            cur.close()
            logger.info(f"払戻データ取得: {len(payouts)}レース")
            return payouts

        except Exception as e:
            logger.error(f"払戻データ取得エラー: {e}")
            return {}
        finally:
            conn.close()

    def load_predictions_from_db(self, target_date: date) -> Optional[Dict]:
        """DBから予想結果を読み込み"""
        db = get_db()
        conn = db.get_connection()

        try:
            cur = conn.cursor()

            # 指定日の予想を取得（最新のものを優先）
            cur.execute('''
                SELECT DISTINCT ON (race_id)
                    prediction_id,
                    race_id,
                    race_date,
                    is_final,
                    prediction_result,
                    predicted_at
                FROM predictions
                WHERE race_date = %s
                ORDER BY race_id, predicted_at DESC
            ''', (target_date,))

            rows = cur.fetchall()
            cur.close()

            if not rows:
                logger.warning(f"予想データが見つかりません: {target_date}")
                return None

            predictions = {
                'date': str(target_date),
                'races': []
            }

            for row in rows:
                prediction_id = row[0]
                race_id = row[1]
                is_final = row[3]
                prediction_result = row[4]

                # prediction_resultがJSON文字列の場合はパース
                if isinstance(prediction_result, str):
                    try:
                        prediction_result = json.loads(prediction_result)
                    except json.JSONDecodeError:
                        prediction_result = {}

                # ranked_horsesからTOP3を抽出
                ranked_horses = prediction_result.get('ranked_horses', [])
                top3 = []
                for h in ranked_horses[:3]:
                    top3.append({
                        'rank': h.get('rank', 0),
                        'umaban': str(h.get('horse_number', '')).zfill(2),
                        'bamei': h.get('horse_name', ''),
                        'win_prob': h.get('win_probability', 0),
                    })

                predictions['races'].append({
                    'prediction_id': prediction_id,
                    'race_code': race_id,
                    'is_final': is_final,
                    'top3': top3,
                    'all_horses': ranked_horses,
                })

            logger.info(f"DB予想読み込み: {len(predictions['races'])}レース")
            return predictions

        except Exception as e:
            logger.error(f"予想読み込みエラー: {e}")
            return None
        finally:
            conn.close()

    def compare_results(self, predictions: Dict, results: List[Dict], payouts: Dict = None) -> Dict:
        """予想と結果を比較（EV推奨・軸馬形式）"""
        comparison = {
            'date': predictions['date'],
            'total_races': 0,
            'analyzed_races': 0,
            'stats': {
                'top1_hit': 0,  # 1位予想が1着
                'top1_in_top3': 0,  # 1位予想が3着以内
                'top3_cover': 0,  # 上位3頭に勝ち馬含む
                'top3_hit': 0,  # TOP3予想が1-2-3着
                'tansho_hit': 0,  # 単勝的中
                'fukusho_hit': 0,  # 複勝的中
                'umaren_hit': 0,  # 馬連的中
                'sanrenpuku_hit': 0,  # 三連複的中
                'mrr_sum': 0.0,  # MRR計算用
            },
            # EV推奨成績（EV >= 1.5 の馬）
            'ev_stats': {
                'ev_rec_races': 0,  # EV推奨があったレース数
                'ev_rec_count': 0,  # EV推奨馬の総数
                'ev_rec_tansho_hit': 0,  # 単勝的中数
                'ev_rec_fukusho_hit': 0,  # 複勝的中数
                'ev_tansho_investment': 0,  # 単勝投資額
                'ev_tansho_return': 0,  # 単勝回収額
                'ev_fukusho_investment': 0,  # 複勝投資額
                'ev_fukusho_return': 0,  # 複勝回収額
            },
            # 軸馬成績（複勝確率最高の馬）
            'axis_stats': {
                'axis_races': 0,  # 軸馬レース数
                'axis_tansho_hit': 0,  # 単勝的中
                'axis_fukusho_hit': 0,  # 複勝的中（3着以内）
                'axis_fukusho_investment': 0,  # 複勝投資額
                'axis_fukusho_return': 0,  # 複勝回収額
            },
            # ランキング別成績（1位〜5位予想の着順分布）
            'ranking_stats': {
                1: {'1着': 0, '2着': 0, '3着': 0, '4着以下': 0, '出走': 0},
                2: {'1着': 0, '2着': 0, '3着': 0, '4着以下': 0, '出走': 0},
                3: {'1着': 0, '2着': 0, '3着': 0, '4着以下': 0, '出走': 0},
                4: {'1着': 0, '2着': 0, '3着': 0, '4着以下': 0, '出走': 0},
                5: {'1着': 0, '2着': 0, '3着': 0, '4着以下': 0, '出走': 0},
            },
            # 回収率計算用（1位予想に100円ずつ賭けた場合）
            'return_stats': {
                'tansho_investment': 0,  # 単勝投資額
                'tansho_return': 0,       # 単勝回収額
                'fukusho_investment': 0,  # 複勝投資額
                'fukusho_return': 0,      # 複勝回収額
            },
            # 人気別成績（1位予想馬の人気と着順）
            'popularity_stats': {
                '1-3番人気': {'的中': 0, '複勝圏': 0, '対象': 0},
                '4-6番人気': {'的中': 0, '複勝圏': 0, '対象': 0},
                '7-9番人気': {'的中': 0, '複勝圏': 0, '対象': 0},
                '10番人気以下': {'的中': 0, '複勝圏': 0, '対象': 0},
            },
            # 信頼度別成績（予想の信頼度スコアで分類）
            'confidence_stats': {
                '高(80%以上)': {'的中': 0, '複勝圏': 0, '対象': 0},
                '中(60-80%)': {'的中': 0, '複勝圏': 0, '対象': 0},
                '低(60%未満)': {'的中': 0, '複勝圏': 0, '対象': 0},
            },
            'races': [],
            'misses': [],  # 取りこぼしリスト
            'by_venue': {},  # 競馬場別
            'by_distance': {},  # 距離別
            'by_field_size': {},  # 頭数別
            'by_track': {},  # 芝/ダート別
            'calibration': {  # キャリブレーション用
                'win_prob_bins': {},  # 単勝確率帯別実績
                'place_prob_bins': {},  # 複勝確率帯別実績
            },
        }

        payouts = payouts or {}

        # レースコードでマッピング
        results_map = {r['race_code']: r for r in results}

        for pred_race in predictions.get('races', []):
            race_code = pred_race['race_code']
            comparison['total_races'] += 1

            if race_code not in results_map:
                continue

            actual = results_map[race_code]
            comparison['analyzed_races'] += 1

            # 予想全体と上位3頭を取得
            all_horses = pred_race.get('all_horses', [])
            pred_top3 = pred_race.get('top3', [])
            pred_top3_umaban = [str(int(p['umaban'])) for p in pred_top3]

            # 実際の着順（TOP3）
            actual_results = actual['results']
            actual_top3 = [str(int(r['umaban'])) for r in actual_results[:3] if r['chakujun'] <= 3]
            winner_umaban = actual_top3[0] if actual_top3 else None

            # レース情報
            keibajo = actual['keibajo']
            kyori = actual.get('kyori', 0)
            track = actual.get('track', '不明')
            field_size = len(actual_results)

            # 距離カテゴリ
            try:
                kyori_int = int(kyori) if kyori else 0
            except:
                kyori_int = 0
            if kyori_int <= 1400:
                distance_cat = '短距離'
            elif kyori_int <= 1800:
                distance_cat = 'マイル'
            elif kyori_int <= 2200:
                distance_cat = '中距離'
            else:
                distance_cat = '長距離'

            # 頭数カテゴリ
            if field_size <= 10:
                field_cat = '少頭数(~10)'
            elif field_size <= 14:
                field_cat = '中頭数(11-14)'
            else:
                field_cat = '多頭数(15~)'

            # 統計計算
            race_result = {
                'race_code': race_code,
                'keibajo': keibajo,
                'race_number': actual['race_number'],
                'kyori': kyori,
                'track': track,
                'field_size': field_size,
                'pred_top3': pred_top3_umaban,
                'actual_top3': actual_top3,
                'hits': {},
                'winner_rank': None,  # 勝ち馬の予測順位
            }

            # 勝ち馬の予測順位を計算（MRR用）
            if winner_umaban and all_horses:
                for idx, h in enumerate(all_horses):
                    h_umaban = str(h.get('horse_number', ''))
                    if h_umaban == winner_umaban:
                        winner_rank = idx + 1
                        race_result['winner_rank'] = winner_rank
                        comparison['stats']['mrr_sum'] += 1.0 / winner_rank
                        break

            # 1位予想が1着
            if pred_top3_umaban and actual_top3:
                if pred_top3_umaban[0] == actual_top3[0]:
                    comparison['stats']['top1_hit'] += 1
                    comparison['stats']['tansho_hit'] += 1
                    race_result['hits']['tansho'] = True

                # 1位予想が3着以内
                if pred_top3_umaban[0] in actual_top3:
                    comparison['stats']['top1_in_top3'] += 1
                    comparison['stats']['fukusho_hit'] += 1
                    race_result['hits']['fukusho'] = True

            # 上位3頭に勝ち馬が含まれるか
            if winner_umaban and winner_umaban in pred_top3_umaban:
                comparison['stats']['top3_cover'] += 1
                race_result['hits']['top3_cover'] = True
            elif winner_umaban and race_result['winner_rank'] and race_result['winner_rank'] > 3:
                # 取りこぼし（勝ち馬を4位以下に評価）
                comparison['misses'].append({
                    'race': f"{keibajo}{actual['race_number']}R",
                    'winner_rank': race_result['winner_rank'],
                    'winner': winner_umaban,
                })

            # TOP3予想が全て3着以内
            if len(pred_top3_umaban) >= 3 and len(actual_top3) >= 3:
                if set(pred_top3_umaban[:3]) == set(actual_top3[:3]):
                    comparison['stats']['top3_hit'] += 1
                    comparison['stats']['sanrenpuku_hit'] += 1
                    race_result['hits']['sanrenpuku'] = True

            # 馬連（1-2位予想が1-2着）
            if len(pred_top3_umaban) >= 2 and len(actual_top3) >= 2:
                if set(pred_top3_umaban[:2]) == set(actual_top3[:2]):
                    comparison['stats']['umaren_hit'] += 1
                    race_result['hits']['umaren'] = True

            # ランキング別成績の集計（1位〜5位予想がそれぞれ何着だったか）
            actual_results_map = {str(int(r['umaban'])): r['chakujun'] for r in actual_results}
            for rank in range(1, 6):  # 1位〜5位予想
                if rank <= len(all_horses):
                    pred_umaban = str(all_horses[rank - 1].get('horse_number', ''))
                    comparison['ranking_stats'][rank]['出走'] += 1

                    if pred_umaban in actual_results_map:
                        actual_pos = actual_results_map[pred_umaban]
                        if actual_pos == 1:
                            comparison['ranking_stats'][rank]['1着'] += 1
                        elif actual_pos == 2:
                            comparison['ranking_stats'][rank]['2着'] += 1
                        elif actual_pos == 3:
                            comparison['ranking_stats'][rank]['3着'] += 1
                        else:
                            comparison['ranking_stats'][rank]['4着以下'] += 1
                    else:
                        # 出走取消など
                        comparison['ranking_stats'][rank]['4着以下'] += 1

            # EV推奨成績（EV >= 1.5 の馬）
            race_payout = payouts.get(race_code, {})
            ev_recommended = []
            for h in all_horses:
                win_prob = h.get('win_probability', 0)
                odds = h.get('predicted_odds', 0)
                if odds > 0 and win_prob > 0:
                    win_ev = win_prob * odds
                    if win_ev >= 1.5:
                        ev_recommended.append(h)

            if ev_recommended:
                comparison['ev_stats']['ev_rec_races'] += 1
                comparison['ev_stats']['ev_rec_count'] += len(ev_recommended)

                for h in ev_recommended:
                    h_umaban = str(int(h.get('horse_number', 0)))
                    # 単勝投資
                    comparison['ev_stats']['ev_tansho_investment'] += 100
                    comparison['ev_stats']['ev_fukusho_investment'] += 100

                    # 的中判定
                    if h_umaban in actual_results_map:
                        actual_pos = actual_results_map[h_umaban]
                        if actual_pos == 1:
                            comparison['ev_stats']['ev_rec_tansho_hit'] += 1
                            # 単勝払戻
                            if race_payout:
                                tansho_payout = race_payout.get('tansho_payout', 0)
                                comparison['ev_stats']['ev_tansho_return'] += tansho_payout
                        if actual_pos <= 3:
                            comparison['ev_stats']['ev_rec_fukusho_hit'] += 1
                            # 複勝払戻
                            if race_payout:
                                for fk in race_payout.get('fukusho', []):
                                    fk_umaban = fk.get('umaban', '')
                                    if fk_umaban and str(int(fk_umaban)) == h_umaban:
                                        comparison['ev_stats']['ev_fukusho_return'] += fk.get('payout', 0)
                                        break

            race_result['ev_recommended'] = [str(int(h.get('horse_number', 0))) for h in ev_recommended]

            # 軸馬成績（複勝確率最高の馬）
            axis_horse = max(all_horses, key=lambda h: h.get('place_probability', 0)) if all_horses else None
            if axis_horse:
                comparison['axis_stats']['axis_races'] += 1
                axis_umaban = str(int(axis_horse.get('horse_number', 0)))
                comparison['axis_stats']['axis_fukusho_investment'] += 100

                if axis_umaban in actual_results_map:
                    actual_pos = actual_results_map[axis_umaban]
                    if actual_pos == 1:
                        comparison['axis_stats']['axis_tansho_hit'] += 1
                    if actual_pos <= 3:
                        comparison['axis_stats']['axis_fukusho_hit'] += 1
                        # 複勝払戻
                        if race_payout:
                            for fk in race_payout.get('fukusho', []):
                                fk_umaban = fk.get('umaban', '')
                                if fk_umaban and str(int(fk_umaban)) == axis_umaban:
                                    comparison['axis_stats']['axis_fukusho_return'] += fk.get('payout', 0)
                                    break

                race_result['axis_horse'] = axis_umaban
                race_result['axis_fukusho'] = axis_umaban in actual_results_map and actual_results_map[axis_umaban] <= 3

            # 回収率計算（払戻データがある場合）- 1位予想ベース（参考）
            if race_payout and all_horses:
                # 馬番を数値として比較（"6" == "06" を正しくマッチさせる）
                pred_1st_num = str(int(all_horses[0].get('horse_number', 0))) if len(all_horses) > 0 else None

                # 単勝（1位予想に100円）
                comparison['return_stats']['tansho_investment'] += 100
                tansho_umaban = race_payout.get('tansho_umaban', '')
                if pred_1st_num and tansho_umaban:
                    tansho_umaban_num = str(int(tansho_umaban)) if tansho_umaban.strip() else ''
                    if tansho_umaban_num == pred_1st_num:
                        comparison['return_stats']['tansho_return'] += race_payout.get('tansho_payout', 0)

                # 複勝（1位予想に100円）
                comparison['return_stats']['fukusho_investment'] += 100
                fukusho_hits = race_payout.get('fukusho', [])
                for fk in fukusho_hits:
                    fk_umaban = fk.get('umaban', '')
                    if fk_umaban:
                        fk_umaban_num = str(int(fk_umaban)) if fk_umaban.strip() else ''
                        if fk_umaban_num == pred_1st_num:
                            comparison['return_stats']['fukusho_return'] += fk.get('payout', 0)
                            break

            # 人気別成績（1位予想馬の人気から）
            pred_1st_umaban = str(int(all_horses[0].get('horse_number', 0))) if all_horses else None
            pred_1st_ninki = None
            for res in actual_results:
                if str(int(res['umaban'])) == pred_1st_umaban:
                    pred_1st_ninki = res.get('ninki')
                    break

            if pred_1st_ninki:
                # 人気カテゴリを決定
                if pred_1st_ninki <= 3:
                    pop_cat = '1-3番人気'
                elif pred_1st_ninki <= 6:
                    pop_cat = '4-6番人気'
                elif pred_1st_ninki <= 9:
                    pop_cat = '7-9番人気'
                else:
                    pop_cat = '10番人気以下'

                comparison['popularity_stats'][pop_cat]['対象'] += 1
                if race_result['hits'].get('tansho'):
                    comparison['popularity_stats'][pop_cat]['的中'] += 1
                if race_result['hits'].get('fukusho'):
                    comparison['popularity_stats'][pop_cat]['複勝圏'] += 1
                race_result['pred_1st_ninki'] = pred_1st_ninki

            # 信頼度別成績（1位予想馬のconfidenceから）
            pred_1st_confidence = all_horses[0].get('confidence', 0) if all_horses else 0
            if pred_1st_confidence >= 0.80:
                conf_cat = '高(80%以上)'
            elif pred_1st_confidence >= 0.60:
                conf_cat = '中(60-80%)'
            else:
                conf_cat = '低(60%未満)'

            comparison['confidence_stats'][conf_cat]['対象'] += 1
            if race_result['hits'].get('tansho'):
                comparison['confidence_stats'][conf_cat]['的中'] += 1
            if race_result['hits'].get('fukusho'):
                comparison['confidence_stats'][conf_cat]['複勝圏'] += 1
            race_result['pred_1st_confidence'] = pred_1st_confidence

            comparison['races'].append(race_result)

            # 条件別集計
            for cat_name, cat_key, cat_val in [
                ('by_venue', keibajo, keibajo),
                ('by_distance', distance_cat, distance_cat),
                ('by_field_size', field_cat, field_cat),
                ('by_track', track, track),
            ]:
                if cat_val not in comparison[cat_name]:
                    comparison[cat_name][cat_val] = {
                        'races': 0, 'top1_hit': 0, 'top1_in_top3': 0, 'top3_cover': 0
                    }
                comparison[cat_name][cat_val]['races'] += 1
                if race_result['hits'].get('tansho'):
                    comparison[cat_name][cat_val]['top1_hit'] += 1
                if race_result['hits'].get('fukusho'):
                    comparison[cat_name][cat_val]['top1_in_top3'] += 1
                if race_result['hits'].get('top3_cover'):
                    comparison[cat_name][cat_val]['top3_cover'] += 1

            # キャリブレーション用データ収集
            if pred_top3 and len(pred_top3) > 0:
                win_prob = pred_top3[0].get('win_prob', 0)
                # 確率を10%刻みのビンに
                win_bin = f"{int(win_prob * 10) * 10}%"
                if win_bin not in comparison['calibration']['win_prob_bins']:
                    comparison['calibration']['win_prob_bins'][win_bin] = {'count': 0, 'hit': 0}
                comparison['calibration']['win_prob_bins'][win_bin]['count'] += 1
                if race_result['hits'].get('tansho'):
                    comparison['calibration']['win_prob_bins'][win_bin]['hit'] += 1

        return comparison

    def calculate_accuracy(self, comparison: Dict) -> Dict:
        """精度指標を計算（詳細版）"""
        n = comparison['analyzed_races']
        if n == 0:
            return {'error': 'no_data'}

        stats = comparison['stats']

        # MRR計算
        mrr = stats['mrr_sum'] / n if n > 0 else 0

        # 条件別精度を計算
        def calc_rates(data: Dict) -> Dict:
            result = {}
            for key, vals in data.items():
                races = vals['races']
                if races > 0:
                    result[key] = {
                        'races': races,
                        'top1_rate': vals['top1_hit'] / races * 100,
                        'top3_rate': vals['top1_in_top3'] / races * 100,
                        'cover_rate': vals['top3_cover'] / races * 100,
                    }
            return result

        # キャリブレーション計算
        calibration = {}
        for bin_name, data in comparison.get('calibration', {}).get('win_prob_bins', {}).items():
            if data['count'] > 0:
                calibration[bin_name] = {
                    'count': data['count'],
                    'actual_rate': data['hit'] / data['count'] * 100,
                }

        # ランキング別成績を整形
        ranking_stats = comparison.get('ranking_stats', {})
        ranking_formatted = {}
        for rank, data in ranking_stats.items():
            total = data.get('出走', 0)
            if total > 0:
                ranking_formatted[rank] = {
                    '出走': total,
                    '1着': data['1着'],
                    '2着': data['2着'],
                    '3着': data['3着'],
                    '4着以下': data['4着以下'],
                    '1着率': data['1着'] / total * 100,
                    '連対率': (data['1着'] + data['2着']) / total * 100,
                    '複勝率': (data['1着'] + data['2着'] + data['3着']) / total * 100,
                }

        # 回収率計算（1位予想ベース・参考）
        return_stats = comparison.get('return_stats', {})
        tansho_inv = return_stats.get('tansho_investment', 0)
        fukusho_inv = return_stats.get('fukusho_investment', 0)
        return_rates = {
            'tansho_roi': (return_stats.get('tansho_return', 0) / tansho_inv * 100) if tansho_inv > 0 else 0,
            'fukusho_roi': (return_stats.get('fukusho_return', 0) / fukusho_inv * 100) if fukusho_inv > 0 else 0,
            'tansho_investment': tansho_inv,
            'tansho_return': return_stats.get('tansho_return', 0),
            'fukusho_investment': fukusho_inv,
            'fukusho_return': return_stats.get('fukusho_return', 0),
        }

        # EV推奨成績を整形
        ev_stats = comparison.get('ev_stats', {})
        ev_rec_count = ev_stats.get('ev_rec_count', 0)
        ev_tansho_inv = ev_stats.get('ev_tansho_investment', 0)
        ev_fukusho_inv = ev_stats.get('ev_fukusho_investment', 0)
        ev_formatted = {
            'ev_rec_races': ev_stats.get('ev_rec_races', 0),
            'ev_rec_count': ev_rec_count,
            'ev_rec_tansho_hit': ev_stats.get('ev_rec_tansho_hit', 0),
            'ev_rec_fukusho_hit': ev_stats.get('ev_rec_fukusho_hit', 0),
            'ev_tansho_rate': (ev_stats.get('ev_rec_tansho_hit', 0) / ev_rec_count * 100) if ev_rec_count > 0 else 0,
            'ev_fukusho_rate': (ev_stats.get('ev_rec_fukusho_hit', 0) / ev_rec_count * 100) if ev_rec_count > 0 else 0,
            'ev_tansho_roi': (ev_stats.get('ev_tansho_return', 0) / ev_tansho_inv * 100) if ev_tansho_inv > 0 else 0,
            'ev_fukusho_roi': (ev_stats.get('ev_fukusho_return', 0) / ev_fukusho_inv * 100) if ev_fukusho_inv > 0 else 0,
            'ev_tansho_investment': ev_tansho_inv,
            'ev_tansho_return': ev_stats.get('ev_tansho_return', 0),
            'ev_fukusho_investment': ev_fukusho_inv,
            'ev_fukusho_return': ev_stats.get('ev_fukusho_return', 0),
        }

        # 軸馬成績を整形
        axis_stats = comparison.get('axis_stats', {})
        axis_races = axis_stats.get('axis_races', 0)
        axis_fukusho_inv = axis_stats.get('axis_fukusho_investment', 0)
        axis_formatted = {
            'axis_races': axis_races,
            'axis_tansho_hit': axis_stats.get('axis_tansho_hit', 0),
            'axis_fukusho_hit': axis_stats.get('axis_fukusho_hit', 0),
            'axis_tansho_rate': (axis_stats.get('axis_tansho_hit', 0) / axis_races * 100) if axis_races > 0 else 0,
            'axis_fukusho_rate': (axis_stats.get('axis_fukusho_hit', 0) / axis_races * 100) if axis_races > 0 else 0,
            'axis_fukusho_roi': (axis_stats.get('axis_fukusho_return', 0) / axis_fukusho_inv * 100) if axis_fukusho_inv > 0 else 0,
            'axis_fukusho_investment': axis_fukusho_inv,
            'axis_fukusho_return': axis_stats.get('axis_fukusho_return', 0),
        }

        # 人気別成績を整形
        popularity_stats = comparison.get('popularity_stats', {})
        popularity_formatted = {}
        for pop_cat, data in popularity_stats.items():
            total = data.get('対象', 0)
            if total > 0:
                popularity_formatted[pop_cat] = {
                    '対象': total,
                    '的中': data['的中'],
                    '複勝圏': data['複勝圏'],
                    '的中率': data['的中'] / total * 100,
                    '複勝率': data['複勝圏'] / total * 100,
                }

        # 信頼度別成績を整形
        confidence_stats = comparison.get('confidence_stats', {})
        confidence_formatted = {}
        for conf_cat, data in confidence_stats.items():
            total = data.get('対象', 0)
            if total > 0:
                confidence_formatted[conf_cat] = {
                    '対象': total,
                    '的中': data['的中'],
                    '複勝圏': data['複勝圏'],
                    '的中率': data['的中'] / total * 100,
                    '複勝率': data['複勝圏'] / total * 100,
                }

        return {
            'date': comparison['date'],
            'total_races': comparison['total_races'],
            'analyzed_races': n,
            'accuracy': {
                'top1_hit_rate': stats['top1_hit'] / n * 100,
                'top1_in_top3_rate': stats['top1_in_top3'] / n * 100,
                'top3_cover_rate': stats['top3_cover'] / n * 100,
                'mrr': mrr,
                'tansho_hit_rate': stats['tansho_hit'] / n * 100,
                'fukusho_hit_rate': stats['fukusho_hit'] / n * 100,
                'umaren_hit_rate': stats['umaren_hit'] / n * 100,
                'sanrenpuku_hit_rate': stats['sanrenpuku_hit'] / n * 100,
            },
            'ev_stats': ev_formatted,
            'axis_stats': axis_formatted,
            'ranking_stats': ranking_formatted,
            'return_rates': return_rates,
            'popularity_stats': popularity_formatted,
            'confidence_stats': confidence_formatted,
            'by_venue': calc_rates(comparison.get('by_venue', {})),
            'by_distance': calc_rates(comparison.get('by_distance', {})),
            'by_field_size': calc_rates(comparison.get('by_field_size', {})),
            'by_track': calc_rates(comparison.get('by_track', {})),
            'calibration': calibration,
            'misses': comparison.get('misses', []),
            'raw_stats': stats
        }

    def collect_and_analyze(self, target_date: date) -> Dict:
        """結果収集と分析を実行"""
        logger.info(f"結果収集開始: {target_date}")

        # DBから予想を読み込み
        predictions = self.load_predictions_from_db(target_date)
        if not predictions:
            return {'status': 'no_predictions', 'date': str(target_date)}

        # 結果を取得
        results = self.get_race_results(target_date)
        if not results:
            logger.info(f"{target_date}の結果データがありません")
            return {'status': 'no_results', 'date': str(target_date)}

        logger.info(f"{len(results)}レースの結果を取得")

        # 払戻データを取得
        payouts = self.get_payouts(target_date)

        # 比較（払戻データ含む）
        comparison = self.compare_results(predictions, results, payouts)

        # 精度計算
        accuracy = self.calculate_accuracy(comparison)

        return {
            'status': 'success',
            'comparison': comparison,
            'accuracy': accuracy
        }

    def save_analysis_to_db(self, analysis: Dict) -> bool:
        """分析結果をDBに保存"""
        if analysis.get('status') != 'success':
            return False

        acc = analysis.get('accuracy', {})
        if 'error' in acc:
            return False

        db = get_db()
        conn = db.get_connection()
        if not conn:
            logger.error("DB接続失敗")
            return False

        try:
            cur = conn.cursor()
            analysis_date = acc.get('date')
            raw_stats = acc.get('raw_stats', {})
            accuracy = acc.get('accuracy', {})

            # UPSERT (ON CONFLICT UPDATE)
            cur.execute('''
                INSERT INTO analysis_results (
                    analysis_date, total_races, analyzed_races,
                    tansho_hit, fukusho_hit, umaren_hit, sanrenpuku_hit, top3_cover,
                    tansho_rate, fukusho_rate, umaren_rate, sanrenpuku_rate, top3_cover_rate, mrr,
                    detail_data
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (analysis_date) DO UPDATE SET
                    total_races = EXCLUDED.total_races,
                    analyzed_races = EXCLUDED.analyzed_races,
                    tansho_hit = EXCLUDED.tansho_hit,
                    fukusho_hit = EXCLUDED.fukusho_hit,
                    umaren_hit = EXCLUDED.umaren_hit,
                    sanrenpuku_hit = EXCLUDED.sanrenpuku_hit,
                    top3_cover = EXCLUDED.top3_cover,
                    tansho_rate = EXCLUDED.tansho_rate,
                    fukusho_rate = EXCLUDED.fukusho_rate,
                    umaren_rate = EXCLUDED.umaren_rate,
                    sanrenpuku_rate = EXCLUDED.sanrenpuku_rate,
                    top3_cover_rate = EXCLUDED.top3_cover_rate,
                    mrr = EXCLUDED.mrr,
                    detail_data = EXCLUDED.detail_data,
                    analyzed_at = CURRENT_TIMESTAMP
            ''', (
                analysis_date,
                acc.get('total_races', 0),
                acc.get('analyzed_races', 0),
                raw_stats.get('tansho_hit', 0),
                raw_stats.get('fukusho_hit', 0),
                raw_stats.get('umaren_hit', 0),
                raw_stats.get('sanrenpuku_hit', 0),
                raw_stats.get('top3_cover', 0),
                accuracy.get('tansho_hit_rate'),
                accuracy.get('fukusho_hit_rate'),
                accuracy.get('umaren_hit_rate'),
                accuracy.get('sanrenpuku_hit_rate'),
                accuracy.get('top3_cover_rate'),
                accuracy.get('mrr'),
                json.dumps({
                    'by_venue': acc.get('by_venue', {}),
                    'by_distance': acc.get('by_distance', {}),
                    'by_track': acc.get('by_track', {}),
                    'calibration': acc.get('calibration', {}),
                    'misses': acc.get('misses', [])
                }, ensure_ascii=False)
            ))

            conn.commit()
            logger.info(f"分析結果DB保存: {analysis_date}")
            return True

        except Exception as e:
            logger.error(f"分析結果DB保存エラー: {e}")
            if conn:
                conn.rollback()
            return False
        finally:
            if conn:
                conn.close()

    def update_accuracy_tracking(self, stats: Dict) -> bool:
        """累積精度トラッキングを更新"""
        db = get_db()
        conn = db.get_connection()
        if not conn:
            logger.error("DB接続失敗")
            return False

        try:
            cur = conn.cursor()

            # 現在の累積値を取得
            cur.execute('SELECT * FROM accuracy_tracking LIMIT 1')
            row = cur.fetchone()

            if row:
                # 更新
                new_total = row[1] + stats.get('analyzed_races', 0)
                new_tansho = row[2] + stats.get('tansho_hit', 0)
                new_fukusho = row[3] + stats.get('fukusho_hit', 0)
                new_umaren = row[4] + stats.get('umaren_hit', 0)
                new_sanrenpuku = row[5] + stats.get('sanrenpuku_hit', 0)

                cur.execute('''
                    UPDATE accuracy_tracking SET
                        total_races = %s,
                        total_tansho_hit = %s,
                        total_fukusho_hit = %s,
                        total_umaren_hit = %s,
                        total_sanrenpuku_hit = %s,
                        cumulative_tansho_rate = CASE WHEN %s > 0 THEN %s::float / %s * 100 ELSE 0 END,
                        cumulative_fukusho_rate = CASE WHEN %s > 0 THEN %s::float / %s * 100 ELSE 0 END,
                        cumulative_umaren_rate = CASE WHEN %s > 0 THEN %s::float / %s * 100 ELSE 0 END,
                        cumulative_sanrenpuku_rate = CASE WHEN %s > 0 THEN %s::float / %s * 100 ELSE 0 END,
                        last_updated = CURRENT_TIMESTAMP
                    WHERE id = %s
                ''', (
                    new_total, new_tansho, new_fukusho, new_umaren, new_sanrenpuku,
                    new_total, new_tansho, new_total,
                    new_total, new_fukusho, new_total,
                    new_total, new_umaren, new_total,
                    new_total, new_sanrenpuku, new_total,
                    row[0]
                ))
            else:
                # 初期挿入
                n = stats.get('analyzed_races', 0)
                cur.execute('''
                    INSERT INTO accuracy_tracking (
                        total_races, total_tansho_hit, total_fukusho_hit,
                        total_umaren_hit, total_sanrenpuku_hit
                    ) VALUES (%s, %s, %s, %s, %s)
                ''', (
                    n,
                    stats.get('tansho_hit', 0),
                    stats.get('fukusho_hit', 0),
                    stats.get('umaren_hit', 0),
                    stats.get('sanrenpuku_hit', 0)
                ))

            conn.commit()
            logger.info("累積トラッキング更新完了")
            return True

        except Exception as e:
            logger.error(f"累積トラッキング更新エラー: {e}")
            if conn:
                conn.rollback()
            return False
        finally:
            if conn:
                conn.close()

    def get_cumulative_stats(self) -> Optional[Dict]:
        """累積統計を取得"""
        db = get_db()
        conn = db.get_connection()
        if not conn:
            return None

        try:
            cur = conn.cursor()
            cur.execute('SELECT * FROM accuracy_tracking LIMIT 1')
            row = cur.fetchone()

            if row:
                return {
                    'total_races': row[1],
                    'tansho_hit': row[2],
                    'fukusho_hit': row[3],
                    'umaren_hit': row[4],
                    'sanrenpuku_hit': row[5],
                    'tansho_rate': row[6],
                    'fukusho_rate': row[7],
                    'umaren_rate': row[8],
                    'sanrenpuku_rate': row[9],
                    'last_updated': row[10]
                }
            return None

        except Exception as e:
            logger.error(f"累積統計取得エラー: {e}")
            return None
        finally:
            if conn:
                conn.close()

    def send_discord_notification(self, analysis: Dict):
        """Discord通知を送信（EV推奨・軸馬形式）"""
        import os
        import requests

        bot_token = os.getenv('DISCORD_BOT_TOKEN')
        channel_id = os.getenv('DISCORD_NOTIFICATION_CHANNEL_ID')

        if not bot_token or not channel_id:
            logger.warning("Discord通知設定がありません")
            return

        acc = analysis.get('accuracy', {})
        if 'error' in acc:
            return

        date_str = acc.get('date', '不明')
        n = acc.get('analyzed_races', 0)
        ev_stats = acc.get('ev_stats', {})
        axis_stats = acc.get('axis_stats', {})
        by_track = acc.get('by_track', {})

        # 基本メッセージ（EV推奨・軸馬中心）
        lines = [
            f"📊 **{date_str} 予想結果レポート**",
            f"分析レース数: {n}R",
            "",
        ]

        # EV推奨成績
        ev_rec_races = ev_stats.get('ev_rec_races', 0)
        ev_rec_count = ev_stats.get('ev_rec_count', 0)
        if ev_rec_count > 0:
            lines.append("**【単複推奨成績】** (EV >= 1.5)")
            lines.append(f"  推奨レース: {ev_rec_races}R / 推奨馬: {ev_rec_count}頭")
            lines.append(f"  単勝: {ev_stats.get('ev_rec_tansho_hit', 0)}的中 ({ev_stats.get('ev_tansho_rate', 0):.1f}%)")
            lines.append(f"  複勝: {ev_stats.get('ev_rec_fukusho_hit', 0)}的中 ({ev_stats.get('ev_fukusho_rate', 0):.1f}%)")
            lines.append(f"  単勝回収率: {ev_stats.get('ev_tansho_return', 0):,}円 / {ev_stats.get('ev_tansho_investment', 0):,}円 = **{ev_stats.get('ev_tansho_roi', 0):.0f}%**")
            lines.append(f"  複勝回収率: {ev_stats.get('ev_fukusho_return', 0):,}円 / {ev_stats.get('ev_fukusho_investment', 0):,}円 = **{ev_stats.get('ev_fukusho_roi', 0):.0f}%**")
        else:
            lines.append("**【単複推奨成績】**")
            lines.append("  EV推奨なし")

        # 軸馬成績
        lines.append("")
        axis_races = axis_stats.get('axis_races', 0)
        if axis_races > 0:
            lines.append("**【軸馬成績】** (複勝確率1位)")
            lines.append(f"  対象レース: {axis_races}R")
            lines.append(f"  単勝: {axis_stats.get('axis_tansho_hit', 0)}的中 ({axis_stats.get('axis_tansho_rate', 0):.1f}%)")
            lines.append(f"  複勝: {axis_stats.get('axis_fukusho_hit', 0)}的中 (**{axis_stats.get('axis_fukusho_rate', 0):.1f}%**)")
            lines.append(f"  複勝回収率: {axis_stats.get('axis_fukusho_return', 0):,}円 / {axis_stats.get('axis_fukusho_investment', 0):,}円 = {axis_stats.get('axis_fukusho_roi', 0):.0f}%")

        # 芝/ダート別（軸馬複勝率として表示）
        if by_track:
            lines.append("")
            lines.append("**【芝/ダート別】** (軸馬複勝率)")
            for track in ['芝', 'ダ']:
                if track in by_track:
                    t = by_track[track]
                    lines.append(f"  {track}: {t['races']}R → {t['top3_rate']:.0f}%")

        message = "\n".join(lines)

        url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
        headers = {
            "Authorization": f"Bot {bot_token}",
            "Content-Type": "application/json"
        }

        try:
            response = requests.post(url, headers=headers, json={"content": message}, timeout=10)
            if response.status_code in (200, 201):
                logger.info("Discord通知送信完了")
            else:
                logger.warning(f"Discord通知失敗: {response.status_code}")
        except Exception as e:
            logger.error(f"Discord通知エラー: {e}")

    def send_weekend_notification(
        self,
        saturday: date,
        sunday: date,
        stats: Dict,
        ranking_stats: Dict = None,
        return_rates: Dict = None,
        popularity_stats: Dict = None,
        confidence_stats: Dict = None,
        by_track: Dict = None,
        daily_data: Dict = None,
        cumulative: Optional[Dict] = None,
        ev_stats: Dict = None,
        axis_stats: Dict = None,
    ):
        """週末合計のDiscord通知を送信（EV推奨・軸馬形式）"""
        import os
        import requests

        bot_token = os.getenv('DISCORD_BOT_TOKEN')
        channel_id = os.getenv('DISCORD_NOTIFICATION_CHANNEL_ID')

        if not bot_token or not channel_id:
            logger.warning("Discord通知設定がありません")
            return

        ev_stats = ev_stats or {}
        axis_stats = axis_stats or {}

        lines = [
            f"📊 **週末予想結果レポート**",
            f"期間: {saturday} - {sunday}",
            f"分析レース数: {stats.get('analyzed_races', 0)}R",
            "",
        ]

        # EV推奨成績
        ev_rec_count = ev_stats.get('ev_rec_count', 0)
        if ev_rec_count > 0:
            lines.append("**【単複推奨成績】** (EV >= 1.5)")
            lines.append(f"  推奨レース: {ev_stats.get('ev_rec_races', 0)}R / 推奨馬: {ev_rec_count}頭")
            lines.append(f"  単勝: {ev_stats.get('ev_rec_tansho_hit', 0)}的中 ({ev_stats.get('ev_tansho_rate', 0):.1f}%)")
            lines.append(f"  複勝: {ev_stats.get('ev_rec_fukusho_hit', 0)}的中 ({ev_stats.get('ev_fukusho_rate', 0):.1f}%)")
            lines.append(f"  単勝回収率: {ev_stats.get('ev_tansho_return', 0):,}円 / {ev_stats.get('ev_tansho_investment', 0):,}円 = **{ev_stats.get('ev_tansho_roi', 0):.0f}%**")
            lines.append(f"  複勝回収率: {ev_stats.get('ev_fukusho_return', 0):,}円 / {ev_stats.get('ev_fukusho_investment', 0):,}円 = **{ev_stats.get('ev_fukusho_roi', 0):.0f}%**")
        else:
            lines.append("**【単複推奨成績】**")
            lines.append("  EV推奨なし")

        # 軸馬成績
        lines.append("")
        axis_races = axis_stats.get('axis_races', 0)
        if axis_races > 0:
            lines.append("**【軸馬成績】** (複勝確率1位)")
            lines.append(f"  対象レース: {axis_races}R")
            lines.append(f"  単勝: {axis_stats.get('axis_tansho_hit', 0)}的中 ({axis_stats.get('axis_tansho_rate', 0):.1f}%)")
            lines.append(f"  複勝: {axis_stats.get('axis_fukusho_hit', 0)}的中 (**{axis_stats.get('axis_fukusho_rate', 0):.1f}%**)")
            lines.append(f"  複勝回収率: {axis_stats.get('axis_fukusho_return', 0):,}円 / {axis_stats.get('axis_fukusho_investment', 0):,}円 = {axis_stats.get('axis_fukusho_roi', 0):.0f}%")

        # 芝/ダート別
        if by_track:
            lines.append("")
            lines.append("**【芝/ダート別】** (軸馬複勝率)")
            for track in ['芝', 'ダ']:
                if track in by_track:
                    t = by_track[track]
                    lines.append(f"  {track}: {t['races']}R → {t['top3_rate']:.0f}%")

        # 日付選択メニューがある場合は案内を追加
        if daily_data:
            lines.append("")
            lines.append("▼ 日付を選択して詳細を表示")

        message = "\n".join(lines)

        url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
        headers = {
            "Authorization": f"Bot {bot_token}",
            "Content-Type": "application/json"
        }

        # リクエストボディ
        payload = {"content": message}

        # 日付別データがある場合はセレクトメニューを追加
        if daily_data and len(daily_data) > 0:
            options = []
            for date_str in sorted(daily_data.keys()):
                data = daily_data[date_str]
                n = data.get('analyzed_races', 0)
                axis_rate = data.get('axis_stats', {}).get('axis_fukusho_rate', 0)
                options.append({
                    "label": f"{date_str} ({n}R)",
                    "value": date_str,
                    "description": f"軸馬複勝率: {axis_rate:.0f}%"
                })

            if options:
                payload["components"] = [
                    {
                        "type": 1,  # Action Row
                        "components": [
                            {
                                "type": 3,  # Select Menu
                                "custom_id": "weekend_result_select",
                                "placeholder": "日付を選択して詳細を表示...",
                                "options": options
                            }
                        ]
                    }
                ]

        try:
            response = requests.post(url, headers=headers, json=payload, timeout=10)
            if response.status_code in (200, 201):
                logger.info("週末Discord通知送信完了")
            else:
                logger.warning(f"週末Discord通知失敗: {response.status_code} - {response.text}")
        except Exception as e:
            logger.error(f"週末Discord通知エラー: {e}")


def collect_today_results():
    """当日のレース結果を収集"""
    collector = ResultCollector()
    today = date.today()

    analysis = collector.collect_and_analyze(today)

    if analysis['status'] == 'success':
        collector.save_analysis_to_db(analysis)
        collector.send_discord_notification(analysis)
        acc = analysis['accuracy']
        print(f"\n=== {acc['date']} 予想精度 ===")
        print(f"分析レース数: {acc['analyzed_races']}")
        print(f"単勝的中率: {acc['accuracy']['tansho_hit_rate']:.1f}%")
        print(f"複勝的中率: {acc['accuracy']['fukusho_hit_rate']:.1f}%")
        print(f"馬連的中率: {acc['accuracy']['umaren_hit_rate']:.1f}%")
        print(f"三連複的中率: {acc['accuracy']['sanrenpuku_hit_rate']:.1f}%")
    else:
        print(f"結果収集失敗: {analysis['status']}")


def get_recent_race_dates(days_back: int = 7) -> list:
    """直近のレース日（予想データがある日）を取得"""
    db = get_db()
    conn = db.get_connection()

    try:
        cur = conn.cursor()
        cur.execute('''
            SELECT DISTINCT race_date
            FROM predictions
            WHERE race_date >= %s AND race_date < %s
            ORDER BY race_date
        ''', (date.today() - timedelta(days=days_back), date.today()))

        dates = [row[0] for row in cur.fetchall()]
        cur.close()
        return dates
    finally:
        conn.close()


def collect_weekend_results():
    """先週末のレース結果を収集してDBに保存（開催日を自動検出）"""
    collector = ResultCollector()

    # 予想データがある直近の日を取得（最大7日前まで）
    weekend_dates = get_recent_race_dates(days_back=7)

    if not weekend_dates:
        print("直近7日間に予想データがありません")
        return

    first_date = weekend_dates[0]
    last_date = weekend_dates[-1]
    total_stats = {
        'total_races': 0,
        'analyzed_races': 0,
        'tansho_hit': 0,
        'fukusho_hit': 0,
        'umaren_hit': 0,
        'sanrenpuku_hit': 0,
    }
    # ランキング別成績の集計用
    total_ranking_stats = {
        1: {'1着': 0, '2着': 0, '3着': 0, '4着以下': 0, '出走': 0},
        2: {'1着': 0, '2着': 0, '3着': 0, '4着以下': 0, '出走': 0},
        3: {'1着': 0, '2着': 0, '3着': 0, '4着以下': 0, '出走': 0},
    }
    # 回収率集計用
    total_return = {
        'tansho_investment': 0,
        'tansho_return': 0,
        'fukusho_investment': 0,
        'fukusho_return': 0,
    }
    # 人気別成績集計用
    total_popularity = {
        '1-3番人気': {'的中': 0, '複勝圏': 0, '対象': 0},
        '4-6番人気': {'的中': 0, '複勝圏': 0, '対象': 0},
        '7-9番人気': {'的中': 0, '複勝圏': 0, '対象': 0},
        '10番人気以下': {'的中': 0, '複勝圏': 0, '対象': 0},
    }
    # 信頼度別成績集計用
    total_confidence = {
        '高(80%以上)': {'的中': 0, '複勝圏': 0, '対象': 0},
        '中(60-80%)': {'的中': 0, '複勝圏': 0, '対象': 0},
        '低(60%未満)': {'的中': 0, '複勝圏': 0, '対象': 0},
    }
    # 芝/ダート別集計用
    total_track = {
        '芝': {'races': 0, 'top1_hit': 0, 'top1_in_top3': 0, 'top3_cover': 0},
        'ダ': {'races': 0, 'top1_hit': 0, 'top1_in_top3': 0, 'top3_cover': 0},
    }
    # EV推奨成績集計用
    total_ev = {
        'ev_rec_races': 0,
        'ev_rec_count': 0,
        'ev_rec_tansho_hit': 0,
        'ev_rec_fukusho_hit': 0,
        'ev_tansho_investment': 0,
        'ev_tansho_return': 0,
        'ev_fukusho_investment': 0,
        'ev_fukusho_return': 0,
    }
    # 軸馬成績集計用
    total_axis = {
        'axis_races': 0,
        'axis_tansho_hit': 0,
        'axis_fukusho_hit': 0,
        'axis_fukusho_investment': 0,
        'axis_fukusho_return': 0,
    }

    # 日付別データ（インタラクション用）
    daily_data = {}

    print(f"\n=== 週末レース結果収集 ({first_date} - {last_date}) ===")
    print(f"対象日: {', '.join(str(d) for d in weekend_dates)}")

    for target_date in weekend_dates:
        analysis = collector.collect_and_analyze(target_date)

        if analysis['status'] == 'success':
            # DB保存
            collector.save_analysis_to_db(analysis)

            acc = analysis['accuracy']
            total_stats['total_races'] += acc['total_races']
            total_stats['analyzed_races'] += acc['analyzed_races']
            total_stats['tansho_hit'] += acc['raw_stats']['tansho_hit']
            total_stats['fukusho_hit'] += acc['raw_stats']['fukusho_hit']
            total_stats['umaren_hit'] += acc['raw_stats']['umaren_hit']
            total_stats['sanrenpuku_hit'] += acc['raw_stats']['sanrenpuku_hit']

            # ランキング別成績を集計
            ranking_stats = acc.get('ranking_stats', {})
            for rank in [1, 2, 3]:
                if rank in ranking_stats:
                    for key in ['1着', '2着', '3着', '4着以下', '出走']:
                        total_ranking_stats[rank][key] += ranking_stats[rank].get(key, 0)

            # 回収率を集計
            return_rates = acc.get('return_rates', {})
            total_return['tansho_investment'] += return_rates.get('tansho_investment', 0)
            total_return['tansho_return'] += return_rates.get('tansho_return', 0)
            total_return['fukusho_investment'] += return_rates.get('fukusho_investment', 0)
            total_return['fukusho_return'] += return_rates.get('fukusho_return', 0)

            # 人気別成績を集計
            popularity_stats = acc.get('popularity_stats', {})
            for pop_cat in total_popularity.keys():
                if pop_cat in popularity_stats:
                    for key in ['的中', '複勝圏', '対象']:
                        total_popularity[pop_cat][key] += popularity_stats[pop_cat].get(key, 0)

            # 信頼度別成績を集計
            confidence_stats = acc.get('confidence_stats', {})
            for conf_cat in total_confidence.keys():
                if conf_cat in confidence_stats:
                    for key in ['的中', '複勝圏', '対象']:
                        total_confidence[conf_cat][key] += confidence_stats[conf_cat].get(key, 0)

            # 芝/ダート別成績を集計（%を回数に戻す）
            by_track = acc.get('by_track', {})
            for track in total_track.keys():
                if track in by_track:
                    t = by_track[track]
                    races = t.get('races', 0)
                    total_track[track]['races'] += races
                    # %から回数を計算
                    total_track[track]['top1_hit'] += int(round(t.get('top1_rate', 0) * races / 100))
                    total_track[track]['top1_in_top3'] += int(round(t.get('top3_rate', 0) * races / 100))
                    total_track[track]['top3_cover'] += int(round(t.get('cover_rate', 0) * races / 100))

            # EV推奨成績を集計
            ev_stats = acc.get('ev_stats', {})
            total_ev['ev_rec_races'] += ev_stats.get('ev_rec_races', 0)
            total_ev['ev_rec_count'] += ev_stats.get('ev_rec_count', 0)
            total_ev['ev_rec_tansho_hit'] += ev_stats.get('ev_rec_tansho_hit', 0)
            total_ev['ev_rec_fukusho_hit'] += ev_stats.get('ev_rec_fukusho_hit', 0)
            total_ev['ev_tansho_investment'] += ev_stats.get('ev_tansho_investment', 0)
            total_ev['ev_tansho_return'] += ev_stats.get('ev_tansho_return', 0)
            total_ev['ev_fukusho_investment'] += ev_stats.get('ev_fukusho_investment', 0)
            total_ev['ev_fukusho_return'] += ev_stats.get('ev_fukusho_return', 0)

            # 軸馬成績を集計
            axis_stats = acc.get('axis_stats', {})
            total_axis['axis_races'] += axis_stats.get('axis_races', 0)
            total_axis['axis_tansho_hit'] += axis_stats.get('axis_tansho_hit', 0)
            total_axis['axis_fukusho_hit'] += axis_stats.get('axis_fukusho_hit', 0)
            total_axis['axis_fukusho_investment'] += axis_stats.get('axis_fukusho_investment', 0)
            total_axis['axis_fukusho_return'] += axis_stats.get('axis_fukusho_return', 0)

            # 日付別データを保存（インタラクション用）
            daily_data[str(target_date)] = {
                'analyzed_races': acc['analyzed_races'],
                'ranking_stats': acc.get('ranking_stats', {}),
                'return_rates': acc.get('return_rates', {}),
                'popularity_stats': acc.get('popularity_stats', {}),
                'confidence_stats': acc.get('confidence_stats', {}),
                'by_track': acc.get('by_track', {}),
                'ev_stats': acc.get('ev_stats', {}),
                'axis_stats': acc.get('axis_stats', {}),
            }

            print(f"\n{acc['date']}: {acc['analyzed_races']}R分析 → DB保存済")
            # EV推奨と軸馬を表示
            ev = acc.get('ev_stats', {})
            ax = acc.get('axis_stats', {})
            if ev.get('ev_rec_count', 0) > 0:
                print(f"  EV推奨: {ev['ev_rec_count']}頭 → 単勝{ev.get('ev_rec_tansho_hit', 0)}的中 複勝{ev.get('ev_rec_fukusho_hit', 0)}的中 (回収率{ev.get('ev_tansho_roi', 0):.0f}%)")
            else:
                print(f"  EV推奨: なし")
            print(f"  軸馬: 複勝{ax.get('axis_fukusho_hit', 0)}/{ax.get('axis_races', 0)}的中 ({ax.get('axis_fukusho_rate', 0):.0f}%)")
        else:
            print(f"\n{target_date}: {analysis['status']}")

    # 週末合計を通知
    if total_stats['analyzed_races'] > 0:
        n = total_stats['analyzed_races']

        # ランキング別成績を整形
        weekend_ranking = {}
        for rank in [1, 2, 3]:
            total = total_ranking_stats[rank]['出走']
            if total > 0:
                weekend_ranking[rank] = {
                    '出走': total,
                    '1着': total_ranking_stats[rank]['1着'],
                    '2着': total_ranking_stats[rank]['2着'],
                    '3着': total_ranking_stats[rank]['3着'],
                    '複勝率': (total_ranking_stats[rank]['1着'] + total_ranking_stats[rank]['2着'] + total_ranking_stats[rank]['3着']) / total * 100,
                }

        # 回収率を計算
        weekend_return = {}
        if total_return['tansho_investment'] > 0:
            weekend_return['tansho_roi'] = total_return['tansho_return'] / total_return['tansho_investment'] * 100
            weekend_return['tansho_investment'] = total_return['tansho_investment']
            weekend_return['tansho_return'] = total_return['tansho_return']
        if total_return['fukusho_investment'] > 0:
            weekend_return['fukusho_roi'] = total_return['fukusho_return'] / total_return['fukusho_investment'] * 100
            weekend_return['fukusho_investment'] = total_return['fukusho_investment']
            weekend_return['fukusho_return'] = total_return['fukusho_return']

        # 人気別成績を整形
        weekend_popularity = {}
        for pop_cat, data in total_popularity.items():
            total = data['対象']
            if total > 0:
                weekend_popularity[pop_cat] = {
                    '対象': total,
                    '的中': data['的中'],
                    '複勝圏': data['複勝圏'],
                    '的中率': data['的中'] / total * 100,
                    '複勝率': data['複勝圏'] / total * 100,
                }

        # 信頼度別成績を整形
        weekend_confidence = {}
        for conf_cat, data in total_confidence.items():
            total = data['対象']
            if total > 0:
                weekend_confidence[conf_cat] = {
                    '対象': total,
                    '的中': data['的中'],
                    '複勝圏': data['複勝圏'],
                    '的中率': data['的中'] / total * 100,
                    '複勝率': data['複勝圏'] / total * 100,
                }

        # 芝/ダート別成績を整形
        weekend_track = {}
        for track, data in total_track.items():
            races = data['races']
            if races > 0:
                weekend_track[track] = {
                    'races': races,
                    'top1_rate': data['top1_hit'] / races * 100,
                    'top3_rate': data['top1_in_top3'] / races * 100,
                    'cover_rate': data['top3_cover'] / races * 100,
                }

        # EV推奨成績を整形
        weekend_ev = {}
        ev_count = total_ev['ev_rec_count']
        ev_tansho_inv = total_ev['ev_tansho_investment']
        ev_fukusho_inv = total_ev['ev_fukusho_investment']
        if ev_count > 0:
            weekend_ev = {
                'ev_rec_races': total_ev['ev_rec_races'],
                'ev_rec_count': ev_count,
                'ev_rec_tansho_hit': total_ev['ev_rec_tansho_hit'],
                'ev_rec_fukusho_hit': total_ev['ev_rec_fukusho_hit'],
                'ev_tansho_rate': total_ev['ev_rec_tansho_hit'] / ev_count * 100,
                'ev_fukusho_rate': total_ev['ev_rec_fukusho_hit'] / ev_count * 100,
                'ev_tansho_roi': (total_ev['ev_tansho_return'] / ev_tansho_inv * 100) if ev_tansho_inv > 0 else 0,
                'ev_fukusho_roi': (total_ev['ev_fukusho_return'] / ev_fukusho_inv * 100) if ev_fukusho_inv > 0 else 0,
                'ev_tansho_investment': ev_tansho_inv,
                'ev_tansho_return': total_ev['ev_tansho_return'],
                'ev_fukusho_investment': ev_fukusho_inv,
                'ev_fukusho_return': total_ev['ev_fukusho_return'],
            }

        # 軸馬成績を整形
        weekend_axis = {}
        axis_races = total_axis['axis_races']
        axis_fukusho_inv = total_axis['axis_fukusho_investment']
        if axis_races > 0:
            weekend_axis = {
                'axis_races': axis_races,
                'axis_tansho_hit': total_axis['axis_tansho_hit'],
                'axis_fukusho_hit': total_axis['axis_fukusho_hit'],
                'axis_tansho_rate': total_axis['axis_tansho_hit'] / axis_races * 100,
                'axis_fukusho_rate': total_axis['axis_fukusho_hit'] / axis_races * 100,
                'axis_fukusho_roi': (total_axis['axis_fukusho_return'] / axis_fukusho_inv * 100) if axis_fukusho_inv > 0 else 0,
                'axis_fukusho_investment': axis_fukusho_inv,
                'axis_fukusho_return': total_axis['axis_fukusho_return'],
            }

        # 累積トラッキング更新
        collector.update_accuracy_tracking(total_stats)

        # 累積統計を取得
        cumulative = collector.get_cumulative_stats()

        print(f"\n=== 週末合計 ===")
        print(f"分析レース数: {n}R")
        print("\n【単複推奨成績】(EV >= 1.5)")
        if weekend_ev:
            print(f"  推奨馬: {weekend_ev['ev_rec_count']}頭")
            print(f"  単勝: {weekend_ev['ev_rec_tansho_hit']}的中 ({weekend_ev['ev_tansho_rate']:.1f}%) 回収率{weekend_ev['ev_tansho_roi']:.0f}%")
            print(f"  複勝: {weekend_ev['ev_rec_fukusho_hit']}的中 ({weekend_ev['ev_fukusho_rate']:.1f}%) 回収率{weekend_ev['ev_fukusho_roi']:.0f}%")
        else:
            print("  EV推奨なし")
        print("\n【軸馬成績】(複勝確率1位)")
        if weekend_axis:
            print(f"  対象: {weekend_axis['axis_races']}R")
            print(f"  複勝: {weekend_axis['axis_fukusho_hit']}的中 ({weekend_axis['axis_fukusho_rate']:.1f}%) 回収率{weekend_axis['axis_fukusho_roi']:.0f}%")

        # Discord通知（週末合計 + 詳細分析 + 日付選択メニュー）
        collector.send_weekend_notification(
            first_date, last_date, total_stats,
            weekend_ranking, weekend_return,
            weekend_popularity, weekend_confidence, weekend_track,
            daily_data, cumulative,
            ev_stats=weekend_ev, axis_stats=weekend_axis
        )

        # SHAP分析を実行（オプション）
        try:
            from src.scheduler.shap_analyzer import ShapAnalyzer, SHAP_AVAILABLE
            if SHAP_AVAILABLE:
                print("\n=== SHAP特徴量分析 ===")
                shap_analyzer = ShapAnalyzer()
                shap_analysis = shap_analyzer.analyze_dates(weekend_dates)
                if shap_analysis.get('status') == 'success':
                    # レポート生成・通知・DB保存
                    report = shap_analyzer.generate_report(shap_analysis)
                    print(report)
                    shap_analyzer.send_discord_notification(report)
                    shap_analyzer.save_analysis_to_db(shap_analysis)

                    # 特徴量調整係数を計算・保存
                    print("\n=== 特徴量調整係数 ===")
                    adjustments = shap_analyzer.calculate_feature_adjustments(shap_analysis)
                    adjusted_count = sum(1 for v in adjustments.values() if v != 1.0)
                    print(f"調整対象: {adjusted_count}特徴量")
                    if adjusted_count > 0:
                        # 調整された特徴量を表示
                        for fname, adj in sorted(adjustments.items(), key=lambda x: x[1]):
                            if adj != 1.0:
                                direction = "↓抑制" if adj < 1.0 else "↑強化"
                                print(f"  {fname}: {adj:.2f} ({direction})")
                        shap_analyzer.save_adjustments_to_db(adjustments)
                else:
                    print("SHAP分析データがありません")
            else:
                logger.info("SHAPライブラリが利用できないため分析をスキップ")
        except Exception as e:
            logger.warning(f"SHAP分析エラー（スキップ）: {e}")


def collect_yesterday_results():
    """昨日のレース結果を収集"""
    collector = ResultCollector()
    yesterday = date.today() - timedelta(days=1)

    analysis = collector.collect_and_analyze(yesterday)

    if analysis['status'] == 'success':
        collector.save_analysis_to_db(analysis)
        collector.send_discord_notification(analysis)
        acc = analysis['accuracy']
        print(f"\n=== {acc['date']} 予想精度 ===")
        print(f"分析レース数: {acc['analyzed_races']}")
        print(f"単勝的中率: {acc['accuracy']['tansho_hit_rate']:.1f}%")
        print(f"複勝的中率: {acc['accuracy']['fukusho_hit_rate']:.1f}%")
        print(f"馬連的中率: {acc['accuracy']['umaren_hit_rate']:.1f}%")
        print(f"三連複的中率: {acc['accuracy']['sanrenpuku_hit_rate']:.1f}%")
    else:
        print(f"結果収集失敗: {analysis['status']}")


def main():
    """メイン実行"""
    import argparse

    parser = argparse.ArgumentParser(description="結果収集")
    parser.add_argument("--date", "-d", help="対象日 (YYYY-MM-DD)")
    parser.add_argument("--today", "-t", action="store_true", help="当日の結果を収集")
    parser.add_argument("--yesterday", "-y", action="store_true", help="昨日の結果を収集")
    parser.add_argument("--weekend", "-w", action="store_true", help="先週末（土日）の結果を収集")

    args = parser.parse_args()

    # 週末モード（デフォルト）
    if args.weekend or (not args.date and not args.today and not args.yesterday):
        collect_weekend_results()
        return

    collector = ResultCollector()

    if args.date:
        target_date = datetime.strptime(args.date, "%Y-%m-%d").date()
    elif args.today:
        target_date = date.today()
    elif args.yesterday:
        target_date = date.today() - timedelta(days=1)
    else:
        target_date = date.today()

    analysis = collector.collect_and_analyze(target_date)

    if analysis['status'] == 'success':
        collector.save_analysis_to_db(analysis)
        collector.send_discord_notification(analysis)
        acc = analysis['accuracy']
        print(f"\n=== {acc['date']} 予想精度 ===")
        print(f"分析レース数: {acc['analyzed_races']}")
        print(f"単勝的中率: {acc['accuracy']['tansho_hit_rate']:.1f}%")
        print(f"複勝的中率: {acc['accuracy']['fukusho_hit_rate']:.1f}%")
        print(f"馬連的中率: {acc['accuracy']['umaren_hit_rate']:.1f}%")
        print(f"三連複的中率: {acc['accuracy']['sanrenpuku_hit_rate']:.1f}%")
    else:
        print(f"結果収集: {analysis['status']}")


if __name__ == "__main__":
    main()
