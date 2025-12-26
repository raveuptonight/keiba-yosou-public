#!/usr/bin/env python3
"""
データベース接続確認スクリプト

JRA-VANデータベースの状況を確認
"""

import sys
import os
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.db.connection import get_db


def check_tables():
    """テーブル一覧とデータ件数を確認"""
    db = get_db()
    conn = db.get_connection()
    if not conn:
        print("❌ データベース接続失敗")
        return

    try:
        cursor = conn.cursor()

        print("=" * 60)
        print("📊 JRA-VANデータベース状況確認")
        print("=" * 60)

        # テーブル一覧取得
        cursor.execute("""
            SELECT tablename
            FROM pg_tables
            WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
            ORDER BY tablename;
        """)

        tables = cursor.fetchall()

        if not tables:
            print("\n⚠️  テーブルが見つかりません")
            return

        print(f"\n📋 テーブル数: {len(tables)}")
        print("-" * 60)

        # 各テーブルのデータ件数を確認
        for (table_name,) in tables:
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {table_name};")
                count = cursor.fetchone()[0]

                # 件数が多いテーブルは強調表示
                if count > 0:
                    print(f"✅ {table_name:40} {count:>12,} 件")
                else:
                    print(f"   {table_name:40} {count:>12,} 件")

            except Exception as e:
                print(f"❌ {table_name:40} エラー: {e}")

        print("-" * 60)

        # 主要テーブルの詳細確認
        print("\n📌 主要テーブルの詳細")
        print("-" * 60)

        # レース情報
        check_race_data(cursor)

        # 馬情報
        check_horse_data(cursor)

        # 騎手情報
        check_jockey_data(cursor)

    except Exception as e:
        print(f"❌ エラー: {e}")
    finally:
        cursor.close()
        conn.close()
        print("\n✅ 接続クローズ")


def check_race_data(cursor):
    """レース情報の確認"""
    try:
        # レース情報テーブルを探す（テーブル名は環境によって異なる可能性）
        race_tables = ['race', 'races', 'n_race', 'race_info']

        for table in race_tables:
            try:
                # データ期間確認
                cursor.execute(f"""
                    SELECT
                        MIN(kaisai_nen) as min_year,
                        MAX(kaisai_nen) as max_year,
                        COUNT(*) as total_races
                    FROM {table}
                    WHERE kaisai_nen IS NOT NULL;
                """)

                result = cursor.fetchone()
                if result:
                    min_year, max_year, total_races = result
                    print(f"\n🏇 レース情報 ({table})")
                    print(f"   期間: {min_year}年 〜 {max_year}年")
                    print(f"   総レース数: {total_races:,} レース")

                    # 最近のデータ確認
                    cursor.execute(f"""
                        SELECT kaisai_nen, COUNT(*) as count
                        FROM {table}
                        GROUP BY kaisai_nen
                        ORDER BY kaisai_nen DESC
                        LIMIT 5;
                    """)

                    recent_years = cursor.fetchall()
                    if recent_years:
                        print(f"\n   最近のデータ:")
                        for year, count in recent_years:
                            print(f"     {year}年: {count:,} レース")

                    return  # 見つかったら終了

            except Exception:
                continue

        print("\n⚠️  レース情報テーブルが見つかりません")

    except Exception as e:
        print(f"\n❌ レース情報確認エラー: {e}")


def check_horse_data(cursor):
    """馬情報の確認"""
    try:
        horse_tables = ['horse', 'horses', 'n_uma', 'uma']

        for table in horse_tables:
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {table};")
                count = cursor.fetchone()[0]

                if count > 0:
                    print(f"\n🐴 馬情報 ({table})")
                    print(f"   登録馬数: {count:,} 頭")
                    return

            except Exception:
                continue

        print("\n⚠️  馬情報テーブルが見つかりません")

    except Exception as e:
        print(f"\n❌ 馬情報確認エラー: {e}")


def check_jockey_data(cursor):
    """騎手情報の確認"""
    try:
        jockey_tables = ['jockey', 'jockeys', 'n_kishu', 'kishu']

        for table in jockey_tables:
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {table};")
                count = cursor.fetchone()[0]

                if count > 0:
                    print(f"\n👤 騎手情報 ({table})")
                    print(f"   登録騎手数: {count:,} 人")
                    return

            except Exception:
                continue

        print("\n⚠️  騎手情報テーブルが見つかりません")

    except Exception as e:
        print(f"\n❌ 騎手情報確認エラー: {e}")


if __name__ == "__main__":
    check_tables()
