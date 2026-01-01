"""
レース予想通知モジュール

出馬表、血統、調教情報を含む詳細な予想結果をDiscordに通知
"""

import logging
import os
from datetime import datetime, date
from typing import Dict, List, Any, Optional
import json

from src.db.connection import get_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class RaceNotifier:
    """レース予想通知クラス"""

    def __init__(self, webhook_url: str = None):
        self.webhook_url = webhook_url or os.getenv('DISCORD_WEBHOOK_URL')
        self.keibajo_names = {
            '01': '札幌', '02': '函館', '03': '福島', '04': '新潟', '05': '東京',
            '06': '中山', '07': '中京', '08': '京都', '09': '阪神', '10': '小倉'
        }
        self.track_names = {
            '10': '芝・左', '11': '芝・左外', '12': '芝・左内外',
            '13': '芝・左内', '14': '芝・左内-外',
            '17': '芝・右', '18': '芝・右外', '19': '芝・右内外',
            '20': '芝・右内', '21': '芝・直',
            '22': 'ダ・左', '23': 'ダ・右', '24': 'ダ・左内', '25': 'ダ・右外',
            '26': '障芝', '27': '障ダ',
            '29': '芝・右内-外'
        }
        self.baba_names = {
            '1': '良', '2': '稍重', '3': '重', '4': '不良'
        }

    def get_race_details(self, race_code: str) -> Dict:
        """レース詳細情報を取得"""
        db = get_db()
        conn = db.get_connection()

        try:
            cur = conn.cursor()

            # レース基本情報
            cur.execute('''
                SELECT
                    race_code, keibajo_code, race_bango, kyori, track_code,
                    shiba_babajotai_code, dirt_babajotai_code,
                    grade_code, joken_code_5
                FROM race_shosai
                WHERE race_code = %s
                LIMIT 1
            ''', (race_code,))

            row = cur.fetchone()
            if not row:
                return {}

            is_turf = row[4] and row[4].startswith('1')
            baba_code = row[5] if is_turf else row[6]

            race_info = {
                'race_code': row[0],
                'keibajo': self.keibajo_names.get(row[1], row[1]),
                'race_number': row[2],
                'kyori': int(row[3]) if row[3] else 0,
                'track': self.track_names.get(row[4], row[4] or ''),
                'baba': self.baba_names.get(baba_code, ''),
                'grade': row[7] or '',
                'joken': row[8] or ''
            }

            cur.close()
            return race_info

        finally:
            conn.close()

    def get_horse_details(self, race_code: str) -> List[Dict]:
        """出走馬の詳細情報を取得"""
        db = get_db()
        conn = db.get_connection()

        try:
            cur = conn.cursor()

            # 出走馬情報
            cur.execute('''
                SELECT
                    u.umaban, u.bamei, u.ketto_toroku_bango,
                    u.kishu_code, u.futan_juryo, u.barei, u.seibetsu_code,
                    u.bataiju, u.zogen_sa
                FROM umagoto_race_joho u
                WHERE u.race_code = %s
                  AND u.data_kubun IN ('3', '4', '5', '6', '7')
                ORDER BY u.umaban::int
            ''', (race_code,))

            horses = []
            sex_names = {'1': '牡', '2': '牝', '3': 'セ'}

            for row in cur.fetchall():
                kettonum = row[2]
                horse = {
                    'umaban': row[0],
                    'bamei': row[1] or '',
                    'kettonum': kettonum,
                    'kishu_code': row[3],
                    'kinryo': float(row[4]) / 10 if row[4] else 55.0,
                    'age': row[5],
                    'sex': sex_names.get(row[6], ''),
                    'weight': row[7],
                    'weight_diff': row[8]
                }

                # 騎手名を取得
                if row[3]:
                    cur.execute('''
                        SELECT kishu_mei FROM kishu_master
                        WHERE kishu_code = %s
                        ORDER BY data_sakusei_nengappi DESC
                        LIMIT 1
                    ''', (row[3],))
                    jockey = cur.fetchone()
                    horse['jockey'] = jockey[0] if jockey else ''
                else:
                    horse['jockey'] = ''

                # 血統情報を取得
                if kettonum:
                    pedigree = self._get_pedigree(cur, kettonum)
                    horse['pedigree'] = pedigree

                # 調教情報を取得
                if kettonum:
                    training = self._get_training(cur, kettonum)
                    horse['training'] = training

                horses.append(horse)

            cur.close()
            return horses

        finally:
            conn.close()

    def _get_pedigree(self, cur, kettonum: str) -> Dict:
        """血統情報を取得"""
        try:
            cur.execute('''
                SELECT
                    chichi_bamei, haha_bamei, hahachichi_bamei
                FROM uma
                WHERE ketto_toroku_bango = %s
                LIMIT 1
            ''', (kettonum,))
            row = cur.fetchone()
            if row:
                return {
                    'father': row[0] or '',
                    'mother': row[1] or '',
                    'mother_father': row[2] or ''
                }
        except Exception:
            pass
        return {'father': '', 'mother': '', 'mother_father': ''}

    def _get_training(self, cur, kettonum: str) -> Dict:
        """直近の調教情報を取得"""
        try:
            cur.execute('''
                SELECT
                    chokyo_nengappi,
                    time_gokei_4furlong,
                    time_gokei_3furlong,
                    lap_time_1furlong
                FROM hanro_chokyo
                WHERE ketto_toroku_bango = %s
                ORDER BY chokyo_nengappi DESC
                LIMIT 1
            ''', (kettonum,))
            row = cur.fetchone()
            if row:
                time_4f = float(row[1]) / 10 if row[1] else None
                time_3f = float(row[2]) / 10 if row[2] else None
                lap_1f = float(row[3]) / 10 if row[3] else None
                return {
                    'date': row[0] or '',
                    'time_4f': time_4f,
                    'time_3f': time_3f,
                    'lap_1f': lap_1f
                }
        except Exception:
            pass
        return {'date': '', 'time_4f': None, 'time_3f': None, 'lap_1f': None}

    def format_race_message(self, race_info: Dict, horses: List[Dict],
                            predictions: List[Dict]) -> str:
        """レース情報をフォーマット"""
        lines = []

        # ヘッダー
        lines.append(f"━━━━━━━━━━━━━━━━━━━━")
        lines.append(f"🏇 **{race_info['keibajo']} {race_info['race_number']}R**")
        lines.append(f"📏 {race_info['kyori']}m {race_info['track']}")
        if race_info['baba']:
            lines.append(f"🌤️ 馬場: {race_info['baba']}")
        lines.append(f"━━━━━━━━━━━━━━━━━━━━")

        # 予想結果（TOP3）
        pred_dict = {p['umaban']: p for p in predictions}
        top3 = sorted(predictions, key=lambda x: x['pred_rank'])[:3]

        lines.append("\n**【予想】**")
        medals = ['🥇', '🥈', '🥉']
        for i, p in enumerate(top3):
            horse = next((h for h in horses if str(h['umaban']) == str(p['umaban'])), {})
            bamei = horse.get('bamei', p.get('bamei', ''))
            jockey = horse.get('jockey', '')[:4] if horse.get('jockey') else ''
            lines.append(f"{medals[i]} **{p['umaban']}番 {bamei}** ({jockey})")

        # 出馬表
        lines.append("\n**【出馬表】**")
        lines.append("```")
        lines.append(f"{'番':>2} {'馬名':<10} {'騎手':<6} {'斤量':>4} {'馬体重':>6}")
        lines.append("-" * 40)

        for horse in horses:
            umaban = str(horse['umaban']).zfill(2)
            bamei = (horse['bamei'] or '')[:8]
            jockey = (horse['jockey'] or '')[:4]
            kinryo = f"{horse['kinryo']:.1f}"
            weight = horse['weight'] or ''
            weight_diff = horse['weight_diff'] or ''
            weight_str = f"{weight}({weight_diff:+d})" if weight and weight_diff else str(weight)

            # 予想順位マーク
            pred = pred_dict.get(horse['umaban'], pred_dict.get(str(horse['umaban'])))
            mark = ''
            if pred:
                rank = pred['pred_rank']
                if rank == 1:
                    mark = '◎'
                elif rank == 2:
                    mark = '○'
                elif rank == 3:
                    mark = '▲'
                elif rank <= 5:
                    mark = '△'

            lines.append(f"{mark}{umaban} {bamei:<10} {jockey:<6} {kinryo:>4} {weight_str:>6}")

        lines.append("```")

        # 血統・調教（TOP3のみ）
        lines.append("\n**【血統・調教】**")
        for p in top3:
            horse = next((h for h in horses if str(h['umaban']) == str(p['umaban'])), {})
            if not horse:
                continue

            bamei = horse.get('bamei', '')[:6]
            pedigree = horse.get('pedigree', {})
            training = horse.get('training', {})

            father = pedigree.get('father', '')[:6] if pedigree.get('father') else '-'
            mf = pedigree.get('mother_father', '')[:6] if pedigree.get('mother_father') else '-'

            train_str = ''
            if training.get('time_4f'):
                train_str = f"4F {training['time_4f']:.1f}秒"
            elif training.get('time_3f'):
                train_str = f"3F {training['time_3f']:.1f}秒"

            lines.append(f"• {p['umaban']}番{bamei}: 父{father} 母父{mf} | {train_str}")

        return "\n".join(lines)

    def send_notification(self, race_code: str, predictions: List[Dict]) -> bool:
        """予想結果を通知"""
        if not self.webhook_url:
            logger.warning("Discord Webhook URLが設定されていません")
            return False

        try:
            import requests

            # 情報取得
            race_info = self.get_race_details(race_code)
            if not race_info:
                logger.error(f"レース情報取得失敗: {race_code}")
                return False

            horses = self.get_horse_details(race_code)
            if not horses:
                logger.error(f"出走馬情報取得失敗: {race_code}")
                return False

            # メッセージ作成
            message = self.format_race_message(race_info, horses, predictions)

            # 送信
            payload = {"content": message}
            response = requests.post(self.webhook_url, json=payload, timeout=10)

            if response.status_code == 204:
                logger.info(f"通知送信成功: {race_info['keibajo']} {race_info['race_number']}R")
                return True
            else:
                logger.error(f"通知送信失敗: {response.status_code}")
                return False

        except Exception as e:
            logger.error(f"通知エラー: {e}")
            return False

    def send_daily_summary(self, results: Dict) -> bool:
        """1日分の予想サマリーを通知"""
        if not self.webhook_url:
            return False

        if results['status'] == 'no_data':
            return False

        try:
            import requests

            lines = [f"🏇 **{results['date']} レース予想一覧**\n"]

            for race in results['races']:
                lines.append(f"\n**{race['keibajo']} {race['race_number']}R** ({race['kyori']}m)")
                for p in race['top3']:
                    medal = ['🥇', '🥈', '🥉'][p['rank'] - 1]
                    lines.append(f"{medal} {p['umaban']}番 {p['bamei']}")

            lines.append(f"\n📅 生成: {results['generated_at'][:16]}")

            payload = {"content": "\n".join(lines)}
            response = requests.post(self.webhook_url, json=payload, timeout=10)

            return response.status_code == 204

        except Exception as e:
            logger.error(f"サマリー通知エラー: {e}")
            return False


def main():
    """テスト実行"""
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--race-code", "-r", help="テスト用レースコード")

    args = parser.parse_args()

    notifier = RaceNotifier()

    if args.race_code:
        # テストデータで通知テスト
        test_predictions = [
            {'umaban': '01', 'bamei': 'テスト馬1', 'pred_rank': 1, 'pred_score': 2.5},
            {'umaban': '02', 'bamei': 'テスト馬2', 'pred_rank': 2, 'pred_score': 3.0},
            {'umaban': '03', 'bamei': 'テスト馬3', 'pred_rank': 3, 'pred_score': 3.5},
        ]
        notifier.send_notification(args.race_code, test_predictions)
    else:
        print("--race-code オプションでレースコードを指定してください")


if __name__ == "__main__":
    main()
