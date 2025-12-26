#!/usr/bin/env python3
"""
予想結果DB初期化スクリプト

PostgreSQLのpredictionsスキーマとテーブルを作成する。

使用方法:
    python scripts/init_results_db.py
"""

import sys
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.db.connection import get_db


def init_database():
    """データベースを初期化"""
    print("=" * 60)
    print("予想結果DBを初期化します")
    print("=" * 60)

    # SQLファイルを読み込み
    sql_file = project_root / "sql" / "init_predictions_schema.sql"

    if not sql_file.exists():
        print(f"エラー: SQLファイルが見つかりません: {sql_file}")
        sys.exit(1)

    print(f"SQLファイル: {sql_file}")

    with open(sql_file, "r", encoding="utf-8") as f:
        sql_script = f.read()

    # DB接続
    db = get_db()
    conn = db.get_connection()

    try:
        # SQLスクリプトを実行
        print("\nSQLスクリプトを実行中...")
        with conn.cursor() as cur:
            cur.execute(sql_script)
        conn.commit()

        print("\n✓ SQLスクリプトの実行が完了しました")

        # テーブル一覧を確認
        print("\n作成されたテーブル:")
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'predictions'
                ORDER BY table_name
                """
            )
            tables = cur.fetchall()
            for (table_name,) in tables:
                print(f"  - predictions.{table_name}")

        # ビュー一覧を確認
        print("\n作成されたビュー:")
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT table_name
                FROM information_schema.views
                WHERE table_schema = 'predictions'
                ORDER BY table_name
                """
            )
            views = cur.fetchall()
            for (view_name,) in views:
                print(f"  - predictions.{view_name}")

        print("\n" + "=" * 60)
        print("初期化が完了しました！")
        print("=" * 60)

        return True

    except Exception as e:
        conn.rollback()
        print(f"\nエラー: {e}")
        import traceback

        traceback.print_exc()
        return False
    finally:
        conn.close()


def test_database():
    """データベースの動作確認"""
    print("\n" + "=" * 60)
    print("動作確認テスト")
    print("=" * 60)

    from datetime import date
    from src.db.results import get_results_db

    db = get_results_db()

    try:
        # テストデータを挿入
        print("\nテストデータを挿入...")
        prediction_id = db.save_prediction(
            race_id="TEST20241226",
            race_name="テストレース",
            race_date=date(2024, 12, 26),
            venue="テスト競馬場",
            analysis_result={"test": "analysis"},
            prediction_result={"test": "prediction"},
            total_investment=1000,
            expected_return=2000,
            expected_roi=2.0,
            llm_model="gemini-test",
        )
        print(f"✓ 予想を保存しました (ID: {prediction_id})")

        # 取得してみる
        print("\nテストデータを取得...")
        prediction = db.get_prediction_by_race_id("TEST20241226")
        if prediction:
            print(f"✓ 予想を取得しました: {prediction['race_name']}")
        else:
            print("✗ 予想の取得に失敗")

        # 統計更新
        print("\n統計を更新...")
        db.update_stats("all", None, None)
        stats = db.get_stats("all")
        if stats:
            print(f"✓ 統計を取得しました: 総レース数={stats['total_races']}")
        else:
            print("✗ 統計の取得に失敗")

        print("\n✓ 全ての動作確認テストが成功しました！")
        return True

    except Exception as e:
        print(f"\n✗ テストエラー: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():
    """メイン処理"""
    # 初期化
    if not init_database():
        print("\n初期化に失敗しました")
        sys.exit(1)

    # 動作確認
    if not test_database():
        print("\n動作確認に失敗しました")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("すべて完了！予想システムの準備が整いました")
    print("=" * 60)


if __name__ == "__main__":
    main()
