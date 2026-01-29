"""
Daily Bias Analysis Module

Calculates various biases from Saturday race results
and generates features to apply to Sunday predictions.
"""

import json
import logging
from dataclasses import asdict, dataclass
from datetime import date, datetime

from src.db.connection import get_db

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class VenueBias:
    """Venue-specific bias data."""
    venue_code: str
    venue_name: str
    race_count: int

    # Post position bias (gates 1-4 vs 5-8)
    inner_waku_win_rate: float  # Win rate for gates 1-4
    outer_waku_win_rate: float  # Win rate for gates 5-8
    waku_bias: float  # Positive if inner advantageous, negative if outer

    # Running style bias (front-runners vs closers)
    zenso_win_rate: float  # Win rate for front-runners (styles 1,2)
    koshi_win_rate: float  # Win rate for closers (styles 3,4)
    pace_bias: float  # Positive if front advantageous, negative if back

    # Track condition
    track_condition: str  # Good/Slightly Heavy/Heavy/Bad

    # Results by track type
    turf_results: int
    dirt_results: int


@dataclass
class JockeyDayPerformance:
    """Jockey's same-day performance."""
    jockey_code: str
    jockey_name: str
    rides: int
    wins: int
    top3: int
    win_rate: float
    top3_rate: float


@dataclass
class DailyBiasResult:
    """Daily bias analysis result."""
    target_date: str
    analyzed_at: str
    total_races: int
    venue_biases: dict[str, VenueBias]
    jockey_performances: dict[str, JockeyDayPerformance]

    def to_dict(self) -> dict:
        return {
            'target_date': self.target_date,
            'analyzed_at': self.analyzed_at,
            'total_races': self.total_races,
            'venue_biases': {k: asdict(v) for k, v in self.venue_biases.items()},
            'jockey_performances': {k: asdict(v) for k, v in self.jockey_performances.items()},
        }


class DailyBiasAnalyzer:
    """Daily bias analysis class."""

    VENUE_NAMES = {
        '01': 'Sapporo', '02': 'Hakodate', '03': 'Fukushima', '04': 'Niigata', '05': 'Tokyo',
        '06': 'Nakayama', '07': 'Chukyo', '08': 'Kyoto', '09': 'Hanshin', '10': 'Kokura'
    }

    TRACK_CONDITION = {
        '1': 'Good', '2': 'Slightly Heavy', '3': 'Heavy', '4': 'Bad'
    }

    def __init__(self):
        self.db = get_db()

    def analyze(self, target_date: date) -> DailyBiasResult | None:
        """Analyze bias for the specified date."""
        logger.info(f"Starting bias analysis: {target_date}")

        conn = self.db.get_connection()
        try:
            cur = conn.cursor()
            kaisai_gappi = target_date.strftime("%m%d")
            kaisai_nen = str(target_date.year)

            # Get race list
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
                logger.warning(f"No race data found: {target_date}")
                return None

            logger.info(f"Analyzing {len(races)} races")

            # Aggregate data by venue
            venue_data: dict[str, dict] = {}
            jockey_data: dict[str, dict] = {}

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

                # Get data for each horse
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
                    horse[0]
                    wakuban = horse[1]
                    chakujun = int(horse[2]) if horse[2] else 99
                    kyakushitsu = horse[3]
                    kishu_code = horse[4]
                    kishu_name = horse[5]

                    is_win = chakujun == 1
                    is_top3 = chakujun <= 3

                    # Post position bias
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

                    # Running style bias
                    try:
                        kyaku = int(kyakushitsu) if kyakushitsu else 0
                        if kyaku in (1, 2):  # Front-runner / Stalker
                            venue_data[venue_code]['zenso_total'] += 1
                            if is_win:
                                venue_data[venue_code]['zenso_wins'] += 1
                        elif kyaku in (3, 4):  # Closer / Deep closer
                            venue_data[venue_code]['koshi_total'] += 1
                            if is_win:
                                venue_data[venue_code]['koshi_wins'] += 1
                    except (ValueError, TypeError):
                        pass

                    # Jockey performance
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

            # Calculate biases
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

            # Calculate jockey performance
            jockey_performances = {}
            for code, data in jockey_data.items():
                if data['rides'] >= 1:  # At least 1 ride
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

            logger.info(f"Bias analysis complete: {len(venue_biases)} venues, {len(jockey_performances)} jockeys")
            return result

        except Exception as e:
            logger.error(f"Bias analysis error: {e}")
            raise
        finally:
            conn.close()

    def save_bias(self, bias_result: DailyBiasResult, output_path: str = None) -> bool:
        """Save bias result to database."""
        conn = self.db.get_connection()
        if not conn:
            logger.error("DB connection failed")
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
            logger.info(f"Bias result saved to DB: {bias_result.target_date}")
            return True

        except Exception as e:
            logger.error(f"Bias save error: {e}")
            if conn:
                conn.rollback()
            return False
        finally:
            conn.close()

    def load_bias(self, target_date: date) -> DailyBiasResult | None:
        """Load bias result from database."""
        conn = self.db.get_connection()
        if not conn:
            logger.error("DB connection failed")
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
            logger.error(f"Bias load error: {e}")
            return None
        finally:
            conn.close()

    def get_bias_features(self, bias_result: DailyBiasResult, venue_code: str,
                          wakuban: int, kishu_code: str) -> dict[str, float]:
        """Get bias features for prediction."""
        features = {
            'bias_waku': 0.0,
            'bias_pace': 0.0,
            'bias_jockey_win_rate': 0.0,
            'bias_jockey_top3_rate': 0.0,
        }

        # Venue bias
        if venue_code in bias_result.venue_biases:
            vb = bias_result.venue_biases[venue_code]

            # Post position bias (adjustment based on horse's gate)
            if 1 <= wakuban <= 4:
                features['bias_waku'] = vb.waku_bias  # Positive if inner advantageous
            else:
                features['bias_waku'] = -vb.waku_bias  # Negative for outer gates

            # Running style bias (front advantage)
            features['bias_pace'] = vb.pace_bias

        # Jockey bias
        if kishu_code in bias_result.jockey_performances:
            jp = bias_result.jockey_performances[kishu_code]
            features['bias_jockey_win_rate'] = jp.win_rate
            features['bias_jockey_top3_rate'] = jp.top3_rate

        return features


def print_bias_report(bias_result: DailyBiasResult):
    """Display bias report."""
    print(f"\n{'='*60}")
    print(f"[{bias_result.target_date} Bias Analysis Report]")
    print(f"Analysis time: {bias_result.analyzed_at}")
    print(f"Races analyzed: {bias_result.total_races}")
    print(f"{'='*60}")

    print("\n* Venue Bias")
    for _venue_code, vb in sorted(bias_result.venue_biases.items()):
        waku_indicator = "Inner favored" if vb.waku_bias > 0.05 else ("Outer favored" if vb.waku_bias < -0.05 else "Neutral")
        pace_indicator = "Front favored" if vb.pace_bias > 0.05 else ("Closer favored" if vb.pace_bias < -0.05 else "Neutral")

        print(f"\n  [{vb.venue_name}] {vb.race_count}R / Track:{vb.track_condition}")
        print(f"    Gate: Inner{vb.inner_waku_win_rate:.1%} vs Outer{vb.outer_waku_win_rate:.1%} -> {waku_indicator}")
        print(f"    Style: Front{vb.zenso_win_rate:.1%} vs Back{vb.koshi_win_rate:.1%} -> {pace_indicator}")

    print("\n* Jockey Performance (by wins)")
    sorted_jockeys = sorted(
        bias_result.jockey_performances.values(),
        key=lambda x: x.wins,
        reverse=True
    )[:10]

    for jp in sorted_jockeys:
        print(f"    {jp.jockey_name}: {jp.wins}W/{jp.rides}rides "
              f"(Win rate{jp.win_rate:.1%}, Top3{jp.top3_rate:.1%})")


def main():
    """Test execution."""
    import argparse

    parser = argparse.ArgumentParser(description="Daily bias analysis")
    parser.add_argument("--date", "-d", help="Target date (YYYY-MM-DD)")
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
        print(f"No data found: {target_date}")


if __name__ == "__main__":
    main()
