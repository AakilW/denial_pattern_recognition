import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import plotly.graph_objects as go
import re

st.set_page_config(page_title="Denial Reason Analyzer", layout="wide")
st.title("📊 Denial Reason Analyzer")

file1 = st.file_uploader("Upload First Excel File", type=["xlsx"])
file2 = st.file_uploader("Upload Second Excel File", type=["xlsx"])

if file1 and file2:
    df1 = pd.read_excel(file1, header=1)
    df2 = pd.read_excel(file2, header=1)
    df = pd.concat([df1, df2], ignore_index=True)
    st.success(f"✅ Combined data shape: {df.shape}")

    # ---------------- Cleaning Function ---------------- #
    def clean_reason_code(row):
        codes = str(row['Reason Codes']).replace(";", ",").replace(" ", "").split(',')
        descs = str(row['Reason Code Descriptions']).split(',')
        codes = [c.strip() for c in codes if c.strip() and c.strip().upper() != 'NAN']

        if not codes:
            return pd.Series(["MISSING", "MISSING"])

        exclude_trivial = {"PR1", "PR2", "PR3", "PR100", "CO253"}
        codes = [c for c in codes if c not in exclude_trivial]

        # Priority selection logic
        if "CO109" in codes or "PR109" in codes:
            selected_code = "CO109"
        elif "CO96" in codes and "OA97" in codes:
            selected_code = "CO96"
        else:
            exclude_secondary = {"CO45", "OA94", "PR94", "CO94"}
            filtered = [c for c in codes if c not in exclude_secondary]
            codes_to_consider = filtered if filtered else codes

            selected_code = None
            for prefix in ["CO", "PR", "PI", "OA"]:
                found = [c for c in codes_to_consider if c.startswith(prefix)]
                if found:
                    selected_code = found[0]
                    break

            if not selected_code:
                selected_code = codes_to_consider[0] if codes_to_consider else "MISSING"

        # Description extraction
        if selected_code in codes and len(descs) >= codes.index(selected_code) + 1:
            desc_text = descs[codes.index(selected_code)].strip()
        else:
            desc_text = descs[0].strip() if descs else "MISSING"

        return pd.Series([selected_code, desc_text])

    df[['Cleaned Code', 'Cleaned Description']] = df.apply(clean_reason_code, axis=1)
    df['Cleaned Code'] = df['Cleaned Code'].fillna("MISSING")
    df['Cleaned Description'] = df['Cleaned Description'].fillna("MISSING")

    # ---------------- Prefix Normalization ---------------- #
    def normalize_prefix(code):
        if not isinstance(code, str):
            return code
        code = code.strip().upper()
        if re.match(r'^(PR|PI|PIB|OA)\d+', code):
            return re.sub(r'^(PR|PI|PIB|OA)', 'CO', code)
        return code

    df['Normalized Code'] = df['Cleaned Code'].apply(normalize_prefix)

    # ---------------- Map CO Descriptions ---------------- #
    co_map = df[df['Cleaned Code'].str.startswith('CO')][['Cleaned Code', 'Cleaned Description']]
    co_map = co_map.drop_duplicates(subset=['Cleaned Code'])
    co_dict = dict(zip(co_map['Cleaned Code'], co_map['Cleaned Description']))

    def get_final_description(row):
        code = row['Normalized Code']
        if code in co_dict:
            return co_dict[code]
        else:
            return row['Cleaned Description']

    df['Final Description'] = df.apply(get_final_description, axis=1)

    # ---------------- Group & Aggregate ---------------- #
    final_summary = (
        df.groupby(['Normalized Code', 'Final Description'])['Visit #']
        .nunique()
        .reset_index()
        .rename(columns={'Visit #': 'Distinct Claims'})
        .sort_values(by='Distinct Claims', ascending=False)
    )

    # ---------------- Tabs ---------------- #
    tab1, tab2 = st.tabs(["📑 Summary Table", "🥧 3D Pie Chart"])

    with tab1:
        st.subheader("Unique Denial Code (Normalized to CO) vs Distinct Claims")
        st.dataframe(final_summary, use_container_width=True)

        st.download_button(
            "⬇️ Download Cleaned Data (Excel)",
            data=final_summary.to_csv(index=False).encode('utf-8'),
            file_name="cleaned_denial_summary.csv",
            mime="text/csv"
        )

    with tab2:
        st.subheader("Top 10 Denial Reasons (3D Pie Chart)")
        top10 = final_summary.head(10)
        others_sum = final_summary['Distinct Claims'][10:].sum()

        if others_sum > 0:
            others = pd.DataFrame({
                'Normalized Code': ['Others'],
                'Final Description': ['All remaining reasons'],
                'Distinct Claims': [others_sum]
            })
            final_df = pd.concat([top10, others], ignore_index=True)
        else:
            final_df = top10

        # ---------------- 3D Pie Chart using Plotly ---------------- #
        fig = go.Figure(
            data=[go.Pie(
                labels=final_df['Normalized Code'],
                values=final_df['Distinct Claims'],
                hole=0.2,
                textinfo='label+percent',
                pull=[0.05]*len(final_df),
                marker=dict(line=dict(color='#000000', width=1)),
            )]
        )

        # 3D effect styling
        fig.update_traces(
            textfont_size=14,
            hoverinfo='label+value+percent',
            rotation=60
        )
        fig.update_layout(
            title="Top 10 Denial Reasons (3D Styled)",
            title_font=dict(size=20),
            showlegend=True,
            template="plotly_dark",
            height=700
        )

        st.plotly_chart(fig, use_container_width=True)
