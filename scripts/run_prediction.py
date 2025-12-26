#!/usr/bin/env python3
"""
競馬予想実行スクリプト

使用方法:
    # モックデータで分析のみ実行
    python scripts/run_prediction.py --mock --phase analyze

    # モックデータで分析→予想まで実行
    python scripts/run_prediction.py --mock --phase predict

    # モックデータで全フェーズ実行
    python scripts/run_prediction.py --mock --phase all

    # 実データで実行（DB接続が必要）
    python scripts/run_prediction.py --race-id 202412280506 --phase all
"""

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.pipeline import HorsePredictionPipeline


def load_mock_data():
    """モックデータを読み込み"""
    race_data_path = project_root / "tests/mock_data/sample_race.json"
    result_data_path = project_root / "tests/mock_data/sample_result.json"

    with open(race_data_path, "r", encoding="utf-8") as f:
        race_data = json.load(f)

    actual_result = None
    if result_data_path.exists():
        with open(result_data_path, "r", encoding="utf-8") as f:
            actual_result = json.load(f)

    return race_data, actual_result


def save_result(result: dict, output_dir: Path):
    """結果をファイルに保存"""
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = output_dir / f"prediction_{timestamp}.json"

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n結果を保存しました: {output_file}")
    return output_file


def main():
    parser = argparse.ArgumentParser(description="競馬予想システム - 回収率200%を目指す")
    parser.add_argument(
        "--mock",
        action="store_true",
        help="モックデータを使用（デフォルト: 実データ）",
    )
    parser.add_argument(
        "--race-id",
        type=str,
        help="レースID（実データ使用時に指定）",
    )
    parser.add_argument(
        "--phase",
        type=str,
        choices=["analyze", "predict", "all"],
        default="all",
        help="実行フェーズ（analyze: 分析のみ, predict: 分析→予想, all: 全フェーズ）",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="results",
        help="結果の保存先ディレクトリ",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.3,
        help="LLMのtemperatureパラメータ（0.0-1.0）",
    )

    args = parser.parse_args()

    # データ読み込み
    if args.mock:
        print("=" * 60)
        print("モックデータを使用します")
        print("=" * 60)
        race_data, actual_result = load_mock_data()
    else:
        if not args.race_id:
            print("エラー: --race-id を指定してください")
            sys.exit(1)
        print(f"レースID: {args.race_id} のデータを取得します（未実装）")
        # TODO: DBからレースデータを取得
        sys.exit(1)

    # パイプライン初期化
    pipeline = HorsePredictionPipeline()

    # フェーズごとに実行
    try:
        result = {}

        if args.phase in ["analyze", "predict", "all"]:
            print("\n" + "=" * 60)
            print("フェーズ1: データ分析")
            print("=" * 60)
            analysis = pipeline.analyze(race_data, temperature=args.temperature)
            result["analysis"] = analysis
            print("\n【分析サマリー】")
            print(f"レース概要: {analysis.get('race_summary', 'N/A')}")
            print(f"重要要因: {', '.join(analysis.get('key_factors', []))}")

        if args.phase in ["predict", "all"]:
            print("\n" + "=" * 60)
            print("フェーズ2: 予想生成")
            print("=" * 60)
            prediction = pipeline.predict(
                race_data, result["analysis"], temperature=args.temperature
            )
            result["prediction"] = prediction
            print("\n【予想サマリー】")
            win_pred = prediction.get("win_prediction", {})
            print(f"◎本命: {win_pred.get('first', {}).get('horse_name', 'N/A')}")
            print(f"○対抗: {win_pred.get('second', {}).get('horse_name', 'N/A')}")
            print(f"▲単穴: {win_pred.get('third', {}).get('horse_name', 'N/A')}")
            print(f"\n投資額: {prediction.get('total_investment', 0):,}円")
            print(f"期待回収: {prediction.get('expected_total_return', 0):,}円")
            print(f"期待ROI: {prediction.get('expected_roi', 0) * 100:.1f}%")

        if args.phase == "all" and actual_result is not None:
            print("\n" + "=" * 60)
            print("フェーズ3: 反省・改善")
            print("=" * 60)
            reflection = pipeline.reflect(
                race_data,
                result["analysis"],
                result["prediction"],
                actual_result,
                temperature=args.temperature,
            )
            result["reflection"] = reflection
            print("\n【反省サマリー】")
            overall = reflection.get("overall_evaluation", {})
            print(f"予想精度: {overall.get('prediction_accuracy', 0) * 100:.1f}%")
            print(f"ROI達成度: {overall.get('roi_achievement', 0) * 100:.1f}%")
            print(f"総合評価: {overall.get('summary', 'N/A')}")

        # 結果を保存
        result["timestamp"] = datetime.now().isoformat()
        result["race_data"] = race_data
        if actual_result:
            result["actual_result"] = actual_result

        output_dir = Path(args.output_dir)
        save_result(result, output_dir)

        print("\n" + "=" * 60)
        print("実行完了！")
        print("=" * 60)

    except KeyboardInterrupt:
        print("\n\n中断されました")
        sys.exit(1)
    except Exception as e:
        print(f"\nエラーが発生しました: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
