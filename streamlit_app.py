# =============================
# streamlit_app.py
# =============================
# ・Excel/CSVをユーザーが毎回アップロード
# ・チーム/ポジション/年齢帯（10代,20代,30代, ...）でグループ化
# ・Y軸にする数値列はユーザーが選択
# ・「外れ値を除外（IQR方式）」チェックで、各グループごとに外れ値を除去
# ・Plotlyで箱ひげ図を描画（インタラクティブ）
# ・日本語UI / です・ます調

import io
import math
import textwrap
from typing import Tuple

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

# -----------------------------
# ページ設定
# -----------------------------
st.set_page_config(
    page_title="箱ひげ図アプリ",
    page_icon="📦",
    layout="wide",
)

st.title("📦 箱ひげ図アプリ（アップロード式）")
st.caption("Excel/CSVファイルを読み込み、チーム・ポジション・年齢帯などで箱ひげ図を作成します。")

# -----------------------------
# ヘルパー関数
# -----------------------------

def load_table(file) -> pd.DataFrame:
    """Excel/CSVの自動判別読み込み。"""
    name = file.name.lower()
    if name.endswith(".csv"):
        return pd.read_csv(file)
    if name.endswith(".tsv"):
        return pd.read_csv(file, sep="\t")
    # Excel（.xlsx, .xlsm 等）
    return pd.read_excel(file)


def detect_column_types(df: pd.DataFrame) -> Tuple[list, list]:
    """簡易的にカテゴリ列・数値列を推定。"""
    numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    # カテゴリ列の定義：object/boolean/カテゴリー/小整数ユニーク値が多くない数値 など
    categorical_cols = [
        c for c in df.columns
        if (
            pd.api.types.is_object_dtype(df[c])
            or pd.api.types.is_bool_dtype(df[c])
            or pd.api.types.is_categorical_dtype(df[c])
            or (
                pd.api.types.is_integer_dtype(df[c])
                and df[c].nunique(dropna=True) <= max(30, int(len(df) * 0.05))
            )
        )
    ]
    return categorical_cols, numeric_cols


def make_age_band(df: pd.DataFrame, age_col: str, new_col: str = "年齢帯") -> pd.DataFrame:
    """年齢の列から10代/20代/30代...の帯を作る。整数年齢前提。"""
    out = df.copy()
    # 年齢列を数値化（例："25歳" → 25）
    out[age_col] = pd.to_numeric(out[age_col].astype(str).str.extract(r"(\d+)")[0], errors="coerce")
    bins = list(range(0, 101, 10))  # 0,10,20,...,100
    labels = [f"{i}代" for i in range(0, 100, 10)]
    out[new_col] = pd.cut(out[age_col], bins=bins, labels=labels, right=False)
    return out


def iqr_filter_per_group(df: pd.DataFrame, y: str, group: str) -> pd.DataFrame:
    """各グループごとにIQR(四分位範囲)で外れ値を除外したDataFrameを返します。"""
    def _filter(g: pd.DataFrame) -> pd.DataFrame:
        series = g[y].dropna()
        if series.empty:
            return g.iloc[0:0]
        q1 = series.quantile(0.25)
        q3 = series.quantile(0.75)
        iqr = q3 - q1
        if not np.isfinite(iqr) or iqr == 0:
            # データが少ない/同値の場合はそのまま
            return g
        lower = q1 - 1.5 * iqr
        upper = q3 + 1.5 * iqr
        return g[(g[y] >= lower) & (g[y] <= upper)]

    return df.groupby(group, dropna=False, group_keys=False).apply(_filter)


# -----------------------------
# サイドバー：操作
# -----------------------------
with st.sidebar:
    st.header("1) ファイルの読み込み")
    st.write("Excel(.xlsx) または CSV/TSV をアップロードしてください。")
    file = st.file_uploader("ファイルを選択", type=["xlsx", "xls", "xlsm", "csv", "tsv"])  

    st.header("2) 基本設定")
    grouping_choice = st.selectbox(
        "グループ化の軸（箱を並べる分類）",
        ["（未選択）", "チーム（列を選んで指定）", "ポジション（列を選んで指定）", "年齢帯（10代/20代/30代…）"],
        index=0,
    )
    remove_outliers = st.checkbox("外れ値を除外（IQR方式）", value=False)
    show_points = st.checkbox("外れ値点を描画（表示優先）", value=True)

    st.header("3) オプション")
    sort_x = st.checkbox("箱の並びを中央値で昇順ソート", value=False)
    show_stats = st.checkbox("各グループの要約統計を表示", value=True)


# -----------------------------
# メイン：ファイルが来たら解析
# -----------------------------
if file is None:
    st.info("左のサイドバーからファイルをアップロードしてください。サンプル列名の例：Team, Position, Age, Salary など。")
    st.stop()

# データ読み込み
try:
    df = load_table(file)
except Exception as e:
    st.error(f"読み込みでエラーが発生しました: {e}")
    st.stop()

if df.empty:
    st.warning("データが空のようです。内容をご確認ください。")
    st.stop()

st.success(f"読み込み完了： {df.shape[0]} 行 × {df.shape[1]} 列")
with st.expander("アップロード内容を確認（先頭50行）"):
    st.dataframe(df.head(50), use_container_width=True)

# 列タイプを推定
cat_cols, num_cols = detect_column_types(df)
if not num_cols:
    st.error("数値列が見つかりませんでした。Y軸にする数値列が必要です。")
    st.stop()

# Y軸（数値列）選択
col_y = st.selectbox("Y軸（箱ひげ図で分布を見る数値列）", num_cols)

# グループ列を決定
group_col = None

if grouping_choice == "チーム（列を選んで指定）":
    if not cat_cols:
        st.error("チームに使えるカテゴリ列が見つかりませんでした。")
        st.stop()
    group_col = st.selectbox("チームを表す列を選んでください", cat_cols)

elif grouping_choice == "ポジション（列を選んで指定）":
    if not cat_cols:
        st.error("ポジションに使えるカテゴリ列が見つかりませんでした。")
        st.stop()
    group_col = st.selectbox("ポジションを表す列を選んでください", cat_cols)

elif grouping_choice == "年齢帯（10代/20代/30代…）":
    # 年齢列をユーザーに選択させて、帯を作る
    age_candidates = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c]) or pd.api.types.is_object_dtype(df[c])]
    if not age_candidates:
        st.error("年齢に使える列が見つかりませんでした。")
        st.stop()
    age_col = st.selectbox("年齢を表す列を選んでください（例：Age, 年齢）", age_candidates)
    df = make_age_band(df, age_col, new_col="年齢帯")
    group_col = "年齢帯"

else:
    st.warning("グループ化の軸が未選択です。1つ選んでください。")
    st.stop()

# -----------------------------
# 前処理：NaN除去など
# -----------------------------
work = df[[group_col, col_y]].copy()
work = work.rename(columns={group_col: "グループ", col_y: "値"})

# 年齢帯のカテゴリ順（10代→20代→…）の整列
if group_col == "年齢帯" and pd.api.types.is_categorical_dtype(work["グループ"]):
    work["グループ"] = work["グループ"].cat.remove_unused_categories()

# 外れ値除外（IQR方式）
if remove_outliers:
    work = iqr_filter_per_group(work, y="値", group="グループ")

# 並び替え（中央値）
if sort_x:
    med = work.groupby("グループ")["値"].median().sort_values()
    category_order = list(med.index.astype(str))
else:
    # デフォルト順（カテゴリ型ならその順）
    if pd.api.types.is_categorical_dtype(work["グループ"]):
        category_order = list(work["グループ"].cat.categories.astype(str))
    else:
        category_order = sorted(work["グループ"].astype(str).unique())

# -----------------------------
# 図の描画（Plotly）
# -----------------------------
points_mode = "outliers" if show_points else False
fig = px.box(
    work,
    x="グループ",
    y="値",
    points=points_mode,
    category_orders={"グループ": category_order},
)
fig.update_layout(
    xaxis_title="グループ",
    yaxis_title=f"{col_y}",
    margin=dict(l=10, r=10, t=30, b=10),
    boxmode="group",
)

st.plotly_chart(fig, use_container_width=True)

# -----------------------------
# 要約統計
# -----------------------------
if show_stats:
    st.subheader("各グループの要約")
    desc = work.groupby("グループ")["値"].describe().rename(columns={
        "count": "件数",
        "mean": "平均",
        "std": "標準偏差",
        "min": "最小値",
        "25%": "第1四分位(Q1)",
        "50%": "中央値",
        "75%": "第3四分位(Q3)",
        "max": "最大値",
    })
    st.dataframe(desc, use_container_width=True)

# -----------------------------
# ダウンロード（現在の加工済みデータ）
# -----------------------------
@st.cache_data
def to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8-sig")

csv_bytes = to_csv_bytes(work.assign(**{"Y列名": col_y}))
st.download_button(
    label="📥 この図の元データをCSVで保存",
    data=csv_bytes,
    file_name="boxplot_data.csv",
    mime="text/csv",
)

st.caption(
    "ヒント：『外れ値を除外（IQR方式）』は各グループごとにQ1, Q3, IQR=Q3-Q1を計算し、[Q1-1.5×IQR, Q3+1.5×IQR]の外を除外します。\n"
    "『外れ値点を描画』をオンにすると、箱の外に点を表示します（除外チェックがONのときは除外後データに対して点を表示）。"
)

# =============================
# requirements.txt（同リポジトリに配置）
# =============================
# streamlit
# pandas
# numpy
# plotly
# openpyxl  # Excel読み込み用

# =============================
# README.md（同リポジトリに配置・参考）
# =============================
# # 箱ひげ図アプリ
# ユーザーがExcel/CSVをアップロードし、チーム/ポジション/年齢帯でグループ化した箱ひげ図を作るStreamlitアプリです。
#
# ## 使い方
# 1. このリポジトリをGitHubに作成し、`streamlit_app.py` と `requirements.txt` を配置します。
# 2. ローカル動作: `pip install -r requirements.txt` → `streamlit run streamlit_app.py`
# 3. クラウド公開（Streamlit Community Cloud）:
#    - https://share.streamlit.io にGitHub連携し、本リポジトリを選択。
#    - Main file path に `streamlit_app.py` を指定してDeploy。
#
# ## データの前提
# - Y軸にする数値列（例：Salary, Score など）が必要です。
# - チーム列/ポジション列は任意。年齢帯は「年齢」列から自動生成できます（"25歳" のような文字列もOK）。
#
# ## よくある調整
# - 外れ値の定義（1.5×IQR）は一般的な規約です。必要があればコード中の倍率を変更してください。
# - グループ順を固定したい場合は、`category_order` の設定を明示的に書き換えてください。
#
# ## ライセンス
# - 教育目的で自由にお使いください。
