# GitHub & PyPI Package Analytics Dashboard

A Streamlit dashboard that provides comprehensive analytics for Python packages, combining PyPI download statistics with GitHub repository metrics.

## Features

- 📊 Real-time PyPI download statistics
- ⭐ GitHub repository metrics (stars, forks, contributors)
- 📈 Interactive visualizations
- 📅 Customizable date ranges
- 📊 Moving averages and trend analysis

## Setup

1. Clone the repository:
```bash
git clone https://github.com/yourusername/Github-Stats.git
cd Github-Stats
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Configure secrets:
   - Create a `.streamlit/secrets.toml` file with:
     ```toml
     GOOGLE_CLOUD_PROJECT_ID = "your-project-id"
     ENCODED_CREDS = "your-base64-encoded-credentials"
     GITHUB_TOKEN = "your-github-token"
     ```

4. Run the app:
```bash
streamlit run app.py
```

## Usage

1. Enter a PyPI package name
2. Enter the corresponding GitHub repository
3. Select your desired date range and granularity
4. Click "Fetch Stats" to view the analytics

## Deployment

The app can be deployed on Streamlit Cloud:
1. Push your code to GitHub
2. Connect your repository to Streamlit Cloud
3. Configure the secrets in Streamlit Cloud dashboard
4. Deploy! 