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

# ====================== MOBILE CSS ======================
st.markdown("""
<style>
    .stExpander {
        border: 1px solid #e0e0e0;
        border-radius: 8px;
        margin-bottom: 8px;
    }
    @media (max-width: 768px) {
        .stButton button {
            width: 100% !important;
        }
    }
</style>
""", unsafe_allow_html=True)

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
    st.error("No data found in the database.")
    st.stop()

# ====================== MONTH SELECTOR (Main Page) ======================
col1, col2 = st.columns([1, 3])
with col1:
    current_month = datetime.now().month
    current_year = datetime.now().year
    default_index = next((i for i, (m, y) in enumerate(month_keys) if m == current_month and y == current_year), len(month_names) - 1)
    
    selected_month_name = st.selectbox("📅 Month", month_names, index=default_index)
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

# ====================== SEARCH & FILTERS (Main Page) ======================
with st.expander("🔍 Search & Filters", expanded=True):
    search_name = st.text_input("Search Staff Name", placeholder="e.g. Athirah, Tan KA, Eric", label_visibility="collapsed")

# ====================== FILTER DATA ======================
filtered_df = df.copy()

columns_to_search = ['ward', 'nicu', 'scn', 'picu', 'passive', 'specialist', 'neonatologist', 'consultant']
for col in columns_to_search:
    if col in filtered_df.columns:
        filtered_df[col] = filtered_df[col].replace('NA', '').fillna('')

solo_shifts = []

if search_name:
    search_clean = search_name.strip().upper()
    
    if search_clean == "NA":
        filtered_df = filtered_df.iloc[0:0]
    else:
        search_lower = search_name.lower().strip()
        
        def name_exists(cell_value):
            if pd.isna(cell_value) or cell_value == '':
                return False
            names = [name.strip().lower() for name in str(cell_value).split(',')]
            return search_lower in names
        
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

        # Detect solo shifts
        for _, row in filtered_df.iterrows():
            section = None
            section_columns = ['ward', 'nicu', 'scn', 'picu', 'passive', 'specialist', 'neonatologist', 'consultant']
            
            for col in section_columns:
                if pd.notna(row[col]) and search_name.lower() in str(row[col]).lower():
                    section = col.upper()
                    break

            if section and section not in ["CONSULTANT", "NEONATOLOGIST", "SPECIALIST", "PASSIVE"]:
                teammates_raw = row.get(section.lower(), "")
                teammates_list = [t.strip() for t in str(teammates_raw).split(",") 
                                  if search_name.lower() not in t.lower()]
                if len(teammates_list) == 0:
                    date_str = row['date'].strftime('%d %B %Y (%a)')
                    solo_shifts.append(f"{date_str} - {section}")

# ====================== WARNING (Right below filter box) ======================
if solo_shifts:
    st.warning("⚠️ You have solo on-call shifts on:\n" + "\n".join([f"- {s}" for s in solo_shifts]))

# ====================== MAIN VIEW ======================
if search_name:
    if not filtered_df.empty:
        st.subheader(f"📋 {search_name}'s On-call Schedule ({selected_month_name})")

        for _, row in filtered_df.iterrows():
            section = None
            section_columns = ['ward', 'nicu', 'scn', 'picu', 'passive', 'specialist', 'neonatologist', 'consultant']
            
            for col in section_columns:
                if pd.notna(row[col]) and search_name.lower() in str(row[col]).lower():
                    section = col.upper()
                    break

            if section is None:
                continue

            date_str = row['date'].strftime('%d %B %Y (%a)')

            teammates_raw = row.get(section.lower(), "")
            teammates_list = [t.strip() for t in str(teammates_raw).split(",") 
                              if search_name.lower() not in t.lower()]

            title_parts = [date_str]
            if section in ["CONSULTANT", "NEONATOLOGIST"]:
                if section == "CONSULTANT" and pd.notna(row['neonatologist']):
                    title_parts.append(f"| Neonatologist: {row['neonatologist']}")
                elif section == "NEONATOLOGIST" and pd.notna(row['consultant']):
                    title_parts.append(f"| Consultant: {row['consultant']}")
            else:
                title_parts.append(f"| {section}")
                if pd.notna(row['consultant']):
                    title_parts.append(f"| Consultant: {row['consultant']}")
                if pd.notna(row['neonatologist']):
                    title_parts.append(f"| Neonatologist: {row['neonatologist']}")

            expander_title = " ".join(title_parts)

            if section == "PASSIVE":
                st.markdown(
                    f"""
                    <div style="
                        background-color: #f3e5f5; 
                        border-left: 5px solid #9c27b0; 
                        padding: 10px 14px; 
                        border-radius: 6px; 
                        margin-bottom: 10px;
                    ">
                        <b style="color:#4a148c; font-size:15px;">🟣 PASSIVE ON-CALL</b><br>
                        <span style="color:#4a148c; font-size:15px;"><b>{expander_title}</b></span>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
                continue

            with st.expander(expander_title, expanded=False):
                st.markdown(f"**Date:** {date_str}")
                st.markdown(f"**Section:** {section}")

                if section in ["CONSULTANT", "NEONATOLOGIST", "SPECIALIST"]:
                    def format_value(val):
                        if pd.isna(val) or val == '' or val == 'NA':
                            return '<span style="color:grey; font-style:italic;">not available</span>'
                        return val

                    st.markdown("**Team Composition:**")
                    st.markdown(f"- **Specialist:** {format_value(row.get('specialist'))}")
                    st.markdown(f"- **Ward:** {format_value(row.get('ward'))}")
                    st.markdown(f"- **NICU:** {format_value(row.get('nicu'))}")
                    st.markdown(f"- **SCN:** {format_value(row.get('scn'))}")
                    st.markdown(f"- **PICU:** {format_value(row.get('picu'))}")
                    st.markdown(f"- **Passive:** {format_value(row.get('passive'))}")
                    st.markdown(f"- **Consultant:** {format_value(row.get('consultant'))}")
                    st.markdown(f"- **Neonatologist:** {format_value(row.get('neonatologist'))}")
                else:
                    teammates_str = ", ".join(teammates_list) if teammates_list else "—"
                    st.markdown(f"**Teammates in {section}:** {teammates_str}")
                    st.markdown(f"**Consultant:** {row['consultant']}")
                    st.markdown(f"**Neonatologist:** {row['neonatologist']}")

    else:
        st.warning(f"No on-call records found for **{search_name}** in {selected_month_name}.")

else:
    if not df.empty:
        display_df = df.copy()
        display_df['date'] = pd.to_datetime(display_df['date']).dt.strftime('%d %B %Y')
        st.dataframe(display_df, use_container_width=True, hide_index=True)
    else:
        st.info(f"No data available for {selected_month_name}.")

# ====================== ONE-CLICK CALENDAR EXPORT ======================
st.divider()
st.subheader("📅 Export to Calendar")

if search_name:
    export_type = st.radio(
        "Export options:",
        options=["All shown dates", "Only for searched person"],
        horizontal=True
    )
else:
    export_type = "All shown dates"

def get_staff_location(row, name):
    columns = ['ward', 'nicu', 'scn', 'picu', 'passive', 'specialist', 'neonatologist', 'consultant']
    name_lower = name.lower()
    for col in columns:
        if pd.notna(row[col]) and name_lower in str(row[col]).lower():
            if col in ['consultant', 'neonatologist']:
                return None
            return col.upper()
    return None

def generate_ics(dataframe, search_name=None):
    ics_content = "BEGIN:VCALENDAR\n"
    ics_content += "VERSION:2.0\n"
    ics_content += "PRODID:-//Hospital Sultanah Bahiyah//Paediatrics On-call//EN\n"
    ics_content += "CALSCALE:GREGORIAN\n"
    ics_content += "METHOD:PUBLISH\n"

    for _, row in dataframe.iterrows():
        event_date = row['date']
        start = datetime.combine(event_date, datetime.min.time())
        end = start + timedelta(days=1)
        uid = str(uuid.uuid4())

        if search_name:
            location = get_staff_location(row, search_name)
            if location:
                summary = f"{search_name} - Oncall - {location}"
            else:
                summary = f"{search_name} - Oncall"
        else:
            summary = f"On-call Roster ({row['day_name']})"

        description = (
            f"Ward: {row['ward']}\\n"
            f"NICU: {row['nicu']}\\n"
            f"SCN: {row['scn']}\\n"
            f"PICU: {row['picu']}\\n"
            f"Passive: {row['passive']}\\n"
            f"Specialist: {row['specialist']}\\n"
            f"Neonatologist: {row['neonatologist']}\\n"
            f"Consultant: {row['consultant']}"
        )

        ics_content += "BEGIN:VEVENT\n"
        ics_content += f"UID:{uid}\n"
        ics_content += f"DTSTART;VALUE=DATE:{start.strftime('%Y%m%d')}\n"
        ics_content += f"DTEND;VALUE=DATE:{end.strftime('%Y%m%d')}\n"
        ics_content += f"SUMMARY:{summary}\n"
        ics_content += f"DESCRIPTION:{description}\n"
        ics_content += "STATUS:CONFIRMED\n"
        ics_content += "TRANSP:TRANSPARENT\n"
        ics_content += "END:VEVENT\n"

    ics_content += "END:VCALENDAR"
    return ics_content

# Two-step export (better for iPhone Safari)
if st.button("📅 Generate Calendar File (.ics)", use_container_width=True):
    if filtered_df.empty:
        st.warning("No data available to export.")
    else:
        if export_type == "Only for searched person" and search_name:
            ics_data = generate_ics(filtered_df, search_name=search_name)
        else:
            ics_data = generate_ics(filtered_df)

        st.download_button(
            label="⬇️ Download .ics File",
            data=ics_data,
            file_name=f"{search_name or 'oncall'}_{selected_month_name.replace(' ', '_')}.ics",
            mime="text/calendar",
            use_container_width=True
        )

st.caption("Data source: Department of Paediatrics, Hospital Sultanah Bahiyah")