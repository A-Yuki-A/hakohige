# =============================
# streamlit_app.py（Jリーグ年俸データ専用・平均×表示／外れ値一覧付き・堅牢版）
# =============================
# ・Excel「箱ひげ図.xlsx / 2022J年俸」をアップロード
# ・列は『チーム』『ポジション』『年齢』『年俸』（＋『順位』『選手名』）を想定
# ・グループ軸：チーム / ポジション のみ
# ・外れ値除外（IQR）時に除外された選手一覧を表示（年俸付き）
# ・箱ひげ図の平均を "×" マーカーで表示
# ・groupby/apply 後の戻りを必ず DataFrame にし、列存在を検証

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
    remove_outliers = st.checkbox(
        "外れ値を除外（IQR方式）",
        value=False,
        help=(
            "IQR（四分位範囲）法とは、データの中央50%の範囲（Q1〜Q3）を基準に、"
            "Q1−1.5×IQRより小さい値やQ3+1.5×IQRより大きい値を外れ値として除外する方法です。"
        ),
    )
    show_points = st.checkbox("外れ値点を描画", value=True)
    exclude_top10 = st.checkbox("年俸の高い上位10人を除外して表示", value=False)

if file is None:
    st.info("左のサイドバーから Excel ファイルをアップロードしてください。想定列: 『順位』『選手名』『年齢』『ポジション』『チーム』『年俸』。")
    st.stop()

# -----------------------------
# データ読み込み
# -----------------------------
try:
    df = pd.read_excel(file, sheet_name="2022J年俸")
except Exception as e:
    st.error(f"読み込みエラー: {e}")
    st.stop()

# -----------------------------
# 前処理
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
# トップ10除外
# -----------------------------
if exclude_top10:
    top10_idx = df["年俸"].nlargest(10).index
    excluded_top10_df = df.loc[top10_idx, [c for c in ["順位","選手名", "チーム", "ポジション", "年齢", "年俸"] if c in df.columns]]
    df = df.drop(index=top10_idx)
else:
    excluded_top10_df = None

# -----------------------------
# プロット用データ作成（氏名なども保持）
# -----------------------------
cols_keep = [c for c in [group_by, "選手名", "チーム", "ポジション", "年齢", "年俸"] if c in df.columns]
if group_by not in df.columns:
    st.error(f"『{group_by}』列が見つかりません。配布ファイルの列名をご確認ください。")
    st.stop()

work = df[cols_keep].copy()
work = work.rename(columns={group_by: "グループ", "年俸": "年俸(万円)"})

# グループ列の確認
if "グループ" not in work.columns:
    st.error("データに『グループ』列が見つかりません。")
    st.stop()

# -----------------------------
# 外れ値除外（IQR）
# -----------------------------
removed_list = []  # 除外された行を貯める
if remove_outliers:
    def iqr_filter(g: pd.DataFrame) -> pd.DataFrame:
        y = g["年俸(万円)"].dropna()
        if y.empty:
            return g.iloc[0:0]
        q1, q3 = y.quantile(0.25), y.quantile(0.75)
        iqr = q3 - q1
        lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        mask = (g["年俸(万円)"] < lo) | (g["年俸(万円)"] > hi)
        removed = g[mask].copy()
        if not removed.empty:
            removed["判定グループ"] = g.name
            removed_list.append(removed)
        return g[~mask]

    work = (
        work.groupby("グループ", dropna=False, group_keys=False)
            .apply(iqr_filter)
            .reset_index(drop=True)
    )
    removed_outliers = pd.concat(removed_list, ignore_index=True) if removed_list else pd.DataFrame()
else:
    removed_outliers = pd.DataFrame()

# -----------------------------
# グループ順の決定（安全化）
# -----------------------------
if work.empty or "グループ" not in work.columns:
    st.warning("有効なデータがありません。フィルタ条件やアップロードファイルを確認してください。")
    st.stop()

groups = work["グループ"]
if groups.isna().all():
    st.warning("グループ列がすべて欠損です。データを確認してください。")
    st.stop()
order = sorted(pd.unique(groups.dropna().astype(str)).tolist())

# -----------------------------
# 箱ひげ図
# -----------------------------
points_mode = "outliers" if show_points else False
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

# 平均値を×マーカーで表示
means = work.groupby("グループ")["年俸(万円)"].mean().reset_index()
if not means.empty:
    fig.add_trace(
        go.Scatter(
            x=means["グループ"].astype(str),
            y=means["年俸(万円)"],
            mode="markers",
            marker_symbol="x",
            marker_size=12,
            name="平均",
            hovertemplate="%{x}<br>平均=%{y}<extra></extra>",
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
# 除外された外れ値一覧（チェックON時）
# -----------------------------
if remove_outliers and not removed_outliers.empty:
    st.subheader("除外された外れ値一覧（IQR方式）")
    # 表示列（存在する列のみ）
    show_cols = [c for c in ["選手名", "チーム", "ポジション", "年齢", "年俸(万円)", "判定グループ"] if c in removed_outliers.columns]
    removed_outliers = removed_outliers.sort_values("年俸(万円)", ascending=False)
    st.dataframe(removed_outliers[show_cols], use_container_width=True)
    st.download_button(
        label="除外された外れ値一覧をCSVで保存",
        data=removed_outliers[show_cols].to_csv(index=False).encode("utf-8-sig"),
        file_name="removed_outliers.csv",
        mime="text/csv",
    )

# -----------------------------
# 除外された上位10人の表示
# -----------------------------
if excluded_top10_df is not None and not excluded_top10_df.empty:
    st.subheader("除外された上位10人（年俸が高い順）")
    excluded_top10_df = excluded_top10_df.sort_values("年俸", ascending=False)
    st.dataframe(excluded_top10_df, use_container_width=True)

st.caption(
    "※ IQR（四分位範囲）法：データの中央50%の範囲（Q1〜Q3）を基準に、Q1−1.5×IQRより小さい値やQ3+1.5×IQRより大きい値を外れ値とみなします。\n"
    "外れ値除外をONにすると、この範囲外の値を除いて箱ひげ図を描き、除外された選手の一覧を表示します。"
)

# =============================
# requirements.txt
# =============================
# streamlit
# pandas
# numpy
# plotly
# openpyxl
