"""
Model Statistics Page

Displays ML model information and feature importance.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from pathlib import Path
import json

st.set_page_config(
    page_title="モデル統計",
    page_icon="🤖",
    layout="wide",
)

st.title("🤖 モデル統計")
st.markdown("機械学習モデルの詳細情報と特徴量分析")

# =============================================================================
# Model Overview
# =============================================================================

st.markdown("## 📊 モデル概要")

col1, col2, col3 = st.columns(3)

with col1:
    st.markdown(
        """
    ### XGBoost
    - **バージョン**: 2.0.0
    - **max_depth**: 6
    - **n_estimators**: 100
    - **learning_rate**: 0.1
    - **重み**: 40%
    """
    )

with col2:
    st.markdown(
        """
    ### LightGBM
    - **バージョン**: 4.0.0
    - **num_leaves**: 31
    - **n_estimators**: 100
    - **learning_rate**: 0.1
    - **重み**: 35%
    """
    )

with col3:
    st.markdown(
        """
    ### CatBoost
    - **バージョン**: 1.2.0
    - **depth**: 6
    - **iterations**: 100
    - **learning_rate**: 0.1
    - **重み**: 25%
    """
    )

st.markdown("---")

# =============================================================================
# Training History
# =============================================================================

st.markdown("## 📈 学習履歴")

# Sample training history
training_history = pd.DataFrame(
    {
        "date": pd.date_range(end="2025-01-28", periods=10, freq="W"),
        "train_auc": [0.68, 0.69, 0.70, 0.70, 0.71, 0.71, 0.72, 0.72, 0.72, 0.72],
        "val_auc": [0.66, 0.67, 0.68, 0.68, 0.69, 0.69, 0.70, 0.70, 0.71, 0.72],
        "train_samples": [
            100000,
            105000,
            110000,
            112000,
            115000,
            118000,
            120000,
            122000,
            124000,
            125000,
        ],
    }
)

col1, col2 = st.columns(2)

with col1:
    fig_auc = go.Figure()
    fig_auc.add_trace(
        go.Scatter(
            x=training_history["date"],
            y=training_history["train_auc"],
            name="Training AUC",
            mode="lines+markers",
        )
    )
    fig_auc.add_trace(
        go.Scatter(
            x=training_history["date"],
            y=training_history["val_auc"],
            name="Validation AUC",
            mode="lines+markers",
        )
    )
    fig_auc.update_layout(
        title="AUC推移",
        xaxis_title="日付",
        yaxis_title="AUC",
        height=350,
    )
    st.plotly_chart(fig_auc, use_container_width=True)

with col2:
    fig_samples = px.line(
        training_history,
        x="date",
        y="train_samples",
        title="学習サンプル数推移",
    )
    fig_samples.update_layout(
        xaxis_title="日付",
        yaxis_title="サンプル数",
        height=350,
    )
    st.plotly_chart(fig_samples, use_container_width=True)

st.markdown("---")

# =============================================================================
# Feature Importance
# =============================================================================

st.markdown("## 🎯 特徴量重要度")

# Sample feature importance
feature_importance = pd.DataFrame(
    {
        "feature": [
            "speed_index",
            "jockey_win_rate",
            "horse_career_win_rate",
            "trainer_win_rate",
            "distance_aptitude",
            "track_condition_score",
            "recent_form_score",
            "weight_ratio",
            "draw_advantage",
            "class_score",
            "age_factor",
            "rest_days",
        ],
        "importance": [0.15, 0.12, 0.11, 0.09, 0.08, 0.08, 0.07, 0.07, 0.06, 0.06, 0.05, 0.05],
        "category": [
            "パフォーマンス",
            "騎手",
            "馬",
            "調教師",
            "距離",
            "馬場",
            "調子",
            "体重",
            "枠",
            "クラス",
            "馬齢",
            "休養",
        ],
    }
).sort_values("importance", ascending=True)

col1, col2 = st.columns([2, 1])

with col1:
    fig_importance = px.bar(
        feature_importance,
        x="importance",
        y="feature",
        orientation="h",
        title="特徴量重要度 (Top 12)",
        color="category",
    )
    fig_importance.update_layout(
        xaxis_title="重要度",
        yaxis_title="特徴量",
        height=500,
    )
    st.plotly_chart(fig_importance, use_container_width=True)

with col2:
    st.markdown("### カテゴリ別")
    category_importance = (
        feature_importance.groupby("category")["importance"].sum().reset_index()
    )
    category_importance = category_importance.sort_values("importance", ascending=False)

    fig_category = px.pie(
        category_importance,
        values="importance",
        names="category",
        title="カテゴリ別重要度",
    )
    fig_category.update_layout(height=400)
    st.plotly_chart(fig_category, use_container_width=True)

st.markdown("---")

# =============================================================================
# Calibration
# =============================================================================

st.markdown("## 📐 キャリブレーション")

st.markdown(
    """
Isotonic回帰によるキャリブレーションを適用し、予測確率の信頼性を向上させています。
"""
)

# Sample calibration data
calibration_data = pd.DataFrame(
    {
        "predicted_prob": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8],
        "actual_rate": [0.08, 0.18, 0.28, 0.38, 0.48, 0.58, 0.68, 0.78],
        "count": [1000, 800, 600, 400, 300, 200, 100, 50],
    }
)

fig_calibration = go.Figure()

# Perfect calibration line
fig_calibration.add_trace(
    go.Scatter(
        x=[0, 1],
        y=[0, 1],
        mode="lines",
        name="理想的なキャリブレーション",
        line=dict(dash="dash", color="gray"),
    )
)

# Actual calibration
fig_calibration.add_trace(
    go.Scatter(
        x=calibration_data["predicted_prob"],
        y=calibration_data["actual_rate"],
        mode="lines+markers",
        name="実際の的中率",
        marker=dict(size=calibration_data["count"] / 50),
    )
)

fig_calibration.update_layout(
    title="キャリブレーションカーブ",
    xaxis_title="予測確率",
    yaxis_title="実際の的中率",
    height=400,
)
st.plotly_chart(fig_calibration, use_container_width=True)

st.markdown("---")

# =============================================================================
# Model Performance by Conditions
# =============================================================================

st.markdown("## 🏟️ 条件別パフォーマンス")

col1, col2 = st.columns(2)

with col1:
    st.subheader("距離別精度")
    distance_perf = pd.DataFrame(
        {
            "距離": ["~1200m", "1400-1600m", "1800-2000m", "2200m~"],
            "AUC": [0.71, 0.73, 0.72, 0.70],
            "的中率": [42, 45, 44, 40],
        }
    )

    fig_distance = px.bar(
        distance_perf,
        x="距離",
        y="AUC",
        title="距離別AUC",
        text="AUC",
    )
    st.plotly_chart(fig_distance, use_container_width=True)

with col2:
    st.subheader("馬場状態別精度")
    track_perf = pd.DataFrame(
        {
            "馬場状態": ["良", "稍重", "重", "不良"],
            "AUC": [0.73, 0.71, 0.69, 0.67],
            "サンプル数": [80000, 25000, 15000, 5000],
        }
    )

    fig_track = px.bar(
        track_perf,
        x="馬場状態",
        y="AUC",
        title="馬場状態別AUC",
        text="AUC",
        color="サンプル数",
    )
    st.plotly_chart(fig_track, use_container_width=True)

st.markdown("---")

# =============================================================================
# Model Files
# =============================================================================

st.markdown("## 📁 モデルファイル")

model_dir = Path("models")
if model_dir.exists():
    model_files = list(model_dir.glob("*.pkl"))
    if model_files:
        file_info = []
        for f in model_files:
            stat = f.stat()
            file_info.append(
                {
                    "ファイル名": f.name,
                    "サイズ": f"{stat.st_size / 1024 / 1024:.1f} MB",
                    "更新日時": pd.Timestamp(stat.st_mtime, unit="s"),
                }
            )
        st.dataframe(pd.DataFrame(file_info), use_container_width=True)
    else:
        st.info("モデルファイルが見つかりません")
else:
    st.info("モデルディレクトリが見つかりません")
