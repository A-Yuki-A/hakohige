# =============================
# streamlit_app.py（Jリーグ年俸データ専用・チーム/ポジション版）
# =============================
# ・配布Excel「箱ひげ図.xlsx / 2022J年俸」をアップロード
# ・列は『チーム』『ポジション』『年齢』『年俸』（＋『順位』『選手名』）を想定
# ・グループ軸：チーム / ポジション のみ（年齢帯は除外）
# ・外れ値除外（IQR）チェック → IQR法の説明を追加
# ・トップ10高額年俸を除外してプロット（除外された10人の一覧を表示）
# ・箱ひげ図の中央値を "×" マーカーで表示

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title="箱ひげ図（J年俸）", layout="wide")
st.title("Jリーグ年俸データの箱ひげ図アプリ")
st.caption("Excel『箱ひげ図.xlsx』をアップロードし、チームやポジションごとの年俸分布を確認します。")

# -----------------------------
# サイドバー
# -----------------------------
with st.sidebar:
    st.header("1) ファイルの読み込み")
    st.write("配布した Excel ファイル（箱ひげ図.xlsx）をアップロードしてください。")
    file = st.file_uploader("箱ひげ図.xlsx を選択", type=["xlsx"]) 

    st.header("2) 表示設定")
    group_by = st.selectbox(
        "箱を並べる分類（グループ軸）",
        ["チーム", "ポジション"],
        index=0,
    )
    remove_outliers = st.checkbox("外れ値を除外（IQR方式）", value=False,
        help="IQR（四分位範囲）法とは、データの中央50%の範囲を基準にして極端に離れた値を外れ値として除外する方法です。")
    show_points = st.checkbox("外れ値点を描画", value=True)
    exclude_top10 = st.checkbox("年俸の高い上位10人を除外して表示", value=False)

if file is None:
    st.info("左のサイドバーから Excel ファイルをアップロードしてください。想定列: 『順位』『選手名』『年齢』『ポジション』『チーム』『年俸』。")
    st.stop()

# -----------------------------
# 読み込み（固定シート名）
# -----------------------------
try:
    df = pd.read_excel(file, sheet_name="2022J年俸")
except Exception as e:
    st.error(f"読み込みエラー: {e}")
    st.stop()

# -----------------------------
# 前処理：不要列削除、型整備
# -----------------------------
for col in ["Unnamed: 0"]:
    if col in df.columns:
        df = df.drop(columns=col)

if "年齢" in df.columns:
    df["年齢"] = pd.to_numeric(df["年齢"], errors="coerce")

if "年俸" not in df.columns:
    st.error("『年俸』列が見つかりません。配布ファイルをご確認ください。")
    st.stop()

# -----------------------------
# トップ10除外（年俸が高い順）
# -----------------------------
if exclude_top10:
    top10_idx = df["年俸"].nlargest(10).index
    excluded_top10_df = df.loc[top10_idx, [c for c in ["順位","選手名", "チーム", "ポジション", "年齢", "年俸"] if c in df.columns]]
    df = df.drop(index=top10_idx)
else:
    excluded_top10_df = None

# -----------------------------
# プロット用データ
# -----------------------------
work = df[[group_by, "年俸"]].copy()
work = work.rename(columns={group_by: "グループ", "年俸": "年俸(万円)"})

# -----------------------------
# 外れ値除外（IQR方式）
# -----------------------------
if remove_outliers:
    def iqr_filter(g: pd.DataFrame) -> pd.DataFrame:
        y = g["年俸(万円)"].dropna()
        if y.empty:
            return g.iloc[0:0]
        q1, q3 = y.quantile(0.25), y.quantile(0.75)
        iqr = q3 - q1
        if not np.isfinite(iqr) or iqr == 0:
            return g
        lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        return g[(g["年俸(万円)"] >= lo) & (g["年俸(万円)"] <= hi)]
    work = work.groupby("グループ", dropna=False, group_keys=False).apply(iqr_filter)

# -----------------------------
# 箱ひげ図
# -----------------------------
points_mode = "outliers" if show_points else False
order = sorted(work["グループ"].astype(str).unique())

fig = px.box(
    work,
    x="グループ",
    y="年俸(万円)",
    points=points_mode,
    category_orders={"グループ": order},
)
fig.update_layout(
    xaxis_title=group_by,
    yaxis_title="年俸(万円)",
    margin=dict(l=10, r=10, t=30, b=10),
    boxmode="group",
)

# 中央値 "×" マーカーの重ね描き
medians = work.groupby("グループ")["年俸(万円)"].median().reset_index()
fig.add_trace(
    go.Scatter(
        x=medians["グループ"].astype(str),
        y=medians["年俸(万円)"],
        mode="markers",
        marker_symbol="x",
        marker_size=12,
        name="中央値",
        hovertemplate="%{x}<br>中央値=%{y}<extra></extra>",
        showlegend=True,
    )
)

st.plotly_chart(fig, use_container_width=True)

# -----------------------------
# グループ別の要約統計
# -----------------------------
st.subheader("各グループの要約")
desc = work.groupby("グループ")["年俸(万円)"].describe().rename(columns={
    "count": "件数", "mean": "平均", "std": "標準偏差", "min": "最小値",
    "25%": "Q1", "50%": "中央値", "75%": "Q3", "max": "最大値",
})
st.dataframe(desc, use_container_width=True)

# -----------------------------
# 除外された上位10人の表示（チェックON時）
# -----------------------------
if excluded_top10_df is not None and not excluded_top10_df.empty:
    st.subheader("除外された上位10人（年俸が高い順）")
    excluded_top10_df = excluded_top10_df.sort_values("年俸", ascending=False)
    st.dataframe(excluded_top10_df, use_container_width=True)

st.caption("※ IQR（四分位範囲）法：データの中央50%の範囲（Q1～Q3）を基準に、\nQ1-1.5×IQRより小さい値やQ3+1.5×IQRより大きい値を外れ値とみなします。\n外れ値除外をONにすると、この範囲外の値を除いて箱ひげ図を描きます。")

# =============================
# requirements.txt
# =============================
# streamlit
# pandas
# numpy
# plotly
# openpyxl
