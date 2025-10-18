# =============================
# streamlit_app.py（Jリーグ年俸データ専用・簡潔版）
# =============================
# ・生徒が配布された Excel「箱ひげ図.xlsx（シート: 2022J年俸）」を毎回アップロード
# ・列は『チーム』『ポジション』『年齢』『年俸』を想定（そのまま使います）
# ・グループ軸：チーム / ポジション / 年齢帯（10代/20代/30代…）
# ・外れ値除外チェック（IQR方式）で各グループごとに外れ値を除去
# ・Plotlyで箱ひげ図を描画

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="箱ひげ図（J年俸）", page_icon="📦", layout="wide")
st.title("📦 Jリーグ年俸データの箱ひげ図アプリ")
st.caption("Excel『箱ひげ図.xlsx』をアップロードし、チーム/ポジション/年齢帯ごとの年俸分布を確認します。")

# -----------------------------
# アップロード
# -----------------------------
with st.sidebar:
    st.header("1) ファイルの読み込み")
    st.write("配布した Excel ファイル（箱ひげ図.xlsx）をアップロードしてください。")
    file = st.file_uploader("箱ひげ図.xlsx を選択", type=["xlsx"]) 

    st.header("2) 表示設定")
    group_by = st.selectbox(
        "箱を並べる分類（グループ軸）",
        ["チーム", "ポジション", "年齢帯（10代/20代/30代…）"],
        index=0,
    )
    remove_outliers = st.checkbox("外れ値を除外（IQR方式）", value=False)
    show_points = st.checkbox("外れ値点を描画", value=True)

if file is None:
    st.info("左のサイドバーから Excel ファイルをアップロードしてください。想定列: 『順位』『選手名』『年齢』『ポジション』『チーム』『年俸』。")
    st.stop()

# -----------------------------
# 読み込み（固定シート名を利用）
# -----------------------------
try:
    df = pd.read_excel(file, sheet_name="2022J年俸")
except Exception as e:
    st.error(f"読み込みエラー: {e}")
    st.stop()

# 前処理：不要列削除、型整備
for col in ["Unnamed: 0"]:
    if col in df.columns:
        df = df.drop(columns=col)

# 年齢を数値化、年俸を数値化
if "年齢" in df.columns:
    df["年齢"] = pd.to_numeric(df["年齢"], errors="coerce")

if "年俸" not in df.columns:
    st.error("『年俸』列が見つかりません。配布ファイルをご確認ください。")
    st.stop()

# 年齢帯の作成
def make_age_band(s: pd.Series) -> pd.Categorical:
    bins = list(range(0, 101, 10))  # 0,10,20,...,100
    labels = [f"{i}代" for i in range(0, 100, 10)]
    return pd.cut(s, bins=bins, labels=labels, right=False)

if group_by.startswith("年齢帯"):
    if "年齢" not in df.columns:
        st.error("『年齢』列が見つかりません。年齢帯は作成できません。")
        st.stop()
    df["年齢帯"] = make_age_band(df["年齢"]) 
    group_col = "年齢帯"
else:
    group_col = group_by  # 『チーム』または『ポジション』

# 対象データ（グループ列と年俸）
work = df[[group_col, "年俸"]].copy()
work = work.rename(columns={group_col: "グループ", "年俸": "年俸(万円)"})

# 単位が万円想定。もし違う場合はここで調整可能。

# -----------------------------
# 外れ値除外（IQR）
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

# 年齢帯の順序（10代→…）
if group_col == "年齢帯" and pd.api.types.is_categorical_dtype(work["グループ"]):
    order = list(work["グループ"].cat.categories.astype(str))
else:
    order = sorted(work["グループ"].astype(str).unique())

fig = px.box(
    work,
    x="グループ",
    y="年俸(万円)",
    points=points_mode,
    category_orders={"グループ": order},
)
fig.update_layout(
    xaxis_title=group_col,
    yaxis_title="年俸(万円)",
    margin=dict(l=10, r=10, t=30, b=10),
    boxmode="group",
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

st.caption(
    "※ 外れ値の基準は IQR 法（[Q1-1.5×IQR, Q3+1.5×IQR] の外を除外）です。"
)

# =============================
# requirements.txt
# =============================
# streamlit
# pandas
# numpy
# plotly
# openpyxl

# =============================
# README.md（メモ）
# =============================
# 1. GitHub に `streamlit_app.py` と `requirements.txt` を置く。
# 2. Streamlit Cloud で Main file path を `streamlit_app.py` にしてデプロイ。
# 3. アプリで Excel『箱ひげ図.xlsx』をアップロードし、分類を選ぶだけで箱ひげ図が出ます。
