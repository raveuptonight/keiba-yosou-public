#!/usr/bin/env python3
"""
レース情報取得CLIツール

使用例:
    # 次の開催日のレース一覧
    python scripts/race_info.py --upcoming

    # 特定日のレース一覧
    python scripts/race_info.py --date 2025-12-28

    # 今日のレース一覧
    python scripts/race_info.py --today

    # レース詳細
    python scripts/race_info.py --race 2025122809050812
"""

import os
import sys
import argparse
from datetime import date, datetime, timedelta
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.db.connection import get_db

# 競馬場コードマッピング
VENUE_CODES = {
    "01": "札幌", "02": "函館", "03": "福島", "04": "新潟",
    "05": "東京", "06": "中山", "07": "中京", "08": "京都",
    "09": "阪神", "10": "小倉",
}

# グレードコードマッピング
GRADE_CODES = {
    "A": "G1", "B": "G2", "C": "G3", "D": "重賞",
    "E": "OP", "F": "3勝", "G": "2勝", "H": "1勝", "I": "新馬未勝利",
}


def get_next_race_dates(conn, days_ahead=14):
    """今後の開催日リストを取得"""
    cursor = conn.cursor()
    today = date.today()

    sql = """
        SELECT DISTINCT kaisai_nen, kaisai_gappi
        FROM race_shosai
        WHERE kaisai_nen >= %s
          AND kaisai_gappi >= %s
          AND data_kubun IN ('1', '2', '3', '5', '7')
        ORDER BY kaisai_nen, kaisai_gappi
        LIMIT 10
    """

    cursor.execute(sql, (str(today.year), today.strftime("%m%d")))
    rows = cursor.fetchall()
    cursor.close()

    dates = []
    for row in rows:
        year = row[0].strip()
        monthday = row[1].strip()
        try:
            d = datetime.strptime(f"{year}{monthday}", "%Y%m%d").date()
            if d <= today + timedelta(days=days_ahead):
                dates.append(d)
        except ValueError:
            continue

    return dates


def get_races_for_date(conn, target_date, venue_code=None):
    """指定日のレース一覧を取得"""
    cursor = conn.cursor()

    sql = """
        SELECT DISTINCT
            race_code,
            race_name,
            grade_cd,
            keibajo_code,
            track_code,
            kyori,
            race_bango,
            hasso_jikoku,
            kaisai_nen,
            kaisai_gappi
        FROM race_shosai
        WHERE kaisai_nen = %s
          AND kaisai_gappi = %s
          AND data_kubun IN ('1', '2', '3', '5', '7')
    """
    params = [str(target_date.year), target_date.strftime("%m%d")]

    if venue_code:
        sql += " AND keibajo_code = %s"
        params.append(venue_code)

    sql += " ORDER BY keibajo_code, race_bango"

    cursor.execute(sql, params)
    rows = cursor.fetchall()
    cursor.close()

    races = []
    for row in rows:
        race = {
            "race_code": row[0].strip() if row[0] else "",
            "race_name": row[1].strip() if row[1] else "",
            "grade": GRADE_CODES.get(row[2].strip() if row[2] else "", ""),
            "venue_code": row[3].strip() if row[3] else "",
            "venue": VENUE_CODES.get(row[3].strip() if row[3] else "", "不明"),
            "track": row[4].strip() if row[4] else "",
            "distance": int(row[5]) if row[5] else 0,
            "race_num": int(row[6]) if row[6] else 0,
            "start_time": row[7].strip() if row[7] else "",
            "date": target_date.strftime("%Y-%m-%d"),
        }
        races.append(race)

    return races


def get_race_detail(conn, race_code):
    """レース詳細と出走馬一覧を取得"""
    cursor = conn.cursor()

    # レース基本情報
    sql_race = """
        SELECT
            race_code,
            race_name,
            grade_cd,
            keibajo_code,
            track_code,
            kyori,
            race_bango,
            hasso_jikoku,
            kaisai_nen,
            kaisai_gappi,
            shiba_babajotai_code,
            dart_babajotai_code,
            tenko_code
        FROM race_shosai
        WHERE race_code = %s
          AND data_kubun IN ('1', '2', '3', '5', '7')
        LIMIT 1
    """
    cursor.execute(sql_race, (race_code,))
    race_row = cursor.fetchone()

    if not race_row:
        cursor.close()
        return None

    race_info = {
        "race_code": race_row[0].strip() if race_row[0] else "",
        "race_name": race_row[1].strip() if race_row[1] else "",
        "grade": GRADE_CODES.get(race_row[2].strip() if race_row[2] else "", ""),
        "venue": VENUE_CODES.get(race_row[3].strip() if race_row[3] else "", "不明"),
        "track": "芝" if race_row[4] and race_row[4].strip().startswith("1") else "ダート",
        "distance": int(race_row[5]) if race_row[5] else 0,
        "race_num": int(race_row[6]) if race_row[6] else 0,
        "start_time": race_row[7].strip() if race_row[7] else "",
        "date": f"{race_row[8]}-{race_row[9][:2]}-{race_row[9][2:]}" if race_row[8] and race_row[9] else "",
        "turf_condition": race_row[10].strip() if race_row[10] else "",
        "dirt_condition": race_row[11].strip() if race_row[11] else "",
        "weather": race_row[12].strip() if race_row[12] else "",
    }

    # 出走馬一覧
    sql_entries = """
        SELECT
            ur.umaban,
            ur.wakuban,
            ur.ketto_toroku_bango,
            ur.bamei,
            ur.seibetsu_code,
            ur.barei,
            ur.futan_juryo,
            ur.kishu_code,
            ur.kishumei_ryakusho,
            ur.chokyoshi_code,
            ur.chokyoshimei_ryakusho,
            ur.bataiju,
            ur.zogen_sa,
            ur.tansho_odds,
            ur.tansho_ninkijun
        FROM umagoto_race_joho ur
        WHERE ur.race_code = %s
          AND ur.data_kubun IN ('1', '2', '3', '5', '7')
        ORDER BY CAST(ur.umaban AS INTEGER)
    """
    cursor.execute(sql_entries, (race_code,))
    entry_rows = cursor.fetchall()
    cursor.close()

    entries = []
    sex_map = {"1": "牡", "2": "牝", "3": "セ"}
    for row in entry_rows:
        entry = {
            "umaban": int(row[0]) if row[0] and row[0].strip() else 0,
            "wakuban": int(row[1]) if row[1] and row[1].strip() else 0,
            "kettonum": row[2].strip() if row[2] else "",
            "name": row[3].strip() if row[3] else "",
            "sex": sex_map.get(row[4].strip() if row[4] else "", ""),
            "age": int(row[5]) if row[5] else 0,
            "weight": float(row[6]) / 10 if row[6] else 0,
            "jockey": row[8].strip() if row[8] else "",
            "trainer": row[10].strip() if row[10] else "",
            "horse_weight": int(row[11]) if row[11] and row[11].strip() else 0,
            "weight_diff": int(row[12]) if row[12] and row[12].strip() else 0,
            "odds": float(row[13]) / 10 if row[13] and row[13].strip() else 0,
            "popularity": int(row[14]) if row[14] and row[14].strip() else 0,
        }
        entries.append(entry)

    return {
        "race": race_info,
        "entries": entries,
        "entry_count": len(entries)
    }


def print_upcoming_races(conn, days_ahead=14):
    """今後の開催日とレース一覧を表示"""
    print("=" * 60)
    print("今後の開催日とレース一覧")
    print("=" * 60)

    dates = get_next_race_dates(conn, days_ahead)

    if not dates:
        print("今後のレースデータがありません")
        return

    for d in dates:
        races = get_races_for_date(conn, d)
        if not races:
            continue

        print(f"\n--- {d.strftime('%Y年%m月%d日')} ({['月', '火', '水', '木', '金', '土', '日'][d.weekday()]}) ---")

        # 競馬場ごとにグループ化
        by_venue = {}
        for race in races:
            venue = race["venue"]
            if venue not in by_venue:
                by_venue[venue] = []
            by_venue[venue].append(race)

        for venue, venue_races in sorted(by_venue.items()):
            print(f"\n  [{venue}]")
            for race in sorted(venue_races, key=lambda x: x["race_num"]):
                grade = f"[{race['grade']}]" if race['grade'] else ""
                track = "芝" if race["track"].startswith("1") else "ダ"
                print(f"    {race['race_num']:2d}R {race['start_time']} {track}{race['distance']:4d}m {grade:6s} {race['race_name'][:20]}")
                print(f"        ID: {race['race_code']}")


def print_races_for_date(conn, target_date, venue_code=None):
    """指定日のレース一覧を表示"""
    print("=" * 60)
    print(f"{target_date.strftime('%Y年%m月%d日')} のレース一覧")
    print("=" * 60)

    races = get_races_for_date(conn, target_date, venue_code)

    if not races:
        print("レースデータがありません")
        return

    # 競馬場ごとにグループ化
    by_venue = {}
    for race in races:
        venue = race["venue"]
        if venue not in by_venue:
            by_venue[venue] = []
        by_venue[venue].append(race)

    for venue, venue_races in sorted(by_venue.items()):
        print(f"\n[{venue}]")
        for race in sorted(venue_races, key=lambda x: x["race_num"]):
            grade = f"[{race['grade']}]" if race['grade'] else ""
            track = "芝" if race["track"].startswith("1") else "ダ"
            print(f"  {race['race_num']:2d}R {race['start_time']} {track}{race['distance']:4d}m {grade:6s} {race['race_name'][:25]}")
            print(f"      ID: {race['race_code']}")


def print_race_detail(conn, race_code):
    """レース詳細を表示"""
    detail = get_race_detail(conn, race_code)

    if not detail:
        print(f"レースが見つかりません: {race_code}")
        return

    race = detail["race"]
    entries = detail["entries"]

    print("=" * 70)
    print(f"レース詳細: {race['race_name']}")
    print("=" * 70)
    print(f"  レースID: {race['race_code']}")
    print(f"  開催日時: {race['date']} {race['start_time']}")
    print(f"  競馬場:   {race['venue']} {race['race_num']}R")
    print(f"  コース:   {race['track']} {race['distance']}m")
    if race['grade']:
        print(f"  グレード: {race['grade']}")
    print(f"  出走頭数: {detail['entry_count']}頭")
    print()

    print("出走馬一覧:")
    print("-" * 70)
    print(f"{'枠':>2} {'馬番':>3} {'馬名':<16} {'性齢':>4} {'斤量':>5} {'騎手':<8} {'調教師':<8} {'馬体重':>4} {'オッズ':>6} {'人気':>3}")
    print("-" * 70)

    for e in entries:
        sex_age = f"{e['sex']}{e['age']}" if e['sex'] else f"{e['age']}歳"
        weight_str = f"{e['horse_weight']}" if e['horse_weight'] else "-"
        diff_str = f"({e['weight_diff']:+d})" if e['weight_diff'] else ""
        odds_str = f"{e['odds']:.1f}" if e['odds'] else "-"
        pop_str = str(e['popularity']) if e['popularity'] else "-"

        print(f"{e['wakuban']:2d} {e['umaban']:3d}  {e['name']:<16} {sex_age:>4} {e['weight']:5.1f} {e['jockey']:<8} {e['trainer']:<8} {weight_str:>4}{diff_str:<5} {odds_str:>6} {pop_str:>3}")


def main():
    parser = argparse.ArgumentParser(description="レース情報取得ツール")

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--upcoming", action="store_true", help="今後の開催日とレース一覧")
    group.add_argument("--today", action="store_true", help="今日のレース一覧")
    group.add_argument("--date", type=str, help="指定日のレース一覧 (YYYY-MM-DD形式)")
    group.add_argument("--race", type=str, help="レース詳細 (16桁のレースID)")

    parser.add_argument("--venue", type=str, help="競馬場コード (01-10)")
    parser.add_argument("--days", type=int, default=14, help="今後何日分表示するか (デフォルト: 14)")

    args = parser.parse_args()

    # DB接続
    db = get_db()
    conn = db.get_connection()

    try:
        if args.upcoming:
            print_upcoming_races(conn, args.days)
        elif args.today:
            print_races_for_date(conn, date.today(), args.venue)
        elif args.date:
            target_date = datetime.strptime(args.date, "%Y-%m-%d").date()
            print_races_for_date(conn, target_date, args.venue)
        elif args.race:
            print_race_detail(conn, args.race)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
