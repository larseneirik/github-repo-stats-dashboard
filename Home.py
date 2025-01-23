# app.py
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta

from utils import (
    fetch_pypi_stats,
    fetch_github_stats_api,
    fetch_lifetime_downloads
)

# Set page config (only do this in the main file)
st.set_page_config(
    page_title="Package Analytics Dashboard",
    page_icon="📊",
    layout="wide"
)

st.title("Package Analytics Dashboard")

# Session state to hold GitHub repo data
if 'repo_data' not in st.session_state:
    st.session_state.repo_data = None

# Sidebar controls
with st.sidebar:
    st.header("Settings")
    package = st.text_input("Package Name", value="crewai")
    github_repo = st.text_input("GitHub Repository", value="crewAIInc/crewAI")
    
    date_range = st.selectbox(
        "Preset Date Ranges",
        ["Last 7 days", "Last 30 days", "Last 90 days", "Last 365 days", "Custom"]
    )
    
    if date_range == "Custom":
        start_date = st.date_input("Start Date", datetime.now() - timedelta(days=30))
        end_date = st.date_input("End Date", datetime.now())
    else:
        days = {
            "Last 7 days": 7,
            "Last 30 days": 30,
            "Last 90 days": 90,
            "Last 365 days": 365
        }
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=days[date_range])

    granularity = st.selectbox(
        "Time Granularity",
        ["daily", "weekly", "monthly"]
    )

    show_moving_average = st.checkbox("Show Moving Average", True)
    if show_moving_average:
        ma_window = st.slider("Moving Average Window", 2, 30, 7)

if st.sidebar.button("Fetch Stats"):
    with st.spinner("Fetching statistics..."):
        try:
            # Fetch lifetime total downloads
            lifetime_downloads = fetch_lifetime_downloads(package)
            
            # Fetch PyPI stats for the selected date range
            df_pypi = fetch_pypi_stats(package, start_date, end_date, granularity)
            
            # Fetch GitHub stats
            df_github, repo_data = fetch_github_stats_api(github_repo)
            
            # Store repo_data in session state
            st.session_state.repo_data = repo_data
            
            if df_pypi is not None and df_github is not None:
                # ---- Quick Package Info ----
                with st.expander("📌 Quick Package Info", expanded=False):
                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown(f"""
                        - 📅 **Created**: {pd.to_datetime(repo_data['created_at']).strftime('%Y-%m-%d')}
                        - 🔄 **Last Updated**: {pd.to_datetime(repo_data['updated_at']).strftime('%Y-%m-%d')}
                        """)
                    with col2:
                        st.markdown(f"""
                        - 💻 **Language**: {repo_data['language']}
                        - 📜 **License**: {repo_data.get('license', {}).get('name', 'Not specified')}
                        """)
                    if repo_data['description']:
                        st.markdown(f"📝 **Description**: {repo_data['description']}")

                # ---- Calculate Metrics ----
                today = df_pypi.iloc[-1] if not df_pypi.empty else pd.Series({'date': None, 'downloads': 0})
                yesterday = df_pypi.iloc[-2] if len(df_pypi) > 1 else pd.Series({'date': None, 'downloads': 0})
                
                total_downloads = lifetime_downloads  # lifetime
                avg_downloads = df_pypi['downloads'].mean()
                max_downloads = df_pypi['downloads'].max()
                
                daily_change = today['downloads'] - yesterday['downloads']
                avg_last_week = df_pypi.tail(7)['downloads'].mean()
                avg_previous_week = df_pypi.tail(14).head(7)['downloads'].mean() if len(df_pypi) >= 14 else 0
                avg_change = avg_last_week - avg_previous_week
                
                current_peak = today['downloads']
                previous_peak = df_pypi[:-1]['downloads'].max() if len(df_pypi) > 1 else 0
                peak_change = current_peak - previous_peak

                # GitHub metrics
                stars_change = 0
                forks_change = 0
                if len(df_github) >= 7:
                    stars_change = repo_data['stargazers_count'] - df_github['stars'].iloc[-7]
                    forks_change = repo_data['forks_count'] - df_github['forks'].iloc[-7]
                
                stars_df = pd.DataFrame(repo_data['stars_history'])
                if not stars_df.empty:
                    stars_df['date'] = pd.to_datetime(stars_df['date']).dt.date
                    current_date = datetime.now().date()
                    last_week_stars = stars_df[stars_df['date'] >= (current_date - timedelta(days=7))]['stars'].sum()
                    previous_week_stars = stars_df[
                        (stars_df['date'] >= (current_date - timedelta(days=14))) &
                        (stars_df['date'] < (current_date - timedelta(days=7)))
                    ]['stars'].sum()
                else:
                    last_week_stars, previous_week_stars = 0, 0

                # ---- Key Metrics Overview ----
                st.header("📊 Key Metrics Overview")
                st.divider()

                # 1) PyPI Stats
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric(
                        "Total Downloads", 
                        f"{total_downloads:,.0f}",
                        f"{today['downloads']:+,.0f} today",
                        help="Total number of package downloads"
                    )
                with col2:
                    st.metric(
                        "Daily Downloads", 
                        f"{today['downloads']:,.0f}",
                        f"{daily_change:+,.0f} vs yesterday",
                        help="Number of downloads in the last 24 hours"
                    )
                with col3:
                    st.metric(
                        "Weekly Average", 
                        f"{avg_last_week:,.0f}",
                        f"{avg_change:+,.0f} vs last week",
                        help="Average daily downloads over the past 7 days"
                    )
                with col4:
                    st.metric(
                        "Peak Downloads", 
                        f"{max_downloads:,.0f}",
                        f"{peak_change:+,.0f} from previous",
                        help="Highest number of downloads in a single day"
                    )

                # 2) GitHub Stats
                st.markdown("---")
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric(
                        "Total GitHub Stars", 
                        f"{repo_data['stargazers_count']:,}",
                        f"{stars_change:+,} this week",
                        help="Total number of GitHub stars"
                    )
                with col2:
                    st.metric(
                        "Stars This Week",
                        f"{last_week_stars:,}",
                        f"{last_week_stars - previous_week_stars:+,} vs prev.",
                        help="Stars gained in the last 7 days"
                    )
                with col3:
                    st.metric(
                        "Avg Stars/Day",
                        f"{stars_df['stars'].mean():.1f}" if not stars_df.empty else "0",
                        help="Average daily stars"
                    )
                with col4:
                    peak_stars_day = stars_df['stars'].max() if not stars_df.empty else 0
                    peak_stars_date = stars_df.loc[stars_df['stars'].idxmax(), 'date'] if not stars_df.empty else "N/A"
                    st.metric(
                        "Peak Stars/Day",
                        f"{peak_stars_day:,}",
                        f"on {peak_stars_date}",
                        help="Most stars received in a single day"
                    )

                # 3) Repository Stats
                st.markdown("---")
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric(
                        "Forks",
                        f"{repo_data['forks_count']:,}",
                        f"{forks_change:+,} this week",
                        help="Number of repository forks"
                    )
                with col2:
                    st.metric(
                        "Contributors",
                        f"{repo_data['total_contributors']:,}",
                        help="Total number of contributors"
                    )
                with col3:
                    st.metric(
                        "Releases",
                        f"{repo_data['total_releases']:,}",
                        help="Total number of releases"
                    )
                with col4:
                    st.metric(
                        "Open Issues",
                        f"{repo_data['open_issues_count']:,}",
                        help="Number of open issues"
                    )

                # ---- Detailed Charts ----
                st.header("📈 Detailed Statistics")
                # Download chart
                st.subheader("Download Trends")
                fig_downloads = go.Figure()
                fig_downloads.add_trace(go.Scatter(
                    x=df_pypi['date'],
                    y=df_pypi['downloads'],
                    name='Downloads',
                    mode='lines',
                    line=dict(color='blue')
                ))

                if show_moving_average:
                    df_pypi['MA'] = df_pypi['downloads'].rolling(window=ma_window).mean()
                    fig_downloads.add_trace(go.Scatter(
                        x=df_pypi['date'],
                        y=df_pypi['MA'],
                        name=f'{ma_window}-day Moving Average',
                        line=dict(color='red', dash='dash')
                    ))

                fig_downloads.update_layout(
                    title=f'Downloads Over Time',
                    xaxis_title='Date',
                    yaxis_title='Downloads',
                    hovermode='x unified'
                )
                st.plotly_chart(fig_downloads, use_container_width=True)

                # Stars chart
                st.subheader("Stars Growth")
                if 'stars_history' in repo_data and repo_data['stars_history']:
                    stars_df = pd.DataFrame(repo_data['stars_history'])
                    fig_stars = go.Figure()
                    fig_stars.add_trace(go.Scatter(
                        x=stars_df['date'],
                        y=stars_df['cumulative_stars'],
                        name='Total Stars',
                        mode='lines',
                        line=dict(color='goldenrod')
                    ))
                    fig_stars.add_trace(go.Bar(
                        x=stars_df['date'],
                        y=stars_df['stars'],
                        name='New Stars',
                        marker_color='gold',
                        yaxis='y2'
                    ))
                    fig_stars.update_layout(
                        title='Stars Growth Over Time',
                        xaxis_title='Date',
                        yaxis_title='Total Stars',
                        yaxis2=dict(
                            title='New Stars',
                            overlaying='y',
                            side='right'
                        ),
                        hovermode='x unified',
                        showlegend=True
                    )
                    st.plotly_chart(fig_stars, use_container_width=True)

        except Exception as e:
            st.error(f"Error fetching data: {str(e)}")


# ---- Releases Section ----
st.header("Release History")
with st.expander("📦 View All Releases", expanded=False):
    if st.session_state.repo_data and st.session_state.repo_data.get('releases_data'):
        releases = st.session_state.repo_data['releases_data']
        release_options = [
            f"📦 {r['tag_name']} - {datetime.strptime(r['published_at'], '%Y-%m-%dT%H:%M:%SZ').strftime('%Y-%m-%d')}"
            for r in releases
        ]
        selected_release = st.selectbox("Select a release to view details", release_options)
        selected_index = release_options.index(selected_release)
        release = releases[selected_index]
        
        st.markdown("---")
        body = release['body']
        if "What's Changed" in body:
            sections = body.split('\n\n')
            for section in sections:
                if section.strip():
                    if section.startswith("What's Changed"):
                        st.markdown("### 🔄 What's Changed")
                    elif section.startswith("New Contributors"):
                        st.markdown("### 👥 New Contributors")
                    else:
                        st.markdown(section)
                    st.markdown("---")
        else:
            st.markdown(body)
    else:
        st.info("No releases found for this package.")
