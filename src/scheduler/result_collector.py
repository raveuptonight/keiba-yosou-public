"""
Result Collector Module

Collects race results and compares with predictions.
- 21:00 daily: Collect day's race results
- Load predictions from DB, compare with actual results
"""

import logging
from datetime import datetime, date, timedelta
from typing import Dict, Optional

from src.scheduler.result.db_operations import (
    get_race_results,
    get_payouts,
    load_predictions_from_db,
    save_analysis_to_db,
    update_accuracy_tracking,
    get_cumulative_stats,
    get_recent_race_dates,
    KEIBAJO_NAMES,
)
from src.scheduler.result.analyzer import (
    compare_results,
    calculate_accuracy,
)
from src.scheduler.result.notifier import (
    send_discord_notification,
    send_weekend_notification,
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ResultCollector:
    """Race result collection class."""

    def __init__(self):
        self.keibajo_names = KEIBAJO_NAMES

    def get_race_results(self, target_date: date):
        """Get race results for specified date."""
        return get_race_results(target_date)

    def get_payouts(self, target_date: date):
        """Get payout data for specified date."""
        return get_payouts(target_date)

    def load_predictions_from_db(self, target_date: date):
        """Load prediction results from DB."""
        return load_predictions_from_db(target_date)

    def compare_results(self, predictions: Dict, results, payouts=None):
        """Compare predictions with results (EV recommendation and axis horse format)."""
        return compare_results(predictions, results, payouts)

    def calculate_accuracy(self, comparison: Dict):
        """Calculate accuracy metrics (detailed version)."""
        return calculate_accuracy(comparison)

    def collect_and_analyze(self, target_date: date) -> Dict:
        """Execute result collection and analysis."""
        logger.info(f"Starting result collection: {target_date}")

        # Load predictions from DB
        predictions = load_predictions_from_db(target_date)
        if not predictions:
            return {'status': 'no_predictions', 'date': str(target_date)}

        # Get results
        results = get_race_results(target_date)
        if not results:
            logger.info(f"No result data for {target_date}")
            return {'status': 'no_results', 'date': str(target_date)}

        logger.info(f"Retrieved results for {len(results)} races")

        # Get payout data
        payouts = get_payouts(target_date)

        # Compare (including payout data)
        comparison = compare_results(predictions, results, payouts)

        # Calculate accuracy
        accuracy = calculate_accuracy(comparison)

        return {
            'status': 'success',
            'comparison': comparison,
            'accuracy': accuracy
        }

    def save_analysis_to_db(self, analysis: Dict) -> bool:
        """Save analysis results to DB."""
        return save_analysis_to_db(analysis)

    def update_accuracy_tracking(self, stats: Dict) -> bool:
        """Update cumulative accuracy tracking."""
        return update_accuracy_tracking(stats)

    def get_cumulative_stats(self) -> Optional[Dict]:
        """Get cumulative statistics."""
        return get_cumulative_stats()

    def send_discord_notification(self, analysis: Dict):
        """Send Discord notification (EV recommendation and axis horse format)."""
        send_discord_notification(analysis)

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
        """Send weekend total Discord notification (EV recommendation and axis horse format)."""
        send_weekend_notification(
            saturday, sunday, stats,
            ranking_stats, return_rates,
            popularity_stats, confidence_stats, by_track,
            daily_data, cumulative,
            ev_stats, axis_stats
        )


def collect_today_results():
    """Collect today's race results."""
    collector = ResultCollector()
    today = date.today()

    analysis = collector.collect_and_analyze(today)

    if analysis['status'] == 'success':
        collector.save_analysis_to_db(analysis)
        collector.send_discord_notification(analysis)
        acc = analysis['accuracy']
        print(f"\n=== {acc['date']} Prediction Accuracy ===")
        print(f"Analyzed races: {acc['analyzed_races']}")
        print(f"Win hit rate: {acc['accuracy']['tansho_hit_rate']:.1f}%")
        print(f"Place hit rate: {acc['accuracy']['fukusho_hit_rate']:.1f}%")
        print(f"Exacta hit rate: {acc['accuracy']['umaren_hit_rate']:.1f}%")
        print(f"Trio hit rate: {acc['accuracy']['sanrenpuku_hit_rate']:.1f}%")
    else:
        print(f"Result collection failed: {analysis['status']}")


def collect_weekend_results():
    """Collect last weekend's race results and save to DB (auto-detect race dates)."""
    collector = ResultCollector()

    # Get recent dates with prediction data (up to 7 days back)
    weekend_dates = get_recent_race_dates(days_back=7)

    if not weekend_dates:
        print("No prediction data in the last 7 days")
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
    # Ranking stats aggregation
    total_ranking_stats = {
        1: {'1着': 0, '2着': 0, '3着': 0, '4着以下': 0, '出走': 0},
        2: {'1着': 0, '2着': 0, '3着': 0, '4着以下': 0, '出走': 0},
        3: {'1着': 0, '2着': 0, '3着': 0, '4着以下': 0, '出走': 0},
    }
    # Return rate aggregation
    total_return = {
        'tansho_investment': 0,
        'tansho_return': 0,
        'fukusho_investment': 0,
        'fukusho_return': 0,
    }
    # Popularity stats aggregation
    total_popularity = {
        '1-3番人気': {'的中': 0, '複勝圏': 0, '対象': 0},
        '4-6番人気': {'的中': 0, '複勝圏': 0, '対象': 0},
        '7-9番人気': {'的中': 0, '複勝圏': 0, '対象': 0},
        '10番人気以下': {'的中': 0, '複勝圏': 0, '対象': 0},
    }
    # Confidence stats aggregation
    total_confidence = {
        '高(80%以上)': {'的中': 0, '複勝圏': 0, '対象': 0},
        '中(60-80%)': {'的中': 0, '複勝圏': 0, '対象': 0},
        '低(60%未満)': {'的中': 0, '複勝圏': 0, '対象': 0},
    }
    # Turf/Dirt aggregation
    total_track = {
        '芝': {'races': 0, 'top1_hit': 0, 'top1_in_top3': 0, 'top3_cover': 0},
        'ダ': {'races': 0, 'top1_hit': 0, 'top1_in_top3': 0, 'top3_cover': 0},
    }
    # EV recommendation stats aggregation
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
    # Axis horse stats aggregation
    total_axis = {
        'axis_races': 0,
        'axis_tansho_hit': 0,
        'axis_fukusho_hit': 0,
        'axis_fukusho_investment': 0,
        'axis_fukusho_return': 0,
    }

    # Daily data (for interaction)
    daily_data = {}

    print(f"\n=== Weekend Race Result Collection ({first_date} - {last_date}) ===")
    print(f"Target dates: {', '.join(str(d) for d in weekend_dates)}")

    for target_date in weekend_dates:
        analysis = collector.collect_and_analyze(target_date)

        if analysis['status'] == 'success':
            # Save to DB
            collector.save_analysis_to_db(analysis)

            acc = analysis['accuracy']
            total_stats['total_races'] += acc['total_races']
            total_stats['analyzed_races'] += acc['analyzed_races']
            total_stats['tansho_hit'] += acc['raw_stats']['tansho_hit']
            total_stats['fukusho_hit'] += acc['raw_stats']['fukusho_hit']
            total_stats['umaren_hit'] += acc['raw_stats']['umaren_hit']
            total_stats['sanrenpuku_hit'] += acc['raw_stats']['sanrenpuku_hit']

            # Aggregate ranking stats
            ranking_stats = acc.get('ranking_stats', {})
            for rank in [1, 2, 3]:
                if rank in ranking_stats:
                    for key in ['1着', '2着', '3着', '4着以下', '出走']:
                        total_ranking_stats[rank][key] += ranking_stats[rank].get(key, 0)

            # Aggregate return rates
            return_rates = acc.get('return_rates', {})
            total_return['tansho_investment'] += return_rates.get('tansho_investment', 0)
            total_return['tansho_return'] += return_rates.get('tansho_return', 0)
            total_return['fukusho_investment'] += return_rates.get('fukusho_investment', 0)
            total_return['fukusho_return'] += return_rates.get('fukusho_return', 0)

            # Aggregate popularity stats
            popularity_stats = acc.get('popularity_stats', {})
            for pop_cat in total_popularity.keys():
                if pop_cat in popularity_stats:
                    for key in ['的中', '複勝圏', '対象']:
                        total_popularity[pop_cat][key] += popularity_stats[pop_cat].get(key, 0)

            # Aggregate confidence stats
            confidence_stats = acc.get('confidence_stats', {})
            for conf_cat in total_confidence.keys():
                if conf_cat in confidence_stats:
                    for key in ['的中', '複勝圏', '対象']:
                        total_confidence[conf_cat][key] += confidence_stats[conf_cat].get(key, 0)

            # Aggregate turf/dirt stats (convert % back to counts)
            by_track = acc.get('by_track', {})
            for track in total_track.keys():
                if track in by_track:
                    t = by_track[track]
                    races = t.get('races', 0)
                    total_track[track]['races'] += races
                    # Calculate counts from %
                    total_track[track]['top1_hit'] += int(round(t.get('top1_rate', 0) * races / 100))
                    total_track[track]['top1_in_top3'] += int(round(t.get('top3_rate', 0) * races / 100))
                    total_track[track]['top3_cover'] += int(round(t.get('cover_rate', 0) * races / 100))

            # Aggregate EV recommendation stats
            ev_stats = acc.get('ev_stats', {})
            total_ev['ev_rec_races'] += ev_stats.get('ev_rec_races', 0)
            total_ev['ev_rec_count'] += ev_stats.get('ev_rec_count', 0)
            total_ev['ev_rec_tansho_hit'] += ev_stats.get('ev_rec_tansho_hit', 0)
            total_ev['ev_rec_fukusho_hit'] += ev_stats.get('ev_rec_fukusho_hit', 0)
            total_ev['ev_tansho_investment'] += ev_stats.get('ev_tansho_investment', 0)
            total_ev['ev_tansho_return'] += ev_stats.get('ev_tansho_return', 0)
            total_ev['ev_fukusho_investment'] += ev_stats.get('ev_fukusho_investment', 0)
            total_ev['ev_fukusho_return'] += ev_stats.get('ev_fukusho_return', 0)

            # Aggregate axis horse stats
            axis_stats = acc.get('axis_stats', {})
            total_axis['axis_races'] += axis_stats.get('axis_races', 0)
            total_axis['axis_tansho_hit'] += axis_stats.get('axis_tansho_hit', 0)
            total_axis['axis_fukusho_hit'] += axis_stats.get('axis_fukusho_hit', 0)
            total_axis['axis_fukusho_investment'] += axis_stats.get('axis_fukusho_investment', 0)
            total_axis['axis_fukusho_return'] += axis_stats.get('axis_fukusho_return', 0)

            # Save daily data (for interaction)
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

            print(f"\n{acc['date']}: {acc['analyzed_races']}R analyzed → Saved to DB")
            # Display EV recommendation and axis horse
            ev = acc.get('ev_stats', {})
            ax = acc.get('axis_stats', {})
            if ev.get('ev_rec_count', 0) > 0:
                print(f"  EV rec: {ev['ev_rec_count']} horses → Win {ev.get('ev_rec_tansho_hit', 0)} hits, Place {ev.get('ev_rec_fukusho_hit', 0)} hits (ROI {ev.get('ev_tansho_roi', 0):.0f}%)")
            else:
                print(f"  EV rec: None")
            print(f"  Axis: Place {ax.get('axis_fukusho_hit', 0)}/{ax.get('axis_races', 0)} hits ({ax.get('axis_fukusho_rate', 0):.0f}%)")
        else:
            print(f"\n{target_date}: {analysis['status']}")

    # Send weekend total notification
    if total_stats['analyzed_races'] > 0:
        n = total_stats['analyzed_races']

        # Format ranking stats
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

        # Calculate return rates
        weekend_return = {}
        if total_return['tansho_investment'] > 0:
            weekend_return['tansho_roi'] = total_return['tansho_return'] / total_return['tansho_investment'] * 100
            weekend_return['tansho_investment'] = total_return['tansho_investment']
            weekend_return['tansho_return'] = total_return['tansho_return']
        if total_return['fukusho_investment'] > 0:
            weekend_return['fukusho_roi'] = total_return['fukusho_return'] / total_return['fukusho_investment'] * 100
            weekend_return['fukusho_investment'] = total_return['fukusho_investment']
            weekend_return['fukusho_return'] = total_return['fukusho_return']

        # Format popularity stats
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

        # Format confidence stats
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

        # Format turf/dirt stats
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

        # Format EV recommendation stats
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

        # Format axis horse stats
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

        # Update cumulative tracking
        collector.update_accuracy_tracking(total_stats)

        # Get cumulative stats
        cumulative = collector.get_cumulative_stats()

        print(f"\n=== Weekend Total ===")
        print(f"Analyzed races: {n}R")
        print("\n【Win/Place Recommendation】(EV >= 1.5)")
        if weekend_ev:
            print(f"  Horses: {weekend_ev['ev_rec_count']}")
            print(f"  Win: {weekend_ev['ev_rec_tansho_hit']} hits ({weekend_ev['ev_tansho_rate']:.1f}%) ROI {weekend_ev['ev_tansho_roi']:.0f}%")
            print(f"  Place: {weekend_ev['ev_rec_fukusho_hit']} hits ({weekend_ev['ev_fukusho_rate']:.1f}%) ROI {weekend_ev['ev_fukusho_roi']:.0f}%")
        else:
            print("  No EV recommendations")
        print("\n【Axis Horse Stats】(Highest place probability)")
        if weekend_axis:
            print(f"  Races: {weekend_axis['axis_races']}R")
            print(f"  Place: {weekend_axis['axis_fukusho_hit']} hits ({weekend_axis['axis_fukusho_rate']:.1f}%) ROI {weekend_axis['axis_fukusho_roi']:.0f}%")

        # Discord notification (weekend total + detailed analysis + date select menu)
        collector.send_weekend_notification(
            first_date, last_date, total_stats,
            weekend_ranking, weekend_return,
            weekend_popularity, weekend_confidence, weekend_track,
            daily_data, cumulative,
            ev_stats=weekend_ev, axis_stats=weekend_axis
        )

        # Execute SHAP analysis (optional)
        try:
            from src.scheduler.shap_analyzer import ShapAnalyzer, SHAP_AVAILABLE
            if SHAP_AVAILABLE:
                print("\n=== SHAP Feature Analysis ===")
                shap_analyzer = ShapAnalyzer()
                shap_analysis = shap_analyzer.analyze_dates(weekend_dates)
                if shap_analysis.get('status') == 'success':
                    # Generate report, notify, save to DB
                    report = shap_analyzer.generate_report(shap_analysis)
                    print(report)
                    shap_analyzer.send_discord_notification(report)
                    shap_analyzer.save_analysis_to_db(shap_analysis)

                    # Calculate and save feature adjustment coefficients
                    print("\n=== Feature Adjustment Coefficients ===")
                    adjustments = shap_analyzer.calculate_feature_adjustments(shap_analysis)
                    adjusted_count = sum(1 for v in adjustments.values() if v != 1.0)
                    print(f"Adjusted features: {adjusted_count}")
                    if adjusted_count > 0:
                        # Display adjusted features
                        for fname, adj in sorted(adjustments.items(), key=lambda x: x[1]):
                            if adj != 1.0:
                                direction = "↓suppress" if adj < 1.0 else "↑boost"
                                print(f"  {fname}: {adj:.2f} ({direction})")
                        shap_analyzer.save_adjustments_to_db(adjustments)
                else:
                    print("No SHAP analysis data")
            else:
                logger.info("SHAP library not available, skipping analysis")
        except Exception as e:
            logger.warning(f"SHAP analysis error (skipped): {e}")


def collect_yesterday_results():
    """Collect yesterday's race results."""
    collector = ResultCollector()
    yesterday = date.today() - timedelta(days=1)

    analysis = collector.collect_and_analyze(yesterday)

    if analysis['status'] == 'success':
        collector.save_analysis_to_db(analysis)
        collector.send_discord_notification(analysis)
        acc = analysis['accuracy']
        print(f"\n=== {acc['date']} Prediction Accuracy ===")
        print(f"Analyzed races: {acc['analyzed_races']}")
        print(f"Win hit rate: {acc['accuracy']['tansho_hit_rate']:.1f}%")
        print(f"Place hit rate: {acc['accuracy']['fukusho_hit_rate']:.1f}%")
        print(f"Exacta hit rate: {acc['accuracy']['umaren_hit_rate']:.1f}%")
        print(f"Trio hit rate: {acc['accuracy']['sanrenpuku_hit_rate']:.1f}%")
    else:
        print(f"Result collection failed: {analysis['status']}")


def main():
    """Main execution."""
    import argparse

    parser = argparse.ArgumentParser(description="Result collection")
    parser.add_argument("--date", "-d", help="Target date (YYYY-MM-DD)")
    parser.add_argument("--today", "-t", action="store_true", help="Collect today's results")
    parser.add_argument("--yesterday", "-y", action="store_true", help="Collect yesterday's results")
    parser.add_argument("--weekend", "-w", action="store_true", help="Collect last weekend (Sat-Sun) results")

    args = parser.parse_args()

    # Weekend mode (default)
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
        print(f"\n=== {acc['date']} Prediction Accuracy ===")
        print(f"Analyzed races: {acc['analyzed_races']}")
        print(f"Win hit rate: {acc['accuracy']['tansho_hit_rate']:.1f}%")
        print(f"Place hit rate: {acc['accuracy']['fukusho_hit_rate']:.1f}%")
        print(f"Exacta hit rate: {acc['accuracy']['umaren_hit_rate']:.1f}%")
        print(f"Trio hit rate: {acc['accuracy']['sanrenpuku_hit_rate']:.1f}%")
    else:
        print(f"Result collection: {analysis['status']}")


if __name__ == "__main__":
    main()
