# AnyCompany Customer Support Agent UI

Streamlit-based web interface for the AnyCompany Customer Support Agent, integrated with AWS Cognito for authentication.

## Features

- 🔐 AWS Cognito authentication
- 💬 Interactive chat interface
- 📊 Conversation history
- 🔍 Issue tracking integration

## Setup

1. Install dependencies with UI extras (from project root):
   ```bash
   uv sync --extra ui
   ```
   
   This will install all core dependencies plus UI-specific dependencies.
   
   For development, you can also use:
   ```bash
   uv sync --extra ui --dev
   ```

2. Configure environment variables (copy `.env.example` to `.env` and fill in values):
   ```bash
   cp .env.example .env
   ```
   
   Required for Cognito authentication:
   - `COGNITO_USER_POOL_ID`: Your AWS Cognito User Pool ID (e.g., `us-west-2_xxxxxxxxx`)
   - `COGNITO_CLIENT_ID`: Your Cognito App Client ID
   - `AWS_REGION`: AWS region where your Cognito User Pool is located
   
   Required for LangGraph API:
   - `LANGGRAPH_API_URL`: URL of your LangGraph API endpoint (default: `http://localhost:8123`)
   - `LANGGRAPH_ASSISTANT_ID`: Assistant ID for your agent (default: `Customer Support Agent`)
   
   See `.env.example` for all available configuration options.

3. Run the app (from project root):
   ```bash
   streamlit run src/ui/app.py
   ```
   
   Or from the ui directory:
   ```bash
   cd src/ui
   streamlit run app.py
   ```

## Architecture

- `app.py` - Main Streamlit application
- `auth.py` - Cognito authentication logic
- `components/` - Reusable UI components
