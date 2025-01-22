# pages/Compare.py
import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta

from utils import (
    fetch_pypi_stats,
    fetch_lifetime_downloads,
    fetch_github_stats_api
)

def compare_packages():
    st.title("Compare Multiple Packages")

    # Package input section with clear instructions
    st.markdown("""
    ### Step 1: Enter Package Names
    Enter the PyPI package names you want to compare. For multiple packages, separate them with commas.
    
    **Example:** `crewai, langgraph, autogen`
    """)
    packages_input = st.text_input("PyPI Package Names:", placeholder="e.g., crewai, langgraph, autogen")
    package_list = [p.strip() for p in packages_input.split(",") if p.strip()]

    # GitHub input section
    st.markdown("""
    ### Step 2: Enter GitHub Repositories (Optional)
    If you want to see GitHub statistics, enter the corresponding GitHub repositories in the same order as the packages above.
    
    **Example:** If you entered `crewai, langgraph, autogen` above, enter: `crewAIInc/crewAI, langchain-ai/langgraph, autogenai/autogen`
    """)
    github_input = st.text_area(
        "GitHub Repositories:",
        placeholder="e.g., crewAIInc/crewAI, langchain-ai/langgraph, autogenai/autogen",
        help="Format: owner/repository (e.g., crewAIInc/crewAI, langchain-ai/langgraph, autogenai/autogen)"
    )
    github_list = [g.strip() for g in github_input.split(",") if g.strip()]

    # Date range section
    st.markdown("### Step 3: Select Time Range")
    date_range = st.selectbox("Preset Date Ranges", 
                          ["Last 7 days", "Last 30 days", "Last 90 days", "Last 365 days", "Custom"])
    
    if date_range == "Custom":
        col1, col2 = st.columns(2)
        with col1:
            start_date = st.date_input("Start Date", datetime.now() - timedelta(days=30))
        with col2:
            end_date = st.date_input("End Date", datetime.now())
    else:
        days_map = {
            "Last 7 days": 7,
            "Last 30 days": 30,
            "Last 90 days": 90,
            "Last 365 days": 365
        }
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=days_map[date_range])
    
    st.markdown("### Step 4: Select Data Granularity")
    granularity = st.selectbox(
        "Time Granularity",
        ["daily", "weekly", "monthly"],
        help="How to group the download data: daily, weekly, or monthly intervals"
    )

    if st.button("Compare", type="primary"):
        if not package_list:
            st.error("Please enter at least one package name.")
            return
        
        # Container for results
        all_data = []
        
        for i, pkg in enumerate(package_list):
            st.subheader(f"**{pkg}**")
            with st.spinner(f"Fetching data for {pkg}..."):
                # Fetch PyPI data
                df_pypi = fetch_pypi_stats(pkg, start_date, end_date, granularity)
                total_downloads = fetch_lifetime_downloads(pkg)
                
                # Display basic stats
                if not df_pypi.empty:
                    daily_avg = df_pypi['downloads'].mean()
                    max_val = df_pypi['downloads'].max()
                    st.write(f"- **Date Range Downloads**: {df_pypi['downloads'].sum():,}")
                    st.write(f"- **Lifetime Downloads**: {total_downloads:,}")
                    st.write(f"- **Avg Daily**: {daily_avg:,.0f}")
                    st.write(f"- **Max Daily**: {max_val:,.0f}")
                    
                    # Plot
                    fig = px.line(df_pypi, x='date', y='downloads', title=f"{pkg} Downloads")
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info("No download data found.")
                
                # Optional GitHub data
                if len(github_list) == len(package_list):
                    repo_name = github_list[i]
                    df_github, repo_data = fetch_github_stats_api(repo_name)
                    if df_github is not None and repo_data is not None:
                        st.write(f"**GitHub Stars**: {repo_data['stargazers_count']:,}")
                        st.write(f"**Forks**: {repo_data['forks_count']:,}")
                        st.write(f"**Open Issues**: {repo_data['open_issues_count']:,}")
                    else:
                        st.info("No GitHub data found or invalid repo.")
                else:
                    st.write("_No GitHub repo provided or mismatch in count._")
                
                st.markdown("---")
                
                # Keep data for final comparison chart
                if not df_pypi.empty:
                    # Tag the data by package
                    temp = df_pypi.copy()
                    temp['package'] = pkg
                    all_data.append(temp)
        
        # Overall comparison chart for all packages
        if all_data:
            df_all = pd.concat(all_data, ignore_index=True)
            fig_comparison = px.line(
                df_all,
                x='date', 
                y='downloads',
                color='package',
                title='Comparison of Downloads'
            )
            st.plotly_chart(fig_comparison, use_container_width=True)

def main():
    compare_packages()

if __name__ == "__main__":
    main()
