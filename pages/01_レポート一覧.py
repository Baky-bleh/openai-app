import pandas as pd
import streamlit as st
from utils.data_io import load_records

st.header("📊 レポート一覧")

# ---------- データ読み込み -------------
records = load_records()
st.caption(f"🗂️ 取得レコード数: {len(records)}")

if not records:
    st.info("まだデータがありません。左の『📝 レポート生成』で追加してください。")
    st.stop()

df = pd.DataFrame(records)

# ----------- 最小フィルタ（名前キーワード） -----------
kw = st.text_input("レポート名キーワードでフィルタ", key="kw")
if kw:
    df = df[df["レポート名"].str.contains(kw, na=False)]

# ----------- ソート -----------
sort_col = st.selectbox("Sort by", df.columns.tolist(), index=0)
ascending = st.checkbox("昇順", value=True)

df = df.sort_values(
    sort_col,
    ascending=ascending,
    key=lambda s: s.astype(str) if s.dtype == "object" else s,
)

# ----------- 表示 -----------
st.dataframe(df, use_container_width=True, hide_index=True)

if st.button("🔄 最新データを読み込み直す"):
    st.rerun()