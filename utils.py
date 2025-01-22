# utils.py
import json
import base64
import pandas as pd
import requests
from datetime import datetime, timedelta
from google.cloud import bigquery
from google.oauth2 import service_account
import streamlit as st

# ----------- AUTHENTICATION -----------
def load_credentials():
    """Loads credentials from st.secrets."""
    encoded_creds = st.secrets["ENCODED_CREDS"]
    credentials_dict = json.loads(base64.b64decode(encoded_creds).decode())
    credentials = service_account.Credentials.from_service_account_info(
        credentials_dict,
        scopes=["https://www.googleapis.com/auth/cloud-platform"],
    )
    project_id = st.secrets["GOOGLE_CLOUD_PROJECT_ID"]
    github_token = st.secrets["GITHUB_TOKEN"]
    return credentials, project_id, github_token


# ----------- PYPI QUERIES -----------
@st.cache_data(ttl=60*60*24)
def fetch_pypi_stats(package_name, start_date, end_date, granularity='daily'):
    credentials, project_id, _ = load_credentials()
    client = bigquery.Client(project=project_id, credentials=credentials)
    
    time_group, select_time = {
        'hourly':  ('DATETIME_TRUNC(timestamp, HOUR)', 'DATETIME(timestamp)'),
        'daily':   ('DATE(timestamp)', 'DATE(timestamp)'),
        'weekly':  ('DATE_TRUNC(DATE(timestamp), WEEK)', 'DATE_TRUNC(DATE(timestamp), WEEK)'),
        'monthly': ('DATE_TRUNC(DATE(timestamp), MONTH)', 'DATE_TRUNC(DATE(timestamp), MONTH)')
    }.get(granularity, ('DATE(timestamp)', 'DATE(timestamp)'))
    
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

@st.cache_data(ttl=60*60*24)
def fetch_lifetime_downloads(package_name):
    try:
        # Use PyPI's JSON API
        url = f"https://pypistats.org/api/packages/{package_name}/overall"
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        
        # Sum all download counts
        total_downloads = sum(item['downloads'] for item in data['data'])
        return total_downloads
    except requests.RequestException as e:
        st.error(f"Error fetching download stats for {package_name}: {str(e)}")
        return 0


# ----------- GITHUB QUERIES -----------
@st.cache_data(ttl=60*60)
def fetch_github_stats_api(repo_name):
    credentials, _, github_token = load_credentials()
    
    try:
        # Set up headers with authentication
        headers = {
            'Accept': 'application/vnd.github.v3+json',
            'Authorization': f'Bearer {github_token}' if github_token else '',
            'Accept-Encoding': 'gzip, deflate'
        }
        
        base_url = f"https://api.github.com/repos/{repo_name}"
        
        # Get repository info
        repo_response = requests.get(base_url, headers=headers)
        if repo_response.status_code != 200:
            st.error(f"Error fetching GitHub data: {repo_response.json().get('message', '')}")
            return None, None
            
        repo_data = repo_response.json()
        
        # Get stargazers
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
        
        if stars_data:
            stars_df = pd.DataFrame([
                {'date': pd.to_datetime(star['starred_at']).date(), 'stars': 1}
                for star in stars_data
            ])
            date_range = pd.date_range(stars_df['date'].min(), stars_df['date'].max(), freq='D').date
            stars_df = stars_df.groupby('date')['stars'].sum().reindex(date_range, fill_value=0).reset_index()
            stars_df.columns = ['date', 'stars']
            stars_df['cumulative_stars'] = stars_df['stars'].cumsum()
            stars_df['star_change'] = stars_df['stars'].diff().fillna(stars_df['stars'])
        else:
            stars_df = pd.DataFrame(columns=['date', 'stars', 'cumulative_stars', 'star_change'])

        # Commit activity
        commits_response = requests.get(f"{base_url}/stats/commit_activity", headers=headers)
        commits_data = commits_response.json() if commits_response.status_code == 200 else []
        
        # Contributors
        contributors_response = requests.get(f"{base_url}/stats/contributors", headers=headers)
        contributors_data = contributors_response.json() if contributors_response.status_code == 200 else []
        
        # Releases
        releases_response = requests.get(f"{base_url}/releases", headers=headers)
        releases_data = releases_response.json() if releases_response.status_code == 200 else []
        
        # Pull requests
        prs_response = requests.get(f"{base_url}/pulls?state=all&per_page=100", headers=headers)
        prs_data = prs_response.json() if prs_response.status_code == 200 else []
        
        total_commits = sum(week['total'] for week in commits_data) if commits_data else 0
        total_contributors = len(contributors_data)
        total_releases = len(releases_data)
        
        dates = pd.date_range(end=datetime.now(), periods=len(commits_data), freq='W') if commits_data else []
        df = pd.DataFrame({
            'date': dates,
            'stars': repo_data['stargazers_count'],
            'forks': repo_data['forks_count'],
            'open_issues': repo_data['open_issues_count'],
            'watchers': repo_data['watchers_count'],
            'weekly_commits': [week['total'] for week in commits_data] if commits_data else [],
        })
        
        # Add extra data into repo_data
        repo_data.update({
            'total_commits': total_commits,
            'total_contributors': total_contributors,
            'total_releases': total_releases,
            'commits_data': commits_data,
            'contributors_data': contributors_data,
            'releases_data': releases_data,
            'prs_data': prs_data,
            'stars_history': stars_df.to_dict('records')
        })
        
        return df, repo_data
    
    except Exception as e:
        st.error(f"Error fetching GitHub data: {str(e)}")
        return None, None
