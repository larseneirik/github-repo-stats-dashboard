import streamlit as st
import pandas as pd
from google.cloud import bigquery
from google.oauth2 import service_account
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import os
import json
import base64
import requests

# Initialize credentials quietly
try:
    encoded_creds = st.secrets["ENCODED_CREDS"]
    credentials_dict = json.loads(base64.b64decode(encoded_creds).decode())
    credentials = service_account.Credentials.from_service_account_info(
        credentials_dict,
        scopes=["https://www.googleapis.com/auth/cloud-platform"],
    )
    project_id = st.secrets["GOOGLE_CLOUD_PROJECT_ID"]
    github_token = st.secrets.get("GITHUB_TOKEN")  # Add GitHub token from secrets
except Exception as e:
    st.error("Error loading credentials. Please check your configuration.")
    st.stop()

@st.cache_data(ttl=60*60*24)
def fetch_pypi_stats(package_name, start_date, end_date, granularity='daily'):
    client = bigquery.Client(project=project_id, credentials=credentials)
    
    if granularity == 'hourly':
        time_group = 'DATETIME_TRUNC(timestamp, HOUR)'
        select_time = 'DATETIME(timestamp)'
    elif granularity == 'daily':
        time_group = 'DATE(timestamp)'
        select_time = 'DATE(timestamp)'
    elif granularity == 'weekly':
        time_group = 'DATE_TRUNC(DATE(timestamp), WEEK)'
        select_time = 'DATE_TRUNC(DATE(timestamp), WEEK)'
    else:  # monthly
        time_group = 'DATE_TRUNC(DATE(timestamp), MONTH)'
        select_time = 'DATE_TRUNC(DATE(timestamp), MONTH)'
    
    query = f"""
    SELECT
        {select_time} AS date,
        COUNT(*) AS downloads
    FROM
        `bigquery-public-data.pypi.file_downloads`
    WHERE
        file.project = @package_name
        AND DATE(timestamp) BETWEEN @start_date AND @end_date
    GROUP BY
        date
    ORDER BY
        date
    """
    
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("package_name", "STRING", package_name),
            bigquery.ScalarQueryParameter("start_date", "DATE", start_date),
            bigquery.ScalarQueryParameter("end_date", "DATE", end_date),
        ]
    )
    
    return client.query(query, job_config=job_config).to_dataframe()

@st.cache_data(ttl=60*60)
def fetch_github_stats_api(repo_name):
    """Fetch GitHub stats directly from GitHub API"""
    try:
        # Set up headers with authentication
        headers = {
            'Accept': 'application/vnd.github.v3+json',
            'Authorization': f'Bearer {github_token}' if github_token else '',
            'Accept-Encoding': 'gzip, deflate'
        }
        
        # Define base URL for GitHub API
        base_url = f"https://api.github.com/repos/{repo_name}"
        
        # Get repository info
        repo_response = requests.get(base_url, headers=headers)
        if repo_response.status_code != 200:
            st.error(f"Error fetching GitHub data: {repo_response.json().get('message', '')}")
            return None, None
            
        repo_data = repo_response.json()
        
        # Get all stargazers with pagination
        stars_data = []
        page = 1
        while True:
            stars_response = requests.get(
                f"{base_url}/stargazers",
                headers={**headers, 'Accept': 'application/vnd.github.star+json'},
                params={'per_page': 100, 'page': page}
            )
            if stars_response.status_code != 200 or not stars_response.json():
                break
            stars_data.extend(stars_response.json())
            page += 1
        
        # Create stars history dataframe
        if stars_data:
            stars_df = pd.DataFrame([
                {
                    'date': pd.to_datetime(star['starred_at']).date(),
                    'stars': 1
                }
                for star in stars_data
            ])
            # Fill in missing dates with zeros and ensure date types match
            date_range = pd.date_range(stars_df['date'].min(), stars_df['date'].max(), freq='D').date
            stars_df = stars_df.groupby('date')['stars'].sum().reindex(date_range, fill_value=0).reset_index()
            stars_df.columns = ['date', 'stars']
            stars_df['cumulative_stars'] = stars_df['stars'].cumsum()
            
            # Calculate daily star changes
            stars_df['star_change'] = stars_df['stars'].diff().fillna(stars_df['stars'])
        else:
            stars_df = pd.DataFrame(columns=['date', 'stars', 'cumulative_stars', 'star_change'])

        # Get commit activity for the last year
        commits_response = requests.get(f"{base_url}/stats/commit_activity", headers=headers)
        commits_data = commits_response.json() if commits_response.status_code == 200 else []
        
        # Get contributors stats
        contributors_response = requests.get(f"{base_url}/stats/contributors", headers=headers)
        contributors_data = contributors_response.json() if contributors_response.status_code == 200 else []
        
        # Get release info
        releases_response = requests.get(f"{base_url}/releases", headers=headers)
        releases_data = releases_response.json() if releases_response.status_code == 200 else []
        
        # Get pull requests
        prs_response = requests.get(f"{base_url}/pulls?state=all&per_page=100", headers=headers)
        prs_data = prs_response.json() if prs_response.status_code == 200 else []
        
        # Calculate additional metrics
        total_commits = sum(week['total'] for week in commits_data) if commits_data else 0
        total_contributors = len(contributors_data)
        total_releases = len(releases_data)
        
        # Create time series data
        dates = pd.date_range(end=datetime.now(), periods=len(commits_data), freq='W') if commits_data else []
        
        df = pd.DataFrame({
            'date': dates,
            'stars': repo_data['stargazers_count'],
            'forks': repo_data['forks_count'],
            'open_issues': repo_data['open_issues_count'],
            'watchers': repo_data['watchers_count'],
            'weekly_commits': [week['total'] for week in commits_data] if commits_data else [],
        })
        
        # Add to repo_data
        repo_data.update({
            'total_commits': total_commits,
            'total_contributors': total_contributors,
            'total_releases': total_releases,
            'commits_data': commits_data,
            'contributors_data': contributors_data,
            'releases_data': releases_data,
            'prs_data': prs_data
        })
        
        # Add stars history to repo_data
        repo_data['stars_history'] = stars_df.to_dict('records')
        
        return df, repo_data
        
    except Exception as e:
        st.error(f"Error fetching GitHub data: {str(e)}")
        return None, None

@st.cache_data(ttl=60*60*24)
def fetch_lifetime_downloads(package_name):
    """Fetch total lifetime downloads for a package"""
    client = bigquery.Client(project=project_id, credentials=credentials)
    
    query = """
    SELECT
        COUNT(*) as total_downloads
    FROM
        `bigquery-public-data.pypi.file_downloads`
    WHERE
        file.project = @package_name
    """
    
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("package_name", "STRING", package_name),
        ]
    )
    
    result = client.query(query, job_config=job_config).result()
    return next(result).total_downloads

st.title("Package Analytics Dashboard")

# Initialize session state for repo data if not exists
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

    show_raw_data = st.checkbox("Show Raw Data", False)
    show_moving_average = st.checkbox("Show Moving Average", True)
    if show_moving_average:
        ma_window = st.slider("Moving Average Window", 2, 30, 7)

@st.fragment
def show_releases():
    if st.session_state.repo_data is not None:
        st.header("Release History")
        with st.expander("📦 View All Releases", expanded=True):
            if st.session_state.repo_data['releases_data']:
                # Create a list of release options
                releases = st.session_state.repo_data['releases_data']
                release_options = [
                    f"📦 {release['tag_name']} - {datetime.strptime(release['published_at'], '%Y-%m-%dT%H:%M:%SZ').strftime('%Y-%m-%d')}"
                    for release in releases
                ]
                
                selected_release = st.selectbox(
                    "Select a release to view details",
                    release_options,
                    index=0
                )
                
                # Find and display the selected release
                selected_index = release_options.index(selected_release)
                release = releases[selected_index]
                st.markdown("---")
                
                # Display release body with better formatting
                body = release['body']
                
                # Check if it's an automated release note (contains "What's Changed")
                if "What's Changed" in body:
                    sections = body.split('\n\n')
                    for section in sections:
                        if section.strip():
                            # Add proper headers for each section
                            if section.startswith("What's Changed"):
                                st.markdown("### 🔄 What's Changed")
                            elif section.startswith("New Contributors"):
                                st.markdown("### 👥 New Contributors")
                            else:
                                st.markdown(section)
                            st.markdown("---")
                else:
                    # For manual release notes, just display as is
                    st.markdown(body)
            else:
                st.info("No releases found for this package.")

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
                # Display Quick Package Info at the top
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

                # Calculate all metrics first
                # PyPI metrics
                today = df_pypi.iloc[-1] if not df_pypi.empty else pd.Series({'date': None, 'downloads': 0})
                yesterday = df_pypi.iloc[-2] if len(df_pypi) > 1 else pd.Series({'date': None, 'downloads': 0})
                
                # Use lifetime downloads instead of date range sum
                total_downloads = lifetime_downloads
                avg_downloads = df_pypi['downloads'].mean()
                max_downloads = df_pypi['downloads'].max()
                
                daily_change = today['downloads'] - yesterday['downloads']
                avg_last_week = df_pypi.tail(7)['downloads'].mean()
                avg_previous_week = df_pypi.tail(14).head(7)['downloads'].mean()
                avg_change = avg_last_week - avg_previous_week
                
                current_peak = today['downloads']
                previous_peak = df_pypi[:-1]['downloads'].max() if len(df_pypi) > 1 else 0
                peak_change = current_peak - previous_peak

                # GitHub metrics
                stars_change = repo_data['stargazers_count'] - df_github['stars'].iloc[-7] if len(df_github) >= 7 else 0
                forks_change = repo_data['forks_count'] - df_github['forks'].iloc[-7] if len(df_github) >= 7 else 0

                # Stars metrics
                stars_df = pd.DataFrame(repo_data['stars_history'])
                if not stars_df.empty:
                    stars_df['date'] = pd.to_datetime(stars_df['date']).dt.date
                    current_date = datetime.now().date()
                    
                    # Calculate star metrics
                    last_week_stars = stars_df[stars_df['date'] >= (current_date - timedelta(days=7))]['stars'].sum()
                    previous_week_stars = stars_df[
                        (stars_df['date'] >= (current_date - timedelta(days=14))) &
                        (stars_df['date'] < (current_date - timedelta(days=7)))
                    ]['stars'].sum()

                # Key Metrics Overview Section
                st.header("📊 Key Metrics Overview")
                st.divider()

                # First row - Package Downloads
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

                # Second row - GitHub Metrics
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
                        f"{last_week_stars - previous_week_stars:+,} vs previous",
                        help="Stars gained in the last 7 days"
                    )
                with col3:
                    st.metric(
                        "Average Stars/Day",
                        f"{stars_df['stars'].mean():.1f}",
                        f"{stars_df['stars'].tail(7).mean() - stars_df['stars'].tail(14).head(7).mean():+.1f} vs last week",
                        help="Average daily stars"
                    )
                with col4:
                    st.metric(
                        "Peak Stars/Day",
                        f"{stars_df['stars'].max():,}",
                        f"on {stars_df.loc[stars_df['stars'].idxmax(), 'date']}",
                        help="Most stars received in a single day"
                    )

                # Third row - Repository Metrics
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

                # Detailed Statistics Sections
                st.header("📈 Detailed Statistics")

                # Downloads chart
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
                    title=f'Daily Downloads',
                    xaxis_title='Date',
                    yaxis_title='Downloads',
                    hovermode='x unified'
                )
                st.plotly_chart(fig_downloads, use_container_width=True)

                if show_raw_data:
                    st.subheader("Raw Data")
                    tab1, tab2 = st.tabs(["PyPI Data", "GitHub Data"])
                    with tab1:
                        st.dataframe(df_pypi.style.format({'downloads': '{:,.0f}'}))
                    with tab2:
                        st.dataframe(df_github)

                # Stars history chart
                st.subheader("Stars Growth")
                if repo_data.get('stars_history'):
                    stars_df = pd.DataFrame(repo_data['stars_history'])
                    if not stars_df.empty:
                        # Create stars visualization
                        fig_stars = go.Figure()
                        
                        # Cumulative stars
                        fig_stars.add_trace(go.Scatter(
                            x=stars_df['date'],
                            y=stars_df['cumulative_stars'],
                            name='Total Stars',
                            mode='lines',
                            line=dict(color='goldenrod')
                        ))
                        
                        # Daily new stars
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

# Call the releases fragment outside the Fetch Stats block
show_releases()