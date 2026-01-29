"""
Backtest Results Page

Displays detailed backtest results and analysis.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import json
from pathlib import Path

st.set_page_config(
    page_title="バックテスト結果",
    page_icon="📊",
    layout="wide",
)

st.title("📊 バックテスト結果")
st.markdown("過去の予想精度とパフォーマンス分析")


def load_results():
    """Load backtest results."""
    results_dir = Path("backtest_results")
    if not results_dir.exists():
        return None

    results = []
    for file in sorted(results_dir.glob("*.json"), reverse=True):
        try:
            with open(file) as f:
                data = json.load(f)
                results.append(data)
        except Exception:
            pass

    return pd.DataFrame(results) if results else None


# Load data
df = load_results()

if df is None or df.empty:
    st.warning("バックテストデータがありません")

    # Create sample data for demonstration
    st.info("サンプルデータを表示しています")

    sample_dates = pd.date_range(end=datetime.now(), periods=50, freq="D")
    df = pd.DataFrame(
        {
            "date": sample_dates,
            "race_name": [f"テストレース{i}" for i in range(50)],
            "track": ["中山", "東京", "阪神", "京都", "中京"][: 50 % 5] * 10,
            "predicted_rank1": [1, 2, 3, 1, 2] * 10,
            "actual_rank1": [1, 3, 2, 2, 1] * 10,
            "roi": [120, 0, 150, 0, 200] * 10,
            "ev_recommended": [True, False, True, False, True] * 10,
            "ev_hit": [True, False, True, False, False] * 10,
        }
    )

# =============================================================================
# Filters
# =============================================================================

st.sidebar.header("フィルター")

# Track filter
if "track" in df.columns:
    tracks = ["全て"] + sorted(df["track"].unique().tolist())
    selected_track = st.sidebar.selectbox("競馬場", tracks)
    if selected_track != "全て":
        df = df[df["track"] == selected_track]

# Date range filter
if "date" in df.columns:
    date_range = st.sidebar.date_input(
        "期間",
        value=(df["date"].min(), df["date"].max()),
    )

# =============================================================================
# Summary Stats
# =============================================================================

st.markdown("## 📈 サマリー統計")

col1, col2, col3, col4 = st.columns(4)

total_races = len(df)
hits = len(df[df["predicted_rank1"] == df["actual_rank1"]]) if "actual_rank1" in df.columns else 0
hit_rate = hits / total_races * 100 if total_races > 0 else 0
avg_roi = df["roi"].mean() if "roi" in df.columns else 0

with col1:
    st.metric("総レース数", f"{total_races:,}")

with col2:
    st.metric("的中数", f"{hits:,}")

with col3:
    st.metric("的中率", f"{hit_rate:.1f}%")

with col4:
    st.metric("平均回収率", f"{avg_roi:.0f}%")

st.markdown("---")

# =============================================================================
# ROI Chart
# =============================================================================

st.markdown("## 💰 回収率推移")

if "date" in df.columns and "roi" in df.columns:
    daily_roi = df.groupby("date")["roi"].mean().reset_index()

    fig = px.line(
        daily_roi,
        x="date",
        y="roi",
        title="日別平均回収率",
    )
    fig.add_hline(y=100, line_dash="dash", line_color="red")
    fig.update_layout(
        xaxis_title="日付",
        yaxis_title="回収率 (%)",
        height=400,
    )
    st.plotly_chart(fig, use_container_width=True)

st.markdown("---")

# =============================================================================
# Track Performance
# =============================================================================

st.markdown("## 🏟️ 競馬場別成績")

if "track" in df.columns:
    track_stats = (
        df.groupby("track")
        .agg(
            {
                "roi": ["count", "mean"],
            }
        )
        .reset_index()
    )
    track_stats.columns = ["競馬場", "レース数", "平均回収率"]
    track_stats = track_stats.sort_values("平均回収率", ascending=False)

    col1, col2 = st.columns(2)

    with col1:
        st.dataframe(
            track_stats.style.format({"平均回収率": "{:.1f}%"}),
            use_container_width=True,
        )

    with col2:
        fig = px.bar(
            track_stats,
            x="競馬場",
            y="平均回収率",
            title="競馬場別回収率",
            color="平均回収率",
            color_continuous_scale="RdYlGn",
        )
        fig.add_hline(y=100, line_dash="dash", line_color="red")
        st.plotly_chart(fig, use_container_width=True)

st.markdown("---")

# =============================================================================
# EV Recommendations Analysis
# =============================================================================

st.markdown("## 🎯 EV推奨分析")

if "ev_recommended" in df.columns:
    ev_df = df[df["ev_recommended"] == True]
    non_ev_df = df[df["ev_recommended"] == False]

    col1, col2 = st.columns(2)

    with col1:
        ev_roi = ev_df["roi"].mean() if len(ev_df) > 0 else 0
        st.metric(
            "EV推奨馬の回収率",
            f"{ev_roi:.0f}%",
            delta=f"+{ev_roi - 100:.0f}%" if ev_roi > 100 else f"{ev_roi - 100:.0f}%",
        )

    with col2:
        non_ev_roi = non_ev_df["roi"].mean() if len(non_ev_df) > 0 else 0
        st.metric(
            "非推奨馬の回収率",
            f"{non_ev_roi:.0f}%",
        )

    # Comparison chart
    comparison_data = pd.DataFrame(
        {
            "カテゴリ": ["EV推奨", "非推奨"],
            "回収率": [ev_roi, non_ev_roi],
            "レース数": [len(ev_df), len(non_ev_df)],
        }
    )

    fig = px.bar(
        comparison_data,
        x="カテゴリ",
        y="回収率",
        title="EV推奨 vs 非推奨",
        color="カテゴリ",
        text="レース数",
    )
    fig.add_hline(y=100, line_dash="dash", line_color="red")
    st.plotly_chart(fig, use_container_width=True)

st.markdown("---")

# =============================================================================
# Recent Results Table
# =============================================================================

st.markdown("## 📋 直近の結果")

display_cols = [
    col
    for col in ["date", "race_name", "track", "predicted_rank1", "actual_rank1", "roi"]
    if col in df.columns
]

if display_cols:
    recent_df = df.head(20)[display_cols]
    recent_df.columns = ["日付", "レース名", "競馬場", "予想1位", "実際1位", "回収率"][
        : len(display_cols)
    ]
    st.dataframe(recent_df, use_container_width=True)
