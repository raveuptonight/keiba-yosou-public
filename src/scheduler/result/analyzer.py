"""
Result Analyzer Module

Functions for comparing predictions with actual race results
and calculating accuracy metrics.
"""

import logging

logger = logging.getLogger(__name__)


def compare_results(predictions: dict, results: list[dict], payouts: dict = None) -> dict:
    """
    Compare predictions with actual results (EV recommendation and axis horse format).

    Args:
        predictions: Prediction data dictionary
        results: List of race results
        payouts: Optional payout data

    Returns:
        Comparison result dictionary
    """
    comparison = {
        "date": predictions["date"],
        "total_races": 0,
        "analyzed_races": 0,
        "stats": {
            "top1_hit": 0,  # Top 1 prediction wins
            "top1_in_top3": 0,  # Top 1 prediction finishes in top 3
            "top3_cover": 0,  # Winner is in top 3 predictions
            "top3_hit": 0,  # TOP3 prediction matches 1-2-3
            "tansho_hit": 0,  # Win bet hit
            "fukusho_hit": 0,  # Place bet hit
            "umaren_hit": 0,  # Exacta hit
            "sanrenpuku_hit": 0,  # Trio hit
            "mrr_sum": 0.0,  # MRR calculation
        },
        # EV recommendation stats (EV >= 1.5 horses)
        "ev_stats": {
            "ev_rec_races": 0,  # Races with EV recommendations
            "ev_rec_count": 0,  # Total EV recommended horses
            "ev_rec_tansho_hit": 0,  # Win hits
            "ev_rec_fukusho_hit": 0,  # Place hits
            "ev_tansho_investment": 0,  # Win investment
            "ev_tansho_return": 0,  # Win return
            "ev_fukusho_investment": 0,  # Place investment
            "ev_fukusho_return": 0,  # Place return
        },
        # Axis horse stats (horse with highest place probability)
        "axis_stats": {
            "axis_races": 0,  # Axis horse races
            "axis_tansho_hit": 0,  # Win hits
            "axis_fukusho_hit": 0,  # Place hits (top 3)
            "axis_fukusho_investment": 0,  # Place investment
            "axis_fukusho_return": 0,  # Place return
        },
        # Ranking stats (position distribution for ranks 1-5)
        "ranking_stats": {
            1: {"1着": 0, "2着": 0, "3着": 0, "4着以下": 0, "出走": 0},
            2: {"1着": 0, "2着": 0, "3着": 0, "4着以下": 0, "出走": 0},
            3: {"1着": 0, "2着": 0, "3着": 0, "4着以下": 0, "出走": 0},
            4: {"1着": 0, "2着": 0, "3着": 0, "4着以下": 0, "出走": 0},
            5: {"1着": 0, "2着": 0, "3着": 0, "4着以下": 0, "出走": 0},
        },
        # Return rate calculation (100 yen each on top 1 prediction)
        "return_stats": {
            "tansho_investment": 0,  # Win investment
            "tansho_return": 0,  # Win return
            "fukusho_investment": 0,  # Place investment
            "fukusho_return": 0,  # Place return
        },
        # Popularity-based stats (popularity of top 1 prediction)
        "popularity_stats": {
            "1-3番人気": {"的中": 0, "複勝圏": 0, "対象": 0},
            "4-6番人気": {"的中": 0, "複勝圏": 0, "対象": 0},
            "7-9番人気": {"的中": 0, "複勝圏": 0, "対象": 0},
            "10番人気以下": {"的中": 0, "複勝圏": 0, "対象": 0},
        },
        # Confidence-based stats (confidence score of prediction)
        "confidence_stats": {
            "高(80%以上)": {"的中": 0, "複勝圏": 0, "対象": 0},
            "中(60-80%)": {"的中": 0, "複勝圏": 0, "対象": 0},
            "低(60%未満)": {"的中": 0, "複勝圏": 0, "対象": 0},
        },
        "races": [],
        "misses": [],  # Missed winners list
        "by_venue": {},  # By venue
        "by_distance": {},  # By distance
        "by_field_size": {},  # By field size
        "by_track": {},  # Turf/dirt
        "calibration": {  # For calibration
            "win_prob_bins": {},  # Win probability bin stats
            "place_prob_bins": {},  # Place probability bin stats
        },
    }

    payouts = payouts or {}

    # Map by race code
    results_map = {r["race_code"]: r for r in results}

    for pred_race in predictions.get("races", []):
        race_code = pred_race["race_code"]
        comparison["total_races"] += 1

        if race_code not in results_map:
            continue

        actual = results_map[race_code]
        comparison["analyzed_races"] += 1

        # Get all horses and top 3 predictions
        all_horses = pred_race.get("all_horses", [])
        pred_top3 = pred_race.get("top3", [])
        pred_top3_umaban = [str(int(p["umaban"])) for p in pred_top3]

        # Actual results (TOP3)
        actual_results = actual["results"]
        actual_top3 = [str(int(r["umaban"])) for r in actual_results[:3] if r["chakujun"] <= 3]
        winner_umaban = actual_top3[0] if actual_top3 else None

        # Race info
        keibajo = actual["keibajo"]
        kyori = actual.get("kyori", 0)
        track = actual.get("track", "不明")
        field_size = len(actual_results)

        # Distance category
        try:
            kyori_int = int(kyori) if kyori else 0
        except Exception:
            kyori_int = 0
        if kyori_int <= 1400:
            distance_cat = "短距離"
        elif kyori_int <= 1800:
            distance_cat = "マイル"
        elif kyori_int <= 2200:
            distance_cat = "中距離"
        else:
            distance_cat = "長距離"

        # Field size category
        if field_size <= 10:
            field_cat = "少頭数(~10)"
        elif field_size <= 14:
            field_cat = "中頭数(11-14)"
        else:
            field_cat = "多頭数(15~)"

        # Calculate stats
        race_result = {
            "race_code": race_code,
            "keibajo": keibajo,
            "race_number": actual["race_number"],
            "kyori": kyori,
            "track": track,
            "field_size": field_size,
            "pred_top3": pred_top3_umaban,
            "actual_top3": actual_top3,
            "hits": {},
            "winner_rank": None,  # Winner's predicted rank
        }

        # Calculate winner's predicted rank (for MRR)
        if winner_umaban and all_horses:
            for idx, h in enumerate(all_horses):
                h_umaban = str(h.get("horse_number", ""))
                if h_umaban == winner_umaban:
                    winner_rank = idx + 1
                    race_result["winner_rank"] = winner_rank
                    comparison["stats"]["mrr_sum"] += 1.0 / winner_rank
                    break

        # Top 1 prediction wins
        if pred_top3_umaban and actual_top3:
            if pred_top3_umaban[0] == actual_top3[0]:
                comparison["stats"]["top1_hit"] += 1
                comparison["stats"]["tansho_hit"] += 1
                race_result["hits"]["tansho"] = True

            # Top 1 prediction in top 3
            if pred_top3_umaban[0] in actual_top3:
                comparison["stats"]["top1_in_top3"] += 1
                comparison["stats"]["fukusho_hit"] += 1
                race_result["hits"]["fukusho"] = True

        # Winner in top 3 predictions
        if winner_umaban and winner_umaban in pred_top3_umaban:
            comparison["stats"]["top3_cover"] += 1
            race_result["hits"]["top3_cover"] = True
        elif winner_umaban and race_result["winner_rank"] and race_result["winner_rank"] > 3:
            # Missed (winner ranked 4th or lower)
            comparison["misses"].append(
                {
                    "race": f"{keibajo}{actual['race_number']}R",
                    "winner_rank": race_result["winner_rank"],
                    "winner": winner_umaban,
                }
            )

        # TOP3 prediction matches all top 3
        if len(pred_top3_umaban) >= 3 and len(actual_top3) >= 3:
            if set(pred_top3_umaban[:3]) == set(actual_top3[:3]):
                comparison["stats"]["top3_hit"] += 1
                comparison["stats"]["sanrenpuku_hit"] += 1
                race_result["hits"]["sanrenpuku"] = True

        # Exacta (1-2 prediction matches 1-2)
        if len(pred_top3_umaban) >= 2 and len(actual_top3) >= 2:
            if set(pred_top3_umaban[:2]) == set(actual_top3[:2]):
                comparison["stats"]["umaren_hit"] += 1
                race_result["hits"]["umaren"] = True

        # Ranking stats (what position did rank 1-5 predictions finish)
        actual_results_map = {str(int(r["umaban"])): r["chakujun"] for r in actual_results}
        for rank in range(1, 6):  # Ranks 1-5
            if rank <= len(all_horses):
                pred_umaban = str(all_horses[rank - 1].get("horse_number", ""))
                comparison["ranking_stats"][rank]["出走"] += 1

                if pred_umaban in actual_results_map:
                    actual_pos = actual_results_map[pred_umaban]
                    if actual_pos == 1:
                        comparison["ranking_stats"][rank]["1着"] += 1
                    elif actual_pos == 2:
                        comparison["ranking_stats"][rank]["2着"] += 1
                    elif actual_pos == 3:
                        comparison["ranking_stats"][rank]["3着"] += 1
                    else:
                        comparison["ranking_stats"][rank]["4着以下"] += 1
                else:
                    # Scratched, etc.
                    comparison["ranking_stats"][rank]["4着以下"] += 1

        # EV recommendation stats (EV >= 1.5 horses)
        race_payout = payouts.get(race_code, {})
        ev_recommended = []
        for h in all_horses:
            win_prob = h.get("win_probability", 0)
            odds = h.get("predicted_odds", 0)
            if odds > 0 and win_prob > 0:
                win_ev = win_prob * odds
                if win_ev >= 1.5:
                    ev_recommended.append(h)

        if ev_recommended:
            comparison["ev_stats"]["ev_rec_races"] += 1
            comparison["ev_stats"]["ev_rec_count"] += len(ev_recommended)

            for h in ev_recommended:
                h_umaban = str(int(h.get("horse_number", 0)))
                # Win investment
                comparison["ev_stats"]["ev_tansho_investment"] += 100
                comparison["ev_stats"]["ev_fukusho_investment"] += 100

                # Hit check
                if h_umaban in actual_results_map:
                    actual_pos = actual_results_map[h_umaban]
                    if actual_pos == 1:
                        comparison["ev_stats"]["ev_rec_tansho_hit"] += 1
                        # Win payout
                        if race_payout:
                            tansho_payout = race_payout.get("tansho_payout", 0)
                            comparison["ev_stats"]["ev_tansho_return"] += tansho_payout
                    if actual_pos <= 3:
                        comparison["ev_stats"]["ev_rec_fukusho_hit"] += 1
                        # Place payout
                        if race_payout:
                            for fk in race_payout.get("fukusho", []):
                                fk_umaban = fk.get("umaban", "")
                                if fk_umaban and str(int(fk_umaban)) == h_umaban:
                                    comparison["ev_stats"]["ev_fukusho_return"] += fk.get(
                                        "payout", 0
                                    )
                                    break

        race_result["ev_recommended"] = [str(int(h.get("horse_number", 0))) for h in ev_recommended]

        # Axis horse stats (horse with highest place probability)
        axis_horse = (
            max(all_horses, key=lambda h: h.get("place_probability", 0)) if all_horses else None
        )
        if axis_horse:
            comparison["axis_stats"]["axis_races"] += 1
            axis_umaban = str(int(axis_horse.get("horse_number", 0)))
            comparison["axis_stats"]["axis_fukusho_investment"] += 100

            if axis_umaban in actual_results_map:
                actual_pos = actual_results_map[axis_umaban]
                if actual_pos == 1:
                    comparison["axis_stats"]["axis_tansho_hit"] += 1
                if actual_pos <= 3:
                    comparison["axis_stats"]["axis_fukusho_hit"] += 1
                    # Place payout
                    if race_payout:
                        for fk in race_payout.get("fukusho", []):
                            fk_umaban = fk.get("umaban", "")
                            if fk_umaban and str(int(fk_umaban)) == axis_umaban:
                                comparison["axis_stats"]["axis_fukusho_return"] += fk.get(
                                    "payout", 0
                                )
                                break

            race_result["axis_horse"] = axis_umaban
            race_result["axis_fukusho"] = (
                axis_umaban in actual_results_map and actual_results_map[axis_umaban] <= 3
            )

        # Return rate calculation (with payout data) - top 1 prediction based (reference)
        if race_payout and all_horses:
            # Compare horse numbers as integers ("6" == "06")
            pred_1st_num = (
                str(int(all_horses[0].get("horse_number", 0))) if len(all_horses) > 0 else None
            )

            # Win (100 yen on top 1 prediction)
            comparison["return_stats"]["tansho_investment"] += 100
            tansho_umaban = race_payout.get("tansho_umaban", "")
            if pred_1st_num and tansho_umaban:
                tansho_umaban_num = str(int(tansho_umaban)) if tansho_umaban.strip() else ""
                if tansho_umaban_num == pred_1st_num:
                    comparison["return_stats"]["tansho_return"] += race_payout.get(
                        "tansho_payout", 0
                    )

            # Place (100 yen on top 1 prediction)
            comparison["return_stats"]["fukusho_investment"] += 100
            fukusho_hits = race_payout.get("fukusho", [])
            for fk in fukusho_hits:
                fk_umaban = fk.get("umaban", "")
                if fk_umaban:
                    fk_umaban_num = str(int(fk_umaban)) if fk_umaban.strip() else ""
                    if fk_umaban_num == pred_1st_num:
                        comparison["return_stats"]["fukusho_return"] += fk.get("payout", 0)
                        break

        # Popularity stats (from top 1 prediction's popularity)
        pred_1st_umaban = str(int(all_horses[0].get("horse_number", 0))) if all_horses else None
        pred_1st_ninki = None
        for res in actual_results:
            if str(int(res["umaban"])) == pred_1st_umaban:
                pred_1st_ninki = res.get("ninki")
                break

        if pred_1st_ninki:
            # Determine popularity category
            if pred_1st_ninki <= 3:
                pop_cat = "1-3番人気"
            elif pred_1st_ninki <= 6:
                pop_cat = "4-6番人気"
            elif pred_1st_ninki <= 9:
                pop_cat = "7-9番人気"
            else:
                pop_cat = "10番人気以下"

            comparison["popularity_stats"][pop_cat]["対象"] += 1
            if race_result["hits"].get("tansho"):
                comparison["popularity_stats"][pop_cat]["的中"] += 1
            if race_result["hits"].get("fukusho"):
                comparison["popularity_stats"][pop_cat]["複勝圏"] += 1
            race_result["pred_1st_ninki"] = pred_1st_ninki

        # Confidence stats (from top 1 prediction's confidence)
        pred_1st_confidence = all_horses[0].get("confidence", 0) if all_horses else 0
        if pred_1st_confidence >= 0.80:
            conf_cat = "高(80%以上)"
        elif pred_1st_confidence >= 0.60:
            conf_cat = "中(60-80%)"
        else:
            conf_cat = "低(60%未満)"

        comparison["confidence_stats"][conf_cat]["対象"] += 1
        if race_result["hits"].get("tansho"):
            comparison["confidence_stats"][conf_cat]["的中"] += 1
        if race_result["hits"].get("fukusho"):
            comparison["confidence_stats"][conf_cat]["複勝圏"] += 1
        race_result["pred_1st_confidence"] = pred_1st_confidence

        comparison["races"].append(race_result)

        # Category-based aggregation
        for cat_name, _cat_key, cat_val in [
            ("by_venue", keibajo, keibajo),
            ("by_distance", distance_cat, distance_cat),
            ("by_field_size", field_cat, field_cat),
            ("by_track", track, track),
        ]:
            if cat_val not in comparison[cat_name]:
                comparison[cat_name][cat_val] = {
                    "races": 0,
                    "top1_hit": 0,
                    "top1_in_top3": 0,
                    "top3_cover": 0,
                }
            comparison[cat_name][cat_val]["races"] += 1
            if race_result["hits"].get("tansho"):
                comparison[cat_name][cat_val]["top1_hit"] += 1
            if race_result["hits"].get("fukusho"):
                comparison[cat_name][cat_val]["top1_in_top3"] += 1
            if race_result["hits"].get("top3_cover"):
                comparison[cat_name][cat_val]["top3_cover"] += 1

        # Calibration data collection
        if pred_top3 and len(pred_top3) > 0:
            win_prob = pred_top3[0].get("win_prob", 0)
            # Bin by 10% increments
            win_bin = f"{int(win_prob * 10) * 10}%"
            if win_bin not in comparison["calibration"]["win_prob_bins"]:
                comparison["calibration"]["win_prob_bins"][win_bin] = {"count": 0, "hit": 0}
            comparison["calibration"]["win_prob_bins"][win_bin]["count"] += 1
            if race_result["hits"].get("tansho"):
                comparison["calibration"]["win_prob_bins"][win_bin]["hit"] += 1

    return comparison


def calculate_accuracy(comparison: dict) -> dict:
    """
    Calculate accuracy metrics (detailed version).

    Args:
        comparison: Comparison result dictionary

    Returns:
        Accuracy metrics dictionary
    """
    n = comparison["analyzed_races"]
    if n == 0:
        return {"error": "no_data"}

    stats = comparison["stats"]

    # MRR calculation
    mrr = stats["mrr_sum"] / n if n > 0 else 0

    # Calculate rates by category
    def calc_rates(data: dict) -> dict:
        result = {}
        for key, vals in data.items():
            races = vals["races"]
            if races > 0:
                result[key] = {
                    "races": races,
                    "top1_rate": vals["top1_hit"] / races * 100,
                    "top3_rate": vals["top1_in_top3"] / races * 100,
                    "cover_rate": vals["top3_cover"] / races * 100,
                }
        return result

    # Calibration calculation
    calibration = {}
    for bin_name, data in comparison.get("calibration", {}).get("win_prob_bins", {}).items():
        if data["count"] > 0:
            calibration[bin_name] = {
                "count": data["count"],
                "actual_rate": data["hit"] / data["count"] * 100,
            }

    # Format ranking stats
    ranking_stats = comparison.get("ranking_stats", {})
    ranking_formatted = {}
    for rank, data in ranking_stats.items():
        total = data.get("出走", 0)
        if total > 0:
            ranking_formatted[rank] = {
                "出走": total,
                "1着": data["1着"],
                "2着": data["2着"],
                "3着": data["3着"],
                "4着以下": data["4着以下"],
                "1着率": data["1着"] / total * 100,
                "連対率": (data["1着"] + data["2着"]) / total * 100,
                "複勝率": (data["1着"] + data["2着"] + data["3着"]) / total * 100,
            }

    # Return rate calculation (top 1 prediction based, reference)
    return_stats = comparison.get("return_stats", {})
    tansho_inv = return_stats.get("tansho_investment", 0)
    fukusho_inv = return_stats.get("fukusho_investment", 0)
    return_rates = {
        "tansho_roi": (
            (return_stats.get("tansho_return", 0) / tansho_inv * 100) if tansho_inv > 0 else 0
        ),
        "fukusho_roi": (
            (return_stats.get("fukusho_return", 0) / fukusho_inv * 100) if fukusho_inv > 0 else 0
        ),
        "tansho_investment": tansho_inv,
        "tansho_return": return_stats.get("tansho_return", 0),
        "fukusho_investment": fukusho_inv,
        "fukusho_return": return_stats.get("fukusho_return", 0),
    }

    # Format EV recommendation stats
    ev_stats = comparison.get("ev_stats", {})
    ev_rec_count = ev_stats.get("ev_rec_count", 0)
    ev_tansho_inv = ev_stats.get("ev_tansho_investment", 0)
    ev_fukusho_inv = ev_stats.get("ev_fukusho_investment", 0)
    ev_formatted = {
        "ev_rec_races": ev_stats.get("ev_rec_races", 0),
        "ev_rec_count": ev_rec_count,
        "ev_rec_tansho_hit": ev_stats.get("ev_rec_tansho_hit", 0),
        "ev_rec_fukusho_hit": ev_stats.get("ev_rec_fukusho_hit", 0),
        "ev_tansho_rate": (
            (ev_stats.get("ev_rec_tansho_hit", 0) / ev_rec_count * 100) if ev_rec_count > 0 else 0
        ),
        "ev_fukusho_rate": (
            (ev_stats.get("ev_rec_fukusho_hit", 0) / ev_rec_count * 100) if ev_rec_count > 0 else 0
        ),
        "ev_tansho_roi": (
            (ev_stats.get("ev_tansho_return", 0) / ev_tansho_inv * 100) if ev_tansho_inv > 0 else 0
        ),
        "ev_fukusho_roi": (
            (ev_stats.get("ev_fukusho_return", 0) / ev_fukusho_inv * 100)
            if ev_fukusho_inv > 0
            else 0
        ),
        "ev_tansho_investment": ev_tansho_inv,
        "ev_tansho_return": ev_stats.get("ev_tansho_return", 0),
        "ev_fukusho_investment": ev_fukusho_inv,
        "ev_fukusho_return": ev_stats.get("ev_fukusho_return", 0),
    }

    # Format axis horse stats
    axis_stats = comparison.get("axis_stats", {})
    axis_races = axis_stats.get("axis_races", 0)
    axis_fukusho_inv = axis_stats.get("axis_fukusho_investment", 0)
    axis_formatted = {
        "axis_races": axis_races,
        "axis_tansho_hit": axis_stats.get("axis_tansho_hit", 0),
        "axis_fukusho_hit": axis_stats.get("axis_fukusho_hit", 0),
        "axis_tansho_rate": (
            (axis_stats.get("axis_tansho_hit", 0) / axis_races * 100) if axis_races > 0 else 0
        ),
        "axis_fukusho_rate": (
            (axis_stats.get("axis_fukusho_hit", 0) / axis_races * 100) if axis_races > 0 else 0
        ),
        "axis_fukusho_roi": (
            (axis_stats.get("axis_fukusho_return", 0) / axis_fukusho_inv * 100)
            if axis_fukusho_inv > 0
            else 0
        ),
        "axis_fukusho_investment": axis_fukusho_inv,
        "axis_fukusho_return": axis_stats.get("axis_fukusho_return", 0),
    }

    # Format popularity stats
    popularity_stats = comparison.get("popularity_stats", {})
    popularity_formatted = {}
    for pop_cat, data in popularity_stats.items():
        total = data.get("対象", 0)
        if total > 0:
            popularity_formatted[pop_cat] = {
                "対象": total,
                "的中": data["的中"],
                "複勝圏": data["複勝圏"],
                "的中率": data["的中"] / total * 100,
                "複勝率": data["複勝圏"] / total * 100,
            }

    # Format confidence stats
    confidence_stats = comparison.get("confidence_stats", {})
    confidence_formatted = {}
    for conf_cat, data in confidence_stats.items():
        total = data.get("対象", 0)
        if total > 0:
            confidence_formatted[conf_cat] = {
                "対象": total,
                "的中": data["的中"],
                "複勝圏": data["複勝圏"],
                "的中率": data["的中"] / total * 100,
                "複勝率": data["複勝圏"] / total * 100,
            }

    return {
        "date": comparison["date"],
        "total_races": comparison["total_races"],
        "analyzed_races": n,
        "accuracy": {
            "top1_hit_rate": stats["top1_hit"] / n * 100,
            "top1_in_top3_rate": stats["top1_in_top3"] / n * 100,
            "top3_cover_rate": stats["top3_cover"] / n * 100,
            "mrr": mrr,
            "tansho_hit_rate": stats["tansho_hit"] / n * 100,
            "fukusho_hit_rate": stats["fukusho_hit"] / n * 100,
            "umaren_hit_rate": stats["umaren_hit"] / n * 100,
            "sanrenpuku_hit_rate": stats["sanrenpuku_hit"] / n * 100,
        },
        "ev_stats": ev_formatted,
        "axis_stats": axis_formatted,
        "ranking_stats": ranking_formatted,
        "return_rates": return_rates,
        "popularity_stats": popularity_formatted,
        "confidence_stats": confidence_formatted,
        "by_venue": calc_rates(comparison.get("by_venue", {})),
        "by_distance": calc_rates(comparison.get("by_distance", {})),
        "by_field_size": calc_rates(comparison.get("by_field_size", {})),
        "by_track": calc_rates(comparison.get("by_track", {})),
        "calibration": calibration,
        "misses": comparison.get("misses", []),
        "raw_stats": stats,
    }
