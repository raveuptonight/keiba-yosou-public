"""
馬券買い目最適化モジュール

予算内で最適な馬券の買い方を提案
"""

import logging
from typing import Dict, List, Any, Tuple
from itertools import combinations, permutations

from src.config import (
    BETTING_TICKET_TYPES,
    BETTING_MIN_AMOUNT,
    BETTING_MAX_AMOUNT,
    BETTING_UNIT_AMOUNT,
    BETTING_MAX_COMBINATIONS,
    BETTING_TOP_HORSES_COUNT,
    BETTING_MIN_CONFIDENCE,
)

# ロガー設定
logger = logging.getLogger(__name__)


class TicketOptimizer:
    """
    馬券買い目最適化クラス

    予想結果に基づいて、指定予算内で最適な買い目を生成します。
    """

    def __init__(self):
        """初期化"""
        logger.debug("TicketOptimizer初期化")

    def optimize(
        self,
        ticket_type: str,
        budget: int,
        prediction_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        最適な買い目を生成

        Args:
            ticket_type: 馬券タイプ（"単勝", "馬連", "3連複"等）
            budget: 予算（円）
            prediction_result: 予想結果

        Returns:
            最適化された買い目情報

        Raises:
            ValueError: 予算が不正、馬券タイプが不正な場合
        """
        # 入力検証
        if ticket_type not in BETTING_TICKET_TYPES:
            raise ValueError(f"未対応の馬券タイプ: {ticket_type}")

        if budget < BETTING_MIN_AMOUNT:
            raise ValueError(f"予算が少なすぎます: {budget}円 (最小{BETTING_MIN_AMOUNT}円)")

        if budget > BETTING_MAX_AMOUNT:
            raise ValueError(f"予算が大きすぎます: {budget}円 (最大{BETTING_MAX_AMOUNT}円)")

        logger.info(f"買い目最適化開始: ticket_type={ticket_type}, budget={budget}")

        # 予想結果から上位馬を抽出
        top_horses = self._extract_top_horses(prediction_result)

        if not top_horses:
            logger.warning("予想結果から馬が抽出できませんでした")
            return {
                "ticket_type": ticket_type,
                "budget": budget,
                "tickets": [],
                "total_cost": 0,
                "expected_return": 0,
                "message": "予想データが不足しています"
            }

        # 馬券タイプに応じて買い目生成
        tickets = self._generate_tickets(ticket_type, top_horses, budget)

        # 総コスト計算
        total_cost = sum(t["amount"] for t in tickets)

        # 期待回収額計算（簡易版）
        expected_return = self._calculate_expected_return(tickets, top_horses)

        logger.info(f"買い目生成完了: tickets={len(tickets)}, total_cost={total_cost}, expected_return={expected_return}")

        return {
            "ticket_type": ticket_type,
            "budget": budget,
            "tickets": tickets,
            "total_cost": total_cost,
            "expected_return": expected_return,
            "expected_roi": (expected_return / total_cost * 100) if total_cost > 0 else 0,
            "message": f"{len(tickets)}通りの買い目を生成しました"
        }

    def _extract_top_horses(self, prediction_result: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        予想結果から上位馬を抽出

        Args:
            prediction_result: 予想結果

        Returns:
            上位馬リスト（信頼度降順）
        """
        try:
            # prediction_resultから馬情報を抽出
            win_prediction = prediction_result.get("win_prediction", {})

            horses = []

            # 本命、対抗、穴馬を取得
            for rank, key in enumerate(["first", "second", "third"], start=1):
                horse = win_prediction.get(key, {})
                if horse:
                    horses.append({
                        "horse_number": horse.get("horse_number"),
                        "horse_name": horse.get("horse_name", "不明"),
                        "confidence": 1.0 / rank,  # 簡易的な信頼度（1位=1.0, 2位=0.5, 3位=0.33）
                        "expected_odds": horse.get("expected_odds", 5.0)  # デフォルト5倍
                    })

            # さらに他の候補馬があれば追加
            other_horses = win_prediction.get("others", [])
            for i, horse in enumerate(other_horses[:BETTING_TOP_HORSES_COUNT - 3], start=4):
                horses.append({
                    "horse_number": horse.get("horse_number"),
                    "horse_name": horse.get("horse_name", "不明"),
                    "confidence": 1.0 / i,
                    "expected_odds": horse.get("expected_odds", 10.0)
                })

            # 信頼度でソート
            horses.sort(key=lambda x: x["confidence"], reverse=True)

            # 信頼度が閾値以上の馬のみ
            horses = [h for h in horses if h["confidence"] >= BETTING_MIN_CONFIDENCE]

            logger.debug(f"上位馬抽出: {len(horses)}頭")
            return horses[:BETTING_TOP_HORSES_COUNT]

        except Exception as e:
            logger.error(f"上位馬抽出エラー: {e}")
            return []

    def _generate_tickets(
        self,
        ticket_type: str,
        horses: List[Dict[str, Any]],
        budget: int
    ) -> List[Dict[str, Any]]:
        """
        馬券タイプに応じて買い目を生成

        Args:
            ticket_type: 馬券タイプ
            horses: 候補馬リスト
            budget: 予算

        Returns:
            買い目リスト
        """
        ticket_info = BETTING_TICKET_TYPES[ticket_type]
        required_horses = ticket_info["min_horses"]

        if len(horses) < required_horses:
            logger.warning(f"候補馬不足: {len(horses)}頭 (必要{required_horses}頭)")
            return []

        tickets = []

        # 馬券タイプ別の処理
        if ticket_type == "単勝":
            tickets = self._generate_win_tickets(horses, budget)
        elif ticket_type == "複勝":
            tickets = self._generate_place_tickets(horses, budget)
        elif ticket_type in ["馬連", "ワイド"]:
            tickets = self._generate_quinella_tickets(horses, budget)
        elif ticket_type == "馬単":
            tickets = self._generate_exacta_tickets(horses, budget)
        elif ticket_type == "3連複":
            tickets = self._generate_trio_tickets(horses, budget)
        elif ticket_type == "3連単":
            tickets = self._generate_trifecta_tickets(horses, budget)

        return tickets

    def _generate_win_tickets(
        self,
        horses: List[Dict[str, Any]],
        budget: int
    ) -> List[Dict[str, Any]]:
        """単勝の買い目生成"""
        tickets = []

        # 上位3頭に予算を配分（信頼度に応じて）
        top_3 = horses[:3]
        total_confidence = sum(h["confidence"] for h in top_3)

        for horse in top_3:
            # 信頼度に応じて予算配分
            allocation = int(budget * (horse["confidence"] / total_confidence))
            # 100円単位に調整
            allocation = (allocation // BETTING_UNIT_AMOUNT) * BETTING_UNIT_AMOUNT

            if allocation >= BETTING_UNIT_AMOUNT:
                tickets.append({
                    "numbers": [horse["horse_number"]],
                    "horse_names": [horse["horse_name"]],
                    "amount": allocation,
                    "expected_payout": allocation * horse["expected_odds"]
                })

        return tickets

    def _generate_place_tickets(
        self,
        horses: List[Dict[str, Any]],
        budget: int
    ) -> List[Dict[str, Any]]:
        """複勝の買い目生成"""
        # 単勝と同じロジック（複勝は配当が低いので上位馬優先）
        return self._generate_win_tickets(horses, budget)

    def _generate_quinella_tickets(
        self,
        horses: List[Dict[str, Any]],
        budget: int
    ) -> List[Dict[str, Any]]:
        """馬連・ワイドの買い目生成"""
        tickets = []

        # 上位5頭から2頭の組み合わせ
        top_horses = horses[:5]
        combos = list(combinations(top_horses, 2))

        if not combos:
            return []

        # 組み合わせ数が多すぎる場合は制限
        if len(combos) > BETTING_MAX_COMBINATIONS:
            # 信頼度の積でソート
            combos.sort(key=lambda c: c[0]["confidence"] * c[1]["confidence"], reverse=True)
            combos = combos[:BETTING_MAX_COMBINATIONS]

        # 各組み合わせに均等配分
        amount_per_ticket = budget // len(combos)
        amount_per_ticket = (amount_per_ticket // BETTING_UNIT_AMOUNT) * BETTING_UNIT_AMOUNT

        if amount_per_ticket < BETTING_UNIT_AMOUNT:
            amount_per_ticket = BETTING_UNIT_AMOUNT

        for h1, h2 in combos:
            tickets.append({
                "numbers": [h1["horse_number"], h2["horse_number"]],
                "horse_names": [h1["horse_name"], h2["horse_name"]],
                "amount": amount_per_ticket,
                "expected_payout": amount_per_ticket * min(h1["expected_odds"], h2["expected_odds"]) * 0.7
            })

        return tickets

    def _generate_exacta_tickets(
        self,
        horses: List[Dict[str, Any]],
        budget: int
    ) -> List[Dict[str, Any]]:
        """馬単の買い目生成"""
        tickets = []

        # 上位5頭から2頭の順列
        top_horses = horses[:5]
        perms = list(permutations(top_horses, 2))

        if not perms:
            return []

        # 組み合わせ数が多すぎる場合は制限
        if len(perms) > BETTING_MAX_COMBINATIONS:
            # 1着馬の信頼度を重視してソート
            perms.sort(key=lambda p: p[0]["confidence"] * 2 + p[1]["confidence"], reverse=True)
            perms = perms[:BETTING_MAX_COMBINATIONS]

        # 各組み合わせに配分（上位ほど多く）
        amount_per_ticket = budget // len(perms)
        amount_per_ticket = (amount_per_ticket // BETTING_UNIT_AMOUNT) * BETTING_UNIT_AMOUNT

        if amount_per_ticket < BETTING_UNIT_AMOUNT:
            amount_per_ticket = BETTING_UNIT_AMOUNT

        for h1, h2 in perms:
            tickets.append({
                "numbers": [h1["horse_number"], h2["horse_number"]],
                "horse_names": [h1["horse_name"], h2["horse_name"]],
                "amount": amount_per_ticket,
                "expected_payout": amount_per_ticket * h1["expected_odds"] * h2["expected_odds"] * 0.5
            })

        return tickets

    def _generate_trio_tickets(
        self,
        horses: List[Dict[str, Any]],
        budget: int
    ) -> List[Dict[str, Any]]:
        """3連複の買い目生成"""
        tickets = []

        # 上位6頭から3頭の組み合わせ
        top_horses = horses[:6]
        combos = list(combinations(top_horses, 3))

        if not combos:
            return []

        # 組み合わせ数が多すぎる場合は制限
        if len(combos) > BETTING_MAX_COMBINATIONS:
            # 信頼度の積でソート
            combos.sort(
                key=lambda c: c[0]["confidence"] * c[1]["confidence"] * c[2]["confidence"],
                reverse=True
            )
            combos = combos[:BETTING_MAX_COMBINATIONS]

        # 各組み合わせに配分
        amount_per_ticket = budget // len(combos)
        amount_per_ticket = (amount_per_ticket // BETTING_UNIT_AMOUNT) * BETTING_UNIT_AMOUNT

        if amount_per_ticket < BETTING_UNIT_AMOUNT:
            amount_per_ticket = BETTING_UNIT_AMOUNT

        for h1, h2, h3 in combos:
            tickets.append({
                "numbers": [h1["horse_number"], h2["horse_number"], h3["horse_number"]],
                "horse_names": [h1["horse_name"], h2["horse_name"], h3["horse_name"]],
                "amount": amount_per_ticket,
                "expected_payout": amount_per_ticket * min(h1["expected_odds"], h2["expected_odds"]) * 5
            })

        return tickets

    def _generate_trifecta_tickets(
        self,
        horses: List[Dict[str, Any]],
        budget: int
    ) -> List[Dict[str, Any]]:
        """3連単の買い目生成"""
        tickets = []

        # 上位5頭から3頭の順列
        top_horses = horses[:5]
        perms = list(permutations(top_horses, 3))

        if not perms:
            return []

        # 組み合わせ数が多すぎる場合は制限
        if len(perms) > BETTING_MAX_COMBINATIONS:
            # 1着馬の信頼度を最重視
            perms.sort(
                key=lambda p: p[0]["confidence"] * 3 + p[1]["confidence"] * 2 + p[2]["confidence"],
                reverse=True
            )
            perms = perms[:BETTING_MAX_COMBINATIONS]

        # 各組み合わせに配分
        amount_per_ticket = budget // len(perms)
        amount_per_ticket = (amount_per_ticket // BETTING_UNIT_AMOUNT) * BETTING_UNIT_AMOUNT

        if amount_per_ticket < BETTING_UNIT_AMOUNT:
            amount_per_ticket = BETTING_UNIT_AMOUNT

        for h1, h2, h3 in perms:
            tickets.append({
                "numbers": [h1["horse_number"], h2["horse_number"], h3["horse_number"]],
                "horse_names": [h1["horse_name"], h2["horse_name"], h3["horse_name"]],
                "amount": amount_per_ticket,
                "expected_payout": amount_per_ticket * h1["expected_odds"] * h2["expected_odds"] * 0.3
            })

        return tickets

    def _calculate_expected_return(
        self,
        tickets: List[Dict[str, Any]],
        horses: List[Dict[str, Any]]
    ) -> float:
        """
        期待回収額を計算（簡易版）

        Args:
            tickets: 買い目リスト
            horses: 候補馬リスト

        Returns:
            期待回収額
        """
        total_expected = 0.0

        for ticket in tickets:
            # 簡易的に expected_payout を使用
            total_expected += ticket.get("expected_payout", 0)

        # 的中確率を考慮（上位馬の信頼度平均で近似）
        if horses:
            avg_confidence = sum(h["confidence"] for h in horses[:3]) / 3
            total_expected *= avg_confidence

        return int(total_expected)
