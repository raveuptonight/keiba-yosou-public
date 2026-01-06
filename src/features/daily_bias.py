"""
日次バイアス分析モジュール

土曜のレース結果から各種バイアスを計算し、
日曜の予想に反映するための特徴量を生成する。
"""

import logging
from datetime import date, datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
import json

from src.db.connection import get_db

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class VenueBias:
    """競馬場別バイアスデータ"""
    venue_code: str
    venue_name: str
    race_count: int

    # 枠順バイアス (1-4枠 vs 5-8枠)
    inner_waku_win_rate: float  # 1-4枠の勝率
    outer_waku_win_rate: float  # 5-8枠の勝率
    waku_bias: float  # 内枠有利なら正、外枠有利なら負

    # 脚質バイアス (逃げ先行 vs 差し追込)
    zenso_win_rate: float  # 逃げ・先行(1,2)の勝率
    koshi_win_rate: float  # 差し・追込(3,4)の勝率
    pace_bias: float  # 前有利なら正、後有利なら負

    # 馬場状態
    track_condition: str  # 良/稍重/重/不良

    # トラック種別ごとの成績
    turf_results: int
    dirt_results: int


@dataclass
class JockeyDayPerformance:
    """騎手の当日成績"""
    jockey_code: str
    jockey_name: str
    rides: int
    wins: int
    top3: int
    win_rate: float
    top3_rate: float


@dataclass
class DailyBiasResult:
    """日次バイアス分析結果"""
    target_date: str
    analyzed_at: str
    total_races: int
    venue_biases: Dict[str, VenueBias]
    jockey_performances: Dict[str, JockeyDayPerformance]

    def to_dict(self) -> Dict:
        return {
            'target_date': self.target_date,
            'analyzed_at': self.analyzed_at,
            'total_races': self.total_races,
            'venue_biases': {k: asdict(v) for k, v in self.venue_biases.items()},
            'jockey_performances': {k: asdict(v) for k, v in self.jockey_performances.items()},
        }


class DailyBiasAnalyzer:
    """日次バイアス分析クラス"""

    VENUE_NAMES = {
        '01': '札幌', '02': '函館', '03': '福島', '04': '新潟', '05': '東京',
        '06': '中山', '07': '中京', '08': '京都', '09': '阪神', '10': '小倉'
    }

    TRACK_CONDITION = {
        '1': '良', '2': '稍重', '3': '重', '4': '不良'
    }

    def __init__(self):
        self.db = get_db()

    def analyze(self, target_date: date) -> Optional[DailyBiasResult]:
        """指定日のバイアスを分析"""
        logger.info(f"バイアス分析開始: {target_date}")

        conn = self.db.get_connection()
        try:
            cur = conn.cursor()
            kaisai_gappi = target_date.strftime("%m%d")
            kaisai_nen = str(target_date.year)

            # レース一覧を取得
            cur.execute('''
                SELECT DISTINCT r.race_code, r.keibajo_code, r.race_bango,
                       r.track_code, r.shiba_babajotai_code, r.dirt_babajotai_code
                FROM race_shosai r
                WHERE r.kaisai_nen = %s
                  AND r.kaisai_gappi = %s
                  AND r.data_kubun IN ('6', '7')
                ORDER BY r.race_code
            ''', (kaisai_nen, kaisai_gappi))

            races = cur.fetchall()
            if not races:
                logger.warning(f"レースデータがありません: {target_date}")
                return None

            logger.info(f"{len(races)}レースを分析")

            # 競馬場別にデータを集計
            venue_data: Dict[str, Dict] = {}
            jockey_data: Dict[str, Dict] = {}

            for race in races:
                race_code = race[0]
                venue_code = race[1]
                track_code = race[3]
                baba_code = race[4] if track_code and track_code.startswith('1') else race[5]

                if venue_code not in venue_data:
                    venue_data[venue_code] = {
                        'race_count': 0,
                        'inner_wins': 0, 'inner_total': 0,
                        'outer_wins': 0, 'outer_total': 0,
                        'zenso_wins': 0, 'zenso_total': 0,
                        'koshi_wins': 0, 'koshi_total': 0,
                        'turf_results': 0, 'dirt_results': 0,
                        'track_condition': self.TRACK_CONDITION.get(str(baba_code), '不明'),
                    }

                venue_data[venue_code]['race_count'] += 1

                if track_code and track_code.startswith('1'):
                    venue_data[venue_code]['turf_results'] += 1
                else:
                    venue_data[venue_code]['dirt_results'] += 1

                # 各馬のデータを取得
                cur.execute('''
                    SELECT umaban, wakuban, kakutei_chakujun,
                           kyakushitsu_hantei, kishu_code, kishumei_ryakusho
                    FROM umagoto_race_joho
                    WHERE race_code = %s
                      AND data_kubun IN ('6', '7')
                      AND kakutei_chakujun IS NOT NULL
                      AND kakutei_chakujun != ''
                      AND kakutei_chakujun ~ '^[0-9]+$'
                ''', (race_code,))

                horses = cur.fetchall()

                for horse in horses:
                    umaban = horse[0]
                    wakuban = horse[1]
                    chakujun = int(horse[2]) if horse[2] else 99
                    kyakushitsu = horse[3]
                    kishu_code = horse[4]
                    kishu_name = horse[5]

                    is_win = chakujun == 1
                    is_top3 = chakujun <= 3

                    # 枠順バイアス
                    try:
                        waku = int(wakuban) if wakuban else 0
                        if 1 <= waku <= 4:
                            venue_data[venue_code]['inner_total'] += 1
                            if is_win:
                                venue_data[venue_code]['inner_wins'] += 1
                        elif 5 <= waku <= 8:
                            venue_data[venue_code]['outer_total'] += 1
                            if is_win:
                                venue_data[venue_code]['outer_wins'] += 1
                    except (ValueError, TypeError):
                        pass

                    # 脚質バイアス
                    try:
                        kyaku = int(kyakushitsu) if kyakushitsu else 0
                        if kyaku in (1, 2):  # 逃げ・先行
                            venue_data[venue_code]['zenso_total'] += 1
                            if is_win:
                                venue_data[venue_code]['zenso_wins'] += 1
                        elif kyaku in (3, 4):  # 差し・追込
                            venue_data[venue_code]['koshi_total'] += 1
                            if is_win:
                                venue_data[venue_code]['koshi_wins'] += 1
                    except (ValueError, TypeError):
                        pass

                    # 騎手成績
                    if kishu_code:
                        if kishu_code not in jockey_data:
                            jockey_data[kishu_code] = {
                                'name': kishu_name or kishu_code,
                                'rides': 0, 'wins': 0, 'top3': 0
                            }
                        jockey_data[kishu_code]['rides'] += 1
                        if is_win:
                            jockey_data[kishu_code]['wins'] += 1
                        if is_top3:
                            jockey_data[kishu_code]['top3'] += 1

            cur.close()

            # バイアス計算
            venue_biases = {}
            for venue_code, data in venue_data.items():
                inner_rate = data['inner_wins'] / data['inner_total'] if data['inner_total'] > 0 else 0
                outer_rate = data['outer_wins'] / data['outer_total'] if data['outer_total'] > 0 else 0
                zenso_rate = data['zenso_wins'] / data['zenso_total'] if data['zenso_total'] > 0 else 0
                koshi_rate = data['koshi_wins'] / data['koshi_total'] if data['koshi_total'] > 0 else 0

                venue_biases[venue_code] = VenueBias(
                    venue_code=venue_code,
                    venue_name=self.VENUE_NAMES.get(venue_code, venue_code),
                    race_count=data['race_count'],
                    inner_waku_win_rate=inner_rate,
                    outer_waku_win_rate=outer_rate,
                    waku_bias=inner_rate - outer_rate,
                    zenso_win_rate=zenso_rate,
                    koshi_win_rate=koshi_rate,
                    pace_bias=zenso_rate - koshi_rate,
                    track_condition=data['track_condition'],
                    turf_results=data['turf_results'],
                    dirt_results=data['dirt_results'],
                )

            # 騎手成績計算
            jockey_performances = {}
            for code, data in jockey_data.items():
                if data['rides'] >= 1:  # 1騎乗以上
                    jockey_performances[code] = JockeyDayPerformance(
                        jockey_code=code,
                        jockey_name=data['name'],
                        rides=data['rides'],
                        wins=data['wins'],
                        top3=data['top3'],
                        win_rate=data['wins'] / data['rides'] if data['rides'] > 0 else 0,
                        top3_rate=data['top3'] / data['rides'] if data['rides'] > 0 else 0,
                    )

            result = DailyBiasResult(
                target_date=str(target_date),
                analyzed_at=datetime.now().isoformat(),
                total_races=len(races),
                venue_biases=venue_biases,
                jockey_performances=jockey_performances,
            )

            logger.info(f"バイアス分析完了: {len(venue_biases)}競馬場, {len(jockey_performances)}騎手")
            return result

        except Exception as e:
            logger.error(f"バイアス分析エラー: {e}")
            raise
        finally:
            conn.close()

    def save_bias(self, bias_result: DailyBiasResult, output_path: str = None) -> bool:
        """バイアス結果をDBに保存"""
        conn = self.db.get_connection()
        if not conn:
            logger.error("DB接続失敗")
            return False

        try:
            cur = conn.cursor()
            data = bias_result.to_dict()

            # UPSERT
            cur.execute('''
                INSERT INTO daily_bias (
                    target_date, analyzed_at, total_races,
                    venue_biases, jockey_performances
                ) VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (target_date) DO UPDATE SET
                    analyzed_at = EXCLUDED.analyzed_at,
                    total_races = EXCLUDED.total_races,
                    venue_biases = EXCLUDED.venue_biases,
                    jockey_performances = EXCLUDED.jockey_performances
            ''', (
                bias_result.target_date,
                bias_result.analyzed_at,
                bias_result.total_races,
                json.dumps(data['venue_biases'], ensure_ascii=False),
                json.dumps(data['jockey_performances'], ensure_ascii=False)
            ))

            conn.commit()
            logger.info(f"バイアス結果DB保存: {bias_result.target_date}")
            return True

        except Exception as e:
            logger.error(f"バイアス保存エラー: {e}")
            if conn:
                conn.rollback()
            return False
        finally:
            conn.close()

    def load_bias(self, target_date: date) -> Optional[DailyBiasResult]:
        """DBからバイアス結果を読み込み"""
        conn = self.db.get_connection()
        if not conn:
            logger.error("DB接続失敗")
            return None

        try:
            cur = conn.cursor()
            date_str = target_date.strftime("%Y-%m-%d")

            cur.execute('''
                SELECT target_date, analyzed_at, total_races,
                       venue_biases, jockey_performances
                FROM daily_bias
                WHERE target_date = %s
            ''', (date_str,))

            row = cur.fetchone()
            if not row:
                return None

            venue_biases_data = row[3] if isinstance(row[3], dict) else json.loads(row[3]) if row[3] else {}
            jockey_data = row[4] if isinstance(row[4], dict) else json.loads(row[4]) if row[4] else {}

            venue_biases = {
                k: VenueBias(**v) for k, v in venue_biases_data.items()
            }
            jockey_performances = {
                k: JockeyDayPerformance(**v) for k, v in jockey_data.items()
            }

            return DailyBiasResult(
                target_date=str(row[0]),
                analyzed_at=str(row[1]),
                total_races=row[2],
                venue_biases=venue_biases,
                jockey_performances=jockey_performances,
            )

        except Exception as e:
            logger.error(f"バイアス読み込みエラー: {e}")
            return None
        finally:
            conn.close()

    def get_bias_features(self, bias_result: DailyBiasResult, venue_code: str,
                          wakuban: int, kishu_code: str) -> Dict[str, float]:
        """予想用のバイアス特徴量を取得"""
        features = {
            'bias_waku': 0.0,
            'bias_pace': 0.0,
            'bias_jockey_win_rate': 0.0,
            'bias_jockey_top3_rate': 0.0,
        }

        # 競馬場バイアス
        if venue_code in bias_result.venue_biases:
            vb = bias_result.venue_biases[venue_code]

            # 枠順バイアス（その馬の枠に応じた補正値）
            if 1 <= wakuban <= 4:
                features['bias_waku'] = vb.waku_bias  # 内枠有利なら正
            else:
                features['bias_waku'] = -vb.waku_bias  # 外枠なら逆

            # 脚質バイアス（前有利度）
            features['bias_pace'] = vb.pace_bias

        # 騎手バイアス
        if kishu_code in bias_result.jockey_performances:
            jp = bias_result.jockey_performances[kishu_code]
            features['bias_jockey_win_rate'] = jp.win_rate
            features['bias_jockey_top3_rate'] = jp.top3_rate

        return features


def print_bias_report(bias_result: DailyBiasResult):
    """バイアスレポートを表示"""
    print(f"\n{'='*60}")
    print(f"【{bias_result.target_date} バイアス分析レポート】")
    print(f"分析時刻: {bias_result.analyzed_at}")
    print(f"分析レース数: {bias_result.total_races}")
    print(f"{'='*60}")

    print("\n■ 競馬場別バイアス")
    for venue_code, vb in sorted(bias_result.venue_biases.items()):
        waku_indicator = "内枠有利" if vb.waku_bias > 0.05 else ("外枠有利" if vb.waku_bias < -0.05 else "中立")
        pace_indicator = "前有利" if vb.pace_bias > 0.05 else ("後有利" if vb.pace_bias < -0.05 else "中立")

        print(f"\n  【{vb.venue_name}】 {vb.race_count}R / 馬場:{vb.track_condition}")
        print(f"    枠順: 内枠{vb.inner_waku_win_rate:.1%} vs 外枠{vb.outer_waku_win_rate:.1%} → {waku_indicator}")
        print(f"    脚質: 前{vb.zenso_win_rate:.1%} vs 後{vb.koshi_win_rate:.1%} → {pace_indicator}")

    print("\n■ 騎手成績 (勝利数順)")
    sorted_jockeys = sorted(
        bias_result.jockey_performances.values(),
        key=lambda x: x.wins,
        reverse=True
    )[:10]

    for jp in sorted_jockeys:
        print(f"    {jp.jockey_name}: {jp.wins}勝/{jp.rides}騎乗 "
              f"(勝率{jp.win_rate:.1%}, 3着内{jp.top3_rate:.1%})")


def main():
    """テスト実行"""
    import argparse

    parser = argparse.ArgumentParser(description="日次バイアス分析")
    parser.add_argument("--date", "-d", help="対象日 (YYYY-MM-DD)")
    args = parser.parse_args()

    if args.date:
        target_date = datetime.strptime(args.date, "%Y-%m-%d").date()
    else:
        target_date = date.today()

    analyzer = DailyBiasAnalyzer()
    result = analyzer.analyze(target_date)

    if result:
        print_bias_report(result)
        analyzer.save_bias(result)
    else:
        print(f"データがありません: {target_date}")


if __name__ == "__main__":
    main()
