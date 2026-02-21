.PHONY: help local staging

help:
	@echo "Available targets:"
	@echo "  make local    - Run dashboard with ENV_FILE=.env"
	@echo "  make staging  - Run dashboard with ENV_FILE=.env.staging"

local:
	ENV_FILE=.env python -m streamlit run streamlit_app.py

staging:
	ENV_FILE=.env.staging python -m streamlit run streamlit_app.py
