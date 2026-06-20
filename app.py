import streamlit as st
from supabase import create_client, Client
import pandas as pd
from datetime import datetime, timedelta
import uuid

# ====================== SUPABASE CONFIG ======================
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

st.set_page_config(
    page_title="Paediatrics On-call Roster",
    layout="wide",
    page_icon="🏥",
    initial_sidebar_state="expanded"
)

# ====================== MOBILE-FRIENDLY CSS ======================
st.markdown("""
<style>
    .stExpander {
        border: 1px solid #e0e0e0;
        border-radius: 8px;
        margin-bottom: 8px;
    }
    .team-row {
        padding: 6px 0;
        border-bottom: 1px solid #f0f0f0;
    }
    .team-row:last-child {
        border-bottom: none;
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

# ====================== MONTH SELECTOR ======================
st.sidebar.header("📅 Select Month")

current_month = datetime.now().month
current_year = datetime.now().year
default_index = next((i for i, (m, y) in enumerate(month_keys) if m == current_month and y == current_year), len(month_names) - 1)

selected_month_name = st.sidebar.selectbox("Month", month_names, index=default_index)
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

# ====================== SIDEBAR SEARCH ======================
st.sidebar.header("🔍 Search Staff")
search_name = st.sidebar.text_input("Enter Staff Name", placeholder="e.g. Athirah, Tan KA, Eric")

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

# ====================== MAIN VIEW ======================
if search_name:
    if not filtered_df.empty:
        st.subheader(f"📋 {search_name}'s On-call Schedule ({selected_month_name})")

        solo_shifts = []

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
            is_solo = len(teammates_list) == 0

            if is_solo and section not in ["CONSULTANT", "NEONATOLOGIST", "SPECIALIST", "PASSIVE"]:
                solo_shifts.append(f"{date_str} - {section}")

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

        if solo_shifts:
            warning_text = "⚠️ You have solo on-call shifts on:\n"
            for shift in solo_shifts:
                warning_text += f"- {shift}\n"
            st.sidebar.warning(warning_text)

    else:
        st.warning(f"No on-call records found for **{search_name}** in {selected_month_name}.")

else:
    if not df.empty:
        display_df = df.copy()
        display_df['date'] = pd.to_datetime(display_df['date']).dt.strftime('%d %B %Y')

        st.dataframe(
            display_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "date": st.column_config.TextColumn("Date", width="medium"),
                "day_name": st.column_config.TextColumn("Day", width="small"),
            }
        )
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

if st.download_button(
    label="📅 Export to Google Calendar / Apple Calendar",
    data=generate_ics(filtered_df, search_name=search_name if export_type == "Only for searched person" else None),
    file_name=f"{search_name}_{selected_month_name.replace(' ', '_')}.ics" if search_name else f"oncall_{selected_month_name.replace(' ', '_')}.ics",
    mime="text/calendar",
    use_container_width=True
):
    st.success("Calendar file downloaded!")

st.caption("Data source: Department of Paediatrics, Hospital Sultanah Bahiyah")