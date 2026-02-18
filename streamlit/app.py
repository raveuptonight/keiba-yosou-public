"""
keiba-yosou Dashboard - Main Application

Streamlit dashboard for horse racing prediction system.
Displays hit rates, ROI, and model statistics from database.
"""

import os
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

import streamlit as st

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Page configuration
st.set_page_config(
    page_title="競馬予想ダッシュボード",
    page_icon="🏇",
    layout="wide",
    initial_sidebar_state="expanded",
)


# =============================================================================
# Database Functions
# =============================================================================


def get_db_connection():
    """Get database connection."""
    try:
        import psycopg2

        conn = psycopg2.connect(
            host=os.getenv("DB_HOST", "host.docker.internal"),
            port=os.getenv("DB_PORT", "5432"),
            database=os.getenv("DB_NAME", "keiba_db"),
            user=os.getenv("DB_USER", "postgres"),
            password=os.getenv("DB_PASSWORD", ""),
        )
        return conn
    except Exception as e:
        st.error(f"DB接続エラー: {e}")
        return None


@st.cache_data(ttl=300)
def get_analysis_results(days: int = 30) -> pd.DataFrame:
    """Get analysis results from database."""
    conn = get_db_connection()
    if not conn:
        return pd.DataFrame()

    try:
        query = """
            SELECT
                analysis_date,
                total_races,
                analyzed_races,
                tansho_hit,
                fukusho_hit,
                umaren_hit,
                sanrenpuku_hit,
                top3_cover,
                tansho_rate,
                fukusho_rate,
                umaren_rate,
                sanrenpuku_rate,
                top3_cover_rate,
                mrr,
                tansho_roi,
                fukusho_roi,
                axis_fukusho_roi,
                tansho_investment,
                tansho_return,
                fukusho_investment,
                fukusho_return
            FROM analysis_results
            WHERE analysis_date >= CURRENT_DATE - INTERVAL '%s days'
            ORDER BY analysis_date DESC
        """
        df = pd.read_sql_query(query, conn, params=(days,))
        return df
    except Exception as e:
        st.error(f"データ取得エラー: {e}")
        return pd.DataFrame()
    finally:
        conn.close()


@st.cache_data(ttl=300)
def get_cumulative_stats() -> dict | None:
    """Get cumulative statistics."""
    conn = get_db_connection()
    if not conn:
        return None

    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                total_races,
                total_tansho_hit,
                total_fukusho_hit,
                total_umaren_hit,
                total_sanrenpuku_hit,
                cumulative_tansho_rate,
                cumulative_fukusho_rate,
                cumulative_umaren_rate,
                cumulative_sanrenpuku_rate,
                last_updated
            FROM accuracy_tracking
            LIMIT 1
        """
        )
        row = cur.fetchone()
        cur.close()

        if row:
            return {
                "total_races": row[0] or 0,
                "tansho_hit": row[1] or 0,
                "fukusho_hit": row[2] or 0,
                "umaren_hit": row[3] or 0,
                "sanrenpuku_hit": row[4] or 0,
                "tansho_rate": row[5] or 0,
                "fukusho_rate": row[6] or 0,
                "umaren_rate": row[7] or 0,
                "sanrenpuku_rate": row[8] or 0,
                "last_updated": row[9],
            }
        return None
    except Exception as e:
        st.error(f"累積統計取得エラー: {e}")
        return None
    finally:
        conn.close()


@st.cache_data(ttl=600)
def get_model_info() -> dict | None:
    """Get model information from model file or database."""
    # Try loading from pickle file first
    try:
        import joblib

        model_path = Path("/app/models/ensemble_model_latest.pkl")
        if not model_path.exists():
            model_path = Path("models/ensemble_model_latest.pkl")

        if model_path.exists():
            model_data = joblib.load(model_path)

            if isinstance(model_data, dict):
                feature_names = model_data.get("feature_names", [])
                weights = model_data.get("weights", {})

                return {
                    "trained_at": model_data.get("trained_at", "不明"),
                    "version": model_data.get("version", "不明"),
                    "feature_count": len(feature_names),
                    "rmse": model_data.get("rmse"),
                    "win_accuracy": model_data.get("win_accuracy"),
                    "place_accuracy": model_data.get("place_accuracy"),
                    "win_auc": model_data.get("win_auc"),
                    "place_auc": model_data.get("place_auc"),
                    "weights": weights,
                    "samples": model_data.get("samples"),
                }
    except Exception:
        pass  # Fall through to database lookup

    # Fallback: try to get model info from database
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT model_version, calibration_data, created_at
                FROM model_calibration
                WHERE is_active = TRUE
                ORDER BY created_at DESC
                LIMIT 1
            """
            )
            row = cur.fetchone()
            cur.close()

            if row:
                import json

                calibration_data = row[1]
                if isinstance(calibration_data, str):
                    calibration_data = json.loads(calibration_data)

                return {
                    "trained_at": row[2].strftime("%Y-%m-%d %H:%M") if row[2] else "不明",
                    "version": row[0] or "不明",
                    "feature_count": calibration_data.get("feature_count", "不明"),
                    "win_auc": calibration_data.get("win_auc"),
                    "place_auc": calibration_data.get("place_auc"),
                    "weights": calibration_data.get("weights", {}),
                    "samples": calibration_data.get("samples"),
                }
        except Exception:
            pass
        finally:
            conn.close()

    # Return default values if all else fails
    return {
        "trained_at": "不明（Pickle互換性エラー）",
        "version": "ensemble_v3",
        "feature_count": 42,
        "weights": {"xgboost": 0.4, "lightgbm": 0.35, "catboost": 0.25},
    }


# =============================================================================
# Sidebar
# =============================================================================

with st.sidebar:
    st.title("🏇 競馬予想システム")
    st.markdown("---")

    # Date range selector
    st.subheader("期間選択")
    date_options = {
        "過去7日": 7,
        "過去30日": 30,
        "過去90日": 90,
        "過去180日": 180,
    }
    date_range = st.selectbox(
        "表示期間",
        list(date_options.keys()),
        index=1,
    )
    selected_days = date_options[date_range]

    st.markdown("---")

    # Quick links
    st.subheader("クイックリンク")
    st.markdown(
        """
    - [API Docs](http://localhost:8000/docs)
    - [GitHub](https://github.com/raveuptonight/keiba-yosou)
    """
    )

    st.markdown("---")

    # Refresh button
    if st.button("🔄 データ更新"):
        st.cache_data.clear()
        st.rerun()

    st.caption(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")


# =============================================================================
# Main Content
# =============================================================================

st.title("🏇 競馬予想ダッシュボード")
st.markdown("機械学習アンサンブルモデル（XGBoost + LightGBM + CatBoost）による競馬予想システム")

# Load data
analysis_df = get_analysis_results(selected_days)
cumulative = get_cumulative_stats()
model_info = get_model_info()

# =============================================================================
# Summary Metrics (Cumulative)
# =============================================================================

st.markdown("## 📊 累積成績")

if cumulative:
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            label="総レース数",
            value=f"{cumulative['total_races']:,}",
        )

    with col2:
        st.metric(
            label="単勝的中率",
            value=f"{cumulative['tansho_rate']:.1f}%",
            help="TOP1予想の単勝的中率",
        )

    with col3:
        st.metric(
            label="複勝的中率",
            value=f"{cumulative['fukusho_rate']:.1f}%",
            help="TOP1予想の複勝的中率",
        )

    with col4:
        st.metric(
            label="3連複的中率",
            value=f"{cumulative['sanrenpuku_rate']:.1f}%",
            help="TOP3予想の3連複的中率",
        )

    if cumulative.get("last_updated"):
        st.caption(f"最終更新: {cumulative['last_updated']}")
else:
    st.info("累積データがありません。レース結果の分析を実行してください。")

st.markdown("---")

# =============================================================================
# Charts Section - Daily Performance
# =============================================================================

st.markdown("## 📈 パフォーマンス推移")

if not analysis_df.empty:
    # Sort by date for charts
    chart_df = analysis_df.sort_values("analysis_date")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("的中率推移")
        fig_rate = go.Figure()

        fig_rate.add_trace(
            go.Scatter(
                x=chart_df["analysis_date"],
                y=chart_df["tansho_rate"],
                mode="lines+markers",
                name="単勝",
                line={"color": "#1f77b4"},
            )
        )
        fig_rate.add_trace(
            go.Scatter(
                x=chart_df["analysis_date"],
                y=chart_df["fukusho_rate"],
                mode="lines+markers",
                name="複勝",
                line={"color": "#2ca02c"},
            )
        )
        fig_rate.add_trace(
            go.Scatter(
                x=chart_df["analysis_date"],
                y=chart_df["top3_cover_rate"],
                mode="lines+markers",
                name="TOP3カバー率",
                line={"color": "#ff7f0e"},
            )
        )

        fig_rate.update_layout(
            xaxis_title="日付",
            yaxis_title="的中率 (%)",
            height=400,
            legend={"x": 0.02, "y": 0.98},
        )
        st.plotly_chart(fig_rate, use_container_width=True)

    with col2:
        st.subheader("回収率推移")
        fig_roi = go.Figure()

        # Filter rows with ROI data
        roi_df = chart_df[chart_df["tansho_roi"].notna()]

        if not roi_df.empty:
            fig_roi.add_trace(
                go.Scatter(
                    x=roi_df["analysis_date"],
                    y=roi_df["tansho_roi"],
                    mode="lines+markers",
                    name="単勝ROI",
                    line={"color": "#1f77b4"},
                )
            )
            fig_roi.add_trace(
                go.Scatter(
                    x=roi_df["analysis_date"],
                    y=roi_df["fukusho_roi"],
                    mode="lines+markers",
                    name="複勝ROI",
                    line={"color": "#2ca02c"},
                )
            )
            fig_roi.add_trace(
                go.Scatter(
                    x=roi_df["analysis_date"],
                    y=roi_df["axis_fukusho_roi"],
                    mode="lines+markers",
                    name="軸馬複勝ROI",
                    line={"color": "#d62728"},
                )
            )

            # 100% breakeven line
            fig_roi.add_hline(
                y=100, line_dash="dash", line_color="gray", annotation_text="損益分岐点"
            )

        fig_roi.update_layout(
            xaxis_title="日付",
            yaxis_title="回収率 (%)",
            height=400,
            legend={"x": 0.02, "y": 0.98},
        )
        st.plotly_chart(fig_roi, use_container_width=True)

    # Summary table with ROI
    st.subheader("日別サマリー")
    display_cols = [
        "analysis_date",
        "analyzed_races",
        "tansho_rate",
        "tansho_roi",
        "fukusho_rate",
        "fukusho_roi",
        "axis_fukusho_roi",
    ]
    display_df = analysis_df[display_cols].copy()
    display_df.columns = [
        "日付",
        "R数",
        "単勝率",
        "単勝ROI",
        "複勝率",
        "複勝ROI",
        "軸馬ROI",
    ]

    # Format percentages
    for col in ["単勝率", "単勝ROI", "複勝率", "複勝ROI", "軸馬ROI"]:
        display_df[col] = display_df[col].apply(lambda x: f"{x:.1f}%" if pd.notna(x) else "-")

    st.dataframe(display_df, use_container_width=True, hide_index=True)

else:
    st.info("分析データがありません。結果分析ジョブの実行後にデータが表示されます。")

st.markdown("---")

# =============================================================================
# Model Information
# =============================================================================

st.markdown("## 🤖 モデル情報")

col1, col2 = st.columns(2)

with col1:
    st.subheader("アンサンブル構成")

    if model_info and model_info.get("weights"):
        weights = model_info["weights"]
        model_weights = pd.DataFrame(
            {
                "モデル": list(weights.keys()),
                "重み": list(weights.values()),
            }
        )
        fig_weights = px.pie(
            model_weights,
            values="重み",
            names="モデル",
            title="モデル重み配分",
        )
        fig_weights.update_layout(height=300)
        st.plotly_chart(fig_weights, use_container_width=True)
    else:
        # Default weights display
        model_weights = pd.DataFrame(
            {
                "モデル": ["XGBoost", "LightGBM", "CatBoost"],
                "重み": [0.4, 0.35, 0.25],
            }
        )
        fig_weights = px.pie(
            model_weights,
            values="重み",
            names="モデル",
            title="モデル重み配分（デフォルト）",
        )
        fig_weights.update_layout(height=300)
        st.plotly_chart(fig_weights, use_container_width=True)

with col2:
    st.subheader("モデルステータス")

    if model_info:
        status_data = []
        status_data.append(("最終学習日", model_info.get("trained_at", "不明")))
        status_data.append(("モデルバージョン", model_info.get("version", "不明")))
        status_data.append(("特徴量数", str(model_info.get("feature_count", "不明"))))

        if model_info.get("samples"):
            status_data.append(("学習サンプル数", f"{model_info['samples']:,}"))

        if model_info.get("win_auc"):
            status_data.append(("Win AUC", f"{model_info['win_auc']:.4f}"))
        elif model_info.get("win_accuracy"):
            status_data.append(("Win精度", f"{model_info['win_accuracy']:.4f}"))

        if model_info.get("place_auc"):
            status_data.append(("Place AUC", f"{model_info['place_auc']:.4f}"))
        elif model_info.get("place_accuracy"):
            status_data.append(("Place精度", f"{model_info['place_accuracy']:.4f}"))

        if model_info.get("rmse"):
            status_data.append(("RMSE", f"{model_info['rmse']:.4f}"))

        # Create markdown table
        table_md = "| 項目 | 値 |\n|------|-----|\n"
        for label, value in status_data:
            table_md += f"| {label} | {value} |\n"

        st.markdown(table_md)
    else:
        st.markdown(
            """
        | 項目 | 値 |
        |------|-----|
        | 最終学習日 | 不明 |
        | 特徴量数 | 不明 |
        | キャリブレーション | Isotonic |

        *モデルファイルの読み込みに失敗しました*
        """
        )

st.markdown("---")

# =============================================================================
# Recent Period Summary
# =============================================================================

if not analysis_df.empty:
    st.markdown(f"## 📋 {date_range}の集計")

    total_races = analysis_df["analyzed_races"].sum()
    total_tansho = analysis_df["tansho_hit"].sum()
    total_fukusho = analysis_df["fukusho_hit"].sum()

    # ROI calculation from investment/return totals
    total_tansho_inv = analysis_df["tansho_investment"].sum()
    total_tansho_ret = analysis_df["tansho_return"].sum()
    total_fukusho_inv = analysis_df["fukusho_investment"].sum()
    total_fukusho_ret = analysis_df["fukusho_return"].sum()

    tansho_roi = (total_tansho_ret / total_tansho_inv * 100) if total_tansho_inv > 0 else 0
    fukusho_roi = (total_fukusho_ret / total_fukusho_inv * 100) if total_fukusho_inv > 0 else 0

    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        st.metric("分析レース数", f"{total_races:,}")

    with col2:
        rate = (total_tansho / total_races * 100) if total_races > 0 else 0
        st.metric("単勝的中率", f"{rate:.1f}%", help=f"{total_tansho}/{total_races}")

    with col3:
        delta = f"{tansho_roi - 100:+.1f}%" if tansho_roi > 0 else None
        st.metric(
            "単勝回収率",
            f"{tansho_roi:.1f}%",
            delta=delta,
            delta_color="normal" if tansho_roi >= 100 else "inverse",
            help=f"投資{total_tansho_inv:,}円 → 回収{total_tansho_ret:,}円",
        )

    with col4:
        rate = (total_fukusho / total_races * 100) if total_races > 0 else 0
        st.metric("複勝的中率", f"{rate:.1f}%", help=f"{total_fukusho}/{total_races}")

    with col5:
        delta = f"{fukusho_roi - 100:+.1f}%" if fukusho_roi > 0 else None
        st.metric(
            "複勝回収率",
            f"{fukusho_roi:.1f}%",
            delta=delta,
            delta_color="normal" if fukusho_roi >= 100 else "inverse",
            help=f"投資{total_fukusho_inv:,}円 → 回収{total_fukusho_ret:,}円",
        )

st.markdown("---")

# =============================================================================
# Footer
# =============================================================================

st.markdown(
    """
<div style="text-align: center; color: #666; font-size: 0.8em;">
    keiba-yosou v1.0.0 |
    <a href="https://github.com/raveuptonight/keiba-yosou">GitHub</a> |
    Powered by XGBoost + LightGBM + CatBoost
</div>
""",
    unsafe_allow_html=True,
)
