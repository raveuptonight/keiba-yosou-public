#!/usr/bin/env python3
"""
テーブル名確認スクリプト

mykeibadbが作成した実際のテーブル名を確認し、
src/db/table_names.py の更新用に出力する
"""

import sys
import os
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.db.connection import get_db


def check_table_names():
    """実際のテーブル名を確認"""
    db = get_db()
    conn = db.get_connection()
    if not conn:
        print("❌ データベース接続失敗")
        return

    try:
        cursor = conn.cursor()

        print("=" * 80)
        print("📋 mykeibadb テーブル名確認")
        print("=" * 80)

        # テーブル一覧取得（アルファベット順）
        cursor.execute("""
            SELECT tablename
            FROM pg_tables
            WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
            ORDER BY tablename;
        """)

        tables = cursor.fetchall()

        if not tables:
            print("\n⚠️  テーブルが見つかりません")
            print("データダウンロードが完了していない可能性があります。")
            return

        print(f"\n✅ テーブル数: {len(tables)}")
        print("-" * 80)

        # テーブル名一覧を出力
        print("\n【テーブル一覧】")
        for i, (table_name,) in enumerate(tables, 1):
            # データ件数も確認
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {table_name};")
                count = cursor.fetchone()[0]
                print(f"{i:2}. {table_name:40} ({count:>12,} 件)")
            except Exception as e:
                print(f"{i:2}. {table_name:40} (エラー: {e})")

        # JRA-VAN 27テーブルの想定マッピングを表示
        print("\n" + "=" * 80)
        print("📝 src/db/table_names.py 更新用リファレンス")
        print("=" * 80)

        expected_mappings = {
            "RA（レース詳細）": ["race", "n_race", "race_info", "races"],
            "SE（馬毎レース情報）": ["uma_race", "n_uma_race", "horse_race", "se"],
            "HR（払戻）": ["haraimodoshi", "n_haraimodoshi", "payout", "hr"],
            "JG（重賞）": ["jyusyo", "n_jyusyo", "graded", "jg"],
            "UM（競走馬マスタ）": ["uma", "n_uma", "horse", "horses"],
            "KS（騎手マスタ）": ["kishu", "n_kishu", "jockey", "jockeys"],
            "CH（調教師マスタ）": ["chokyoshi", "n_chokyoshi", "trainer", "trainers"],
            "BR（繁殖馬マスタ）": ["hanshoku_uma", "n_hanshoku_uma", "broodmare", "br"],
            "HN（繁殖馬名）": ["hanshoku_mei", "n_hanshoku_mei", "broodmare_name", "hn"],
            "SK（産駒）": ["sanku", "n_sanku", "progeny", "sk"],
            "UM（馬主マスタ）": ["banushi", "n_banushi", "owner", "owners"],
            "BT（馬体重）": ["batai", "n_batai", "weight", "bt"],
            "CK（出走別着度数）": ["chakudo", "n_chakudo", "record", "ck"],
            "WC（調教）": ["chokyo", "n_chokyo", "workout", "training", "wc"],
            "HC（競走馬履歴）": ["uma_rireki", "n_uma_rireki", "horse_career", "hc"],
            "RC（レコード）": ["record", "n_record", "track_record", "rc"],
            "O1（単勝オッズ）": ["odds_tan", "n_odds_tan", "win_odds", "o1"],
            "O2（複勝オッズ）": ["odds_fuku", "n_odds_fuku", "place_odds", "o2"],
            "O3（枠連オッズ）": ["odds_waku", "n_odds_waku", "bracket_odds", "o3"],
            "O4（馬連オッズ）": ["odds_umaren", "n_odds_umaren", "quinella_odds", "o4"],
            "O5（ワイドオッズ）": ["odds_wide", "n_odds_wide", "wide_odds", "o5"],
            "O6（馬単オッズ）": ["odds_umatan", "n_odds_umatan", "exacta_odds", "o6"],
            "YS（開催スケジュール）": ["schedule", "n_schedule", "kaisai_schedule", "ys"],
            "AV（アボイド）": ["avoid", "n_avoid", "av"],
            "JC（騎手変更）": ["kishu_henkou", "n_kishu_henkou", "jockey_change", "jc"],
            "TC（調教師変更）": ["chokyoshi_henkou", "n_chokyoshi_henkou", "trainer_change", "tc"],
            "CC（コース変更）": ["course_henkou", "n_course_henkou", "course_change", "cc"],
        }

        print("\n⚠️  以下の想定名と実際のテーブル名を照合してください：\n")

        found_tables = [t[0].lower() for t in tables]

        for jra_type, possible_names in expected_mappings.items():
            matched = None
            for name in possible_names:
                if name in found_tables:
                    matched = name
                    break

            if matched:
                print(f"✅ {jra_type:30} → {matched}")
            else:
                print(f"❌ {jra_type:30} → 見つかりません（候補: {', '.join(possible_names)}）")

        print("\n" + "=" * 80)
        print("📌 次のステップ")
        print("=" * 80)
        print("1. 上記のマッピングを確認")
        print("2. src/db/table_names.py を実際のテーブル名に更新")
        print("3. python scripts/check_db_data.py でデータ確認")
        print("4. psql -U postgres -d keiba_db -f src/db/migrations/001_create_predictions_table.sql")
        print("5. ./scripts/start_api.sh でFastAPI起動テスト")
        print("=" * 80)

    except Exception as e:
        print(f"❌ エラー: {e}")
        import traceback
        traceback.print_exc()
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    check_table_names()
