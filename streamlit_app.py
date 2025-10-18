# =============================
# streamlit_app.py（Jリーグ年俸データ専用・拡張版）
# =============================
# ・配布Excel「箱ひげ図.xlsx / 2022J年俸」をアップロード
# ・列は『チーム』『ポジション』『年齢』『年俸』（＋『順位』『選手名』）を想定
# ・グループ軸：チーム / ポジション / 年齢帯（10代/20代/30代…）
# ・外れ値除外（IQR）チェック
# ・トップ10高額年俸を除外して判定/表示（各チームの外れ値一覧も出力）
# ・箱ひげ図に中央値を明示表示（注記）

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="箱ひげ図（J年俸）", page_icon="📦", layout="wide")
st.title("📦 Jリーグ年俸データの箱ひげ図アプリ")
st.caption("Excel『箱ひげ図.xlsx』をアップロードし、チーム/ポジション/年齢帯ごとの年俸分布を確認します。")

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
        ["チーム", "ポジション", "年齢帯（10代/20代/30代…）"],
        index=0,
    )
    remove_outliers = st.checkbox("外れ値を除外（IQR方式）", value=False)
    show_points = st.checkbox("外れ値点を描画", value=True)
    exclude_top10 = st.checkbox("トップ10（年俸が高い選手）を除外して判定・表示", value=False)

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
    excluded_top10_df = df.loc[top10_idx, ["選手名", "チーム", "ポジション", "年齢", "年俸"]]
    df = df.drop(index=top10_idx)
else:
    excluded_top10_df = None

# -----------------------------
# 年齢帯の作成 & グループ列の決定
# -----------------------------
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

# -----------------------------
# プロット用データ
# -----------------------------
work = df[[group_col, "年俸"]].copy()
work = work.rename(columns={group_col: "グループ", "年俸": "年俸(万円)"})

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

# 中央値を明示表示（各グループに注記）
medians = work.groupby("グループ")["年俸(万円)"].median()
for g, m in medians.items():
    if pd.notna(m):
        fig.add_annotation(x=str(g), y=m, text=f"中央値: {m:.0f}", showarrow=False, yshift=10)

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
# 各チームの外れ値一覧（トップ10除外時のみ判定・表示）
# -----------------------------
if exclude_top10 and "チーム" in df.columns:
    st.subheader("トップ10除外後の『各チームの外れ値』一覧")
    st.caption("各チーム内で IQR 法により外れ値と判定された選手（年俸）。")

    def team_iqr_outliers(g: pd.DataFrame) -> pd.DataFrame:
        y = g["年俸"].dropna()
        if y.empty:
            return g.iloc[0:0]
        q1, q3 = y.quantile(0.25), y.quantile(0.75)
        iqr = q3 - q1
        if not np.isfinite(iqr) or iqr == 0:
            return g.iloc[0:0]
        lo, hi = q1 - 1.5*iqr, q3 + 1.5*iqr
        return g[(g["年俸"] < lo) | (g["年俸"] > hi)]

    cols_keep = [c for c in ["選手名", "チーム", "ポジション", "年齢", "年俸"] if c in df.columns]
    _tmp = df[cols_keep].copy()
    team_outliers_df = _tmp.groupby("チーム", dropna=False, group_keys=False).apply(team_iqr_outliers)

    if team_outliers_df is not None and not team_outliers_df.empty:
        team_outliers_df = team_outliers_df.sort_values(["チーム", "年俸"], ascending=[True, False])
        st.dataframe(team_outliers_df, use_container_width=True)
        csv_out = team_outliers_df.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            label="📥 外れ値一覧をCSVで保存",
            data=csv_out,
            file_name="team_outliers_excluding_top10.csv",
            mime="text/csv",
        )
    else:
        st.info("トップ10を除外後、各チームに外れ値は見つかりませんでした。")

st.caption("※ 外れ値の基準は IQR 法（[Q1-1.5×IQR, Q3+1.5×IQR] の外）。『トップ10を除外』がONのとき、判定はトップ10除外後のデータに対して行います。")

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
# 3. アプリで Excel『箱ひげ図.xlsx』をアップロードし、分類やオプションを選ぶだけで箱ひげ図が出ます。
