import streamlit as st
from supabase import create_client, Client
import pandas as pd
from datetime import datetime, timedelta
import uuid

# ====================== SUPABASE CONFIG ======================
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

st.set_page_config(page_title="Paediatrics On-call Roster", layout="wide", page_icon="🏥")

st.title("🏥 Paediatrics On-call Roster")

# ====================== AUTO MONTH DETECTION ======================
@st.cache_data(ttl=300)
def get_available_months():
    response = supabase.table("oncall_roster").select("month, year").execute()
    df = pd.DataFrame(response.data)
    if df.empty:
        return [], []
    months_df = df.drop_duplicates().sort_values(["year", "month"])
    month_names, month_keys = [], []
    for _, row in months_df.iterrows():
        month_name = datetime(row['year'], row['month'], 1).strftime("%B %Y")
        month_names.append(month_name)
        month_keys.append((row['month'], row['year']))
    return month_names, month_keys

month_names, month_keys = get_available_months()

if not month_names:
    st.error("No data found.")
    st.stop()

# ====================== SIDEBAR (Only Month) ======================
st.sidebar.header("📅 Month")
current_month = datetime.now().month
current_year = datetime.now().year
default_index = next((i for i, (m, y) in enumerate(month_keys) if m == current_month and y == current_year), len(month_names) - 1)

selected_month_name = st.sidebar.selectbox("Select Month", month_names, index=default_index)
selected_index = month_names.index(selected_month_name)
selected_month, selected_year = month_keys[selected_index]

st.caption(f"Department of Paediatrics • Hospital Sultanah Bahiyah • {selected_month_name}")

# ====================== LOAD DATA ======================
@st.cache_data(ttl=300)
def load_data(month, year):
    response = supabase.table("oncall_roster").select("*").eq("month", month).eq("year", year).order("date").execute()
    df = pd.DataFrame(response.data)
    if not df.empty:
        df['date'] = pd.to_datetime(df['date']).dt.date
        for col in ['id', 'month', 'year']:
            if col in df.columns:
                df = df.drop(columns=[col])
    return df

df = load_data(selected_month, selected_year)

# ====================== FILTER SECTION (Main Page) ======================
with st.expander("🔍 Search & Filters", expanded=True):
    col1, col2 = st.columns([3, 1])
    
    with col1:
        search_name = st.text_input("Search Staff Name", placeholder="e.g. Athirah, Tan KA, Eric", label_visibility="collapsed")
    
    with col2:
        show_solo_only = st.checkbox("Show only solo shifts", value=False)

# ====================== FILTER DATA ======================
filtered_df = df.copy()

columns_to_search = ['ward', 'nicu', 'scn', 'picu', 'passive', 'specialist', 'neonatologist', 'consultant']
for col in columns_to_search:
    if col in filtered_df.columns:
        filtered_df[col] = filtered_df[col].replace('NA', '').fillna('')

if search_name:
    search_clean = search_name.strip().upper()
    if search_clean == "NA":
        filtered_df = filtered_df.iloc[0:0]
    else:
        search_lower = search_name.lower().strip()
        def name_exists(val):
            if pd.isna(val) or val == '':
                return False
            return search_lower in [n.strip().lower() for n in str(val).split(',')]
        mask = (
            filtered_df['ward'].apply(name_exists) |
            filtered_df['nicu'].apply(name_exists) |
            filtered_df['scn'].apply(name_exists) |
            filtered_df['picu'].apply(name_exists) |
            filtered_df['passive'].apply(name_exists) |
            filtered_df['specialist'].apply(name_exists) |
            filtered_df['neonatologist'].apply(name_exists) |
            filtered_df['consultant'].apply(name_exists)
        )
        filtered_df = filtered_df[mask]

if show_solo_only:
    # Simple solo detection (you can improve this logic later)
    solo_mask = filtered_df.apply(
        lambda row: all(
            len([x.strip() for x in str(row.get(col, '')).split(',') if x.strip()]) <= 1 
            for col in ['ward', 'nicu', 'scn', 'picu']
        ), axis=1
    )
    filtered_df = filtered_df[solo_mask]

# ====================== MAIN CONTENT ======================
if search_name or show_solo_only:
    if not filtered_df.empty:
        st.subheader(f"Results ({len(filtered_df)} days)")

        for _, row in filtered_df.iterrows():
            section = next((col.upper() for col in ['ward','nicu','scn','picu','passive','specialist','neonatologist','consultant']
                           if pd.notna(row[col]) and (search_name.lower() in str(row[col]).lower() if search_name else True)), None)
            
            if not section:
                continue

            date_str = row['date'].strftime('%d %b %Y (%a)')
            title = f"{date_str} | {section}"

            if section == "PASSIVE":
                st.markdown(f"**🟣 {title}**")
                continue

            with st.expander(title, expanded=False):
                st.write(f"**Date:** {date_str}")
                st.write(f"**Section:** {section}")

                if section in ["CONSULTANT", "NEONATOLOGIST", "SPECIALIST"]:
                    def format_value(val):
                        if pd.isna(val) or val == '' or val == 'NA':
                            return '<span style="color:grey; font-style:italic;">not available</span>'
                        return val
                    st.markdown("**Team Composition:**")
                    for c in ['specialist','ward','nicu','scn','picu','passive','consultant','neonatologist']:
                        st.markdown(f"- **{c.title()}:** {format_value(row.get(c))}", unsafe_allow_html=True)
                else:
                    teammates = [t.strip() for t in str(row.get(section.lower(), '')).split(',') if search_name.lower() not in t.lower()]
                    st.write(f"**Teammates:** {', '.join(teammates) if teammates else '—'}")
                    st.write(f"**Consultant:** {row.get('consultant', '—')}")
                    st.write(f"**Neonatologist:** {row.get('neonatologist', '—')}")
    else:
        st.info("No matching records found.")
else:
    # Default view - show full roster
    if not df.empty:
        display_df = df.copy()
        display_df['date'] = pd.to_datetime(display_df['date']).dt.strftime('%d %b %Y')
        st.dataframe(display_df, use_container_width=True, hide_index=True)
    else:
        st.info("No data available for this month.")

# ====================== CALENDAR EXPORT ======================
st.divider()
st.subheader("📅 Export to Calendar")

if st.download_button(
    "📅 Export to Google Calendar / Apple Calendar",
    data="",
    file_name="oncall_calendar.ics",
    mime="text/calendar",
    use_container_width=True
):
    st.success("Calendar export feature coming soon!")

st.caption("Hospital Sultanah Bahiyah • Paediatrics Department")